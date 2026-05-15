#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIT-Thesis-MD v2 -> 上海应用技术大学 LaTeX 模板工程。

设计原则：
1. 复制用户提供的 LaTeX 模板工程，只生成 main.tex；不重新发明模板。
2. Markdown 只表达语义；字号、行距、封面、目录、图题/表题由 sithesis.cls 控制。
3. 表格按“逻辑表”处理，不保留 Word 因分页拆出的续表；超宽表自动换行/长表分页。
4. 默认按用户确认规则修正页脚：奇数页页码在右侧，偶数页页码在左侧。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except Exception as exc:  # pragma: no cover
    raise SystemExit("需要 PyYAML：pip install pyyaml") from exc


@dataclass
class FigureBlock:
    src: str
    caption: str
    label: str = ""
    width: str = "0.85\\textwidth"


@dataclass
class TableBlock:
    caption: str
    header: List[str]
    rows: List[List[str]]
    label: str = ""
    kind: str = "auto"          # auto/table/longtable
    fit: str = "auto"           # auto/wrap/scale
    widths: List[float] = field(default_factory=list)
    align: List[str] = field(default_factory=list)
    fontsize: str = ""          # usually empty; class sets 五号. Emergency: small/footnotesize.
    source_notes: List[str] = field(default_factory=list)


@dataclass
class EquationBlock:
    body: str
    label: str = ""


@dataclass
class DocumentParts:
    meta: Dict[str, Any]
    body_lines: List[str]
    acknowledgements: List[str] = field(default_factory=list)
    references: List[Tuple[int, str]] = field(default_factory=list)
    appendix: List[str] = field(default_factory=list)


LATEX_SPECIALS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

PLACEHOLDER_PREFIX = "@@SITPLACEHOLDER"
ALLOWBREAK_TOKEN = "@@SITALLOWBREAK@@"
CIRCLED_DIGIT_MAP = {
    "①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
    "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10",
    "⑪": "11", "⑫": "12", "⑬": "13", "⑭": "14", "⑮": "15",
    "⑯": "16", "⑰": "17", "⑱": "18", "⑲": "19", "⑳": "20",
}


def latex_escape(text: str) -> str:
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def safe_meta_tex(value: Any) -> str:
    if value is None:
        return ""
    return latex_escape(str(value).strip())


def strip_numbered_heading(title: str) -> str:
    return re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", title).strip()


def strip_caption_prefix(caption: str, kind: str) -> Tuple[str, str, bool]:
    """去掉 caption 中的“图3.1/表4.8/续表4.8/表4.8（续）”前缀。"""
    raw = caption.strip()
    is_cont = False
    if kind == "fig":
        m = re.match(r"^\s*图\s*(\d+(?:\.\d+)*)\s*[:：]?\s*(.*)$", raw)
    else:
        m = re.match(r"^\s*(续表|表)\s*(\d+(?:\.\d+)*)\s*(?:\(续\)|（续）)?\s*[:：]?\s*(.*)$", raw)
        if m and (m.group(1) == "续表" or "续" in raw[: max(8, len(m.group(0)))]):
            is_cont = True
    if m:
        if kind == "fig":
            number, text = m.group(1), m.group(2)
        else:
            number, text = m.group(2), m.group(3)
        return text.strip(), number.replace(".", "-"), is_cont
    return raw, "", False


def canonical_caption(caption: str) -> str:
    text = caption.strip()
    text = re.sub(r"^\s*(续表|表)\s*\d+(?:\.\d+)*\s*(?:\(续\)|（续）)?\s*[:：]?", "", text)
    text = re.sub(r"[\s　]+", "", text)
    text = text.replace("（续）", "").replace("(续)", "")
    return text


