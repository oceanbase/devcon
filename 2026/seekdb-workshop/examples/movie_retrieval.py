"""第六课的检索逻辑：SQL 业务过滤，seekdb 系统包执行全文、向量及 RRF 融合。"""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import re
import time

from pydantic import BaseModel, ConfigDict, Field, field_validator
import pylibseekdb
import pymysql


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIELDS = [
    "id", "title", "year", "runtime_minutes", "genres", "countries",
    "rating", "overview", "source_url",
]
MODES = ("fulltext", "vector", "hybrid")


class MovieFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    since: int | None = Field(default=None, ge=1880, le=2100)
    max_minutes: int | None = Field(default=None, ge=1, le=600)
    genre: str | list[str] | None = Field(default=None, min_length=1, max_length=50)
    country: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, value):
        return value.upper() if value is not None else None

    @field_validator("genre")
    @classmethod
    def normalize_genres(cls, value):
        if isinstance(value, list):
            if any(not genre or len(genre) > 50 for genre in value):
                raise ValueError("类型标签必须是 1～50 个字符的非空字符串。")
            unique = list(dict.fromkeys(value))
            return unique[0] if len(unique) == 1 else unique
        return value


@contextmanager
def movie_database():
    folder = ROOT / ".runtime" / "seekdb"
    if not folder.is_dir():
        raise ValueError("请先完成第二至第五课：创建数据库、导入电影、建立全文及向量索引。")
    instance = pylibseekdb.open(db_dir=str(folder))
    try:
        connection = pymysql.connect(
            database="movie_workshop", charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            **instance.connection_options(),
        )
        try:
            yield connection
        finally:
            connection.close()
    finally:
        instance.close()


def check_database(connection, manifest):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(embedding IS NOT NULL "
            "AND embedding_model = %s AND embedding_text_sha256 = SHA2(overview, 256)), 0) AS ready "
            "FROM movies",
            (manifest["model_tag"],),
        )
        counts = cursor.fetchone()
        if counts["total"] != manifest["movie_count"] or counts["ready"] != counts["total"]:
            raise ValueError("电影资料或向量不完整、模型不一致或剧情已变化，请按第三、第五课重新核对并导入。")
        cursor.execute("SHOW INDEX FROM movies")
        names = {row["Key_name"] for row in cursor.fetchall()}
        if not {"ft_overview", "vec_overview"}.issubset(names):
            raise ValueError("缺少本课需要的索引，请先运行第四课的全文索引和第五课的向量索引脚本。")
        cursor.execute("SELECT VERSION() AS version")
        return cursor.fetchone()["version"]


def eligible_movies(connection, filters):
    """先由数据库完成 JSON 成员及标量过滤，避免取 Top-K 后再过滤。"""
    sql = "SELECT id FROM movies WHERE 1 = 1"
    parameters = []
    if filters.since is not None:
        sql += " AND `year` >= %s"
        parameters.append(filters.since)
    if filters.max_minutes is not None:
        sql += " AND runtime_minutes <= %s"
        parameters.append(filters.max_minutes)
    if filters.genre is not None:
        # JSON_CONTAINS 的数组参数要求每个类型都存在，组合需求不会拼成虚构标签。
        sql += " AND JSON_CONTAINS(genres, %s)"
        parameters.append(json.dumps(filters.genre, ensure_ascii=False))
    if filters.country is not None:
        sql += " AND JSON_CONTAINS(countries, %s)"
        parameters.append(json.dumps(filters.country))
    sql += " ORDER BY id"
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        ids = [row["id"] for row in cursor.fetchall()]
    return ids, sql, parameters


def rrf_window_size(limit, configured=None):
    """默认窗口 5；seekdb 1.4 对全文按窗口的 20 倍预取。"""
    window = max(5, limit) if configured is None else configured
    if isinstance(window, bool) or not isinstance(window, int) or not limit <= window <= 1000:
        raise ValueError("RRF 窗口需为不小于返回数量的整数，且不超过 1000。")
    return window


def search_request(mode, text, embedding, ids, limit, candidates, rank_constant,
                   rank_window_size=None):
    # 当前 seekdb 1.4 系统包不支持 JSON_CONTAINS DSL；两路都用 SQL 选出的 ID 硬过滤。
    # 没有业务条件时直接搜索全表，让优化器选择全文和向量索引访问。
    filters = [{"terms": {"id": ids}}] if ids is not None else []
    request = {"_source": SOURCE_FIELDS, "size": limit}
    if mode in ("fulltext", "hybrid"):
        match = {"match": {"overview": text}}
        request["query"] = {"bool": {"must": [match], "filter": filters}} if filters else match
    if mode in ("vector", "hybrid"):
        request["knn"] = {
            "field": "embedding", "query_vector": embedding,
            "k": candidates,
        }
        if filters:
            request["knn"]["filter"] = filters
    if mode == "hybrid":
        request["rank"] = {"rrf": {"rank_window_size": rrf_window_size(limit, rank_window_size),
                                    "rank_constant": rank_constant}}
    return request


