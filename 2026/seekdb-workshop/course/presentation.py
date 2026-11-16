"""显示真实检索依据与应用调用位置；不生成或改写数据库结果。"""

import ast
from html import escape
import json
import math
from pathlib import Path
import re

import pandas as pd
from IPython.display import HTML, Markdown, display

from course.lab import display_table


def plot_excerpt(overview, limit=150):
    """优先显示与本课查案需求有关的原文，逐字保留资料。"""
    for word in ("心情", "心思", "动机", "案件", "调查", "犯罪"):
        position = overview.find(word)
        if position >= 0:
            start = max(0, position - 35)
            return ("…" if start else "") + overview[start:start + limit] + ("…" if start + limit < len(overview) else "")
    return overview[:limit] + ("…" if len(overview) > limit else "")


def display_result_evidence(report):
    """每路第一名的分数、字段、原文；分数不跨检索方式比较。"""
    cards, plots = [], []
    for mode, label in (("fulltext", "全文"), ("vector", "向量"), ("hybrid", "混合")):
        movies = report["results"][mode]["movies"]
        if not movies:
            cards.append(f'<p><b>{escape(label)}</b>：无结果</p>')
            continue
        movie = movies[0]
        cards.append('<section style="margin:10px 0;padding:8px 14px;border-left:3px solid #7cb5ff">'
                     f'<b>{escape(label)}第一名 · {escape(movie["title"])}</b>'
                     f'　<span>本路得分：{movie["_score"]:.5f}</span>'
                     f'<p style="margin:4px 0">类型：{escape("、".join(movie["genres"]))}'
                     f'　年份：{movie["year"]}　片长：{movie["runtime_minutes"]} 分钟</p>'
                     f'<p style="margin:4px 0">{escape(plot_excerpt(movie["overview"]))}</p></section>')
        plots.append(f'<p><strong>{escape(label)} · {escape(movie["title"])}</strong></p><p>{escape(movie["overview"])}</p>')
    display(HTML('<div style="font-size:18px;line-height:1.5">' + "".join(cards) + '</div>'))
    display(HTML('<details style="font-size:18px;line-height:1.6;margin:12px 0">'
                 '<summary style="cursor:pointer">展开三路第一名的完整剧情</summary>' + "".join(plots) + '</details>'))


def display_case_observations(report):
    """只报告真实返回集合与标签覆盖；不把标签数量冒充推荐质量。"""
    titles = {mode: {movie["id"] for movie in group["movies"]}
              for mode, group in report["results"].items()}
    overlap = len(titles["fulltext"] & titles["vector"])
    display(Markdown(f"**这轮实际发生了什么：** 全文和向量展示结果共有 **{overlap} 部**相同电影。"
                     "结合上表剧情，区分文字命中与查案情节；名次变化本身不代表效果提升。"))
    rows = [{"方式": label, "返回数量": len(report["results"][mode]["movies"]),
             "同时带犯罪、悬疑标签": sum({"犯罪", "悬疑"}.issubset(movie["genres"])
                                     for movie in report["results"][mode]["movies"])}
            for mode, label in (("fulltext", "全文"), ("vector", "向量"), ("hybrid", "混合"))]
    table = pd.DataFrame(rows).to_html(index=False, escape=True, border=0)
    table = table.replace('<table ', '<table style="width:100%;font-size:18px" ', 1)
    display(HTML('<details style="font-size:18px;margin:12px 0"><summary style="cursor:pointer">'
                 '展开本轮标签核对（仅标签覆盖，不是整体准确率）</summary>' + table + '</details>'))


