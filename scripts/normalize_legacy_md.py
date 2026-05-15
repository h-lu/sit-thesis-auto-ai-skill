#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
旧抽取 Markdown -> SIT-Thesis-MD v2。

重点修正：
- Word/PDF 因分页拆开的“续表”不会延续到标准 Markdown；脚本会合并成一个逻辑表。
- 表格只保留 caption/header/rows 语义；分页、续页由 LaTeX longtable 自动处理。
- 对较宽/较长表格写入 type/widths 提示，后续 md_to_latex.py 会自动换行。
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


@dataclass
class TableBlock:
    caption: str
    number: str
    header: List[str]
    rows: List[List[str]]
    label: str = ""
    attrs: Dict[str, str] = field(default_factory=dict)


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            raw = text[4:end].strip()
            rest = text[text.find("\n", end + 4) + 1 :]
            return yaml.safe_load(raw) or {}, rest
    return {}, text


def find_section(lines: List[str], heading_regex: str, start: int = 0) -> Tuple[int, int]:
    pat = re.compile(heading_regex, flags=re.I)
    s = -1
    level = 1
    for i in range(start, len(lines)):
        if pat.match(lines[i].strip()):
            s = i
            m = re.match(r"^(#+)", lines[i].strip())
            level = len(m.group(1)) if m else 1
            break
    if s < 0:
        return -1, -1
    e = len(lines)
    for j in range(s + 1, len(lines)):
        m = re.match(r"^(#+)\s+", lines[j].strip())
        if m and len(m.group(1)) <= level:
            e = j
            break
    return s, e


def first_match(lines: List[str], pattern: str) -> str:
    pat = re.compile(pattern)
    for line in lines:
        m = pat.search(line)
        if m:
            return m.group(1).strip()
    return ""


def clean_para(lines: List[str]) -> str:
    text = "\n".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    return text


def parse_keywords(line: str) -> List[str]:
    value = re.sub(r"^(关键词|Keywords|KeyWords)\s*[:：]\s*", "", line.strip(), flags=re.I)
    parts = re.split(r"[;；]", value)
    return [p.strip().rstrip("。.;；") for p in parts if p.strip().rstrip("。.;；")]


def strip_caption_prefix(text: str, prefix: str = "表") -> Tuple[str, str, bool]:
    m = re.match(rf"^\s*(续表|{prefix})\s*(\d+(?:\.\d+)*)\s*(?:\(续\)|（续）)?\s*[:：]?\s*(.*)$", text.strip())
    if m:
        return m.group(3).strip(), m.group(2), (m.group(1) == "续表" or "续" in text[:12])
    return text.strip(), "", False


def canonical_caption(caption: str) -> str:
    return re.sub(r"\s+", "", caption.replace("（续）", "").replace("(续)", "").strip())


def table_signature(header: List[str]) -> str:
    return "|".join(re.sub(r"\s+", "", h.strip()) for h in header)


def is_table_separator(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells)


def parse_markdown_table(lines: List[str]) -> Tuple[List[str], List[List[str]]]:
    clean = [l.strip() for l in lines if l.strip()]
    if len(clean) < 2:
        return [], []
    header = [c.strip() for c in clean[0].strip("|").split("|")]
    rows: List[List[str]] = []
    for line in clean[2:]:
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return header, rows


def normalize_row(row: List[str], n: int) -> List[str]:
    if len(row) < n:
        return row + [""] * (n - len(row))
    if len(row) > n:
        return row[: n - 1] + [" ".join(row[n - 1 :])]
    return row


def infer_table_attrs(table: TableBlock) -> Dict[str, str]:
    n = max(1, len(table.header))
    rows = len(table.rows)
    total_chars = sum(len(c) for c in table.header) + sum(len(c) for row in table.rows for c in row)
    max_cell = max([len(c) for c in table.header] + [len(c) for row in table.rows for c in row] + [0])
    attrs: Dict[str, str] = {}
    if rows > 8 or total_chars > 900 or (n >= 6 and rows > 5) or max_cell > 90:
        attrs["type"] = "longtable"
    attrs["fit"] = "wrap"
    # 常见论文表的保守列宽建议；可手动改。
    caption_key = canonical_caption(table.caption)
    if n == 4 and ("API" in table.caption or "接口" in table.caption):
        attrs["widths"] = "0.36, 0.13, 0.13, 0.36"
    elif n == 4 and ("数据表" in table.caption or "字段" in table.caption):
        attrs["widths"] = "0.12, 0.34, 0.28, 0.26"
    elif n == 7 and "功能测试" in table.caption:
        attrs["widths"] = "0.07, 0.11, 0.17, 0.20, 0.22, 0.13, 0.07"
    elif n == 8 and "性能" in table.caption:
        attrs["widths"] = "0.07, 0.15, 0.08, 0.09, 0.12, 0.10, 0.08, 0.25"
    elif n == 6:
        attrs["widths"] = "0.20, 0.15, 0.23, 0.12, 0.18, 0.12"
    elif n == 3:
        attrs["widths"] = "0.22, 0.18, 0.56"
    return attrs


