"""读取并校验组织者发放的向量资料包；仅使用 Python 标准库。"""

import hashlib
import json
import math
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def checked_model_file(model_dir, name):
    """模型允许标准子目录；拒绝绝对路径、盘符和跳出目录的文件名。"""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("模型文件名称无效。")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
        raise ValueError("模型文件名称无效。")
    model_dir = Path(model_dir)
    path = model_dir.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(model_dir.resolve()):
        raise ValueError("模型文件必须位于本机模型目录中。")
    return path


def load_bundle(folder=None):
    folder = Path(folder) if folder is not None else ROOT / "data"
    manifest = json.loads((folder / "embedding-manifest.json").read_text(encoding="utf-8"))
    if manifest["format_version"] != 1 or manifest["dimension"] != 512 or manifest["distance"] != "cosine":
        raise ValueError("本课需要 512 维、cosine 距离的第 1 版向量资料包。")
    files = ("movies.json", "search-queries.json", "movie-embeddings.json", "query-embeddings.json")
    loaded = {}
    for name in files:
        raw = (folder / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["files_sha256"][name]:
            raise ValueError(f"{name} 的校验值不匹配，请使用同一批资料包中的文件。")
        loaded[name] = json.loads(raw)

    movies = loaded["movies.json"]
    movie_vectors = loaded["movie-embeddings.json"]
    queries = loaded["query-embeddings.json"]
    expected_queries = loaded["search-queries.json"]
    ids = {movie["id"] for movie in movies}
    if len(ids) != len(movies) or len(movie_vectors) != manifest["movie_count"] or len(movie_vectors) != len(movies):
        raise ValueError("电影数量或 ID 不匹配。")
    if {item["id"] for item in movie_vectors} != ids:
        raise ValueError("电影向量的 ID 与原始电影不对应。")
    if len(queries) != manifest["query_count"] or len({item["id"] for item in queries}) != len(queries):
        raise ValueError("示例问题数量或 ID 不匹配。")
    if {item["id"]: item["text"] for item in queries} != {item["id"]: item["text"] for item in expected_queries}:
        raise ValueError("示例问题文字与预计算向量不对应。")
    expected_hashes = {
        movie["id"]: hashlib.sha256(movie["overview"].encode("utf-8")).hexdigest()
        for movie in movies
    }
    for item in movie_vectors:
        if item["overview_sha256"] != expected_hashes[item["id"]]:
            raise ValueError(f"{item['id']} 的剧情已变更，请重新准备向量。")
    for item in [*movie_vectors, *queries]:
        vector = item["embedding"]
        if len(vector) != manifest["dimension"] or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vector):
            raise ValueError(f"{item['id']} 的向量维度或数值无效。")
        if not math.isclose(sum(v * v for v in vector), 1.0, abs_tol=1e-4):
            raise ValueError(f"{item['id']} 的向量未完成 L2 归一化。")
    return manifest, movie_vectors, queries
