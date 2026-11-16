"""使用固定版本中文模型在本机编码问题；本地没有权重时从 Hugging Face 下载。"""

import hashlib
from importlib.metadata import version
import math
from pathlib import Path

from embedding_data import checked_model_file

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "bge-small-zh-v1.5"
HF_MIRROR = "https://hf-mirror.com"


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_model_files(manifest, model_dir):
    missing = []
    mismatched = []
    for name, expected in manifest["model_files_sha256"].items():
        path = checked_model_file(model_dir, name)
        if not path.is_file():
            missing.append(name)
        elif _sha256_file(path) != expected:
            mismatched.append(name)
    return missing, mismatched


def ensure_local_model(manifest, model_dir=None):
    """本地权重齐全且校验通过则直接使用；否则下载固定 revision 并再次校验。"""
    model_dir = Path(model_dir) if model_dir is not None else MODEL_DIR
    missing, mismatched = _verify_model_files(manifest, model_dir)
    if not missing and not mismatched:
        return model_dir

    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError("缺少 huggingface_hub，请先安装本项目 requirements.txt。") from error

    repo = manifest["model_repo"]
    revision = manifest["model_revision"]
    model_dir.mkdir(parents=True, exist_ok=True)
    for name in mismatched:
        checked_model_file(model_dir, name).unlink()

    print(
        f"正在下载 Embedding 模型 {repo}@{revision} 到 {model_dir}（约 92MB）。"
        f"国内网络较慢时可设置环境变量 HF_ENDPOINT={HF_MIRROR} 后重试。",
        flush=True,
    )
    try:
        snapshot_download(
            repo_id=repo,
            revision=revision,
            local_dir=str(model_dir),
            allow_patterns=list(manifest["model_files_sha256"]),
        )
    except Exception as error:
        raise RuntimeError(
            "下载 Embedding 模型失败。请检查网络，或设置 HF_ENDPOINT="
            f"{HF_MIRROR} 后重新运行。"
        ) from error

    missing, mismatched = _verify_model_files(manifest, model_dir)
    if missing or mismatched:
        details = []
        if missing:
            details.append("缺少 " + ", ".join(missing))
        if mismatched:
            details.append("校验失败 " + ", ".join(mismatched))
        raise ValueError("下载后的模型与电影向量使用的版本不一致：" + "；".join(details))
    return model_dir


class LocalEmbeddings:
    def __init__(self, manifest, model_dir=None):
        if manifest.get("embedding_backend") != "sentence-transformers":
            raise ValueError("请使用 Sentence Transformers 版模型和向量资料包，不能混用旧版向量。")
        for package in ("sentence-transformers", "transformers", "tokenizers", "torch"):
            actual = version(package).split("+", 1)[0]
            expected = manifest["runtime_versions"][package].split("+", 1)[0]
            if actual != expected:
                raise ValueError(f"{package} 版本与向量资料包不一致，请安装本项目 requirements.txt。")

        self.model_dir = ensure_local_model(manifest, model_dir)

        import torch
        from sentence_transformers import SentenceTransformer
        from transformers.utils import logging as transformers_logging

        torch.set_num_threads(2)
        transformers_logging.disable_progress_bar()

        self.manifest = manifest
        self.model = SentenceTransformer(
            str(self.model_dir),
            backend="torch",
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"attn_implementation": "eager"},
        )
        self.model.float()
        self.model.max_seq_length = manifest["max_input_tokens"]
        if self.model.get_embedding_dimension() != manifest["dimension"]:
            raise ValueError("离线模型的输出维度与向量资料包不一致。")

    def _encode(self, texts, batch_size=8):
        values = self.model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False, precision="float32",
        )
        vectors = []
        for row in values:
            vector = [float(value) for value in row]
            if len(vector) != self.manifest["dimension"] or not all(math.isfinite(value) for value in vector):
                raise ValueError("模型输出向量的维度或数值无效。")
            if not math.isclose(sum(value * value for value in vector), 1.0, abs_tol=1e-4):
                raise ValueError("模型输出向量未完成 L2 归一化。")
            vectors.append(vector)
        return vectors

    def embed_documents(self, texts, batch_size=8):
        """组织者课前编码电影剧情；文档不添加查询前缀。"""
        texts = list(texts)
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("电影剧情必须是非空文本。")
        return self._encode(texts, batch_size)

    def embed_query(self, text):
        if not text.strip():
            raise ValueError("请输入非空的问题。")
        return self._encode([self.manifest["query_prefix"] + text.strip()])[0]
