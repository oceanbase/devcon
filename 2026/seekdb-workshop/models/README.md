# Embedding 模型

自由输入的查询向量使用固定版本的 `BAAI/bge-small-zh-v1.5`（commit `7999e1d3359715c523056ef9478215996d62a620`），与 `data/` 中预计算的电影向量一致。模型使用 Sentence Transformers + PyTorch CPU 后端，CLS 池化、L2 归一化、512 维输出；查询前缀保存在 `data/embedding-manifest.json`。

仓库不包含约 92MB 的模型权重。第一次对自定义描述编码时，会从 Hugging Face 下载到 `models/bge-small-zh-v1.5/`，并按 manifest 中的 SHA256 校验。之后直接读取本地文件。示例问题复用课前向量，不必下载模型。

国内访问 Hugging Face 较慢时，启动课程前设置镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

Windows PowerShell：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

模型来源：https://huggingface.co/BAAI/bge-small-zh-v1.5  
许可见 `docs/licenses/`。权重不纳入 Git。
