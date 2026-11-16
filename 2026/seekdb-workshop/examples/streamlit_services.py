"""Streamlit 资源：复用数据库运行时和本机 Embedding 模型，每次查询单独建立 SQL 连接。"""

import atexit
import json
from threading import RLock

import pylibseekdb
import pymysql

from embedding_data import load_bundle
from local_embeddings import LocalEmbeddings
from movie_retrieval import ROOT, retrieve_movies


def load_catalog():
    manifest, _, queries = load_bundle()
    movies = json.loads((ROOT / "data" / "movies.json").read_text(encoding="utf-8"))
    return {
        "manifest": manifest,
        "queries": queries,
        "genres": sorted({genre for movie in movies for genre in movie["genres"]}),
        "countries": sorted({country for movie in movies for country in movie["countries"]}),
    }


class MovieSearchRuntime:
    def __init__(self):
        folder = ROOT / ".runtime" / "seekdb"
        if not folder.is_dir():
            raise ValueError("请先按第二至第五课准备数据库、电影、向量及索引。")
        self.lock = RLock()
        self.closed = False
        self.instance = pylibseekdb.open(db_dir=str(folder))
        atexit.register(self.close)

    def search(self, text, embedding, manifest, **options):
        # 同一台电脑上的浏览器会话共用运行时；SQL 连接不跨线程复用。
        with self.lock:
            if self.closed:
                raise ValueError("数据库运行时已经关闭，请刷新页面后重试。")
            connection = pymysql.connect(
                database="movie_workshop", charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                **self.instance.connection_options(),
            )
            try:
                return retrieve_movies(connection, text, embedding, manifest, **options)
            finally:
                connection.close()

    def close(self):
        with self.lock:
            if not self.closed:
                self.instance.close()
                self.closed = True


class LocalQueryEncoder:
    def __init__(self, manifest):
        self.lock = RLock()
        self.encoder = LocalEmbeddings(manifest)

    def encode(self, text):
        with self.lock:
            return self.encoder.embed_query(text)
