"""组织者在真实 Jupyter 内核中执行课程，保存逐格输出。"""
import argparse
import copy
from datetime import datetime
import json
import os
import re
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from course.services import kernel_environment


def prepare_validation_notebook(notebook, with_model=False):
    """验证副本只有显式 --with-model 才能启用聊天调用。"""
    notebook = copy.deepcopy(notebook)
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        cell.outputs = []
        cell.execution_count = None
        if "model-run" in cell.metadata.get("tags", []):
            cell.source, changed = re.subn(
                r"(?m)^RUN_CHAT_MODEL\s*=\s*(?:True|False)\b",
                f"RUN_CHAT_MODEL = {with_model}", cell.source, count=1,
            )
            if changed != 1:
                raise ValueError("没有找到模型格的显式开关，停止自动验证。")
    return notebook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-model", action="store_true", help="明确启用模型验证，会使用所选聊天后端额度")
    args = parser.parse_args()
    environment = kernel_environment()
    for name in ("JUPYTER_PATH", "IPYTHONDIR"):
        os.environ[name] = environment[name]
    notebook = prepare_validation_notebook(
        nbformat.read(ROOT / "Workshop.ipynb", as_version=4), args.with_model,
    )
    name = "Workshop-model-validation" if args.with_model else "Workshop-executed"
    target = ROOT / "reports" / f"{name}.ipynb"
    target.parent.mkdir(parents=True, exist_ok=True)
    client = NotebookClient(notebook, timeout=240, kernel_name="seekdb-workshop",
                            resources={"metadata": {"path": str(ROOT)}}, record_timing=True)
    started = time.monotonic()
    passed = False
    try:
        client.execute()
        passed = True
    finally:
        nbformat.write(notebook, target)
        summary = {
            "checked_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "passed": passed, "model_enabled": args.with_model,
            "seconds": round(time.monotonic() - started, 2),
            "executed_cells": sum(cell.get("execution_count") is not None for cell in notebook.cells),
            "notebook": str(target.relative_to(ROOT)),
            "errors": [{"cell": index, "type": output.get("ename"), "message": output.get("evalue")}
                       for index, cell in enumerate(notebook.cells) for output in cell.get("outputs", [])
                       if output.output_type == "error"],
        }
        (ROOT / "reports" / f"{name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
