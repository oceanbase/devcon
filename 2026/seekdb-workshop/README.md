# seekdb 电影 Workshop

本次 Workshop 面向 DBA 与开发者，帮助参与者理解 seekdb 的 SQL / JSON 过滤、中文全文、向量与数据库内 RRF 混合检索，学会结合字段和原文判断结果，并看懂 LangChain 连接模型与检索工具的流程。课程以电影资料为实践场景，讲师与学员使用同一份滚动 `Workshop.ipynb`。

Windows 启动后会保留窗口中的课程链接；按任意键关闭窗口后，课程服务继续在后台运行。如果没有自动打开浏览器，可复制窗口中的完整课程链接。启动日志保存在 `.runtime/launcher.log`，服务日志保存在 `.runtime/jupyter.log`。手动运行 `python scripts/launch_notebook.py` 时也会自动切换到本项目 `.venv`。

## 打开课程

1. 本机需要 CPython 3.11 或更高的 Python 3 版本（Windows 使用 64 位版本）。macOS 3.12、Linux 3.13.11、Windows 3.15.2 已分别完成课程或启动验证。首次双击对应平台的启动脚本，会创建本项目 `.venv` 并安装依赖。手动安装可运行 `python3 scripts/setup_environment.py`；Windows 使用 `python scripts\setup_environment.py`。`requirements.txt` 统一维护依赖，使用清华源。
2. 双击 `start_workshop.command`（macOS）、`start_workshop.bat`（Windows），或在 Linux 的课程目录运行 `bash start_workshop.sh`。
3. 浏览器打开 `Workshop.ipynb`，内核选择 **Python · seekdb workshop**。先阅读开场说明，再从第 0 节的环境准备代码开始运行。选中代码格后按 `Ctrl+Enter` 执行。正式活动的第 0–2 节课前完成。

Windows 启动脚本会先检查已有虚拟环境，再优先使用当前可运行的 `python`、`python3`，必要时尝试 `py -3`、带版本号的命令及常见安装目录；不会先指定 Python 3.12，也不要求安装 `py` 启动器。若旧虚拟环境已失效或依赖安装中断，会重新准备环境。如果提示找不到 CPython 3.11 及以上版本，请安装可用版本并勾选 **Add python.exe to PATH**，再重新打开终端或启动脚本。Embedding 已切换为支持 Python 3.15 的 Sentence Transformers + PyTorch CPU 后端。

Windows 请将资料解压到完整路径不含中文的目录，例如 `C:\seekdb-workshop`；父目录和用户名中的中文也会影响当前版本的数据库启动。

macOS / Linux 启动脚本会检查虚拟环境是否已完成依赖安装。首次准备失败后可以直接重新运行；无法启动的 `.venv` 会保留为 `.venv.failed-时间戳`，再用基础 Python 的真实路径重新创建。仅当安装全部成功后才记录完成状态。

多数依赖通过清华镜像安装；PyTorch CPU 构建通过官方下载页面安装。建议课前完成首次安装。升级旧环境时，重新运行 `scripts/setup_environment.py`，再从第 0 节按顺序运行课程。第 5 节会把新版预计算向量写入已有电影表。

JupyterLab 与 Streamlit 默认监听 `0.0.0.0`。在其他机器的浏览器访问时，将入口地址中的 `127.0.0.1` 换成运行课程的主机 IP；JupyterLab 链接保留完整的 token 参数。默认端口分别从 8888 和 8503 开始，遇到占用会自动选择可用端口。升级已运行的旧版本后，先运行 `stop_workshop`，再重新启动以应用监听地址。

可直接用项目 Python 启动：

```bash
# macOS / Linux
.venv/bin/python scripts/launch_notebook.py

# Windows
.venv\Scripts\python.exe scripts\launch_notebook.py
```

默认使用 JupyterLab Dark、单文档模式、代码行号。正文和讲解表格为 18px、代码 17px、排名表 20px；两侧面板、页头与状态栏默认收起。启动脚本每次打开课程时都会复制课程布局，避免新标签页的独立工作区恢复默认侧边栏；需要新开课程页面时，请再次运行 `start_workshop`。需要章节导航时选择“查看 → 目录”。必做代码默认展开，包括环境准备与生成推荐前的流程定义；只有明确标为“可选”的计划检查、应用源码对照保留折叠，可以跳过。

