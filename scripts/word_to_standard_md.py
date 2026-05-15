#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOCX -> SIT-Thesis-MD v2 初步标准论文 Markdown。

设计原则：
- Word 只做内容抽取，不保留 Word 分页造成的手工续表。
- 表格以“逻辑表”输出；若 Word 把同一表拆成续表，脚本按表号/表头合并。
- 图、表、公式先尽量保留；Word 原生 Office Math(OMML) 会转换为 LaTeX。
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Tuple

import yaml
from docx import Document
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from omml_to_latex import OmmlConversionStats, OmmlToLatex, iter_omath_elements, local_name


@dataclass
class TableBlock:
    caption: str
    number: str
    header: List[str]
    rows: List[List[str]]
    label: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


def iter_block_items(parent: _Document) -> Iterable[Paragraph | Table]:
    for child in parent.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def sanitize(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", name).strip("_") or "image"


def extract_images(docx_path: Path, figures_dir: Path) -> dict[str, str]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    rel_to_file: dict[str, str] = {}
    with zipfile.ZipFile(docx_path) as zf:
        for name in zf.namelist():
            if name.startswith("word/media/"):
                out_name = sanitize(Path(name).name)
                out_path = figures_dir / out_name
                out_path.write_bytes(zf.read(name))
                rel_to_file[Path(name).name] = f"figures/{out_name}"
    return rel_to_file


def count_omml(docx_path: Path) -> int:
    """Count actual OMML equation objects in document.xml.

    ``m:oMathPara`` is only a display container and usually contains one or more
    ``m:oMath`` elements, so counting both would double count display equations.
    """
    with zipfile.ZipFile(docx_path) as zf:
        try:
            xml = zf.read("word/document.xml")
        except KeyError:
            return 0
    try:
        from lxml import etree
        root = etree.fromstring(xml)
        return sum(1 for _ in iter_omath_elements(root))
    except Exception:
        text = xml.decode("utf-8", errors="ignore")
        return len(re.findall(r"<m:oMath\b", text))



EQUATION_TAG_RE = re.compile(r"^\s*[（(]?\s*([0-9]+(?:[.\-—–][0-9]+)*|[A-Za-z]?[0-9]+)\s*[）)]?\s*$")


def parse_equation_tag(text: str) -> str:
    """Return Word-visible equation number text, without surrounding parens."""
    m = EQUATION_TAG_RE.match(text.strip())
    return m.group(1).strip() if m else ""


def equation_block_markdown(tex: str, tag: str = "") -> str:
    lines = ["::: equation"]
    if tag:
        lines.append(f"tag: {tag}")
    lines.append(tex.strip())
    lines.append(":::")
    return "\n".join(lines)

def word_text_from_element(el) -> str:
    """Extract visible text from a Word XML element without touching OMML."""
    name = local_name(el)
    if name == "t":
        return el.text or ""
    if name == "tab":
        return "\t"
    if name in {"br", "cr"}:
        return "\n"
    if name in {"drawing", "pict"}:
        return ""
    return "".join(word_text_from_element(c) for c in el)


def paragraph_text_with_math(paragraph: Paragraph, stats: OmmlConversionStats, *, force_inline: bool = False) -> str:
    """Return paragraph text while converting OMML to LaTeX.

    Policy for Word consistency:
    - inline formulas inside ordinary text stay inline as ``$...$``;
    - a standalone Word formula becomes an explicit equation block;
    - if Word shows a visible number next to the formula, preserve that exact
      number as ``tag`` instead of letting LaTeX auto-number.
    """
    converter = OmmlToLatex(stats)
    tokens: List[tuple[str, str]] = []
    for child in paragraph._p.iterchildren():
        name = local_name(child)
        if name == "oMath":
            tex = converter.convert_element(child)
            if tex:
                tokens.append(("math_inline", tex))
        elif name == "oMathPara":
            tex = converter.convert_element(child)
            if tex:
                tokens.append(("math_display", tex))
        elif name in {"r", "hyperlink", "smartTag", "sdt"}:
            txt = word_text_from_element(child)
            if txt:
                tokens.append(("text", txt))
        else:
            continue

    math_tokens = [(typ, val) for typ, val in tokens if typ.startswith("math_")]
    text = "".join(val for typ, val in tokens if typ == "text").strip()

    # Standalone formula with optional visible Word number, e.g. formula + “(2-1)”.
    # Table cells are rendered as table cells, so keep their formulas inline.
    if not force_inline and len(math_tokens) == 1 and (not text or parse_equation_tag(text)):
        return equation_block_markdown(math_tokens[0][1], parse_equation_tag(text))

    parts: List[str] = []
    for typ, val in tokens:
        if typ == "math_inline":
            parts.append(f"${val}$")
        elif typ == "math_display":
            parts.append(equation_block_markdown(val))
        else:
            parts.append(val)
    return "".join(parts).strip()


def image_refs_in_paragraph(paragraph: Paragraph, relmap: dict[str, str], used: set[str]) -> List[str]:
    refs: List[str] = []
    xml = paragraph._p.xml
    for rid in re.findall(r'r:embed="(rId\d+)"', xml):
        rel = paragraph.part.rels.get(rid)
        if rel is None:
            continue
        target = Path(str(rel.target_ref)).name
        if target in relmap and target not in used:
            used.add(target)
            refs.append(relmap[target])
    return refs


def strip_caption_prefix(text: str, kind: str = "表") -> Tuple[str, str, bool]:
    """返回 caption, number, 是否为续表。"""
    raw = text.strip()
    if kind == "图":
        m = re.match(r"^\s*图\s*(\d+(?:\.\d+)*)\s*[:：]?\s*(.*)$", raw)
        if m:
            return m.group(2).strip(), m.group(1), False
        return raw, "", False
    m = re.match(r"^\s*(续表|表)\s*(\d+(?:\.\d+)*)\s*(?:\(续\)|（续）)?\s*[:：]?\s*(.*)$", raw)
    if m:
        return m.group(3).strip(), m.group(2), (m.group(1) == "续表" or "续" in raw[:12])
    return raw, "", False


def is_table_caption(text: str) -> bool:
    return bool(re.match(r"^\s*(续表|表)\s*\d+(?:\.\d+)*", text.strip()))


def canonical_caption(caption: str) -> str:
    return re.sub(r"\s+", "", caption.replace("（续）", "").replace("(续)", "").strip())


def table_signature(header: List[str]) -> str:
    return "|".join(re.sub(r"\s+", "", h.strip()) for h in header)


def normalize_row(row: List[str], n: int) -> List[str]:
    row = [str(c).strip().replace("\n", " ") for c in row]
    if len(row) < n:
        return row + [""] * (n - len(row))
    if len(row) > n:
        return row[: n - 1] + [" ".join(row[n - 1 :])]
    return row


def cell_text_with_math(cell, stats: OmmlConversionStats) -> str:
    parts = [paragraph_text_with_math(p, stats, force_inline=True) for p in cell.paragraphs]
    return " ".join(p for p in parts if p).strip()


def table_to_rows(table: Table, stats: OmmlConversionStats | None = None) -> List[List[str]]:
    stats = stats or OmmlConversionStats()
    rows: List[List[str]] = []
    for row in table.rows:
        rows.append([cell_text_with_math(cell, stats).replace("\n", " ") for cell in row.cells])
    # 去掉 Word 合并单元格可能产生的完全重复空行。
    return [r for r in rows if any(c.strip() for c in r)]


def infer_table_attrs(table: TableBlock) -> dict[str, str]:
    n = max(1, len(table.header))
    rows = len(table.rows)
    total_chars = sum(len(c) for c in table.header) + sum(len(c) for row in table.rows for c in row)
    max_cell = max([len(c) for c in table.header] + [len(c) for row in table.rows for c in row] + [0])
    attrs: dict[str, str] = {"fit": "wrap"}
    if rows > 8 or total_chars > 900 or (n >= 6 and rows > 5) or max_cell > 90:
        attrs["type"] = "longtable"
    if n == 4 and ("API" in table.caption or "接口" in table.caption):
        attrs["widths"] = "0.36, 0.13, 0.13, 0.36"
    elif n == 4 and ("数据表" in table.caption or "字段" in table.caption):
        attrs["widths"] = "0.12, 0.34, 0.28, 0.26"
    elif n == 7 and "功能测试" in table.caption:
        attrs["widths"] = "0.07, 0.11, 0.17, 0.20, 0.22, 0.13, 0.07"
    elif n == 8 and "性能" in table.caption:
        attrs["widths"] = "0.07, 0.15, 0.08, 0.09, 0.12, 0.10, 0.08, 0.25"
    elif n == 3:
        attrs["widths"] = "0.22, 0.18, 0.56"
    return attrs


def merge_continuation_tables(items: List[Any]) -> Tuple[List[Any], int]:
    merged: List[Any] = []
    last_table_idx: int | None = None
    count = 0
    for item in items:
        if not isinstance(item, TableBlock):
            merged.append(item)
            if isinstance(item, str) and item.strip() and not item.strip().startswith("<!--"):
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
            if (cont and (same_number or same_header)) or (same_number and same_header) or (same_caption and same_header):
                rows_to_add = table.rows[:]
                if rows_to_add and table_signature(rows_to_add[0]) == table_signature(prev.header):
                    rows_to_add = rows_to_add[1:]
                prev.rows.extend(rows_to_add)
                prev.attrs.update(infer_table_attrs(prev))
                prev.attrs["type"] = "longtable"
                merged_into = True
                count += 1
        if not merged_into:
            table.attrs.update(infer_table_attrs(table))
            merged.append(table)
            last_table_idx = len(merged) - 1
    return merged, count


def serialize_table(table: TableBlock) -> List[str]:
    attrs = {k: v for k, v in table.attrs.items() if k != "continuation" and v}
    out = ["::: table", f"caption: {table.caption}"]
    if table.label:
        out.append(f"label: {table.label}")
    for key in ["type", "fit", "widths", "align", "font_size"]:
        if key in attrs:
            out.append(f"{key}: {attrs[key]}")
    out.append("| " + " | ".join(table.header) + " |")
    out.append("| " + " | ".join(["---"] * max(1, len(table.header))) + " |")
    for row in table.rows:
        out.append("| " + " | ".join(normalize_row(row, len(table.header))) + " |")
    out.append(":::")
    out.append("")
    return out


def serialize_items(items: List[Any]) -> List[str]:
    out: List[str] = []
    for item in items:
        if isinstance(item, TableBlock):
            out.extend(serialize_table(item))
        else:
            out.append(str(item))
    return out



def parse_keywords_line(line: str) -> List[str]:
    value = re.sub(r"^\s*(关键词|Key\s*Words|Keywords)\s*[:：]", "", line.strip(), flags=re.I)
    return [x.strip().strip("；;，,。.") for x in re.split(r"[;；]", value) if x.strip().strip("；;，,。.")]


def compact_text(text: str) -> str:
    return re.sub(r"[\s　]+", "", text.strip())


def extract_after_label(line: str, label: str) -> str:
    c = compact_text(line)
    if c.startswith(label):
        return c[len(label):].lstrip(":：").strip()
    return ""


def fill_meta_from_lines(lines: List[str], meta: dict[str, Any]) -> None:
    """Fill cover/declaration/abstract fields from plain paragraph lines."""
    plain = [l.strip() for l in lines if l.strip() and not l.strip().startswith(":::") and not l.strip().startswith("|")]

    for line in plain[:120]:
        value = extract_after_label(line, "课题名称")
        if value and not meta.get("title"):
            meta["title"] = value
            meta["short_title"] = value
        value = extract_after_label(line, "学院")
        if value and not meta.get("college"):
            meta["college"] = value
        value = extract_after_label(line, "专业")
        if value and not meta.get("major"):
            meta["major"] = value
        c = compact_text(line)
        m = re.match(r"^班级(.+?)学号(.+)$", c)
        if m:
            meta["class_id"] = m.group(1).strip()
            meta["student_id"] = m.group(2).strip()
        value = extract_after_label(line, "学生姓名")
        if value:
            meta["student_name"] = value
        value = extract_after_label(line, "指导教师")
        if value:
            meta["supervisor"] = value
        value = extract_after_label(line, "起止日期")
        if value:
            meta["period"] = value
        value = extract_after_label(line, "作者签名")
        if value:
            meta.setdefault("declaration", {})["author"] = value
        # “日期”可能被写成“日    期”
        c_no_space = compact_text(line)
        if c_no_space.startswith("日期") and len(c_no_space) > 2:
            meta.setdefault("declaration", {})["date"] = c_no_space[2:].lstrip(":：")

    # Chinese abstract: 摘要：... until 关键词
    cn_parts: List[str] = []
    in_cn = False
    for line in plain:
        s = line.strip()
        if re.match(r"^摘要\s*[:：]", s):
            in_cn = True
            cn_parts.append(re.sub(r"^摘要\s*[:：]", "", s).strip())
            continue
        if in_cn and re.match(r"^关键词\s*[:：]", s):
            meta.setdefault("keywords", {})["cn"] = parse_keywords_line(s)
            break
        if in_cn:
            cn_parts.append(s)
    if cn_parts:
        meta.setdefault("abstract", {})["cn"] = "".join(cn_parts).strip()

    # English abstract: line immediately before Abstract is usually the English title.
    for idx, line in enumerate(plain):
        s = line.strip()
        if re.match(r"^Abstract\s*[:：]", s, flags=re.I):
            if idx > 0 and not meta.get("english_title"):
                prev = plain[idx - 1].strip()
                if not re.match(r"^(关键词|摘要|Key\s*Words|Keywords)\b", prev, flags=re.I):
                    meta["english_title"] = prev
                    meta.setdefault("abstract", {})["en_title"] = prev
            en_parts = [re.sub(r"^Abstract\s*[:：]", "", s, flags=re.I).strip()]
            for nxt in plain[idx + 1 :]:
                if re.match(r"^(Key\s*Words|Keywords)\s*[:：]", nxt.strip(), flags=re.I):
                    meta.setdefault("keywords", {})["en"] = parse_keywords_line(nxt)
                    break
                en_parts.append(nxt.strip())
            meta.setdefault("abstract", {})["en"] = " ".join(x for x in en_parts if x).strip()
            break


def is_markdown_block_start(line: str) -> bool:
    return line.strip() in {"::: figure", "::: table", "::: equation"}


def find_body_start(lines: List[str]) -> int:
    candidates: List[int] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r"^#\s*1\s+", s) or re.match(r"^1\s+\S+", s):
            candidates.append(i)
    if candidates:
        return candidates[-1]
    for i, line in enumerate(lines):
        if re.match(r"^#\s+", line.strip()) or re.match(r"^\d+(?:\.\d+)*\s+\S+", line.strip()):
            return i
    return 0