def slug_label(prefix: str, text: str, fallback: str = "") -> str:
    if fallback:
        return f"{prefix}:{fallback}"
    ascii_part = re.sub(r"[^0-9A-Za-z-]+", "", re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-").lower())
    if ascii_part:
        return f"{prefix}:{ascii_part[:40]}"
    return f"{prefix}:{abs(hash(text)) % 100000}"


def normalize_key(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            raw = text[4:end].strip()
            rest = text[text.find("\n", end + 4) + 1 :]
            return yaml.safe_load(raw) or {}, rest
    return {}, text


def parse_key_value_block(lines: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        if ":" in line:
            key, value = line.split(":", 1)
        elif "：" in line:
            key, value = line.split("：", 1)
        else:
            continue
        out[normalize_key(key)] = value.strip()
    return out


def parse_float_list(value: str) -> List[float]:
    if not value:
        return []
    parts = re.split(r"[,，;；\s]+", value.strip())
    out: List[float] = []
    for p in parts:
        if not p:
            continue
        p = p.rstrip("%")
        try:
            f = float(p)
            if f > 1:
                f = f / 100.0
            out.append(f)
        except ValueError:
            pass
    return out


def parse_align_list(value: str, n: int) -> List[str]:
    if not value:
        return []
    vals = [x.strip().lower()[0] for x in re.split(r"[,，;；\s]+", value) if x.strip()]
    vals = [x if x in {"l", "c", "r"} else "l" for x in vals]
    if len(vals) < n:
        vals += ["l"] * (n - len(vals))
    return vals[:n]


def join_keywords(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        items = re.split(r"[;；]", value)
    else:
        items = list(value)
    return "；".join(str(x).strip().rstrip("。.;；") for x in items if str(x).strip())


def fix_asset_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def latex_path(path: str) -> str:
    return path.replace("\\", "/")


def breakify_text(text: str) -> str:
    """在长路径、接口、英文/代码 token 中插入可断点。"""
    if not text:
        return text

    def repl_token(m: re.Match[str]) -> str:
        token = m.group(0)
        if len(token) < 8:
            return token
        # 不破坏纯小数；重点处理 API 路径、snake_case、枚举值、括号和英文长串。
        token = re.sub(r"([/_:\-.,(){}])", r"\1" + ALLOWBREAK_TOKEN, token)
        return token

    return re.sub(r"[A-Za-z0-9_:/.,'(){}-]{8,}", repl_token, text)


class InlineConverter:
    def __init__(self, citations: bool = True):
        self.citations = citations
        self.placeholders: List[str] = []

    def _hold(self, latex: str) -> str:
        idx = len(self.placeholders)
        self.placeholders.append(latex)
        return f"{PLACEHOLDER_PREFIX}{idx}@@"

    def _restore(self, text: str) -> str:
        for idx, value in enumerate(self.placeholders):
            text = text.replace(f"{PLACEHOLDER_PREFIX}{idx}@@", value)
        text = text.replace(ALLOWBREAK_TOKEN, r"\allowbreak{}")
        return text

    def _citation_repl(self, m: re.Match[str]) -> str:
        raw = m.group(1)
        keys: List[str] = []
        for part in re.split(r"[,，]", raw):
            part = part.strip()
            if re.fullmatch(r"\d+", part):
                keys.append(f"ref{part}")
            elif re.fullmatch(r"\d+\s*[-–—]\s*\d+", part):
                a, b = re.split(r"[-–—]", part)
                keys.extend(f"ref{i}" for i in range(int(a), int(b) + 1))
        if not keys:
            return m.group(0)
        return self._hold(r"\cite{" + ",".join(keys) + "}")

    def convert(self, text: str, *, break_long_tokens: bool = False) -> str:
        self.placeholders = []
        text = str(text)

        def link_repl(m: re.Match[str]) -> str:
            label, url = m.group(1), m.group(2)
            return self._hold(r"\href{" + url + "}{" + latex_escape(label) + "}")
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)

        def code_repl(m: re.Match[str]) -> str:
            content = latex_escape(m.group(1))
            return self._hold(r"\texttt{" + content + "}")
        text = re.sub(r"`([^`]+)`", code_repl, text)

        def math_repl(m: re.Match[str]) -> str:
            return self._hold("$" + m.group(1) + "$")
        text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", math_repl, text)

        if self.citations:
            text = re.sub(r"\[(\d+(?:\s*[,，]\s*\d+|\s*[-–—]\s*\d+)*)\]", self._citation_repl, text)

        def bold_repl(m: re.Match[str]) -> str:
            return self._hold(r"\textbf{" + latex_escape(m.group(1)) + "}")
        text = re.sub(r"\*\*([^*]+)\*\*", bold_repl, text)

        def url_repl(m: re.Match[str]) -> str:
            raw = m.group(0)
            url = raw.rstrip(".,;:，。；：．")
            suffix = raw[len(url):]
            return self._hold(r"\url{" + url + "}") + suffix
        text = re.sub(r"https?://[^\s]+", url_repl, text)

        def circled_repl(m: re.Match[str]) -> str:
            num = CIRCLED_DIGIT_MAP[m.group(0)]
            return self._hold(num + r".\,")
        text = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]", circled_repl, text)

        # Windows 宋体/黑体子集常不含箭头符号；映射为 TeX 数学符号以避免缺字。
        arrow_map = {"→": r"$\rightarrow$", "←": r"$\leftarrow$", "↔": r"$\leftrightarrow$", "⇒": r"$\Rightarrow$", "≤": r"$\leq$", "≥": r"$\geq$"}
        text = re.sub(r"[→←↔⇒≤≥]", lambda m: self._hold(arrow_map[m.group(0)]), text)

        if break_long_tokens:
            text = breakify_text(text)
        text = latex_escape(text)
        return self._restore(text)


def split_special_sections(markdown_body: str) -> Tuple[List[str], List[str], List[Tuple[int, str]], List[str]]:
    lines = markdown_body.splitlines()
    sections: Dict[str, List[str]] = {"body": [], "ack": [], "refs": [], "appendix": []}
    current = "body"
    for line in lines:
        h = line.strip().replace(" ", "")
        if re.match(r"^#\s*致\s*谢\s*$", line.strip()) or h == "#致谢":
            current = "ack"
            continue
        if re.match(r"^#\s*参考文献\s*$", line.strip()):
            current = "refs"
            continue
        if re.match(r"^#\s*附\s*录\s*$", line.strip()) or h == "#附录":
            current = "appendix"
            continue
        sections[current].append(line)
    return sections["body"], sections["ack"], parse_references(sections["refs"]), sections["appendix"]


def parse_references(lines: List[str]) -> List[Tuple[int, str]]:
    refs: List[Tuple[int, str]] = []
    current_num: Optional[int] = None
    current_parts: List[str] = []

    def flush() -> None:
        nonlocal current_num, current_parts
        if current_num is not None:
            text = " ".join(p.strip() for p in current_parts if p.strip()).strip()
            if text:
                refs.append((current_num, text))
        current_num = None
        current_parts = []

    for line in lines:
        if line.strip().startswith("---"):
            break
        m = re.match(r"^\s*\[(\d+)\]\s*(.*)$", line)
        if m:
            flush()
            current_num = int(m.group(1))
            current_parts = [m.group(2).strip()]
        elif current_num is not None:
            current_parts.append(line.strip())
    flush()
    return refs


def parse_document(path: Path) -> DocumentParts:
    text = path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    body_lines, ack, refs, appendix = split_special_sections(body)
    return DocumentParts(meta=meta, body_lines=body_lines, acknowledgements=ack, references=refs, appendix=appendix)


def normalize_row(row: List[str], n: int) -> List[str]:
    if len(row) < n:
        return row + [""] * (n - len(row))
    if len(row) > n:
        return row[: n - 1] + [" ".join(row[n - 1 :])]
    return row


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


def table_signature(header: List[str]) -> str:
    return "|".join(re.sub(r"\s+", "", h.strip()) for h in header)


class BlockConverter:
    def __init__(self, md_dir: Path):
        self.md_dir = md_dir
        self.inline = InlineConverter(citations=True)
        self.report: Dict[str, Any] = {"figures": [], "tables": [], "equations": [], "warnings": [], "template_patches": []}

    def convert_lines(self, lines: List[str]) -> str:
        lines = self.merge_semantic_continuation_tables(lines)
        out: List[str] = []
        i = 0
        paragraph: List[str] = []
        in_code = False
        code_lines: List[str] = []
        in_display_math = False
        math_lines: List[str] = []

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                text = " ".join(x.strip() for x in paragraph if x.strip())
                if text:
                    out.append(self.inline.convert(text, break_long_tokens=True))
                    out.append("")
                paragraph = []

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("```"):
                flush_paragraph()
                if not in_code:
                    in_code = True
                    code_lines = []
                else:
                    in_code = False
                    out.append(r"\begin{verbatim}")
                    out.extend(code_lines)
                    out.append(r"\end{verbatim}")
                    out.append("")
                i += 1
                continue
            if in_code:
                code_lines.append(line)
                i += 1
                continue

            if stripped == "$$":
                flush_paragraph()
                if not in_display_math:
                    in_display_math = True
                    math_lines = []
                else:
                    in_display_math = False
                    out.append(self.render_equation(EquationBlock("\n".join(math_lines).strip())))
                    out.append("")
                i += 1
                continue
            if in_display_math:
                math_lines.append(line)
                i += 1
                continue

            if stripped == "::: figure":
                flush_paragraph()
                block, new_i = self.collect_colon_block(lines, i)
                out.append(self.render_figure(self.parse_figure_block(block)))
                out.append("")
                i = new_i
                continue
            if stripped == "::: table":
                flush_paragraph()
                block, new_i = self.collect_colon_block(lines, i)
                out.append(self.render_table(self.parse_table_block(block)))
                out.append("")
                i = new_i
                continue
            if stripped == "::: equation":
                flush_paragraph()
                block, new_i = self.collect_colon_block(lines, i)
                out.append(self.render_equation(self.parse_equation_block(block)))
                out.append("")
                i = new_i
                continue

            m = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
            if m:
                flush_paragraph()
                level = len(m.group(1))
                title = strip_numbered_heading(m.group(2).strip())
                if level == 1:
                    out.append(r"\section{" + self.inline.convert(title) + "}")
                    out.append(r"\resetsubitemtitle")
                elif level == 2:
                    out.append(r"\subsection{" + self.inline.convert(title) + "}")
                    out.append(r"\resetsubitemtitle")
                else:
                    out.append(r"\subsubsection{" + self.inline.convert(title) + "}")
                out.append("")
                i += 1
                continue

            img = re.match(r"^!\[(.*?)\]\((.*?)\)(?:\{(.*?)\})?\s*$", stripped)
            if img:
                flush_paragraph()
                caption_raw, src, attrs = img.group(1), img.group(2), img.group(3) or ""
                caption, num, _ = strip_caption_prefix(caption_raw, "fig")
                width = "0.85\\textwidth"
                w = re.search(r"width\s*=\s*([^\s}]+)", attrs)
                if w:
                    width = w.group(1)
                out.append(self.render_figure(FigureBlock(src=fix_asset_path(src), caption=caption, label=slug_label("fig", caption, num), width=width)))
                out.append("")
                i += 1
                continue

            cap = re.match(r"^\*\*\s*((?:续表|表)\s*\d+(?:\.\d+)*.*)\s*\*\*\s*$", stripped)
            if cap:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip().startswith("|"):
                    flush_paragraph()
                    table_lines: List[str] = []
                    while j < len(lines) and lines[j].strip().startswith("|"):
                        table_lines.append(lines[j])
                        j += 1
                    caption, num, is_cont = strip_caption_prefix(cap.group(1), "tab")
                    header, rows = parse_markdown_table(table_lines)
                    table = TableBlock(caption=caption, label=slug_label("tab", caption, num), header=header, rows=rows)
                    if is_cont:
                        self.report["warnings"].append(f"检测到未标准化续表：{cap.group(1)}；建议先运行 normalize_legacy_md.py 合并为逻辑表。")
                    out.append(self.render_table(table))
                    out.append("")
                    i = j
                    continue

            if stripped.startswith("|") and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
                flush_paragraph()
                table_lines = []
                j = i
                while j < len(lines) and lines[j].strip().startswith("|"):
                    table_lines.append(lines[j])
                    j += 1
                header, rows = parse_markdown_table(table_lines)
                out.append(self.render_table(TableBlock(caption="未命名表格", header=header, rows=rows)))
                out.append("")
                i = j
                continue

            if not stripped:
                flush_paragraph()
                i += 1
                continue

            paragraph.append(line)
            i += 1

        flush_paragraph()
        return "\n".join(out).rstrip() + "\n"

    def collect_colon_block(self, lines: List[str], start: int) -> Tuple[List[str], int]:
        block: List[str] = []
        i = start + 1
        while i < len(lines):
            if lines[i].strip() == ":::":
                return block, i + 1
            block.append(lines[i])
            i += 1
        self.report["warnings"].append(f"未闭合 ::: 块，起始行 {start + 1}")
        return block, i

    def merge_semantic_continuation_tables(self, lines: List[str]) -> List[str]:
        """安全兜底：合并标准 Markdown 中相邻/近邻的续表块。"""
        parsed: List[Any] = []
        i = 0
        while i < len(lines):
            if lines[i].strip() == "::: table":
                block, new_i = self.collect_colon_block(lines, i)
                table = self.parse_table_block(block)
                parsed.append(("table", table))
                i = new_i
            else:
                parsed.append(("line", lines[i]))
                i += 1

        merged: List[Any] = []
        last_table_idx: Optional[int] = None
        for item_type, item in parsed:
            if item_type != "table":
                merged.append((item_type, item))
                # 遇到实质性文字后不跨段合并，仅允许空行/注释隔开。
                if str(item).strip() and not str(item).strip().startswith("<!--"):
                    last_table_idx = None
                continue
            table: TableBlock = item
            capcanon = canonical_caption(table.caption)
            merged_into = False
            if last_table_idx is not None and last_table_idx < len(merged):
                prev_type, prev = merged[last_table_idx]
                if prev_type == "table":
                    prev_table: TableBlock = prev
                    same_label = table.label and prev_table.label and table.label == prev_table.label
                    same_caption = capcanon and capcanon == canonical_caption(prev_table.caption)
                    same_header = table_signature(table.header) == table_signature(prev_table.header)
                    if same_label or (same_caption and same_header):
                        rows_to_add = table.rows[:]
                        # 若 Word 把表头作为续表第一行重复抽取，去掉。
                        if rows_to_add and table_signature(rows_to_add[0]) == table_signature(prev_table.header):
                            rows_to_add = rows_to_add[1:]
                        prev_table.rows.extend(rows_to_add)
                        prev_table.kind = "longtable" if len(prev_table.rows) > 8 else prev_table.kind
                        prev_table.source_notes.append("merged_continuation")
                        self.report["warnings"].append(f"已合并续表到逻辑表：{prev_table.caption}")
                        merged_into = True
            if not merged_into:
                merged.append(("table", table))
                last_table_idx = len(merged) - 1

        out: List[str] = []
        for typ, item in merged:
            if typ == "line":
                out.append(item)
            else:
                out.extend(self.serialize_table_block(item))
        return out

    def serialize_table_block(self, table: TableBlock) -> List[str]:
        lines = ["::: table", f"caption: {table.caption}"]
        if table.label:
            lines.append(f"label: {table.label}")
        if table.kind != "auto":
            lines.append(f"type: {table.kind}")
        if table.fit != "auto":
            lines.append(f"fit: {table.fit}")
        if table.widths:
            lines.append("widths: " + ", ".join(f"{w:.3f}" for w in table.widths))
        if table.align:
            lines.append("align: " + ", ".join(table.align))
        lines.append("| " + " | ".join(table.header) + " |")
        lines.append("| " + " | ".join(["---"] * max(1, len(table.header))) + " |")
        for row in table.rows:
            lines.append("| " + " | ".join(row) + " |")
        lines.append(":::")
        return lines

    def parse_figure_block(self, lines: List[str]) -> FigureBlock:
        kv = parse_key_value_block(lines)
        src = kv.get("src", "")
        caption, num, _ = strip_caption_prefix(kv.get("caption", ""), "fig")
        label = kv.get("label", "") or slug_label("fig", caption, num)
        return FigureBlock(src=fix_asset_path(src), caption=caption, label=label, width=kv.get("width", "0.85\\textwidth"))

    def parse_table_block(self, lines: List[str]) -> TableBlock:
        meta_lines: List[str] = []
        table_lines: List[str] = []
        in_table = False
        for line in lines:
            if line.strip().startswith("|"):
                in_table = True
            if in_table:
                table_lines.append(line)
            else:
                meta_lines.append(line)
        kv = parse_key_value_block(meta_lines)
        caption, num, _ = strip_caption_prefix(kv.get("caption", "未命名表格"), "tab")
        header, rows = parse_markdown_table(table_lines)
        n = max(1, len(header))
        widths = parse_float_list(kv.get("widths", kv.get("columns", "")))
        align = parse_align_list(kv.get("align", ""), n)
        return TableBlock(
            caption=caption,
            label=kv.get("label", "") or slug_label("tab", caption, num),
            header=header,
            rows=rows,
            kind=kv.get("type", kv.get("kind", "auto")).lower(),
            fit=kv.get("fit", "auto").lower(),
            widths=widths,
            align=align,
            fontsize=kv.get("font_size", kv.get("fontsize", "")),
        )

    def parse_equation_block(self, lines: List[str]) -> EquationBlock:
        label = ""
        body_lines: List[str] = []
        for line in lines:
            if not body_lines and (line.startswith("label:") or line.startswith("label：")):
                _, label = re.split(r"[:：]", line, maxsplit=1)
                label = label.strip()
            else:
                body_lines.append(line)
        return EquationBlock("\n".join(body_lines).strip(), label=label)

    def render_figure(self, fig: FigureBlock) -> str:
        if not fig.src:
            self.report["warnings"].append(f"空图片路径：{fig.caption}")
        elif not (self.md_dir / fig.src).exists():
            self.report["warnings"].append(f"图片不存在：{fig.src}")
        self.report["figures"].append({"src": fig.src, "caption": fig.caption, "label": fig.label})
        parts = [r"\begin{figure}[htbp]", r"  \centering"]
        parts.append(r"  \includegraphics[width=" + fig.width + "]{" + latex_path(fig.src) + "}")
        parts.append(r"  \caption{" + self.inline.convert(fig.caption) + "}")
        if fig.label:
            parts.append(r"  \label{" + fig.label + "}")
        parts.append(r"\end{figure}")
        return "\n".join(parts)

    def choose_table_kind(self, table: TableBlock) -> bool:
        n = max(1, len(table.header))
        total_chars = sum(len(c) for c in table.header) + sum(len(c) for row in table.rows for c in row)
        max_cell = max([len(c) for c in table.header] + [len(c) for row in table.rows for c in row] + [0])
        if table.kind == "longtable":
            return True
        if table.kind in {"table", "tabular", "float"}:
            return False
        return len(table.rows) > 8 or total_chars > 900 or (n >= 6 and len(table.rows) > 5) or max_cell > 90

    def auto_widths(self, table: TableBlock, longtable: bool) -> List[float]:
        n = max(1, len(table.header))
        if table.widths and len(table.widths) >= n:
            widths = table.widths[:n]
        else:
            scores: List[float] = []
            for c in range(n):
                values = [table.header[c] if c < len(table.header) else ""]
                values += [row[c] if c < len(row) else "" for row in table.rows]
                # header 重要，但长文本列更应给宽。
                avg = sum(min(len(v), 80) for v in values) / max(1, len(values))
                mx = max((min(len(v), 120) for v in values), default=1)
                scores.append(max(6.0, 0.55 * avg + 0.45 * mx))
            total = sum(scores) or 1.0
            widths = [s / total for s in scores]
        # 限制极窄列，给多列留 tabcolsep 空间。
        min_w = 0.07 if n >= 7 else 0.09 if n >= 5 else 0.12
        max_w = 0.42 if n >= 4 else 0.65
        widths = [min(max(w, min_w), max_w) for w in widths]
        total = sum(widths)
        # longtable/tabular 的 p 列要留出列间距；列越多，总宽越保守。
        target = max(0.80, 0.96 - 0.012 * n) if longtable else max(0.82, 0.94 - 0.010 * n)
        widths = [w / total * target for w in widths]
        return widths

    def colspec(self, widths: List[float], align: List[str], x_columns: bool = False) -> str:
        specs: List[str] = []
        n = len(widths)
        if not align:
            align = ["l"] * n
        for idx, w in enumerate(widths):
            a = align[idx] if idx < len(align) else "l"
            rag = r"\raggedright" if a == "l" else r"\centering" if a == "c" else r"\raggedleft"
            specs.append(r">{" + rag + r"\arraybackslash}p{" + f"{w:.3f}" + r"\textwidth}")
        return "".join(specs)

    def cell(self, text: str) -> str:
        return self.inline.convert(str(text).strip(), break_long_tokens=True)

    def render_table(self, table: TableBlock) -> str:
        n = max(1, len(table.header))
        table.rows = [normalize_row(row, n) for row in table.rows]
        use_long = self.choose_table_kind(table)
        widths = self.auto_widths(table, use_long)
        max_cell = max([len(c) for c in table.header] + [len(c) for row in table.rows for c in row] + [0])
        self.report["tables"].append({
            "caption": table.caption,
            "label": table.label,
            "columns": n,
            "rows": len(table.rows),
            "longtable": use_long,
            "widths": [round(x, 3) for x in widths],
            "max_cell_chars": max_cell,
        })
        if n >= 7 or max_cell > 90:
            self.report["warnings"].append(f"表格可能较宽，已启用自动换行列：{table.caption}")
        if use_long:
            return self.render_longtable(table, widths)
        return self.render_float_table(table, widths)

    def render_float_table(self, table: TableBlock, widths: List[float]) -> str:
        colspec = self.colspec(widths, table.align)
        fontcmd = ("\\" + table.fontsize) if table.fontsize else ""
        out = [r"\begin{table}[htbp]", r"  \caption{" + self.inline.convert(table.caption) + "}"]
        if table.label:
            out.append(r"  \label{" + table.label + "}")
        out.extend([r"  \centering", r"  \begingroup", r"  \setlength{\tabcolsep}{3pt}"])
        if fontcmd:
            out.append("  " + fontcmd)
        out.append(r"  \begin{tabular}{" + colspec + "}")
        out.append(r"    \toprule")
        out.append("    " + " & ".join(self.cell(c) for c in table.header) + r" \\")
        out.append(r"    \midrule")
        for row in table.rows:
            out.append("    " + " & ".join(self.cell(c) for c in row) + r" \\")
        out.extend([r"    \bottomrule", r"  \end{tabular}", r"  \endgroup", r"\end{table}"])
        return "\n".join(out)

    def render_longtable(self, table: TableBlock, widths: List[float]) -> str:
        colspec = self.colspec(widths, table.align)
        n = max(1, len(table.header))
        header_tex = " & ".join(self.cell(c) for c in table.header) + r" \\" 
        fontcmd = ("\\" + table.fontsize) if table.fontsize else ""
        out = [r"\begingroup", r"\setlength{\tabcolsep}{3pt}", r"\setlength{\LTleft}{0pt}", r"\setlength{\LTright}{0pt}"]
        if fontcmd:
            out.append(fontcmd)
        out.append(r"\refstepcounter{table}")
        if table.label:
            out.append(r"\label{" + table.label + "}")
        out.append(r"\begin{longtable}{" + colspec + "}")
        out.append(
            r"  \multicolumn{" + str(n) + r"}{c}{\zihao{5}\heiti 表\thetable\quad "
            + self.inline.convert(table.caption)
            + r"}\\"
        )
        out.append(r"  \toprule")
        out.append("  " + header_tex)
        out.append(r"  \midrule")
        out.append(r"  \endfirsthead")
        # 续页只在 LaTeX 内部自动出现；Markdown 仍只有一个逻辑表。
        out.append(
            r"  \multicolumn{" + str(n) + r"}{c}{\zihao{5}\heiti 表\thetable\quad "
            + self.inline.convert(table.caption)
            + r"（续）}\\"
        )
        out.append(r"  \toprule")
        out.append("  " + header_tex)
        out.append(r"  \midrule")
        out.append(r"  \endhead")
        out.append(r"  \midrule")
        out.append(r"  \endfoot")
        out.append(r"  \bottomrule")
        out.append(r"  \endlastfoot")
        for row in table.rows:
            out.append("  " + " & ".join(self.cell(c) for c in row) + r" \\")
        out.append(r"\end{longtable}")
        out.append(r"\endgroup")
        return "\n".join(out)

    def render_equation(self, eq: EquationBlock) -> str:
        self.report["equations"].append({"label": eq.label, "chars": len(eq.body)})
        out = [r"\begin{equation}", eq.body]
        if eq.label:
            out.append(r"  \label{" + eq.label + "}")
        out.append(r"\end{equation}")
        return "\n".join(out)


def generate_main_tex(parts: DocumentParts, md_dir: Path) -> Tuple[str, Dict[str, Any]]:
    meta = parts.meta
    title = meta.get("title", "毕业设计（论文）题目")
    short_title = meta.get("short_title") or meta.get("shorttitle") or title
    abstract = meta.get("abstract", {}) or {}
    keywords = meta.get("keywords", {}) or {}
    english_title = meta.get("english_title") or meta.get("englishtitle") or (abstract.get("en_title") if isinstance(abstract, dict) else "") or ""

    cn_abs = abstract.get("cn", "") if isinstance(abstract, dict) else ""
    en_abs = abstract.get("en", "") if isinstance(abstract, dict) else ""
    en_title = abstract.get("en_title", english_title) if isinstance(abstract, dict) else english_title
    cn_keywords = join_keywords(keywords.get("cn") if isinstance(keywords, dict) else "")
    en_keywords = join_keywords(keywords.get("en") if isinstance(keywords, dict) else "")

    converter = BlockConverter(md_dir)
    body_tex = converter.convert_lines(parts.body_lines)
    ack_tex = converter.convert_lines(parts.acknowledgements) if parts.acknowledgements else ""
    appendix_tex = converter.convert_lines(parts.appendix) if parts.appendix else ""

    bib_lines: List[str] = []
    ref_inline = InlineConverter(citations=False)
    bib_lines.append(r"\begin{thebibliography}{99}")
    if parts.references:
        for num, text in sorted(parts.references, key=lambda x: x[0]):
            bib_lines.append(r"\bibitem{ref" + str(num) + "} " + ref_inline.convert(text, break_long_tokens=True))
    else:
        converter.report["warnings"].append("未检测到参考文献。")
    bib_lines.append(r"\end{thebibliography}")

    logo = meta.get("logo") or meta.get("university_logo") or meta.get("universitylogo") or "figures/sit-logo.pdf"

    tex = textwrap.dedent(f"""\
    % !TeX program = xelatex
    % Auto-generated by scripts/md_to_latex.py. Edit Markdown source, not this file.
    \\documentclass{{sithesis}}

    \\thesistitle{{{safe_meta_tex(title)}}}
    \\shorttitle{{{safe_meta_tex(short_title)}}}
    \\englishtitle{{{safe_meta_tex(en_title or english_title)}}}
    \\college{{{safe_meta_tex(meta.get('college', ''))}}}
    \\major{{{safe_meta_tex(meta.get('major', ''))}}}
    \\classid{{{safe_meta_tex(meta.get('class_id', meta.get('class', '')))}}}
    \\studentid{{{safe_meta_tex(meta.get('student_id', meta.get('studentid', '')))}}}
    \\studentname{{{safe_meta_tex(meta.get('student_name', meta.get('studentname', '')))}}}
    \\supervisor{{{safe_meta_tex(meta.get('supervisor', ''))}}}
    \\period{{{safe_meta_tex(meta.get('period', ''))}}}
    \\universitylogo{{{latex_path(str(logo))}}}

    \\begin{{document}}

    \\makecover

    \\frontmatter
    \\makedeclaration

    \\begin{{cnabstract}}
    {InlineConverter(citations=False).convert(cn_abs)}
    \\end{{cnabstract}}
    \\cnkeywords{{{InlineConverter(citations=False).convert(cn_keywords)}}}

    \\begin{{enabstract}}
    {InlineConverter(citations=False).convert(en_abs)}
    \\end{{enabstract}}
    \\enkeywords{{{InlineConverter(citations=False).convert(en_keywords)}}}

    \\maketableofcontents

    \\mainmatter

    {body_tex}
    """)
    if ack_tex.strip():
        tex += "\n" + r"\begin{acknowledgements}" + "\n" + ack_tex + "\n" + r"\end{acknowledgements}" + "\n"
    tex += "\n" + "\n".join(bib_lines) + "\n"
    if appendix_tex.strip():
        tex += "\n" + r"\begin{appendixmaterial}" + "\n" + appendix_tex + "\n" + r"\end{appendixmaterial}" + "\n"
    tex += "\n" + r"\end{document}" + "\n"
    return tex, converter.report


def resolve_template(template: Path) -> Tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]:
    temp_obj: Optional[tempfile.TemporaryDirectory[str]] = None
    if template.is_file() and template.suffix.lower() == ".zip":
        temp_obj = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(template) as zf:
            zf.extractall(temp_obj.name)
        candidates = [p for p in Path(temp_obj.name).rglob("sithesis.cls") if "__MACOSX" not in str(p)]
        if not candidates:
            raise FileNotFoundError("模板 zip 中找不到 sithesis.cls")
        return candidates[0].parent, temp_obj
    if template.is_dir():
        if (template / "sithesis.cls").exists():
            return template, None
        candidates = [p for p in template.rglob("sithesis.cls") if "__MACOSX" not in str(p)]
        if candidates:
            return candidates[0].parent, None
    raise FileNotFoundError(f"无法定位模板目录或 sithesis.cls：{template}")


def copy_template(template_dir: Path, output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    ignore = shutil.ignore_patterns("*.aux", "*.log", "*.out", "*.toc", "*.fls", "*.fdb_latexmk", "*.xdv", "*.pdf", "__MACOSX", ".DS_Store", "._*")
    shutil.copytree(template_dir, output_dir, ignore=ignore)


def patch_page_parity(output_dir: Path, report: Dict[str, Any]) -> None:
    """按用户确认规则：奇数页右侧、偶数页左侧。只修正页脚 fancyhdr 位置。"""
    cls = output_dir / "sithesis.cls"
    if not cls.exists():
        return
    text = cls.read_text(encoding="utf-8")
    old = text
    text = text.replace("页码奇数页在左侧，偶数页在右侧", "页码奇数页在右侧，偶数页在左侧")
    text = text.replace("% 按文字要求：页码奇数页在左侧，偶数页在右侧。", "% 按用户确认：页码奇数页在右侧，偶数页在左侧。")
    text = text.replace("% 按文字要求：页码奇数页在右侧，偶数页在左侧。", "% 按用户确认：页码奇数页在右侧，偶数页在左侧。")
    text = text.replace(r"\fancyfoot[LO]{\sit@pagenumformat{\thepage}}", r"\fancyfoot[RO]{\sit@pagenumformat{\thepage}}")
    text = text.replace(r"\fancyfoot[RE]{\sit@pagenumformat{\thepage}}", r"\fancyfoot[LE]{\sit@pagenumformat{\thepage}}")
    if text != old:
        cls.write_text(text, encoding="utf-8")
        report.setdefault("template_patches", []).append("page_parity_odd_right_even_left")
    elif (
        r"\fancyfoot[RO]{\sit@pagenumformat{\thepage}}" in text
        and r"\fancyfoot[LE]{\sit@pagenumformat{\thepage}}" in text
    ):
        report.setdefault("template_patches", []).append("page_parity_odd_right_even_left")

    # 模板 README 只作为工程说明，不影响排版；如果复制到输出工程，也同步更正说明，避免误导。
    readme = output_dir / "README.md"
    if readme.exists():
        r = readme.read_text(encoding="utf-8")
        r_old = r
        r = r.replace("页码奇数在左侧，偶数在右侧", "页码奇数在右侧，偶数在左侧")
        r = r.replace("奇数左、偶数右", "奇数右、偶数左")
        if r != r_old:
            readme.write_text(r, encoding="utf-8")
            report.setdefault("template_patches", []).append("readme_page_parity_note")


def copy_assets(md_path: Path, output_dir: Path, meta: Dict[str, Any]) -> None:
    src_fig = md_path.parent / "figures"
    dst_fig = output_dir / "figures"
    dst_fig.mkdir(parents=True, exist_ok=True)
    if src_fig.exists():
        for item in src_fig.iterdir():
            if item.is_file():
                shutil.copy2(item, dst_fig / item.name)
    logo = meta.get("logo") or meta.get("university_logo") or meta.get("universitylogo")
    if logo:
        src = md_path.parent / str(logo)
        dst = output_dir / str(logo)
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def maybe_compile(output_dir: Path) -> None:
    latexmk = shutil.which("latexmk")
    xelatex = shutil.which("xelatex")
    if latexmk:
        subprocess.run([latexmk, "-xelatex", "-interaction=nonstopmode", "main.tex"], cwd=output_dir, check=False)
    elif xelatex:
        subprocess.run([xelatex, "-interaction=nonstopmode", "main.tex"], cwd=output_dir, check=False)
        subprocess.run([xelatex, "-interaction=nonstopmode", "main.tex"], cwd=output_dir, check=False)
    else:
        print("未找到 latexmk/xelatex，已跳过 PDF 编译。", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="标准论文 Markdown 转 SIT LaTeX 模板工程")
    parser.add_argument("markdown", type=Path, help="标准论文 Markdown 文件")
    parser.add_argument("--template", type=Path, required=True, help="模板目录或模板 zip，必须包含 sithesis.cls")
    parser.add_argument("--output", type=Path, required=True, help="输出 LaTeX 工程目录")
    parser.add_argument("--compile", action="store_true", help="若本机有 latexmk/xelatex，则尝试编译 PDF")
    parser.add_argument("--no-patch-page-parity", action="store_true", help="不修正模板页脚奇偶页位置")
    args = parser.parse_args()

    parts = parse_document(args.markdown)
    template_dir, temp_obj = resolve_template(args.template)
    try:
        copy_template(template_dir, args.output)
        copy_assets(args.markdown, args.output, parts.meta)
        tex, report = generate_main_tex(parts, args.markdown.parent)
        if not args.no_patch_page_parity:
            patch_page_parity(args.output, report)
        (args.output / "main.tex").write_text(tex, encoding="utf-8")
        (args.output / "conversion-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.compile:
            maybe_compile(args.output)
        print(f"已生成：{args.output}")
        if report.get("warnings"):
            print("警告：", *report["warnings"], sep="\n- ", file=sys.stderr)
    finally:
        if temp_obj is not None:
            temp_obj.cleanup()


if __name__ == "__main__":
    main()