字体使用本机已有字体自动回退，不下载网页字体，也不要求额外安装：macOS 正文优先苹方（PingFang SC）、代码 Menlo；Windows 正文优先微软雅黑 UI、代码 Consolas；Linux 优先可用的 Noto Sans CJK、Liberation Mono / DejaVu Sans Mono，缺少时交给系统无衬线或等宽字体。启动脚本会为本项目应用这组设置。

浏览器标签页使用 seekdb 官方图标，课程启动时自动应用到本项目 `.venv` 内的 Jupyter 静态图标。原图标备份在 `.runtime/original-favicons/`，不需要重启内核。图标与来源说明位于 `assets/branding/`。这项设置不改变操作系统为 `.ipynb` 文件分配的文件图标。

Notebook 会保存执行输出。发放主文件前清空输出并保存，真实运行参考保留在 `reports/Workshop-executed.ipynb`。页面上的历史输出不等于当前内核已经运行。

## 学什么、改什么

| 章节 | 主要操作与判断 |
|---|---|
| 0–2 课前准备 | 环境、真实记录、启动嵌入式 seekdb |
| 3 SQL / JSON | 用年份、片长、犯罪与悬疑标签确定范围；片长 120 改 100，核对总数 |
| 4 全文 | 用开场需求查剧情，区分字词命中与字段条件 |
| 5 向量 | 导入 512 维向量、建索引；选问题 ID 或自由描述，同模型编码查询 |
| 6 混搜 | 同句描述比较三路，读剧情；前置 SQL 选 ID，同一 ID 过滤进入全文与向量请求 |
| 7 LangChain | 定义并手动调用工具，可选体验模型提取条件与生成推荐 |
| 8 应用与回顾 | 核对两个按钮的真实调用，体验准备好的页面，解释一条返回结果 |

主线只有一个案例。类型、年份和片长的硬条件在第 3 节先验证，第 4–5 节单独观察无过滤的相关性，第 6 节再合并。排名后面提供三路第一名的原文依据；加入条件后显示哪些旧候选被过滤以及原因。

第 5 节先列出可选问题，再提供 `QUERY_ID` / `CUSTOM_TEXT` 输入。修改后重跑选择格、向量查询格和第 6 节对比格。自由输入会在首次使用时下载固定版本 Embedding 模型并在本机编码；示例原文复用课前向量。

第 6 节修改 `NOTEBOOK_FILTERS` 后，从过滤格重跑到结果格。第 7 节使用独立推荐输入，不继承先前的动画等探索条件。深入 SQL、执行计划、候选名次与其他题材练习留在同一 Notebook，便于课后阅读。

## 模型与应用

`CHAT_BACKEND` 读取 `WORKSHOP_CHAT_BACKEND`，默认使用 `glm`，当前模型为 `glm-5.3-flash`。复制 `.env.example` 为 `.env`，填入自己的智谱标准 API Key（`ZHIPU_API_KEY`）。仓库不包含 API Key。

聊天默认 `RUN_CHAT_MODEL=False`。完整模型格运行只定义函数；改为 `True` 并运行独立开关格后，才通常发出两次模型请求。前面的检索、工具手动调用都可以独立完成。

### Embedding 模型

自由输入的查询向量使用 `BAAI/bge-small-zh-v1.5`（固定 commit `7999e1d3359715c523056ef9478215996d62a620`），与 `data/` 中预计算的电影向量一致。仓库不包含约 92MB 的模型权重。第一次对自定义描述编码时，会从 Hugging Face 下载到 `models/bge-small-zh-v1.5/`，并按 `data/embedding-manifest.json` 校验文件。之后复用本地缓存。使用课前示例原文时不下载模型。

国内访问 Hugging Face 较慢时，启动课程前设置镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

Windows PowerShell：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

详见 `models/README.md`。模型许可见 `docs/licenses/`。

Streamlit 界面已经提供，课程重点是检索与工具接入。Notebook 可展开 `app.py` 两个按钮的真实调用。应用复用检索模块，重新创建自己的连接与工具，不会自动导入内核里的函数和变量。

第 8 节先释放 Notebook 数据库，再启动应用并返回链接。回到 Notebook 时重跑第 2 节，它只停止本项目的应用。先在页面保留无过滤条件，对照第 6 节第一张表；然后再加年份、片长体验推荐。页面类型框为单标签，工具支持组合标签。

## 资料与目录

课程默认混搜参数为：全文候选上限 100、向量候选数 20、返回 5、RRF 常量 60。当前 seekdb 1.4 使用 `rank_window_size = 5` 和 `knn.k = 20` 原生生成这组上限。应用中调整“向量候选数”只改变向量 k；若增加最终返回数量，默认 RRF 窗口会随之增大，以满足系统包的窗口约束。

