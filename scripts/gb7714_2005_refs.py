#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GB/T 7714-2005 参考文献格式规范化与校验。

目标：
- 只做确定性的格式清理与校验，不补写缺失信息，不编造 DOI/页码/出版社。
- 保持条目语义内容不变：作者、题名、刊名/出版社、年份、URL 等原始信息不主动替换。
- 输出机器可读 JSON 报告；默认原地更新 Markdown 中“# 参考文献”章节。
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

REF_HEADING_RE = re.compile(r"^#\s*参考文献\s*$")
NEXT_HEADING_RE = re.compile(r"^#\s+")
REF_START_RE = re.compile(r"^\s*\[(\d+)\]\s*(.*)$")
TYPE_RE = re.compile(r"\[([A-Z]+(?:/[A-Z]+)?)\]")
URL_RE = re.compile(r"https?://\S+", re.I)
YEAR_RE = re.compile(r"(?:^|[^0-9])((?:19|20)\d{2})(?:[^0-9]|$)")
DATE_RE = re.compile(r"\[(?:19|20)\d{2}[-./年](?:0?[1-9]|1[0-2])[-./月](?:0?[1-9]|[12]\d|3[01])日?\]")
PAGES_RE = re.compile(r"[:：]\s*\d+(?:\s*[-–—]\s*\d+)?")
VOL_ISSUE_RE = re.compile(r"[,，]\s*\d+\s*(?:\(\s*[^)]+\s*\))?\s*[:：]")

SUPPORTED_TYPES = {
    "J", "J/OL", "M", "M/OL", "D", "D/OL", "R", "R/OL",
    "S", "S/OL", "EB/OL", "OL", "C", "C/OL", "N", "N/OL", "P", "P/OL",
}


@dataclass
class RefItem:
    number: int
    original: str
    normalized: str
    type: str | None
    changed: bool
    errors: list[str]
    warnings: list[str]


def split_reference_section(lines: list[str]) -> tuple[int | None, int | None]:
    start = None
    for i, line in enumerate(lines):
        if REF_HEADING_RE.match(line.strip()):
            start = i
            break
    if start is None:
        return None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if NEXT_HEADING_RE.match(lines[j].strip()) and not REF_HEADING_RE.match(lines[j].strip()):
            end = j
            break
    return start, end


def parse_refs(ref_lines: Iterable[str]) -> tuple[list[tuple[int, str]], list[str]]:
    refs: list[tuple[int, str]] = []
    section_warnings: list[str] = []
    current_num: int | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_num, current_parts
        if current_num is not None:
            text = " ".join(p.strip() for p in current_parts if p.strip()).strip()
            if text:
                refs.append((current_num, text))
        current_num = None
        current_parts = []

    for raw in ref_lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("---"):
            break
        m = REF_START_RE.match(line)
        if m:
            flush()
            current_num = int(m.group(1))
            current_parts = [m.group(2).strip()]
        elif current_num is not None:
            current_parts.append(line)
        else:
            section_warnings.append(f"未识别的参考文献行：{line[:80]}")
    flush()
    return refs, section_warnings