def normalize_body_lines(lines: List[str]) -> List[str]:
    out: List[str] = []
    in_block = False
    for line in lines:
        s = line.strip()
        if is_markdown_block_start(s):
            in_block = True
            out.append(line)
            continue
        if in_block:
            out.append(line)
            if s == ":::":
                in_block = False
            continue
        if not s:
            out.append(line)
            continue
        if re.match(r"^#+\s+", s):
            out.append(line)
            continue
        if re.match(r"^\d+\.\d+\.\d+\s+", s):
            out.append("### " + s)
        elif re.match(r"^\d+\.\d+\s+", s):
            out.append("## " + s)
        elif re.match(r"^\d+\s+", s):
            out.append("# " + s)
        elif re.match(r"^致\s*谢$", s):
            out.append("# 致谢")
        elif re.match(r"^参考文献$", s):
            out.append("# 参考文献")
        elif re.match(r"^附\s*录$", s):
            out.append("# 附录")
        else:
            out.append(line)
    # collapse excessive blank lines
    collapsed: List[str] = []
    blank = 0
    for line in out:
        if line.strip():
            blank = 0
            collapsed.append(line)
        else:
            blank += 1
            if blank <= 1:
                collapsed.append("")
    return collapsed



def pair_figure_captions(lines: List[str]) -> List[str]:
    """Attach following “图 x.y 标题” paragraphs to placeholder figure blocks."""
    out: List[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "::: figure":
            block: List[str] = []
            j = i
            while j < len(lines):
                block.append(lines[j])
                if lines[j].strip() == ":::":
                    break
                j += 1
            k = j + 1
            blanks: List[str] = []
            while k < len(lines) and not lines[k].strip():
                blanks.append(lines[k])
                k += 1
            if k < len(lines):
                m = re.match(r"^\s*图\s*(\d+(?:\.\d+)*)\s*[:：]?\s*(.+?)\s*$", lines[k].strip())
                if m and any("caption: 待补充图题" in x for x in block):
                    number = m.group(1)
                    caption = m.group(2).strip() or "待补充图题"
                    label = f"fig:{number.replace('.', '-')}"
                    new_block: List[str] = []
                    for b in block:
                        if b.startswith("caption:"):
                            new_block.append(f"caption: {caption}")
                        elif b.startswith("label:"):
                            new_block.append(f"label: {label}")
                        else:
                            new_block.append(b)
                    out.extend(new_block)
                    out.append("")
                    i = k + 1
                    continue
            out.extend(block)
            i = j + 1
            continue
        out.append(lines[i])
        i += 1
    return out


def normalize_reference_numbers(lines: List[str]) -> List[str]:
    out: List[str] = []
    in_refs = False
    num = 1
    for line in lines:
        s = line.strip()
        h = s.replace(" ", "")
        if re.match(r"^#\s*参考文献\s*$", s):
            in_refs = True
            num = 1
            out.append(line)
            continue
        if in_refs:
            if re.match(r"^#\s+", s) and not re.match(r"^#\s*参考文献\s*$", s):
                in_refs = False
                out.append(line)
                continue
            if s and not s.startswith("[") and not s.startswith("<!--"):
                out.append(f"[{num}] {s}")
                num += 1
                continue
        out.append(line)
    return out

def postprocess_standard_lines(lines: List[str], meta: dict[str, Any]) -> List[str]:
    fill_meta_from_lines(lines, meta)
    start = find_body_start(lines)
    body = normalize_body_lines(lines[start:])
    body = pair_figure_captions(body)
    body = normalize_reference_numbers(body)
    return body

def main() -> None:
    parser = argparse.ArgumentParser(description="DOCX 初步抽取为 SIT-Thesis-MD v2")
    parser.add_argument("docx", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--assets", type=Path, default=None, help="图片输出目录，默认输出文件同级 figures")
    args = parser.parse_args()

    figures_dir = args.assets or (args.output.parent / "figures")
    relmap = extract_images(args.docx, figures_dir)
    omml_count = count_omml(args.docx)
    math_stats = OmmlConversionStats()
    doc = Document(args.docx)

    meta = {
        "schema": "sit-thesis-md/v2",
        "title": "",
        "short_title": "",
        "english_title": "",
        "college": "",
        "major": "",
        "class_id": "",
        "student_id": "",
        "student_name": "",
        "supervisor": "",
        "period": "",
        "logo": "",
        "declaration": {"enabled": True, "author": "", "date": ""},
        "abstract": {"cn": "", "en_title": "", "en": ""},
        "keywords": {"cn": [], "en": []},
    }

    items: List[Any] = []
    used_images: set[str] = set()
    img_counter = 1
    pending_caption = ""

    def flush_pending_caption() -> None:
        nonlocal pending_caption
        if pending_caption:
            items.append(pending_caption)
            items.append("")
            pending_caption = ""

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = paragraph_text_with_math(block, math_stats)
            for src in image_refs_in_paragraph(block, relmap, used_images):
                if not meta["logo"] and img_counter == 1:
                    meta["logo"] = src
                else:
                    items.extend([
                        "::: figure",
                        f"src: {src}",
                        "caption: 待补充图题",
                        f"label: fig:auto-{img_counter}",
                        r"width: 0.85\textwidth",
                        ":::",
                        "",
                    ])
                img_counter += 1
            if not text:
                continue
            if is_table_caption(text):
                # 暂存给后面的 Table；不要把“续表”标题原样写入 Markdown。
                if pending_caption:
                    flush_pending_caption()
                pending_caption = text
                continue
            flush_pending_caption()
            style = (block.style.name or "").lower()
            if "heading 1" in style or "标题 1" in style:
                items.append(f"# {text}")
            elif "heading 2" in style or "标题 2" in style:
                items.append(f"## {text}")
            elif "heading 3" in style or "标题 3" in style:
                items.append(f"### {text}")
            else:
                items.append(text)
            items.append("")
        elif isinstance(block, Table):
            rows = table_to_rows(block, math_stats)
            if not rows:
                pending_caption = ""
                continue
            header = rows[0]
            body = [normalize_row(r, len(header)) for r in rows[1:]]
            cap_text = pending_caption or "待补充表题"
            caption, number, is_cont = strip_caption_prefix(cap_text, "表")
            if not caption:
                caption = "待补充表题"
            label = f"tab:{number.replace('.', '-')}" if number else ""
            table = TableBlock(caption=caption, number=number, label=label, header=header, rows=body)
            table.attrs = infer_table_attrs(table)
            if is_cont:
                table.attrs["continuation"] = "true"
            items.append(table)
            items.append("")
            pending_caption = ""

    flush_pending_caption()
    merged, merged_count = merge_continuation_tables(items)
    lines = serialize_items(merged)
    lines = postprocess_standard_lines(lines, meta)

    out = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n"
    out += "\n".join(lines).strip() + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out, encoding="utf-8")

    report = {
        "source": str(args.docx),
        "images": len(relmap),
        "omml_count": omml_count,
        "omml_converted": math_stats.converted,
        "omml_unconverted": max(0, omml_count - math_stats.converted),
        "omml_unsupported_tags": math_stats.unsupported_tags,
        "omml_errors": math_stats.errors,
        "merged_continuation_tables": merged_count,
        "notes": [
            "本脚本用于初步抽取，封面字段、摘要字段和图表 caption 仍建议校对。",
            "Word 中手工拆开的续表已尽量合并为单个逻辑 table 块；Markdown 中不应保留续表块。",
            "Word 原生公式(OMML)会转换为 LaTeX；若 omml_unconverted > 0 或 omml_errors 非空，必须人工检查对应公式。",
        ],
    }
    (args.output.with_suffix(".report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成：{args.output}")
    print(f"图片数量：{len(relmap)}；OMML 公式数量：{omml_count}；已转换：{math_stats.converted}；合并续表：{merged_count}")


if __name__ == "__main__":
    main()