def transform_body(lines: List[str]) -> List[str]:
    """把图片/表格规整为语义块；先保留表格块，最后合并续表。"""
    out: List[Any] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        img = re.match(r"^!\[(.*?)\]\((.*?)\)(?:\{(.*?)\})?\s*$", stripped)
        if img:
            alt, src, attrs = img.group(1), img.group(2), img.group(3) or ""
            width = "0.85\\textwidth"
            w = re.search(r"width\s*=\s*([^\s}]+)", attrs)
            if w:
                width = w.group(1)
            caption, number, _ = strip_caption_prefix(alt, "图")
            label = f"fig:{number.replace('.', '-')}" if number else ""
            block = ["::: figure", f"src: {src}", f"caption: {caption}"]
            if label:
                block.append(f"label: {label}")
            block.append(f"width: {width}")
            block.append(":::")
            out.extend(block + [""])
            i += 1
            continue

        cap = re.match(r"^\*\*\s*((?:续表|表)\s*\d+(?:\.\d+)*.*)\s*\*\*\s*$", stripped)
        if cap:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("|"):
                table_lines: List[str] = []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    table_lines.append(lines[j].rstrip())
                    j += 1
                caption, number, is_cont = strip_caption_prefix(cap.group(1), "表")
                header, rows = parse_markdown_table(table_lines)
                table = TableBlock(caption=caption, number=number, label=f"tab:{number.replace('.', '-')}" if number else "", header=header, rows=[normalize_row(r, len(header)) for r in rows])
                table.attrs = infer_table_attrs(table)
                if is_cont:
                    table.attrs["continuation"] = "true"
                out.append(table)
                out.append("")
                i = j
                continue

        # 未带表题的裸表：可能是 Word 续表或正文内临时表。
        if stripped.startswith("|") and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            j = i
            table_lines = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                table_lines.append(lines[j].rstrip())
                j += 1
            header, rows = parse_markdown_table(table_lines)
            table = TableBlock(caption="未命名表格", number="", header=header, rows=[normalize_row(r, len(header)) for r in rows])
            table.attrs = infer_table_attrs(table)
            out.append(table)
            out.append("")
            i = j
            continue

        if stripped.startswith("转换备注") or stripped.startswith("---"):
            break
        out.append(line.rstrip())
        i += 1

    merged = merge_continuation_tables(out)
    return serialize_mixed(merged)


def merge_continuation_tables(items: List[Any]) -> List[Any]:
    merged: List[Any] = []
    last_table_idx: int | None = None
    for item in items:
        if not isinstance(item, TableBlock):
            merged.append(item)
            if isinstance(item, str) and item.strip() and not item.strip().startswith("<!--"):
                # 空行允许续表紧随；普通文字后不跨段合并。
                last_table_idx = None
            continue
        table = item
        cont = table.attrs.get("continuation") == "true"
        merged_into = False
        if last_table_idx is not None and 0 <= last_table_idx < len(merged) and isinstance(merged[last_table_idx], TableBlock):
            prev: TableBlock = merged[last_table_idx]
            same_number = table.number and prev.number and table.number == prev.number
            same_caption = canonical_caption(table.caption) and canonical_caption(table.caption) == canonical_caption(prev.caption)
            same_header = table_signature(table.header) == table_signature(prev.header)
            # 明确续表按编号合并；无编号时，只有表头完全相同且紧邻才合并。
            if (cont and (same_number or same_header)) or (same_caption and same_header):
                rows_to_add = table.rows[:]
                if rows_to_add and table_signature(rows_to_add[0]) == table_signature(prev.header):
                    rows_to_add = rows_to_add[1:]
                prev.rows.extend(rows_to_add)
                prev.attrs.update(infer_table_attrs(prev))
                prev.attrs["type"] = "longtable"
                merged_into = True
        if not merged_into:
            merged.append(table)
            last_table_idx = len(merged) - 1
    return merged