def display_filter_effect(report, allowed_ids, filters):
    """解释本次 SQL 已排除的候选，不把相关性得分当作字段条件。"""
    allowed, seen, rows = set(allowed_ids), set(), []
    groups = [group["movies"] for group in report["results"].values()]
    preferred = [movies[0] for movies in groups if movies]
    for candidates in (preferred, [movie for movies in groups for movie in movies]):
        for movie in candidates:
            if movie["id"] in allowed or movie["id"] in seen:
                continue
            seen.add(movie["id"])
            reasons = []
            if filters.get("since") is not None and movie["year"] < filters["since"]:
                reasons.append(f'{movie["year"]} 年早于 {filters["since"]}')
            if filters.get("max_minutes") is not None and movie["runtime_minutes"] > filters["max_minutes"]:
                reasons.append(f'{movie["runtime_minutes"]} 分钟超过 {filters["max_minutes"]}')
            genres = filters.get("genre")
            required = [genres] if isinstance(genres, str) else genres or []
            missing = [genre for genre in required if genre not in movie["genres"]]
            if missing:
                reasons.append("缺少类型标签：" + "、".join(missing))
            if filters.get("country") is not None and filters["country"] not in movie["countries"]:
                reasons.append("出品地区不符合要求")
            rows.append({"之前出现的电影": movie["title"], "这次被过滤的原因": "；".join(reasons)})
    if rows:
        display_table(pd.DataFrame(rows[:3]))
    else:
        display(Markdown("本轮已展示的候选都符合这组硬条件；再结合剧情判断相关性。"))


def display_request(request):
    """只在显示副本里缩短向量和 ID 列表，真实请求保持完整。"""
    preview = json.loads(json.dumps(request))
    preview["knn"]["query_vector"] = f"{len(request['knn']['query_vector'])} 维问题向量，数值仅在显示时省略"
    for filters in (preview["query"]["bool"]["filter"], preview["knn"]["filter"]):
        ids = filters[0]["terms"]["id"]
        if len(ids) > 3:
            filters[0]["terms"]["id"] = [*ids[:3], f"共 {len(ids)} 个 ID，其余仅在显示时省略"]
    from course.lab import display_details
    display_details("展开本次混合请求", json.dumps(preview, ensure_ascii=False, indent=2))


