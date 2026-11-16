"""关闭本目录的课程服务和内核，释放数据库及文件句柄。"""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def _same_path(value, expected, cwd=None):
    try:
        path = Path(value.strip('"'))
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
        return path.resolve() == Path(expected).resolve()
    except (OSError, ValueError, TypeError):
        return False


def _owned_kind(process, root):
    command = process.cmdline()
    if not command:
        return None
    try:
        cwd = process.cwd()
    except OSError:
        cwd = None
    names = {Path(part).name.lower() for part in command}
    if names & {'jupyterlab', 'jupyter_server', 'notebook', 'jupyter-lab',
                'jupyter-lab.exe', 'jupyter-notebook.exe'}:
        flags = ('--ServerApp.root_dir', '--NotebookApp.notebook_dir', '--notebook-dir')
        directories = []
        for index, part in enumerate(command):
            for flag in flags:
                if part.startswith(flag + '='):
                    directories.append(part[len(flag) + 1:])
                elif part == flag and index + 1 < len(command):
                    directories.append(command[index + 1])
        if directories:
            return 'jupyter' if all(_same_path(value, root, cwd) for value in directories) else None
        if cwd and _same_path(cwd, root):
            return 'jupyter'
    if names & {'streamlit', 'streamlit.exe'}:
        if any(_same_path(part, root / 'app.py', cwd) or _same_path(part, root / 'search_app.py', cwd)
               for part in command):
            return 'streamlit'
    if names & {'ipykernel_launcher', 'ipykernel_launcher.py'}:
        if cwd and _same_path(cwd, root):
            return 'kernel'
    return None


def _shutdown_jupyter(info):
    try:
        parts = urlsplit(info['url'])
        if parts.scheme != 'http' or parts.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            return False
        request = Request(f'{parts.scheme}://{parts.netloc}/api/shutdown', data=b'',
                          headers={'Authorization': 'token ' + info['token']}, method='POST')
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            return response.status < 400
    except (OSError, KeyError, TypeError, ValueError):
        return False


def stop_workshop(root=ROOT):
    import psutil

    root = Path(root).resolve()
    parents = psutil.Process().parents()
    protected = {os.getpid(), *(p.pid for p in parents)}
    for parent in parents:
        try:
            if _owned_kind(parent, root):
                return {'stopped': False, 'services': [], 'process_count': 0,
                        'remaining_pids': [parent.pid],
                        'errors': ['请从独立 PowerShell 或系统终端运行停止脚本，不能从课程自身的内核或终端关闭它。']}
        except (OSError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    candidates = {}
    records = {}
    errors = []
    for kind in ('streamlit', 'jupyter'):
        path = root / '.runtime' / f'{kind}-service.json'
        try:
            info = json.loads(path.read_text(encoding='utf-8'))
            records[kind] = (path, info)
            process = psutil.Process(int(info['pid']))
            if process.pid not in protected and _owned_kind(process, root) == kind:
                candidates[process.pid] = (process, kind, info)
        except (OSError, ValueError, TypeError, KeyError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # 进程记录丢失或 PID 已失效时，仍按真实根目录、应用文件和内核工作目录识别。
    for process in psutil.process_iter(['pid', 'name']):
        if process.pid in protected or process.pid in candidates:
            continue
        name = (process.info['name'] or '').lower()
        if not (name.startswith('python') or name.startswith('jupyter') or name.startswith('streamlit')):
            continue
        try:
            kind = _owned_kind(process, root)
            if kind:
                candidates[process.pid] = (process, kind, None)
        except (OSError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    targets = {}
    trees = {}
    for process, kind, info in candidates.values():
        try:
            tree = [process, *process.children(recursive=True)]
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            errors.append(f'无法读取进程 {process.pid} 的子进程。')
            continue
        tree = [p for p in tree if p.pid not in protected]
        trees[process.pid] = tree
        targets.update({p.pid: p for p in tree})

    graceful = set()
    for process, kind, info in candidates.values():
        if kind == 'jupyter' and info and process.pid in trees and _shutdown_jupyter(info):
            graceful.update(p.pid for p in trees[process.pid])

    def signal(process, *, force=False):
        try:
            if process.is_running():
                process.kill() if force else process.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            errors.append(f'没有权限关闭进程 {process.pid}。')

    for process in reversed(list(targets.values())):
        if process.pid not in graceful:
            signal(process)
    _, alive = psutil.wait_procs(list(targets.values()), timeout=5)
    for process in alive:
        signal(process)
    _, alive = psutil.wait_procs(alive, timeout=3)
    for process in alive:
        signal(process, force=True)
    _, alive = psutil.wait_procs(alive, timeout=3)
    remaining = [p.pid for p in alive if p.is_running()]
    if not remaining and not errors:
        for path, info in records.values():
            try:
                if json.loads(path.read_text(encoding='utf-8')) == info:
                    path.unlink()
            except (OSError, ValueError):
                pass
    return {'stopped': not remaining and not errors,
            'services': sorted({kind for _, kind, _ in candidates.values()}),
            'process_count': len(targets), 'remaining_pids': remaining, 'errors': errors}


def main():
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if Path(sys.prefix).resolve() != environment.resolve() and python.is_file():
        child_environment = os.environ.copy()
        for name in ('PYTHONHOME', 'PYTHONPATH'):
            child_environment.pop(name, None)
        return subprocess.call([str(python), str(Path(__file__).resolve())], env=child_environment)
    try:
        result = stop_workshop()
    except Exception as error:
        print('停止失败：' + str(error), file=sys.stderr, flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if result['stopped']:
        print('课程后台进程已停止。' if result['process_count'] else '课程后台进程已经停止，无需重复操作。', flush=True)
        print('删除目录前，请退出该目录，并关闭仍在该目录中的其他终端窗口。', flush=True)
        return 0
    print('仍有进程未关闭，请查看上方信息。', file=sys.stderr, flush=True)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