def serialize_mixed(items: List[Any]) -> List[str]:
    out: List[str] = []
    for item in items:
        if isinstance(item, TableBlock):
            attrs = infer_table_attrs(item)
            attrs.update({k: v for k, v in item.attrs.items() if k != "continuation"})
            out.extend(["::: table", f"caption: {item.caption}"])
            if item.label:
                out.append(f"label: {item.label}")
            for k in ["type", "fit", "widths", "align", "font_size"]:
                if k in attrs and attrs[k]:
                    out.append(f"{k}: {attrs[k]}")
            out.append("| " + " | ".join(item.header) + " |")
            out.append("| " + " | ".join(["---"] * max(1, len(item.header))) + " |")
            for row in item.rows:
                out.append("| " + " | ".join(row) + " |")
            out.append(":::")
            out.append("")
        else:
            out.append(str(item))
    return out


def normalize(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    lines = body.splitlines()

    logo = meta.get("logo", "")
    for line in lines[:20]:
        m = re.match(r"^!\[.*?\]\((.*?)\)", line.strip())
        if m:
            logo = m.group(1)
            break

    dec_start, dec_end = find_section(lines, r"^##\s*独创性声明")
    declaration_author = ""
    declaration_date = ""
    if dec_start >= 0:
        dec_lines = lines[dec_start + 1 : dec_end]
        declaration_author = first_match(dec_lines, r"作者签名\s*[:：]\s*(.*)")
        declaration_date = first_match(dec_lines, r"日期\s*[:：]\s*(.*)") or first_match(dec_lines, r"日\s*期\s*[:：]\s*(.*)")

    cn_abs = ""
    cn_keywords: List[str] = []
    cn_start, cn_end = find_section(lines, r"^##\s*中文摘要")
    if cn_start >= 0:
        cn_content = lines[cn_start + 1 : cn_end]
        abs_lines: List[str] = []
        for line in cn_content:
            if re.match(r"^关键词\s*[:：]", line.strip()):
                cn_keywords = parse_keywords(line)
            elif line.strip():
                abs_lines.append(line)
        cn_abs = clean_para(abs_lines)

    en_title = meta.get("english_title", "")
    en_abs = ""
    en_keywords: List[str] = []
    en_start, en_end = find_section(lines, r"^##\s*English\s+Abstract")
    if en_start >= 0:
        en_content = lines[en_start + 1 : en_end]
        abs_lines = []
        for line in en_content:
            if line.startswith("###") and not en_title:
                en_title = re.sub(r"^#+\s*", "", line).strip()
            elif re.match(r"^Key\s*Words|^Keywords", line.strip(), flags=re.I):
                en_keywords = parse_keywords(line)
            elif line.strip() and not line.startswith("###"):
                abs_lines.append(line)
        en_abs = clean_para(abs_lines)

    body_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^#\s*1\s+", line.strip()):
            body_start = i
            break
    if body_start < 0:
        body_start = 0

    standard_body = transform_body(lines[body_start:])

    new_meta = {
        "schema": "sit-thesis-md/v2",
        "title": meta.get("title", ""),
        "short_title": meta.get("short_title", meta.get("title", "")),
        "english_title": en_title,
        "college": meta.get("college", ""),
        "major": meta.get("major", ""),
        "class_id": meta.get("class_id", meta.get("class", "")),
        "student_id": meta.get("student_id", ""),
        "student_name": meta.get("student_name", ""),
        "supervisor": meta.get("supervisor", ""),
        "period": meta.get("period", ""),
        "logo": logo,
        "declaration": {
            "enabled": True,
            "author": declaration_author or meta.get("student_name", ""),
            "date": declaration_date,
        },
        "abstract": {"cn": cn_abs, "en_title": en_title, "en": en_abs},
        "keywords": {"cn": cn_keywords, "en": en_keywords},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out = "---\n" + yaml.safe_dump(new_meta, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n"
    out += "\n".join(standard_body).strip() + "\n"
    output_path.write_text(out, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="旧版抽取 Markdown -> SIT 标准论文 Markdown v2")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    normalize(args.input, args.output)
    print(f"已生成标准 Markdown：{args.output}")


if __name__ == "__main__":
    main()
