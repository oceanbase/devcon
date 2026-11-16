"""Notebook 数据库生命周期与结果展示；具体 SQL 和工具定义保留在课程单元格中。"""

import atexit
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sys
from threading import RLock

import pandas as pd
import pylibseekdb
import pymysql


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from embedding_data import load_bundle
from local_embeddings import LocalEmbeddings
from movie_retrieval import retrieve_movies, explain_operators


MOVIE_COLUMNS = (
    "id", "tmdb_id", "title", "original_title", "overview", "year", "release_date",
    "genres", "countries", "original_language", "runtime_minutes", "rating",
    "vote_count", "poster_url", "source", "source_url", "data_language",
)
INSERT_MOVIES_SQL = (
    "INSERT INTO movies (" + ", ".join(f"`{name}`" for name in MOVIE_COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * len(MOVIE_COLUMNS)) + ") ON DUPLICATE KEY UPDATE "
    + ", ".join(f"`{name}` = VALUES(`{name}`)" for name in MOVIE_COLUMNS if name != "id")
)


def movie_rows(movies):
    return [tuple(json.dumps(movie[name], ensure_ascii=False) if name in ("genres", "countries")
                  else movie.get(name) for name in MOVIE_COLUMNS) for movie in movies]


class LessonDatabase:
    """同一个内核只保留一个实例；关闭后可以再次打开同一份数据。"""

    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.folder = self.root / ".runtime" / "seekdb"
        self.instance = None
        self.connection = None
        self.lock = RLock()
        atexit.register(self.close)

    @property
    def closed(self):
        return self.instance is None

    def open(self):
        with self.lock:
            if not self.closed:
                return self
            self.folder.parent.mkdir(parents=True, exist_ok=True)
            self.instance = pylibseekdb.open(db_dir=str(self.folder))
            try:
                self.connection = pymysql.connect(
                    database="test", charset="utf8mb4", autocommit=True,
                    cursorclass=pymysql.cursors.DictCursor,
                    **self.instance.connection_options(),
                )
                self.execute("CREATE DATABASE IF NOT EXISTS movie_workshop DEFAULT CHARACTER SET utf8mb4")
                self.connection.select_db("movie_workshop")
            except Exception:
                self.close()
                raise
        return self

    def _check_open(self):
        if self.closed or self.connection is None:
            raise RuntimeError("Notebook 的数据库连接已关闭。请重新运行‘连接数据库’单元格，再继续查询。")

    def execute(self, sql, parameters=None):
        with self.lock:
            self._check_open()
            with self.connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                return cursor.rowcount

    def executemany(self, sql, rows):
        with self.lock:
            self._check_open()
            with self.connection.cursor() as cursor:
                cursor.executemany(sql, rows)
                return cursor.rowcount

    def query(self, sql, parameters=None):
        with self.lock:
            self._check_open()
            with self.connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                columns = [item[0] for item in cursor.description]
                return pd.DataFrame(cursor.fetchall(), columns=columns)

    def has_index(self, name):
        indexes = self.query("SHOW INDEX FROM movies")
        return name in set(indexes["Key_name"])

    def add_vector_columns(self):
        columns = self.query("SHOW COLUMNS FROM movies")
        present = dict(zip(columns["Field"], columns["Type"].str.lower().str.replace(" ", "")))
        expected = {"embedding": "VECTOR(512)", "embedding_model": "VARCHAR(128)",
                    "embedding_text_sha256": "CHAR(64)"}
        for name, sql_type in expected.items():
            if name not in present:
                self.execute(f"ALTER TABLE movies ADD COLUMN {name} {sql_type}")
            elif present[name] != sql_type.lower():
                raise ValueError(f"{name} 已存在，但类型不是 {sql_type}。")

    def import_vectors(self, vectors, manifest):
        stored = self.query("SELECT id, overview FROM movies")
        overviews = dict(zip(stored["id"], stored["overview"]))
        for vector in vectors:
            overview = overviews.get(vector["id"])
            if overview is None or hashlib.sha256(overview.encode()).hexdigest() != vector["overview_sha256"]:
                raise ValueError(f"{vector['id']} 的数据库剧情与预计算向量不一致。")
        rows = [(json.dumps(item["embedding"], allow_nan=False), manifest["model_tag"],
                 item["overview_sha256"], item["id"]) for item in vectors]
        return self.executemany(
            "UPDATE movies SET embedding=%s, embedding_model=%s, embedding_text_sha256=%s WHERE id=%s", rows,
        )

    def search(self, text, embedding, manifest, **options):
        with self.lock:
            self._check_open()
            return retrieve_movies(self.connection, text, embedding, manifest, **options)

    def explain(self, sql, parameters=None):
        with self.lock:
            self._check_open()
            return "\n".join(explain_operators(self.connection, sql, parameters))

    def close(self):
        with self.lock:
            connection, instance = self.connection, self.instance
            self.connection = self.instance = None
            try:
                if connection is not None:
                    connection.close()
            finally:
                if instance is not None:
                    instance.close()


