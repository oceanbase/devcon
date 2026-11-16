"""使用本项目的虚拟环境启动课程；重复运行会打开已有服务。"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if Path(sys.prefix).resolve() != environment.resolve() and python.is_file():
        print("正在使用本项目的 .venv 启动课程……", flush=True)
        child_environment = os.environ.copy()
        for name in ("PYTHONHOME", "PYTHONPATH"):
            child_environment.pop(name, None)
        return subprocess.call([str(python), str(Path(__file__).resolve()), *argv],
                               cwd=ROOT, env=child_environment)

    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    log_path = runtime / "launcher.log"
    with log_path.open("w", encoding="utf-8") as log:
        log_path.chmod(0o600)

        def report(message, *, error=False):
            print(message, file=sys.stderr if error else sys.stdout, flush=True)
            log.write(message + "\n")
            log.flush()

        report("课程启动时间：" + datetime.now().astimezone().isoformat(timespec="seconds"))
        report("Python：" + sys.executable)
        report("正在启动 JupyterLab，首次启动可能需要等待……")
        try:
            from course.services import launch_notebook
            url = launch_notebook(open_browser=not args.no_browser)
        except Exception as error:
            details = traceback.format_exc()
            print(details, file=sys.stderr, flush=True)
            log.write(details)
            report("课程启动失败。完整日志：" + str(log_path), error=True)
            if isinstance(error, ModuleNotFoundError):
                command = (r".\.venv\Scripts\python.exe .\scripts\setup_environment.py"
                           if os.name == "nt" else ".venv/bin/python scripts/setup_environment.py")
                report("项目依赖不完整，请在项目目录运行：" + command, error=True)
            return 1
        report("Notebook 课程入口：" + url)
        report("如果浏览器未自动打开，请复制上方完整地址到浏览器。")
        report("课程已在后台运行，可以关闭此启动窗口。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
