#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 LaTeX 前校验 SIT-Thesis-MD v2 文件。

校验器只报告可能的问题，不改写内容。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover
    raise SystemExit("需要 PyYAML：pip install pyyaml") from exc


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            raw = text[4:end].strip()
            rest = text[text.find("\n", end + 4) + 1 :]
            return yaml.safe_load(raw) or {}, rest
    return {}, text


def scan_blocks(body: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    figures: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    equations: list[dict[str, Any]] = []
    for m in re.finditer(r"::: +(figure|table|equation)\n(.*?)\n:::", body, flags=re.S):
        kind, raw = m.group(1), m.group(2)
        attrs: dict[str, str] = {}
        rows = 0
        cols = 0
        for line in raw.splitlines():
            if ":" in line and not line.lstrip().startswith("|"):
                k, v = line.split(":", 1)
                attrs[k.strip()] = v.strip()
            elif line.lstrip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells and not all(set(c) <= {"-", ":"} for c in cells):
                    rows += 1
                    cols = max(cols, len(cells))
        item = {"attrs": attrs, "rows": rows, "cols": cols, "start": m.start()}
        if kind == "figure":
            figures.append(item)
        elif kind == "table":
            tables.append(item)
        else:
            equations.append(item)
    return figures, tables, equations


def validate(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    figures, tables, equations = scan_blocks(body)
    errors: list[str] = []
    warnings: list[str] = []

    if not meta:
        errors.append("缺少 YAML frontmatter。")
    if str(meta.get("schema", "")).strip() != "sit-thesis-md/v2":
        warnings.append("schema 不是 sit-thesis-md/v2。")
    for key in ["title", "college", "major", "student_name", "supervisor"]:
        if not str(meta.get(key, "")).strip():
            warnings.append(f"frontmatter 缺少或为空：{key}")

    abs_meta = meta.get("abstract") or {}
    kw_meta = meta.get("keywords") or {}
    if not str(abs_meta.get("cn", "")).strip():
        warnings.append("中文摘要为空。")
    if not str(abs_meta.get("en", "")).strip():
        warnings.append("英文摘要为空。")
    if not kw_meta.get("cn"):
        warnings.append("中文关键词为空。")
    if not kw_meta.get("en"):
        warnings.append("英文关键词为空。")

    if re.search(r"^#+\s*(目\s*录|目录)\b", body, flags=re.M):
        warnings.append("正文中出现目录标题；标准 Markdown 不应保留 Word 目录，目录应由 LaTeX 模板生成。")
    if re.search(r"^\s*(续表|表\s*\d+(?:\.\d+)*\s*[（(]续[）)])", body, flags=re.M):
        warnings.append("检测到续表/表(续)文本；标准 Markdown 中应合并为一个 ::: table 逻辑块。")

    labels: dict[str, int] = {}
    for collection_name, collection in [("figure", figures), ("table", tables), ("equation", equations)]:
        for idx, item in enumerate(collection, start=1):
            attrs = item["attrs"]
            label = attrs.get("label", "")
            if label:
                labels[label] = labels.get(label, 0) + 1
            if collection_name in {"figure", "table"} and not attrs.get("caption"):
                warnings.append(f"第 {idx} 个 {collection_name} 缺少 caption。")
            if collection_name == "figure":
                src = attrs.get("src", "")
                if not src:
                    warnings.append(f"第 {idx} 个 figure 缺少 src。")
                elif not (md_path.parent / src).exists():
                    # The template may provide example figures, so this is warning not error.
                    warnings.append(f"图片文件不存在或不在 Markdown 同级资源目录中：{src}")
            if collection_name == "table":
                if item["cols"] >= 5 and attrs.get("fit", "") != "wrap":
                    warnings.append(f"第 {idx} 个表格列数为 {item['cols']}，建议设置 fit: wrap。")
                if item["rows"] > 8 and attrs.get("type", "") != "longtable":
                    warnings.append(f"第 {idx} 个表格行数为 {item['rows']}，建议设置 type: longtable。")
                if item["cols"] > 0 and attrs.get("widths"):
                    widths = [x for x in re.split(r"[,，;；\s]+", attrs["widths"].strip()) if x]
                    if len(widths) != item["cols"]:
                        warnings.append(f"第 {idx} 个表格 widths 数量 {len(widths)} 与列数 {item['cols']} 不一致。")

    duplicated = [k for k, n in labels.items() if n > 1]
    if duplicated:
        errors.append("label 重复：" + ", ".join(sorted(duplicated)))

    return {
        "file": str(md_path),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {"figures": len(figures), "tables": len(tables), "equations": len(equations)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate SIT-Thesis-MD v2")
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--strict", action="store_true", help="有 warning 也返回非零退出码")
    args = parser.parse_args()

    report = validate(args.markdown)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"SIT-Thesis-MD 校验：{args.markdown}")
        print(f"统计：图片 {report['counts']['figures']}，表格 {report['counts']['tables']}，公式 {report['counts']['equations']}")
        for e in report["errors"]:
            print(f"ERROR: {e}", file=sys.stderr)
        for w in report["warnings"]:
            print(f"WARN: {w}", file=sys.stderr)
        print("OK" if report["ok"] else "FAILED")
    if report["errors"] or (args.strict and report["warnings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