def normalize_text(text: str) -> str:
    s = text.strip()
    # 只清理格式噪声；不改实体内容。先保护 URL，避免把 https:// 改成 https: //。
    urls: list[str] = []

    def hold_url(m: re.Match[str]) -> str:
        urls.append(m.group(0).rstrip("."))
        suffix = "." if m.group(0).endswith(".") else ""
        return f"@@URL{len(urls)-1}@@" + suffix

    s = URL_RE.sub(hold_url, s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\[\s*([A-Z]+(?:\s*/\s*[A-Z]+)?)\s*\]", lambda m: "[" + m.group(1).replace(" ", "") + "]", s)
    s = re.sub(r"\]\s*\.\s*", r"]. ", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s*:\s*", ": ", s)
    s = re.sub(r"\s*([-–—])\s*", r"\1", s)
    s = re.sub(r"\s+([.;])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    for i, url in enumerate(urls):
        s = s.replace(f"@@URL{i}@@", url)
    s = re.sub(r"([。．])\.+$", r"\1", s)
    if s and s[-1] not in ".。．":
        s += "."
    return s


def first_type(text: str) -> str | None:
    m = TYPE_RE.search(text)
    return m.group(1) if m else None


def has_year(text: str) -> bool:
    return bool(YEAR_RE.search(text))


def validate_ref(num: int, text: str, rtype: str | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    prefix = f"[{num}]"

    if not rtype:
        errors.append(f"{prefix} 缺少文献类型标识，如 [J]/[M]/[D]/[EB/OL]")
        return errors, warnings
    if rtype not in SUPPORTED_TYPES:
        warnings.append(f"{prefix} 文献类型 [{rtype}] 不在当前校验器常见类型表中，请人工确认")
    if not has_year(text):
        errors.append(f"{prefix} 缺少年份")

    # GB/T 7714-2005 基本结构校验：只报缺失，不自动补写。
    if rtype in {"J", "J/OL"}:
        if not PAGES_RE.search(text):
            warnings.append(f"{prefix} 期刊 [{rtype}] 未检测到页码/文章编号 ': 起止页'")
        if not re.search(r"[,，]\s*(?:19|20)\d{2}\s*[,，]", text):
            warnings.append(f"{prefix} 期刊 [{rtype}] 未检测到 '刊名, 年, 卷(期): 页码' 结构")
    elif rtype == "M":
        if ":" not in text:
            warnings.append(f"{prefix} 专著 [M] 未检测到出版地/出版社分隔 ':'")
        if not re.search(r":\s*[^,，]+,\s*(?:19|20)\d{2}", text):
            warnings.append(f"{prefix} 专著 [M] 未检测到 '出版地: 出版者, 年' 结构")
    elif rtype == "D":
        if ":" not in text:
            warnings.append(f"{prefix} 学位论文 [D] 未检测到保存地/保存单位分隔 ':'")
        if not re.search(r":\s*[^,，]+,\s*(?:19|20)\d{2}", text):
            warnings.append(f"{prefix} 学位论文 [D] 未检测到 '保存地: 保存单位, 年' 结构")
    elif rtype == "R":
        if not has_year(text):
            errors.append(f"{prefix} 报告 [R] 缺少年份")
    elif rtype in {"EB/OL", "S/OL", "OL"} or rtype.endswith("/OL"):
        if not URL_RE.search(text):
            errors.append(f"{prefix} 在线资源 [{rtype}] 缺少 URL")
        if not DATE_RE.search(text):
            warnings.append(f"{prefix} 在线资源 [{rtype}] 未检测到引用日期 [YYYY-MM-DD]")

    if re.search(r"\[\d+\]", text):
        warnings.append(f"{prefix} 条目正文中疑似残留编号")
    return errors, warnings


def process_markdown(path: Path, *, write: bool = True) -> dict:
    original_text = path.read_text(encoding="utf-8")
    lines = original_text.splitlines()
    start, end = split_reference_section(lines)
    report: dict = {
        "standard": "GB/T 7714-2005",
        "file": str(path),
        "found_section": start is not None,
        "normalized_count": 0,
        "changed_count": 0,
        "errors": [],
        "warnings": [],
        "items": [],
    }
    if start is None or end is None:
        report["errors"].append("未找到 '# 参考文献' 章节")
        return report

    refs, section_warnings = parse_refs(lines[start + 1:end])
    report["warnings"].extend(section_warnings)
    if not refs:
        report["errors"].append("参考文献章节为空或未识别到 '[n]' 条目")
        return report

    items: list[RefItem] = []
    for num, text in refs:
        normalized = normalize_text(text)
        rtype = first_type(normalized)
        errors, warnings = validate_ref(num, normalized, rtype)
        item = RefItem(
            number=num,
            original=text,
            normalized=normalized,
            type=rtype,
            changed=normalized != text,
            errors=errors,
            warnings=warnings,
        )
        items.append(item)
        report["errors"].extend(errors)
        report["warnings"].extend(warnings)

    numbers = [item.number for item in items]
    if numbers != sorted(numbers):
        report["warnings"].append("参考文献编号不是升序")
    if len(numbers) != len(set(numbers)):
        report["errors"].append("参考文献编号存在重复")
    if numbers and numbers != list(range(min(numbers), max(numbers) + 1)):
        report["warnings"].append("参考文献编号不连续")

    report["normalized_count"] = len(items)
    report["changed_count"] = sum(1 for item in items if item.changed)
    report["items"] = [asdict(item) for item in items]

    if write:
        new_ref_lines: list[str] = [""]
        for item in items:
            new_ref_lines.append(f"[{item.number}] {item.normalized}")
            new_ref_lines.append("")
        new_lines = lines[: start + 1] + new_ref_lines + lines[end:]
        new_text = "\n".join(new_lines).rstrip() + "\n"
        if new_text != original_text:
            path.write_text(new_text, encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="GB/T 7714-2005 参考文献规范化与校验")
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--check", action="store_true", help="只校验，不写回")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    report = process_markdown(args.markdown.resolve(), write=not args.check)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # 不用返回码阻断 PDF 生成；缺信息由 report 明确列出，不能编造。


if __name__ == "__main__":
    main()
