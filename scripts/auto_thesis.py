#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简论文转换入口。

本脚本只负责调用确定性的转换后端，并把输出文件整理成固定名称。
若输出报告仍有 issues，skill 使用者必须继续由 AI 做最小排版修复并重跑本脚本。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
SKILL_DIR = THIS_DIR.parent
ENGINE = THIS_DIR / "run_thesis_pipeline.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="论文自动转换：Word/Markdown -> LaTeX/PDF")
    parser.add_argument("input", type=Path, help="输入 .docx 或 .md")
    parser.add_argument("--output", type=Path, required=True, help="输出 LaTeX 工程目录")
    parser.add_argument("--compile", action="store_true", help="编译 PDF")
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_dir = args.output.resolve()
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在：{input_path}")
    if not ENGINE.exists():
        raise SystemExit(f"转换后端不存在：{ENGINE}")

    standard_md = output_dir.parent / f"{input_path.stem}.standard.md"
    cmd = [
        sys.executable,
        str(ENGINE),
        str(input_path),
        "--output",
        str(output_dir),
        "--standard-md",
        str(standard_md),
    ]
    if args.compile:
        cmd.append("--compile")

    proc = run(cmd)
    stdout_path = output_dir.parent / f"{output_dir.name}.auto.stdout.txt"
    stderr_path = output_dir.parent / f"{output_dir.name}.auto.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")

    try:
        summary = json.loads(proc.stdout)
    except json.JSONDecodeError:
        summary = {"ok": False, "raw_stdout": str(stdout_path), "raw_stderr": str(stderr_path)}

    # 固定输出名称，方便 AI 和用户找文件。
    report_src = Path(summary["report"]) if summary.get("report") else None
    review_src = Path(summary["ai_review"]) if summary.get("ai_review") else None
    pdf_src = Path(summary["pdf"]) if summary.get("pdf") else None

    if report_src and report_src.exists():
        shutil.copy2(report_src, output_dir.parent / "pipeline-report.json")
    if review_src and review_src.exists():
        shutil.copy2(review_src, output_dir.parent / "ai-review.md")
    if pdf_src and pdf_src.exists():
        shutil.copy2(pdf_src, output_dir.parent / "main.pdf")

    issues = summary.get("issues", [])
    backend_ok = proc.returncode == 0 and bool(summary.get("ok", False))
    print(json.dumps({
        "ok": backend_ok and not issues,
        "needs_ai_fix": backend_ok and bool(issues),
        "output": str(output_dir),
        "pdf": str(output_dir.parent / "main.pdf") if (output_dir.parent / "main.pdf").exists() else None,
        "report": str(output_dir.parent / "pipeline-report.json") if (output_dir.parent / "pipeline-report.json").exists() else None,
        "ai_review": str(output_dir.parent / "ai-review.md") if (output_dir.parent / "ai-review.md").exists() else None,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "issues": issues,
    }, ensure_ascii=False, indent=2))

    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
