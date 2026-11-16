"""只管理本项目的 Notebook / Streamlit 子进程，不影响原版项目。"""

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import re
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

import psutil


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def _process(kind):
    path = RUNTIME / f"{kind}-service.json"
    if not path.exists():
        return None, None
    info = json.loads(path.read_text())
    try:
        process = psutil.Process(info["pid"])
        command = process.cmdline()
        if str(ROOT) not in " ".join(command):
            return None, None
        if kind == "streamlit" and str(ROOT / "app.py") not in command:
            return None, None
        if kind == "jupyter" and not any("jupyterlab" in part for part in command):
            return None, None
        return process, info
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None, None


def stop_app():
    process, info = _process("streamlit")
    if process is None:
        return False
    children = process.children(recursive=True)
    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    process.terminate()
    _, alive = psutil.wait_procs([process, *children], timeout=15)
    for remaining in alive:
        try:
            remaining.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5)
    (RUNTIME / "streamlit-service.json").unlink(missing_ok=True)
    return True


def _port(preferred):
    for candidate in range(preferred, preferred + 30):
        with socket.socket() as listener:
            try:
                listener.bind(("0.0.0.0", candidate))
                return candidate
            except OSError:
                continue
    raise RuntimeError("没有可用的本地端口。")


def _wait(url, process, timeout=45):
    local_http = build_opener(ProxyHandler({}))
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if process.poll() is not None:
            raise RuntimeError("服务启动失败，请查看本项目 .runtime 中的服务日志。")
        try:
            with local_http.open(url, timeout=1) as response:
                if response.status < 400:
                    return
        except OSError:
            pass
        time.sleep(.2)
    raise RuntimeError("服务启动超时，请查看 .runtime 中的服务日志。")


def _background_options():
    options = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return options


def _open_course_browser(url):
    if os.name == "nt":
        try:
            os.startfile(url)
            return True
        except OSError:
            pass
    try:
        return webbrowser.open(url)
    except (OSError, webbrowser.Error):
        return False


def _save(kind, info):
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / f"{kind}-service.json"
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2))
    path.chmod(0o600)


def launch_app(database=None, backend=None):
    if backend is not None and backend not in ("glm", "codex"):
        raise ValueError("聊天后端只支持 glm 或 codex。")
    if database is not None:
        database.close()
    existing, info = _process("streamlit")
    if existing is not None:
        if backend is None or backend == info.get("backend"):
            return info["url"]
        stop_app()
    RUNTIME.mkdir(exist_ok=True)
    port = _port(8503)
    url = f"http://127.0.0.1:{port}/"
    env = os.environ.copy()
    env.pop("JUPYTER_TOKEN", None)
    if backend is not None:
        env["WORKSHOP_CHAT_BACKEND"] = backend
    with (RUNTIME / "streamlit.log").open("ab") as log:
        (RUNTIME / "streamlit.log").chmod(0o600)
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
            "--server.address", "0.0.0.0", "--server.port", str(port),
            "--server.headless", "true", "--browser.gatherUsageStats", "false",
        ], cwd=ROOT, env=env, stdout=log, stderr=log, **_background_options())
    _save("streamlit", {"pid": process.pid, "url": url, "backend": backend})
    _wait(url + "_stcore/health", process)
    return url


def kernel_environment():
    (RUNTIME / "ipython").mkdir(parents=True, exist_ok=True)
    directory = ROOT / ".jupyter" / "kernels" / "seekdb-workshop"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Python · seekdb workshop", "language": "python",
    }, ensure_ascii=False, indent=2))
    env = os.environ.copy()
    env["JUPYTER_PATH"] = str(ROOT / ".jupyter") + (os.pathsep + env["JUPYTER_PATH"] if env.get("JUPYTER_PATH") else "")
    env["IPYTHONDIR"] = str(RUNTIME / "ipython")
    return env


def configure_notebook_branding():
    """在本项目独立虚拟环境中设置 favicon；保留原图标，不重启内核。"""
    import jupyter_server
    from jupyterlab.commands import get_app_dir

    environment = (ROOT / ".venv").resolve()
    icons = Path(jupyter_server.__file__).resolve().parent / "static" / "favicons"
    template = (Path(get_app_dir()) / "static" / "index.html").resolve()
    if not icons.is_relative_to(environment) or not template.is_relative_to(environment):
        raise RuntimeError("请使用本项目 .venv 启动课程，避免修改其他 Jupyter 环境的图标。")
    source = ROOT / "assets" / "branding" / "seekdb.ico"
    data = source.read_bytes()
    backup = RUNTIME / "original-favicons"
    names = ("favicon.ico", "favicon-notebook.ico", "favicon-busy-1.ico",
             "favicon-busy-2.ico", "favicon-busy-3.ico")
    for name in names:
        target = icons / name
        if target.read_bytes() == data:
            continue
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / name).exists():
            shutil.copy2(target, backup / name)
        # 原子替换包内的数据文件，避免修改可能来自安装缓存的共享 inode。
        temporary = target.with_name(name + ".seekdb.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    # 浏览器会单独缓存 favicon；内容版本变化后使用新 URL。
    version = hashlib.sha256(data).hexdigest()[:12]
    html = template.read_text(encoding="utf-8")
    branded, matched = re.subn(
        r'(static/favicons/favicon(?:-busy-1)?\.ico)(?:\?[^"\s]*)?',
        lambda match: match[1] + "?seekdb=" + version, html,
    )
    if matched != 2:
        raise RuntimeError("JupyterLab 的图标模板已变化，请检查课程版本。")
    if branded != html:
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / "index.html").exists():
            shutil.copy2(template, backup / "index.html")
        temporary = template.with_name("index.html.seekdb.tmp")
        temporary.write_text(branded, encoding="utf-8")
        temporary.replace(template)
    return source