class QuestionEncoder:
    def __init__(self, manifest, queries):
        self.manifest = manifest
        self.presets = {query["text"].strip(): query["embedding"] for query in queries}
        self.model = None

    def encode(self, text):
        if text.strip() in self.presets:
            return self.presets[text.strip()]
        if self.model is None:
            self.model = LocalEmbeddings(self.manifest)
        return self.model.embed_query(text)


def movie_frame(movies):
    columns = ["id", "title", "year", "runtime_minutes", "genres", "_score", "overview"]
    frame = pd.DataFrame(movies)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return frame[[name for name in columns if name in frame.columns]]


def comparison_frame(report):
    labels = {"fulltext": "全文检索", "vector": "向量检索", "hybrid": "混合检索"}
    columns = {label: pd.Series([movie["title"] for movie in report["results"][mode]["movies"]], dtype="str")
               for mode, label in labels.items()}
    frame = pd.DataFrame(columns).fillna("—")
    frame.index = frame.index + 1
    frame.index.name = "排名"
    return frame


def display_table(frame, *, index=False, comparison=False):
    """保留完整数据，用可投屏的字号和列宽显示；字符串统一 HTML 转义。"""
    from IPython.display import HTML, display

    frame = frame.copy()
    overviews = []
    if "overview" in frame.columns:
        titles = frame["title"] if "title" in frame.columns else frame.index
        overviews = list(zip(titles, frame["overview"]))
        frame["overview"] = frame["overview"].map(lambda value: str(value)[:120] + "…"
                                                 if len(str(value)) > 120 else str(value))
    if index and frame.index.name:
        frame = frame.reset_index()
        index = False
    css_class = "workshop-ranking" if comparison else "workshop-table"
    table = frame.to_html(index=index, escape=True, border=0, classes=css_class)
    font_size = 20 if comparison else 18
    table = table.replace("<table ", f'<table style="width:100%;margin:0;table-layout:fixed;'
                          f'border-collapse:collapse;font-size:{font_size}px;line-height:1.5" ', 1)
    cell_style = ("text-align:left;vertical-align:top;padding:9px 12px;white-space:normal;"
                  "overflow-wrap:anywhere;font-size:inherit;border-bottom:1px solid #354256")
    table = re.sub(r"<(th|td)(?=[ >])", lambda match: f'<{match[1]} style="{cell_style}"', table)
    widths = {"排名": "64px", "id": "115px", "title": "180px", "year": "84px", "年份": "84px",
              "runtime_minutes": "106px", "片长": "106px", "genres": "150px", "countries": "120px",
              "score": "110px", "_score": "110px", "distance": "110px",
              "混合排名": "84px", "电影": "180px", "全文名次": "105px", "向量名次": "105px",
              "RRF 计算": "280px", "数据库混合得分": "160px"}
    names = ([frame.index.name or ""] if index else []) + list(frame.columns)
    columns = "".join(f'<col style="width:{widths[name]}">' if name in widths else "<col>"
                      for name in names)
    table = table.replace("<thead>", f"<colgroup>{columns}</colgroup><thead>", 1)
    labels = {"id": "电影 ID", "title": "电影", "year": "年份", "runtime_minutes": "片长 / 分",
              "genres": "类型", "countries": "出品地区", "overview": "剧情节选",
              "score": "全文分数", "_score": "得分", "distance": "余弦距离"}
    for name, label in labels.items():
        table = table.replace(f'>{name}</th>', f'>{label}</th>')
    # 内联样式在重新打开未标记为受信任的结果副本时也能保留。
    display(HTML(table))
    if overviews:
        plots = "".join(f'<p><strong>{escape(str(title))}</strong></p><p>{escape(str(overview))}</p>'
                        for title, overview in overviews)
        display(HTML('<details style="margin:12px 0;font-size:18px;line-height:1.6">'
                     '<summary style="cursor:pointer">展开完整剧情</summary>' + plots + '</details>'))


def display_details(title, text):
    """长 SQL 和执行计划随时展开，默认让检索结果留在主画面。"""
    from IPython.display import HTML, display

    display(HTML(f'<details style="margin:12px 0"><summary style="cursor:pointer;'
                 f'font-size:18px">{escape(title)}</summary><pre style="font-size:16px;'
                 f'line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere">'
                 f'{escape(str(text))}</pre></details>'))


def dataset_review(movies):
    from collections import Counter
    counts = Counter(genre for movie in movies for genre in movie["genres"])
    return pd.DataFrame([{"类型": genre, "电影数": count} for genre, count in counts.most_common()])