def readable_sql(sql):
    """省略生成 SQL 中的长数值向量，保留 SQL 结构和真实过滤条件。"""
    return re.sub(r"'\[[-+0-9.eE,\s]{100,}\]'", "'[512维问题向量，显示时省略]'", sql)


def explain_operators(connection, sql, parameters=None):
    """读取算子树；避免解码 seekdb 1.4 诊断尾部截断的中文常量。"""
    use_unicode = connection.use_unicode
    try:
        # EXPLAIN 的 Outputs & filters 可能在 UTF-8 字符中间截断。
        # 先完整读取原始字节包，算子树仍严格按 UTF-8 解码；普通查询配置随后恢复。
        connection.use_unicode = False
        with connection.cursor() as cursor:
            cursor.execute("EXPLAIN " + sql, parameters)
            rows = cursor.fetchall()
    finally:
        connection.use_unicode = use_unicode
    operators = []
    for row in rows:
        line = next(iter(row.values()))
        if isinstance(line, bytes):
            if line.startswith(b"Outputs & filters:"):
                break
            line = line.decode("utf-8")
        if line.startswith("Outputs & filters:"):
            break
        operators.append(line)
    return operators


def explain_request(connection, request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DBMS_HYBRID_SEARCH.GET_SQL(%s, %s) AS sql_text",
            ("movies", json.dumps(request, ensure_ascii=False, allow_nan=False)),
        )
        sql = cursor.fetchone()["sql_text"]
    # GET_SQL 来自数据库系统包，内容由固定表名与结构化请求生成。
    operators = explain_operators(connection, sql)
    return {"generated_sql": readable_sql(sql), "operators": operators}


def retrieve_movies(connection, text, embedding, manifest, *, filters=None,
                    keywords=None, mode="compare", limit=5, candidates=20,
                    rank_constant=60, rank_window_size=None, explain=False):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("请输入非空的电影描述。")
    if keywords is not None and (not isinstance(keywords, str) or not keywords.strip()):
        raise ValueError("全文关键词不能是空白。")
    if len(embedding) != manifest["dimension"] or not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        for value in embedding
    ):
        raise ValueError("问题向量的维度或数值不符合资料包配置。")
    if not math.isclose(sum(value * value for value in embedding), 1.0, abs_tol=1e-4):
        raise ValueError("问题向量需要与电影向量一样完成 L2 归一化。")
    if mode not in (*MODES, "compare"):
        raise ValueError("检索模式必须为 fulltext、vector、hybrid 或 compare。")
    if not 1 <= limit <= 20 or not limit <= candidates <= 1000 or not 1 <= rank_constant <= 10000:
        raise ValueError("返回数量需为 1～20；向量候选数需不小于返回数量且不超过 1000；RRF 常量需为 1～10000。")
    window = rrf_window_size(limit, rank_window_size)
    filters = MovieFilters.model_validate(filters or {})
    version = check_database(connection, manifest)
    ids, sql, parameters = eligible_movies(connection, filters)
    has_filters = any(value is not None for value in filters.model_dump().values())
    lexical_text = keywords.strip() if keywords is not None else text.strip()
    selected_modes = MODES if mode == "compare" else (mode,)
    report = {
        "database_version": version,
        "query": {"text": text.strip(), "lexical_text": lexical_text, "dimension": len(embedding)},
        "filters": filters.model_dump(),
        "settings": {"limit": limit, "candidates": candidates, "rank_constant": rank_constant,
                     "rank_window_size": window, "hybrid_fulltext_candidates": window * 20},
        "eligibility": {"count": len(ids), "sql": sql, "parameters": parameters, "id_constraint_applied": has_filters},
        "execution": "sql_prefilter_then_database_hybrid_search",
        "results": {},
    }
    for selected_mode in selected_modes:
        if not ids:
            report["results"][selected_mode] = {"movies": [], "seconds": 0.0, "status": "no_eligible_movies"}
            continue
        request = search_request(selected_mode, lexical_text, embedding, ids if has_filters else None,
                                 limit, candidates, rank_constant, rank_window_size=window)
        started = time.perf_counter()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DBMS_HYBRID_SEARCH.SEARCH(%s, %s) AS result",
                ("movies", json.dumps(request, ensure_ascii=False, allow_nan=False)),
            )
            raw = cursor.fetchone()["result"]
        movies = json.loads(raw) if raw else []
        if not isinstance(movies, list):
            raise ValueError("系统包返回了与本课预期不同的结果格式。")
        if len(movies) > limit or len({movie["id"] for movie in movies}) != len(movies):
            raise ValueError("系统包返回数量超出请求或包含重复电影。")
        allowed = set(ids)
        if any(movie["id"] not in allowed for movie in movies):
            raise ValueError("结果包含不符合业务过滤条件的电影。")
        result = {"movies": movies, "seconds": round(time.perf_counter() - started, 6), "status": "completed"}
        if explain:
            result["plan"] = explain_request(connection, request)
        report["results"][selected_mode] = result
    return report