def configure_notebook_ui():
    """为课程保存深色单文档布局，设置仅写入本项目目录。"""
    import json5
    from jupyterlab_server.workspaces_handler import WorkspacesManager

    settings = ROOT / ".jupyter" / "lab" / "user-settings"
    preferences = {
        "@jupyterlab/translation-extension:plugin": {"locale": "zh_CN"},
        "@jupyterlab/apputils-extension:themes": {
            "theme": "JupyterLab Dark", "adaptive-theme": False,
            "theme-scrollbars": True,
            "overrides": {
                "content-font-size1": "18px", "code-font-size": "17px",
                "content-font-family": ('"PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", '
                                        '"Noto Sans CJK SC", "Noto Sans SC", system-ui, sans-serif'),
                "code-font-family": ('Menlo, Consolas, "Liberation Mono", "DejaVu Sans Mono", '
                                     '"Noto Sans Mono CJK SC", "PingFang SC", "Microsoft YaHei UI", monospace'),
            },
        },
        "@jupyterlab/application-extension:shell": {
            "startMode": "single", "dockPanelPadding": False,
        },
        "@jupyterlab/statusbar-extension:plugin": {"visible": False},
        "@jupyterlab/notebook-extension:tracker": {
            "codeCellConfig": {"lineNumbers": True, "lineWrap": True},
        },
    }
    for plugin, defaults in preferences.items():
        package, name = plugin.split(":", 1)
        path = settings / package / f"{name}.jupyterlab-settings"
        path.parent.mkdir(parents=True, exist_ok=True)
        current = json5.loads(path.read_text()) if path.exists() else {}
        for key, value in defaults.items():
            if isinstance(value, dict):
                current[key] = {**current.get(key, {}), **value}
            else:
                current[key] = value
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")

    workspaces = ROOT / ".jupyter" / "lab" / "workspaces"
    workspaces.mkdir(parents=True, exist_ok=True)
    manager = WorkspacesManager(str(workspaces))
    saved = [json.loads(path.read_text()) for path in workspaces.glob("*.jupyterlab-workspace")]
    if not any(item["metadata"]["id"].lstrip("/") == "default" for item in saved):
        saved.append({"metadata": {"id": "default"}, "data": {
            "notebook:Workshop.ipynb": {"data": {"path": "Workshop.ipynb", "factory": "Notebook"}},
            "layout-restorer:data": {"main": {
                "dock": {"type": "tab-area", "currentIndex": 0, "widgets": ["notebook:Workshop.ipynb"]},
                "current": "notebook:Workshop.ipynb",
            }},
        }})
    for workspace in saved:
        layout = workspace.setdefault("data", {}).setdefault("layout-restorer:data", {})
        for side in ("left", "right", "down"):
            state = layout.setdefault(side, {})
            state["collapsed"] = True
            state.pop("current", None)
            state.setdefault("widgets", [])
            if side != "down":
                state["visible"] = False
            else:
                state["size"] = 0
        layout["relativeSizes"] = [0, 1, 0]
        layout.setdefault("top", {})["simpleVisibility"] = False
        manager.save(workspace["metadata"]["id"].lstrip("/"), json.dumps(workspace, ensure_ascii=False))
    return settings, workspaces


def launch_notebook(open_browser=True):
    configure_notebook_branding()
    settings, workspaces = configure_notebook_ui()
    existing, info = _process("jupyter")
    if existing is None:
        RUNTIME.mkdir(exist_ok=True)
        port = _port(8888)
        token = secrets.token_urlsafe(32)
        env = kernel_environment()
        env["JUPYTER_TOKEN"] = token
        env["JUPYTERLAB_SETTINGS_DIR"] = str(settings)
        env["JUPYTERLAB_WORKSPACES_DIR"] = str(workspaces)
        url = f"http://127.0.0.1:{port}/lab/tree/Workshop.ipynb"
        with (RUNTIME / "jupyter.log").open("ab") as log:
            (RUNTIME / "jupyter.log").chmod(0o600)
            process = subprocess.Popen([
                sys.executable, "-m", "jupyterlab", "--no-browser", "--ip=0.0.0.0",
                f"--port={port}", f"--ServerApp.root_dir={ROOT}", "--ServerApp.port_retries=0",
            ], cwd=ROOT, env=env, stdout=log, stderr=log, **_background_options())
        info = {"pid": process.pid, "url": url, "token": token}
        _save("jupyter", info)
        # 登录页本身可在未认证时访问；URL 不携带凭证。
        _wait(f"http://127.0.0.1:{port}/login", process, timeout=120 if os.name == "nt" else 45)
    # 同一地址在另一个标签页打开时，JupyterLab 会分配 auto-* 工作区。
    # 显式克隆已配置的课程布局，让这些新工作区也收起侧边栏。
    course_url = info["url"] + "?clone=default"
    login_url = course_url + "&token=" + info["token"]
    if open_browser and not _open_course_browser(login_url):
        print("未能自动打开浏览器，请复制下方的课程入口到浏览器。", flush=True)
    return login_url
