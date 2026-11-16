"""第八课电影推荐入口，同时提供第七课检索界面共用的展示函数。"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import pymysql
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "examples"))

from streamlit_services import LocalQueryEncoder, MovieSearchRuntime, load_catalog


@st.cache_data(show_spinner=False)
def get_catalog():
    return load_catalog()


def release_runtime(runtime):
    runtime.close()


@st.cache_resource(show_spinner=False, on_release=release_runtime, validate=lambda runtime: not runtime.closed)
def get_runtime():
    return MovieSearchRuntime()


@st.cache_resource(show_spinner=False)
def get_encoder(manifest):
    return LocalQueryEncoder(manifest)


COUNTRIES = {
    "CN": "中国大陆", "HK": "中国香港", "TW": "中国台湾", "US": "美国",
    "GB": "英国", "AU": "澳大利亚", "FR": "法国", "DE": "德国",
    "JP": "日本", "KR": "韩国", "CA": "加拿大", "CZ": "捷克",
    "IN": "印度", "NZ": "新西兰", "IT": "意大利", "ES": "西班牙",
    "SE": "瑞典", "DK": "丹麦", "NO": "挪威", "IE": "爱尔兰",
    "BE": "比利时", "NL": "荷兰", "CH": "瑞士", "ZA": "南非",
}
MODE_LABELS = {"hybrid": "混合检索", "fulltext": "全文检索", "vector": "向量检索"}
RECOMMENDATION_STEPS = (
    ("understand", "理解需求"), ("search", "检索电影"),
    ("recommend", "生成推荐"), ("verify", "核对依据"),
)
PAGE_STYLE = """
<style>
[data-testid="stMainBlockContainer"] {
    width: 100%; max-width: 1440px;
    padding: 4rem 1.75rem 1.5rem;
}
[data-testid="stMainBlockContainer"] h1 {
    font-size: 1.75rem; line-height: 1.25; padding: 0; margin: 0;
}
[data-testid="stMainBlockContainer"] h3 {
    font-size: 1.25rem; line-height: 1.35; padding: .2rem 0;
}
.st-key-search_controls [data-testid="stVerticalBlock"] { gap: .5rem; }
.recommendation-steps {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem;
}
.recommendation-step {
    display: flex; align-items: center; gap: .55rem; padding: .55rem .7rem;
    border: 1px solid #424242; border-radius: .25rem; color: #bdbdbd; background: #212121;
}
.recommendation-step-badge {
    display: grid; place-items: center; flex: 0 0 1.35rem; height: 1.35rem;
    border-radius: 50%; background: #424242; color: #e0e0e0; font-size: .8rem;
}
.recommendation-step.current {
    border-color: #64b5f6; background: #132b40; color: #90caf9; font-weight: 600;
}
.recommendation-step.current .recommendation-step-badge {
    background: #1976d2; color: white; animation: recommendation-pulse 1.8s ease-in-out infinite;
}
.recommendation-step.done { color: #81c784; background: #15251b; border-color: #355940; }
.recommendation-step.done .recommendation-step-badge { background: #2e7d32; color: white; }
@keyframes recommendation-pulse { 50% { opacity: .55; } }
@media (prefers-reduced-motion: reduce) {
    .recommendation-step.current .recommendation-step-badge { animation: none; }
}
@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] { padding: 3.5rem 1rem 1rem; }
    .recommendation-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
"""


def recommendation_progress_html(phase):
    current = next(index for index, (key, _) in enumerate(RECOMMENDATION_STEPS) if key == phase)
    steps = []
    for index, (_, label) in enumerate(RECOMMENDATION_STEPS):
        state = "done" if index < current else "current" if index == current else "pending"
        badge = "✓" if index < current else str(index + 1)
        active = ' aria-current="step"' if index == current else ""
        steps.append(f'<div class="recommendation-step {state}" role="listitem"{active}>'
                     f'<span class="recommendation-step-badge" aria-hidden="true">{badge}</span>'
                     f'<span>{label}</span></div>')
    return (f'<div class="recommendation-steps" data-phase="{phase}" role="list" '
            'aria-label="电影推荐进度">' + "".join(steps) + "</div>")


def country_label(code):
    if code is None:
        return "不限"
    return f"{COUNTRIES.get(code, code)}（{code}）"


def clear_results():
    st.session_state.pop("search_report", None)
    st.session_state.pop("recommendation_report", None)


def clear_filters():
    for key in ("genre", "country", "since", "max_minutes"):
        st.session_state[key] = None
    clear_results()


def fill_example(queries):
    query_id = st.session_state["example_query"]
    if query_id is not None:
        st.session_state["movie_description"] = queries[query_id]["text"]
        st.session_state["example_query"] = None
        clear_results()


def filter_summary(filters):
    parts = []
    if filters["genre"]:
        genres = filters["genre"]
        parts.append(" + ".join(genres) if isinstance(genres, list) else genres)
    if filters["country"]:
        parts.append("地区包含" + COUNTRIES.get(filters["country"], filters["country"]))
    if filters["since"] is not None:
        parts.append(f"{filters['since']} 年起")
    if filters["max_minutes"] is not None:
        parts.append(f"不超过 {filters['max_minutes']} 分钟")
    return " · ".join(parts) if parts else "类型、地区、年份和片长不限"


def show_original_movies(movies, label):
    with st.expander(label):
        for movie in movies:
            st.markdown(f"**{movie['title']}**")
            st.write(movie["overview"])
            st.caption(f"电影 ID：{movie['id']}")
            st.link_button("查看 TMDB 来源 ↗", movie["source_url"])


def show_recommendations(run):
    st.subheader("电影推荐", anchor=False)
    if run["status"] != "passed":
        st.error("推荐未完成：" + run.get("error", {}).get("message", "模型未返回有效结果。"))
        if "retrieval" in run:
            st.caption("本次数据库检索结果已保留在下方，可继续核对电影资料。")
    else:
        answer = run["answer"]
        pool = run["tool_movies"]
        movies = {movie["id"]: movie for movie in pool}
        selected = {item["id"]: index for index, item in enumerate(answer["recommendations"], 1)}
        summary = f"{len(pool)} 部候选 · 推荐 {len(selected)} 部 · 耗时 {run['end_to_end_seconds']:.2f} 秒"
        if pool and set(selected) == set(movies):
            summary += " · 推荐与候选集合相同"
        st.caption(summary)
        candidates_view, recommendation_view = st.columns([1, 1.7], gap="large")
        with candidates_view:
            st.subheader("① seekdb 返回的候选", anchor=False)
            st.caption("按混合检索相关性排序。")
            if pool:
                rows = [{"数据库排名": rank, "电影": movie["title"], "RRF 分数": movie["_score"],
                         "模型选择": f"推荐 {selected[movie['id']]}" if movie["id"] in selected else "未选入"}
                        for rank, movie in enumerate(pool, 1)]
                st.dataframe(rows, hide_index=True, width="stretch", key="ai_candidate_table",
                             column_config={"RRF 分数": st.column_config.NumberColumn(format="%.6f")})
                show_original_movies(pool, "查看候选的原始剧情与来源")
            else:
                st.info("数据库未返回可供推荐的候选。")
        with recommendation_view:
            st.subheader("② AI 生成的推荐", anchor=False)
            st.write(answer["message"])
            if not answer["recommendations"]:
                st.info("本次没有生成符合需求的电影推荐，请结合检索结果调整需求或筛选。")
            for index, item in enumerate(answer["recommendations"], 1):
                movie = movies[item["id"]]
                with st.container(border=True):
                    st.subheader(f"推荐 {index} · {movie['title']}", anchor=False)
                    st.caption(f"资料字段：{movie['year']} 年 · {movie['runtime_minutes']} 分钟 · {' / '.join(movie['genres'])}")
                    st.markdown("**AI 推荐理由**")
                    st.info(item["reason"], icon="✨")
                    with st.expander("查看引用的剧情原文（数据库资料）"):
                        st.write(item["evidence_quote"])
                    st.link_button("查看 TMDB 来源 ↗", movie["source_url"])
    with st.expander("LangChain 调用记录 · 模型参数、检索工具与用量"):
        st.caption(f"LangChain · {run['model']} · {len(run['api_calls'])} 次模型请求 · 已报告 {run['total_tokens']:,} Token · 全程 {run['end_to_end_seconds']:.2f} 秒")
        for event in run["events"]:
            st.write("• " + event)
        st.json({
            "模型": run["model"], "状态": run["status"],
            "模型后端": run.get("backend", "glm"),
            "模型返回的工具调用": run.get("tool_call"),
            "页面筛选": run["ui_filters"],
            "模型提取条件": run.get("model_filters"),
            "实际合并条件": run.get("effective_filters"),
            "模型选择的原文片段": run.get("model_answer"),
            "API 请求记录": run["api_calls"],
        }, expanded=False)
        st.caption("仅展示通过电影 ID 和逐字引文校验的推荐；理由是否完整得到资料支持，仍需对照原文判断。")
        st.download_button("下载本次 LangChain 调用记录", json.dumps(run, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="seekdb-langchain-recommendation.json", mime="application/json")


def show_report(report):
    st.subheader("检索结果", anchor=False)
    summary = (f"本次搜索范围 {report['eligibility']['count']} 部 · "
               f"混合返回 {len(report['results']['hybrid']['movies'])} 部 · "
               f"耗时 {report['end_to_end_seconds']:.2f} 秒")
    if any(value is not None for value in report["filters"].values()):
        summary += " · " + filter_summary(report["filters"])
    st.caption(summary)
    eligible = report["eligibility"]["count"]
    if (any(value is not None for value in report["filters"].values())
            and eligible > 0 and len(report["results"]["hybrid"]["movies"]) == eligible):
        st.info(f"符合筛选的电影共 {eligible} 部，本次混合检索已全部列出。"
                "更换描述会在这些电影中重新排序；点击“清空筛选”可以扩大检索范围。")
    tabs = st.tabs(["混合检索", "全文检索", "向量检索"])
    for tab, mode in zip(tabs, MODE_LABELS):
        with tab:
            result = report["results"][mode]
            if not result["movies"]:
                if report["eligibility"]["count"] == 0:
                    st.info("当前筛选条件下没有电影。可调整年份、片长、类型或地区后重新检索。")
                else:
                    st.info("这组检索没有命中。可换一个关键词，并与其他检索结果对照。")
            if result["movies"]:
                score_label = {"hybrid": "RRF 分数", "fulltext": "全文相关度", "vector": "向量相关度"}[mode]
                rows = [{"排名": rank, "电影": movie["title"], "年份": movie["year"],
                         "片长（分钟）": movie["runtime_minutes"], score_label: movie["_score"],
                         "原始剧情摘要": movie["overview"][:90]}
                        for rank, movie in enumerate(result["movies"], 1)]
                st.dataframe(rows, hide_index=True, width="stretch", key=f"retrieval_table_{mode}",
                             column_config={
                                 "排名": st.column_config.NumberColumn(width=55, format="%d"),
                                 "电影": st.column_config.TextColumn(width=240),
                                 "年份": st.column_config.NumberColumn(width=75, format="%d"),
                                 "片长（分钟）": st.column_config.NumberColumn(width=110, format="%d"),
                                 score_label: st.column_config.NumberColumn(width=110, format="%.6f"),
                                 "原始剧情摘要": st.column_config.TextColumn(width=720),
                             })
                show_original_movies(result["movies"], "查看本组电影的原始剧情与来源")
    with st.expander("查询实验面板 · 条件、SQL 与执行计划"):
        st.caption("分数用于各组内部排序；剧情摘要直接来自电影资料。")
        st.json({
            "问题": report["query"]["text"],
            "向量来源": "预计算问题" if report["query"]["vector_source"] == "precomputed_query" else "本地离线模型",
            "向量维度": report["query"]["dimension"],
            "筛选条件": report["filters"],
            "检索设置": report["settings"],
            "数据库版本": report["database_version"],
        }, expanded=False)
        st.caption("业务条件先在 seekdb 中筛选，再将相同条件用于全文和向量检索。")
        st.code(report["eligibility"]["sql"], language="sql")
        st.json({"绑定参数": report["eligibility"]["parameters"]}, expanded=False)
        for mode in MODE_LABELS:
            result = report["results"][mode]
            st.subheader(MODE_LABELS[mode], anchor=False)
            st.caption(f"数据库检索耗时：{result['seconds']:.4f} 秒")
            if "plan" in result:
                st.code(result["plan"]["generated_sql"], language="sql")
                st.code("\n".join(result["plan"]["operators"]), language="text")
        st.download_button(
            "下载本次查询记录", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="seekdb-movie-search.json", mime="application/json",
        )


def main(enable_recommendation=True):
    st.set_page_config(page_title="seekdb 电影实验室", page_icon="🎬", layout="wide")
    st.html(PAGE_STYLE)
    if st.session_state.pop("keywords", None):
        clear_results()
    try:
        catalog = get_catalog()
    except (ValueError, FileNotFoundError) as error:
        st.error("无法读取教学资料：" + str(error))
        st.stop()
    manifest = catalog["manifest"]
    heading, context = st.columns([3, 2], vertical_alignment="center")
    heading.title("今晚想看什么？" if enable_recommendation else "电影检索对比")
    context.caption(("第八课 · seekdb × LangChain" if enable_recommendation else "第七课 · seekdb")
                    + f" · {manifest['movie_count']} 部电影")

    queries = {query["id"]: query for query in catalog["queries"]}
    if "movie_description" not in st.session_state:
        st.session_state["movie_description"] = queries["crime-mystery"]["text"]
    with st.container(border=True, key="search_controls"):
        description, examples = st.columns([3, 2], vertical_alignment="top")
        text = description.text_input("描述想看的电影", placeholder="例如：找部能跟着查案、琢磨人物心思的犯罪悬疑片",
                                      key="movie_description", on_change=clear_results)
        examples.selectbox("试试示例", list(queries), index=None,
                           format_func=lambda value: ("按剧情找片名：" if queries[value]["kind"] == "plot_lookup" else "") + queries[value]["text"],
                           placeholder="选择一个示例……", key="example_query", on_change=fill_example, args=(queries,))
        main_actions, options = st.columns([3, 2], vertical_alignment="top")
        recommended = False
        if enable_recommendation:
            recommend_action, search_action = main_actions.columns(2)
            recommended = recommend_action.button("生成推荐", type="primary", width="stretch")
        else:
            search_action = main_actions
        filter_action, settings_action = options.columns(2)
        submitted = search_action.button("检索对比", type="secondary" if enable_recommendation else "primary", width="stretch")
        with filter_action.popover("筛选条件", width="stretch", key="search_filters"):
            a, b = st.columns(2)
            genre = a.selectbox("电影类型", [None, *catalog["genres"]], format_func=lambda value: value or "不限", placeholder="不限", key="genre", on_change=clear_results)
            country = b.selectbox("出品地区", [None, *catalog["countries"]], format_func=country_label,
                                  help="出品地区包含所选代码即可，合拍片可匹配多个地区。", placeholder="不限", key="country", on_change=clear_results)
            c, d = st.columns(2)
            since = c.number_input("最早上映年份", min_value=1880, max_value=2100, value=None, step=1, placeholder="不限", key="since", on_change=clear_results)
            max_minutes = d.number_input("片长上限（分钟）", min_value=1, max_value=600, value=None, step=1, placeholder="不限", key="max_minutes", on_change=clear_results)
            reset = st.button("清空筛选", on_click=clear_filters, width="stretch")
        with settings_action.popover("检索设置", width="stretch", key="search_settings"):
            limit = st.slider("每组显示数量", 1, 10, 5, key="limit", on_change=clear_results)
            candidates = st.number_input("向量候选数", min_value=10, max_value=100, value=20, step=10, key="candidates", on_change=clear_results)
        current_filters = {"since": since, "max_minutes": max_minutes, "genre": genre, "country": country}
        if any(value is not None for value in current_filters.values()):
            st.caption("已选：" + filter_summary(current_filters))

    if reset:
        st.success("已清空筛选，保留当前描述。")
    if recommended or submitted:
        clear_results()
        if not text.strip():
            st.warning("请先输入一段想看的电影描述。")
        else:
            text = text.strip()
            preset = next((query for query in queries.values() if query["text"].strip() == text), None)
            query_id = preset["id"] if preset is not None else "local-input"
            started = time.perf_counter()
            try:
                if recommended:
                    progress_slot = st.empty()
                    try:
                        with progress_slot.container(border=True, key="recommendation_progress"):
                            with st.spinner("正在为你准备电影推荐……", show_time=True):
                                steps_slot, detail_slot = st.empty(), st.empty()

                                def update_progress(phase, details):
                                    steps_slot.html(recommendation_progress_html(phase))
                                    descriptions = {
                                        "understand": "正在理解你的观影需求，提取类型、年份和片长条件。",
                                        "search": "正在按你的条件检索电影资料。",
                                        "verify": "正在核对电影记录与引用的剧情依据。",
                                    }
                                    if phase == "recommend":
                                        count = details["candidates"]
                                        description = (f"已找到 {count} 部候选电影，正在根据剧情整理推荐理由。"
                                                       if count else "未找到符合条件的电影，正在整理查询结果说明。")
                                    else:
                                        description = descriptions[phase]
                                    detail_slot.caption(description)

                                update_progress("understand", {})
                                from movie_recommendations import recommend_movies
                                run = recommend_movies(
                                    text.strip(), manifest,
                                    search=lambda *args, **kwargs: get_runtime().search(*args, **kwargs),
                                    encode=lambda query_text: get_encoder(manifest).encode(query_text),
                                    preset_embedding=preset["embedding"] if preset is not None else None,
                                    query_id=query_id, filters=current_filters,
                                    limit=limit, candidates=candidates, on_progress=update_progress,
                                )
                                st.session_state["recommendation_report"] = run
                                if "retrieval" in run:
                                    st.session_state["search_report"] = run["retrieval"]
                    finally:
                        progress_slot.empty()
                else:
                    with st.spinner("正在检索电影资料……", show_time=True):
                        if preset is not None:
                            embedding = preset["embedding"]
                            source = "precomputed_query"
                        else:
                            embedding = get_encoder(manifest).encode(text.strip())
                            source = "local_offline_model"
                        report = get_runtime().search(
                            text.strip(), embedding, manifest, filters=current_filters,
                            limit=limit, candidates=candidates, explain=True,
                        )
                        report["query"].update(id=query_id, vector_source=source)
                        report["created_at"] = datetime.now(timezone.utc).isoformat()
                        report["end_to_end_seconds"] = round(time.perf_counter() - started, 6)
                        st.session_state["search_report"] = report
            except FileNotFoundError:
                st.error("自定义描述需要本机 Embedding 模型。首次使用会自动下载；失败时请检查网络，或设置 HF_ENDPOINT=https://hf-mirror.com 后重试。也可以选择一个示例并保持原文，直接体验检索。")
            except (ValueError, RuntimeError, pymysql.Error) as error:
                st.error("检索未完成：" + str(error)[:500])

    if enable_recommendation and "recommendation_report" in st.session_state:
        show_recommendations(st.session_state["recommendation_report"])
    if "search_report" in st.session_state:
        show_report(st.session_state["search_report"])


if __name__ == "__main__":
    main()