500 部简体中文电影资料保留原有 100 部，新增 400 部，补充悬疑、家庭、动画等题材；含 CN/HK/TW 出品或合拍的电影与其他地区各 250 部。资料语种与电影出品地区分开保存。详见 `docs/data-plan.md`。

- `data/`：电影、预计算电影与问题向量、来源与校验清单。
- `models/`：首次自定义查询时下载的 Embedding 模型缓存，权重不纳入 Git。
- `wheels/`：Windows Python 3.15 的两个补充安装包及其来源校验信息，完整资料包会附带。
- `.runtime/seekdb/`：运行后产生的本机数据库数据文件。
- `.runtime/` 中的日志、服务记录与缓存：本机运行状态。
- `.venv/`：本机安装的 Python 依赖，包括 `pylibseekdb` 数据库运行库。
- `course/`：连接、结果与原文展示、服务管理。
- `examples/`、`sql/`：真实检索、推荐逻辑与 SQL；应用和 Notebook 复用。
- `assets/figures/`：6 张原理图的 SVG 源图与 PNG，以及课程收尾图；主文件内嵌 PNG，收尾图的生成提示词一并保存。
- `reports/`：组织者验证输出与界面截图。

`.env`、本机 `.venv`、`.jupyter`、运行数据库、日志、登录状态和 Embedding 模型权重不纳入 Git。具体讲师节奏见 `docs/teaching-guide.md`。

克隆仓库后按课前步骤创建环境。电影资料和预计算向量在 `data/`。自由输入查询时，课程会把 `BAAI/bge-small-zh-v1.5` 下载到 `models/bge-small-zh-v1.5/`。运行后生成的数据库由本机创建。

### Git 管理范围

Git 保留主 Notebook、课程代码、SQL、依赖清单、文档、课程图片与图标，以及 `data/` 中整理好的电影资料和预计算向量。`.env.example`、`.streamlit/config.toml` 和 `models/README.md` 也保留，方便新环境配置。

`.gitignore` 排除本机环境、数据库、密钥、模型权重、API 原始缓存、`dist/` 分发包、`reports/` 验证结果与备份，以及编辑器和 Python 缓存。忽略规则不删除本机文件。其他电脑获取仓库后，按课前步骤创建环境；自定义查询时会自动下载 Embedding 模型。

## 日常修改与验证

日常以 `Workshop.ipynb` 为主文件，直接编辑后按 `⌘S`（Windows 为 `Ctrl+S`）保存。`start_workshop` 只打开现有讲义，不会重新生成内容；重新打开、重启内核或重启电脑后，已保存的修改仍然保留。

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_notebook.py
```

普通验证关闭聊天模型，在真实内核执行并保存 `reports/Workshop-executed.ipynb`。仅显式加 `--with-model` 才启用聊天请求。已在 macOS ARM64 / Python 3.12 和 Windows x86-64 / Python 3.15.2 上完成完整 Notebook 验证。其他平台、正式 API 并发和 30 分钟现场节奏需活动前演练；当前 macOS 依赖使用 Apple Silicon wheel。

### 组织者从模板重建

`scripts/build_notebook.py` 默认拒绝覆盖已有 `Workshop.ipynb`，也不会重建图片。它是模板生成入口，不会自动吸收你在 Notebook 中的手工编辑。

只有明确需要从模板重建时才使用 `.venv/bin/python scripts/build_notebook.py --force`。脚本会先把当前讲义完整备份到 `reports/notebook-backups/Workshop-日期-时间.ipynb`，再写入新讲义；如果生成期间主文件又发生修改，会停止覆盖。需要找回旧内容时，可直接打开备份 Notebook。

电影元数据来自 TMDB，每条记录保留来源链接；Embedding 模型许可见 `docs/licenses/`。


## 停止课程与删除目录

先保存 Notebook，再运行 `stop_workshop.bat`（Windows）、`stop_workshop.command`（macOS）或 `bash stop_workshop.sh`（Linux）。停止脚本会关闭本目录的 Streamlit、JupyterLab、Notebook 内核及其子进程，释放嵌入式数据库和文件句柄。关闭浏览器页面不会停止这些后台进程。

Windows 也可以在 PowerShell 运行：

```powershell
.\stop_workshop.bat
```

如果准备删除课程目录，在 PowerShell 中再执行 `cd ..`，并关闭其他仍位于课程目录中的终端窗口。停止脚本自身会在暂停前切到临时目录，避免继续占用课程目录。重复运行停止脚本也可以。
