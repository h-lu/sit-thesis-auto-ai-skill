#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文转换自动流水线。

本脚本不调用 AI，只串联抽取、校验、生成、编译和日志检查，
并输出机器可读报告与 AI 版面修复交接文件。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_TEMPLATE = SKILL_DIR / "assets" / "sit-latex-thesis-template"


@dataclass
class StageResult:
    name: str
    command: list[str]
    returncode: int
    duration_sec: float
    stdout_path: str
    stderr_path: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def has_standard_schema(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    return "schema:" in text and "sit-thesis-md/v2" in text


def detect_input_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return "word"
    if suffix in {".md", ".markdown"}:
        return "standard-md" if has_standard_schema(path) else "legacy-md"
    raise SystemExit(f"无法自动判断输入类型：{path}。请指定 --input-type。")


def copy_common_assets(source_doc: Path, standard_md: Path) -> None:
    src_fig = source_doc.parent / "figures"
    dst_fig = standard_md.parent / "figures"
    if src_fig.exists() and src_fig.is_dir() and src_fig.resolve() != dst_fig.resolve():
        dst_fig.mkdir(parents=True, exist_ok=True)
        for item in src_fig.iterdir():
            if item.is_file():
                shutil.copy2(item, dst_fig / item.name)


def run_stage(name: str, cmd: list[str], logs_dir: Path, cwd: Path | None = None) -> StageResult:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{name}.stdout.txt"
    stderr_path = logs_dir / f"{name}.stderr.txt"
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    duration = time.monotonic() - start
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    return StageResult(
        name=name,
        command=[str(x) for x in cmd],
        returncode=proc.returncode,
        duration_sec=round(duration, 3),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def scan_latex_log(log_path: Path) -> dict[str, Any]:
    if not log_path.exists():
        return {"exists": False}
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    patterns = {
        "errors": r"^! (?:LaTeX|Package|Class|pdfTeX|XeTeX|Emergency stop|Fatal error).*",
        "overfull_hbox": r"Overfull \\hbox .*",
        "underfull_hbox": r"Underfull \\hbox .*",
        "missing_chars": r"Missing character: .*",
        "undefined_refs": r"(?:Reference|Citation) .* undefined|There were undefined references|Label\\(s\\) may have changed",
    }
    result: dict[str, Any] = {"exists": True, "file": str(log_path)}
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text, flags=re.M)
        result[key] = {"count": len(matches), "samples": matches[:20]}
    # longtable/booktabs 的规则线或表头经常触发 detected-at-line 告警。
    # 正文段落 overfull 更可能是可见问题，优先交给 AI 检查。
    paragraph_overfull = [m for m in re.findall(patterns["overfull_hbox"], text, flags=re.M) if " in paragraph " in m]
    table_like_overfull = [m for m in re.findall(patterns["overfull_hbox"], text, flags=re.M) if " detected at line " in m]
    result["paragraph_overfull_hbox"] = {"count": len(paragraph_overfull), "samples": paragraph_overfull[:20]}
    result["table_like_overfull_hbox"] = {"count": len(table_like_overfull), "samples": table_like_overfull[:20]}
    return result


def inspect_pdf(pdf_path: Path, logs_dir: Path) -> dict[str, Any]:
    if not pdf_path.exists():
        return {"exists": False}
    result: dict[str, Any] = {"exists": True, "file": str(pdf_path)}
    if shutil.which("pdfinfo"):
        stage = run_stage("pdfinfo", ["pdfinfo", str(pdf_path)], logs_dir)
        result["pdfinfo_returncode"] = stage.returncode
        info_text = Path(stage.stdout_path).read_text(encoding="utf-8", errors="ignore")
        pages = re.search(r"^Pages:\s+(\d+)", info_text, flags=re.M)
        page_size = re.search(r"^Page size:\s+(.+)$", info_text, flags=re.M)
        if pages:
            result["pages"] = int(pages.group(1))
        if page_size:
            result["page_size"] = page_size.group(1).strip()
    else:
        result["pdfinfo"] = "not found"

    if shutil.which("pdffonts"):
        stage = run_stage("pdffonts", ["pdffonts", str(pdf_path)], logs_dir)
        result["pdffonts_returncode"] = stage.returncode
        fonts_text = Path(stage.stdout_path).read_text(encoding="utf-8", errors="ignore")
        fonts: list[dict[str, str]] = []
        for line in fonts_text.splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 7:
                fonts.append({"name": parts[0], "type": parts[1], "emb": parts[-2], "uni": parts[-1]})
        result["fonts"] = fonts
        result["font_problems"] = [
            f for f in fonts
            if f.get("emb") == "no" or f.get("uni") == "no"
        ]
    else:
        result["pdffonts"] = "not found"
    return result


def summarize_issues(report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for stage in report.get("stages", []):
        if stage.get("returncode") != 0:
            issues.append(f"stage_failed:{stage.get('name')}")
    validation = report.get("validation") or {}
    for error in validation.get("errors", []):
        issues.append(f"validation_error:{error}")
    for warning in validation.get("warnings", []):
        issues.append(f"validation_warning:{warning}")
    conversion = report.get("conversion") or {}
    for warning in conversion.get("warnings", []):
        # “表格可能较宽，已启用自动换行列”是转换器已经采取的自动排版措施，
        # 保留在 conversion.warnings 中供审计，但不再作为需要 AI 处理的问题。
        if "已启用自动换行列" in warning:
            continue
        issues.append(f"conversion_warning:{warning}")
    log = report.get("latex_log") or {}
    for key in ["errors", "missing_chars", "undefined_refs"]:
        count = (log.get(key) or {}).get("count", 0)
        if count:
            issues.append(f"latex_{key}:{count}")
    paragraph_overfull = (log.get("paragraph_overfull_hbox") or {}).get("count", 0)
    table_like_overfull = (log.get("table_like_overfull_hbox") or {}).get("count", 0)
    if paragraph_overfull:
        issues.append(f"latex_paragraph_overfull_hbox:{paragraph_overfull}")
    if table_like_overfull:
        issues.append(f"latex_table_like_overfull_hbox:{table_like_overfull}")
    pdf = report.get("pdf") or {}
    if pdf.get("font_problems"):
        issues.append(f"pdf_font_problems:{len(pdf['font_problems'])}")
    if report.get("pdf", {}).get("exists") is False:
        issues.append("pdf_missing")
    return issues


def write_ai_review(report: dict[str, Any], path: Path) -> None:
    """写出给 AI 的版面修复交接文件。"""
    issues = report.get("issues", [])
    log = report.get("latex_log") or {}
    conversion = report.get("conversion") or {}
    validation = report.get("validation") or {}

    lines: list[str] = [
        "# AI 版面检查交接",
        "",
        "本文件由自动流水线生成，只用于版面和调试修复。",
        "不要改写论文正文、参考文献、结论或其他内容。",
        "",
        "## 文件",
        "",
        f"- 标准 Markdown：`{report.get('standard_md')}`",
        f"- LaTeX 工程：`{report.get('output')}`",
        f"- PDF: `{(report.get('pdf') or {}).get('file')}`",
        f"- LaTeX 日志：`{(report.get('latex_log') or {}).get('file')}`",
        "",
        "## 问题",
        "",
    ]
    if issues:
        lines.extend(f"- `{issue}`" for issue in issues)
    else:
        lines.append("- 未发现问题。")

    lines.extend(["", "## 建议的 AI 动作", ""])
    if (log.get("missing_chars") or {}).get("count", 0):
        lines.append("- 缺字：在模板或转换器中增加确定性的字体/宏映射。除非用户要求，不要手工替换正文。")
    if (log.get("paragraph_overfull_hbox") or {}).get("count", 0):
        lines.append("- 正文 overfull：检查对应 `main.tex` 行，增加安全断点或模板级断行规则，然后重新编译并跑流水线。")
    if (log.get("table_like_overfull_hbox") or {}).get("count", 0):
        lines.append("- 表格类 overfull：检查 longtable 表题宽度、列宽和规则线；若报告中出现，AI 必须修复并重新跑流水线。")
    if validation.get("warnings"):
        lines.append("- Markdown 校验警告：优先修抽取/规范化脚本，不优先改生成后的 LaTeX。")
    if conversion.get("warnings"):
        lines.append("- 转换警告：判断是否只是提示。宽表已自动换行时，相关警告通常可接受。")
    if not any([
        (log.get("missing_chars") or {}).get("count", 0),
        (log.get("paragraph_overfull_hbox") or {}).get("count", 0),
        (log.get("table_like_overfull_hbox") or {}).get("count", 0),
        validation.get("warnings"),
        conversion.get("warnings"),
    ]):
        lines.append("- 不需要 AI 处理。")

    def add_samples(title: str, key: str) -> None:
        samples = (log.get(key) or {}).get("samples", [])
        if samples:
            lines.extend(["", f"## {title}", ""])
            lines.extend(f"- `{sample}`" for sample in samples[:20])

    add_samples("缺字样本", "missing_chars")
    add_samples("正文 Overfull 样本", "paragraph_overfull_hbox")
    add_samples("表格类 Overfull 样本", "table_like_overfull_hbox")

    refs = report.get("references_gb7714_2005") or {}
    if refs:
        lines.extend(["", "## 参考文献 GB/T 7714-2005 校验", ""])
        lines.append(f"- 识别条目：{refs.get('normalized_count', 0)}")
        lines.append(f"- 自动格式清理：{refs.get('changed_count', 0)} 条")
        if refs.get("errors"):
            lines.append("- 错误：")
            lines.extend(f"  - {e}" for e in refs["errors"][:50])
        if refs.get("warnings"):
            lines.append("- 警告：")
            lines.extend(f"  - {w}" for w in refs["warnings"][:50])
        if not refs.get("errors") and not refs.get("warnings"):
            lines.append("- 未发现明显格式问题。")

    if conversion.get("warnings"):
        lines.extend(["", "## 转换警告", ""])
        lines.extend(f"- {warning}" for warning in conversion["warnings"])
    if validation.get("warnings"):
        lines.extend(["", "## 校验警告", ""])
        lines.extend(f"- {warning}" for warning in validation["warnings"])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 DOCX/Markdown -> 标准 Markdown -> LaTeX/PDF 自动流水线")
    parser.add_argument("input", type=Path)
    parser.add_argument("--input-type", choices=["auto", "word", "legacy-md", "standard-md"], default="auto")
    parser.add_argument("--output", type=Path, required=True, help="输出 LaTeX 工程目录")
    parser.add_argument("--standard-md", type=Path, default=None)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--compile", action="store_true", help="运行 latexmk/xelatex 编译 PDF")
    parser.add_argument("--strict", action="store_true", help="Markdown warning 也作为失败")
    parser.add_argument("--no-patch-page-parity", action="store_true")
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_dir = args.output.resolve()
    standard_md = (args.standard_md or (output_dir.parent / f"{input_path.stem}.standard.md")).resolve()
    logs_dir = output_dir.parent / f"{output_dir.name}-logs"
    input_type = detect_input_type(input_path) if args.input_type == "auto" else args.input_type

    if not input_path.exists():
        raise SystemExit(f"输入文件不存在：{input_path}")
    if not args.template.exists():
        raise SystemExit(f"模板不存在：{args.template}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    standard_md.parent.mkdir(parents=True, exist_ok=True)
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "input": str(input_path),
        "input_type": input_type,
        "standard_md": str(standard_md),
        "output": str(output_dir),
        "template": str(args.template.resolve()),
        "stages": [],
    }

    if input_type == "word":
        stage = run_stage(
            "word_to_standard_md",
            [sys.executable, str(SCRIPT_DIR / "word_to_standard_md.py"), str(input_path), "-o", str(standard_md), "--assets", str(standard_md.parent / "figures")],
            logs_dir,
        )
        report["stages"].append(stage.__dict__)
    elif input_type == "legacy-md":
        copy_common_assets(input_path, standard_md)
        stage = run_stage(
            "normalize_legacy_md",
            [sys.executable, str(SCRIPT_DIR / "normalize_legacy_md.py"), str(input_path), "-o", str(standard_md)],
            logs_dir,
        )
        report["stages"].append(stage.__dict__)
    else:
        copy_common_assets(input_path, standard_md)
        if input_path != standard_md:
            standard_md.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")
        report["stages"].append(StageResult("copy_standard_md", [], 0, 0.0, "", "").__dict__)

    if report["stages"][-1]["returncode"] == 0:
        gb_report_path = output_dir.parent / f"{output_dir.name}.gb7714-2005-report.json"
        stage = run_stage(
            "gb7714_2005_refs",
            [sys.executable, str(SCRIPT_DIR / "gb7714_2005_refs.py"), str(standard_md), "--report", str(gb_report_path)],
            logs_dir,
        )
        report["stages"].append(stage.__dict__)
        report["references_gb7714_2005"] = load_json(gb_report_path)

    if report["stages"][-1]["returncode"] == 0:
        validate_cmd = [sys.executable, str(SCRIPT_DIR / "validate_standard_md.py"), str(standard_md), "--json"]
        if args.strict:
            validate_cmd.append("--strict")
        stage = run_stage("validate_standard_md", validate_cmd, logs_dir)
        report["stages"].append(stage.__dict__)
        validation = json.loads(Path(stage.stdout_path).read_text(encoding="utf-8") or "{}") if stage.stdout_path else None
        report["validation"] = validation
        if stage.returncode == 0:
            (output_dir.parent / f"{output_dir.name}.standard-md-validation.json").write_text(
                json.dumps(validation, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    if all(stage.get("returncode") == 0 for stage in report["stages"]):
        md2tex_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "md_to_latex.py"),
            str(standard_md),
            "--template",
            str(args.template),
            "--output",
            str(output_dir),
        ]
        if args.compile:
            md2tex_cmd.append("--compile")
        if args.no_patch_page_parity:
            md2tex_cmd.append("--no-patch-page-parity")
        stage = run_stage("md_to_latex", md2tex_cmd, logs_dir)
        report["stages"].append(stage.__dict__)

    conversion_report = output_dir / "conversion-report.json"
    report["conversion"] = load_json(conversion_report)
    report["latex_log"] = scan_latex_log(output_dir / "main.log")
    report["pdf"] = inspect_pdf(output_dir / "main.pdf", logs_dir)
    report["issues"] = summarize_issues(report)
    report["ok"] = not any(issue.startswith(("stage_failed", "validation_error", "latex_errors", "latex_missing_chars", "latex_undefined_refs", "pdf_missing")) for issue in report["issues"])

    report_path = output_dir.parent / f"{output_dir.name}-pipeline-report.json"
    ai_review_path = output_dir.parent / f"{output_dir.name}-ai-review.md"
    write_ai_review(report, ai_review_path)
    report["ai_review"] = str(ai_review_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": report["ok"],
        "issues": report["issues"],
        "report": str(report_path),
        "ai_review": str(ai_review_path),
        "standard_md": str(standard_md),
        "output": str(output_dir),
        "pdf": str(output_dir / "main.pdf") if (output_dir / "main.pdf").exists() else None,
    }, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