def fusion_rank_frame(report, database, embedding, limit=5, *, include_single_route=False):
    """从混搜实际 SQL 读取两路 RANK，避免用展示列表猜测内部候选名次。"""
    from movie_retrieval import search_request

    columns = ["混合排名", "电影", "全文名次", "向量名次", "RRF 计算", "数据库混合得分"]
    movies = report["results"]["hybrid"]["movies"][:limit]
    if not movies:
        return pd.DataFrame(columns=columns)
    eligibility = report["eligibility"]
    ids = None
    if eligibility["id_constraint_applied"]:
        ids = database.query(eligibility["sql"], eligibility["parameters"])["id"].tolist()
    settings = report["settings"]
    constant = settings["rank_constant"]
    request = search_request("hybrid", report["query"]["lexical_text"], embedding, ids,
                             len(movies), settings["candidates"], constant,
                             rank_window_size=settings.get("rank_window_size", settings["candidates"]))
    generated = database.query(
        "SELECT DBMS_HYBRID_SEARCH.GET_SQL(%s, %s) AS sql_text",
        ("movies", json.dumps(request, ensure_ascii=False)),
    ).iloc[0]["sql_text"]
    if not re.match(r"\s*SELECT\b", generated, re.I) or any(
        name not in generated for name in ("`_keyword_rank`", "`_semantic_rank`")
    ):
        raise ValueError("系统包的混搜 SQL 结构已变化，请核对课程与 seekdb 版本。")
    traced = re.sub(
        r"^\s*SELECT\s+",
        "SELECT `_fts`.`_keyword_rank` AS workshop_fulltext_rank, "
        "`_vs`.`_semantic_rank` AS workshop_vector_rank, ",
        generated, count=1, flags=re.I,
    )
    if include_single_route:
        # 先保留完整融合排名，再选出三路前几名涉及的电影。
        # 不能在这里重新对展示的几部电影计算 RRF 或编号。
        traced, changed = re.subn(r"\bLIMIT\s+\d+\s*$", f"LIMIT {int(eligibility['count'])}",
                                  traced, count=1, flags=re.I)
        if changed != 1:
            raise ValueError("无法确认混搜 SQL 的最终返回上限，请核对 seekdb 版本。")
    actual_rows = database.query(traced).to_dict("records")
    actual = {row["id"]: row for row in actual_rows}
    for movie in movies:
        if movie["id"] not in actual or not math.isclose(
            float(actual[movie["id"]]["_score"]), float(movie["_score"]), abs_tol=1e-8,
        ):
            raise ValueError("检索结果已变化，请重新运行检索对比后再查看来源名次。")
    if include_single_route:
        selected = {movie["id"] for mode in ("fulltext", "vector", "hybrid")
                    for movie in report["results"][mode]["movies"][:limit]}
        if not selected.issubset(actual):
            raise ValueError("单路结果与本轮融合候选已变化，请重新运行检索对比。")
        ranked = [(rank, row) for rank, row in enumerate(actual_rows, 1) if row["id"] in selected]
    else:
        ranked = [(rank, actual[movie["id"]]) for rank, movie in enumerate(movies, 1)]
    rows = []
    for rank, row in ranked:
        ranks = [None if pd.isna(row[key]) else int(row[key])
                 for key in ("workshop_fulltext_rank", "workshop_vector_rank")]
        expected = sum(1 / (constant + value) for value in ranks if value is not None)
        # 当前系统包的整数除法结果带有限小数位；展示数据库原值。
        if not math.isclose(float(row["_score"]), expected, abs_tol=1e-4):
            raise ValueError("数据库融合分数与两路名次不一致，请检查本次生成 SQL。")
        rows.append({"混合排名": rank, "电影": row["title"],
                     "全文名次": ranks[0] if ranks[0] is not None else "未进入候选",
                     "向量名次": ranks[1] if ranks[1] is not None else "未进入候选",
                     "RRF 计算": " + ".join(f"1/({constant}+{value})" for value in ranks if value is not None),
                     "数据库混合得分": float(row["_score"])})
    return pd.DataFrame(rows, columns=columns)


def display_rank_comparison(report, database, embedding, limit=5, *, heading="同一部电影在三种检索中排第几？"):
    """一行对应一部电影，展示单路前几名在完整融合排名中的位置。"""
    from course.lab import display_details

    frame = fusion_rank_frame(report, database, embedding, limit, include_single_route=True)
    display(Markdown(f"### {heading}\n\n本次搜索范围 **{report['eligibility']['count']} 部**。"
                     f"表中汇总三种检索各自前 **{limit} 名**出现过的电影，每部电影只占一行。"
                     f"**混合排名 1–{limit} 是最终返回结果**；其余行展示单路前 {limit} 名在混搜中的位置。"))
    if frame.empty:
        display(Markdown("本轮没有返回电影。"))
        return
    display_table(frame[["混合排名", "电影", "全文名次", "向量名次", "数据库混合得分"]])
    calculations = frame.loc[frame["混合排名"] <= limit,
                             ["电影", "全文名次", "向量名次", "RRF 计算", "数据库混合得分"]]
    display_details(f"展开混搜前 {limit} 名的 RRF 计算", calculations.to_string(index=False))


def application_call_sites(root):
    """从 app.py 当前源码抽出两个真实调用，避免教学伪代码与应用实现脱节。"""
    source = (Path(root) / "app.py").read_text(encoding="utf-8")
    found = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = ast.unparse(node.func)
        if name in ("get_runtime().search", "recommend_movies") and not any(isinstance(arg, ast.Starred) for arg in node.args):
            found[name] = ast.get_source_segment(source, node)
    if set(found) != {"get_runtime().search", "recommend_movies"}:
        raise ValueError("应用调用已变化，请更新课程中的按钮对应关系。")
    return found
