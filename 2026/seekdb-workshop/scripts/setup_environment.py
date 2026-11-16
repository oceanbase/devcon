"""创建、修复课程虚拟环境，并通过清华源安装统一依赖。"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".venv"
PYTHON = ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
READY = ENV / ".workshop-ready.json"
REQUIREMENTS = ROOT / "requirements.txt"


def clean_environment():
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(name, None)
    return environment


def requirements_hash():
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def environment_ready():
    try:
        marker = json.loads(READY.read_text(encoding="utf-8"))
        return (Path(sys.prefix).resolve() == ENV.resolve()
                and marker["requirements_sha256"] == requirements_hash()
                and marker["python"][:2] == list(sys.version_info[:2])
                and importlib.util.find_spec("pip") is not None)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def python_info(environment):
    try:
        result = subprocess.run(
            [str(PYTHON), "-I", "-c", "import json,sys; print(json.dumps({'prefix':sys.prefix,'version':list(sys.version_info[:3])}))"],
            cwd=ROOT, env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15,
        )
        info = json.loads(result.stdout) if result.returncode == 0 else None
        return info if (info and info["version"][0] == 3
                        and tuple(info["version"][:2]) >= (3, 11)
                        and Path(info["prefix"]).resolve() == ENV.resolve()) else None
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return None


def setup():
    environment = clean_environment()
    required_hash = requirements_hash()
    info = python_info(environment)
    READY.unlink(missing_ok=True)
    if info is None:
        if ENV.exists() or ENV.is_symlink():
            backup = ROOT / (".venv.failed-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            ENV.rename(backup)
            print("原虚拟环境无法启动，已保留到：" + str(backup), flush=True)
        # PATH 中的 Python 可能是 ~/.local/bin 下的链接。必须先解析真实路径，
        # 避免 pyvenv.cfg 把链接所在目录误记为标准库安装位置。
        base_python = Path(getattr(sys, "_base_executable", None) or sys.executable).resolve()
        print("正在创建本项目的 .venv……", flush=True)
        print("基础 Python：" + str(base_python), flush=True)
        # CLI 在 POSIX 上默认使用符号链接；保留 ensurepip 的完整报错输出。
        subprocess.run([str(base_python), "-I", "-m", "venv", str(ENV)],
                       cwd=ROOT, env=environment, check=True)
        info = python_info(environment)
        if info is None:
            raise RuntimeError("新建的虚拟环境无法启动，请检查上方 Python 输出。")

    pip_check = subprocess.run([str(PYTHON), "-m", "pip", "--version"],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15)
    if pip_check.returncode:
        print("正在补全虚拟环境中的 pip……", flush=True)
        subprocess.run([str(PYTHON), "-m", "ensurepip", "--upgrade", "--default-pip"],
                       cwd=ROOT, env=environment, check=True)

    # 清华镜像直连，避免新环境尚无 PySocks 时无法安装其自身。
    for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        environment.pop(name, None)
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    # 所需字节码在首次使用时生成，避免预编译整套大型 AI 依赖。
    subprocess.run([str(PYTHON), "-m", "pip", "install", "--no-compile", "-r", str(REQUIREMENTS)],
                   cwd=ROOT, env=environment, check=True)
    marker = {"requirements_sha256": required_hash, "python": info["version"]}
    temporary = READY.with_suffix(".tmp")
    temporary.write_text(json.dumps(marker) + "\n", encoding="utf-8")
    temporary.replace(READY)
    print("环境已就绪。再次运行 start_workshop 即可打开课程。", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="仅检查上次安装是否完整且依赖清单未改变")
    args = parser.parse_args()
    if args.check:
        return 0 if environment_ready() else 1
    if sys.implementation.name != "cpython" or sys.version_info[0] != 3 or sys.version_info[:2] < (3, 11):
        print("课程需要 CPython 3.11 或更高的 Python 3 版本。", file=sys.stderr)
        return 1
    try:
        setup()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print("环境准备失败：" + str(error), file=sys.stderr)
        print("修复上方错误后重新运行 start_workshop；脚本会继续准备环境。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
