#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from gb7714_2005_refs import first_type, normalize_text, validate_ref  # noqa: E402
from md_to_latex import generate_main_tex, parse_document  # noqa: E402
from word_to_standard_md import ensure_unique_labels, fill_meta_from_lines  # noqa: E402


class StructuralConversionTests(unittest.TestCase):
    def render(self, md: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "sample.md"
            md_path.write_text(md, encoding="utf-8")
            parts = parse_document(md_path)
            tex, _ = generate_main_tex(parts, md_path.parent)
        return tex

    def test_numbered_heading_without_space_is_stripped(self) -> None:
        tex = self.render("""---
schema: sit-thesis-md/v2
title: 测试
---

# 1 绪论

## 1.1 研究背景

### 1.1.2研究意义

正文。
""")
        self.assertIn(r"\subsubsection{研究意义}", tex)
        self.assertNotIn(r"\subsubsection{1.1.2研究意义}", tex)

    def test_explicit_heading_number_controls_latex_depth(self) -> None:
        tex = self.render("""---
schema: sit-thesis-md/v2
title: 测试
---

# 4 系统设计

## 4.3 数据库设计

## 4.3.1 ER图

正文。
""")
        self.assertIn(r"\subsubsection{ER图}", tex)
        self.assertNotIn(r"\subsection{ER图}", tex)

    def test_longtable_does_not_manually_step_table_counter(self) -> None:
        tex = self.render("""---
schema: sit-thesis-md/v2
title: 测试
---

# 4 系统设计

## 4.3.2 核心数据表结构

::: table
caption: 核心数据表字段说明
label: tab:4-1
type: longtable
| 表名 | 字段 | 说明 |
| --- | --- | --- |
| a | b | c |
| a | b | c |
| a | b | c |
| a | b | c |
| a | b | c |
| a | b | c |
| a | b | c |
| a | b | c |
| a | b | c |
:::
""")
        self.assertIn(r"\begin{longtable}", tex)
        self.assertIn(r"\caption{核心数据表字段说明\label{tab:4-1}}\\", tex)
        self.assertNotIn(r"\refstepcounter{table}", tex)

    def test_figures_are_height_limited(self) -> None:
        tex = self.render("""---
schema: sit-thesis-md/v2
title: 测试
---

# 1 绪论

::: figure
src: figures/tall.png
caption: 高截图
label: fig:1-1
width: 0.85\\textwidth
:::
""")
        self.assertIn(r"height=0.72\textheight,keepaspectratio", tex)

    def test_single_cell_code_table_renders_as_code_block(self) -> None:
        tex = self.render("""---
schema: sit-thesis-md/v2
title: 测试
---

# 5 系统实现

代码5.1 数据库初始化核心代码

::: table
caption: 待补充表题
type: longtable
fit: wrap
| import sqlite3 def init_db(): conn = sqlite3.connect('campus_ai.db') cursor = conn.cursor() # 任务记录表 cursor.execute(''' CREATE TABLE IF NOT EXISTS generation_tasks ( task_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL )''') conn.commit() conn.close() |
| --- |
:::
""")
        self.assertIn(r"\footnotesize\ttfamily\raggedright", tex)
        self.assertIn(r"def init\_db", tex)
        self.assertNotIn(r"\begin{longtable}", tex)

    def test_placeholder_captions_are_not_rendered(self) -> None:
        tex = self.render("""---
schema: sit-thesis-md/v2
title: 测试
---

# 1 绪论

::: figure
src: figures/missing.png
caption: 待补充图题
:::

::: table
caption: 待补充表题
| 代码 |
| --- |
| const value = 1; |
:::
""")
        self.assertNotIn("待补充图题", tex)
        self.assertNotIn("待补充表题", tex)
        self.assertNotIn(r"\caption{}", tex)

    def test_fullwidth_terminal_period_is_not_duplicated(self) -> None:
        text = "Wuttke D A. Article[J]. Journal, 2019, 65(3): 242-261．"
        self.assertEqual(normalize_text(text), text)
        self.assertEqual(normalize_text(text + "."), text)

    def test_online_journal_type_is_supported(self) -> None:
        text = normalize_text(
            "孟奇. 面向领域适配的大语言模型研究[J/OL]. 计算机工程与应用, "
            "1-9[2026-04-22]. https://example.com/paper"
        )
        rtype = first_type(text)
        errors, warnings = validate_ref(1, text, rtype)
        self.assertEqual(rtype, "J/OL")
        self.assertNotIn("[1] 文献类型 [J/OL] 不在当前校验器常见类型表中，请人工确认", warnings)
        self.assertEqual(errors, [])

    def test_split_cover_title_continuation_is_preserved(self) -> None:
        meta = {"title": "", "short_title": "", "abstract": {"cn": ""}, "keywords": {"cn": []}}
        fill_meta_from_lines([
            "本科毕业设计(论文)",
            "课题名称: 基于Python的智能健身房",
            "     系统的设计与开发     ",
            "学    院       经济与管理学院        ",
            "基于Python的智能健身房系统的设计与开发",
            "摘要：正文",
            "关键词：智能健身房；管理系统",
        ], meta)
        self.assertEqual(meta["title"], "基于Python的智能健身房系统的设计与开发")
        self.assertEqual(meta["short_title"], "基于Python的智能健身房系统的设计与开发")

    def test_duplicate_labels_are_made_unique(self) -> None:
        lines = ensure_unique_labels([
            "label: fig:5-11",
            "正文",
            "label: fig:5-11",
            "label: tab:2-1",
            "label: fig:5-11",
        ])
        self.assertEqual(lines[0], "label: fig:5-11")
        self.assertEqual(lines[2], "label: fig:5-11-2")
        self.assertEqual(lines[3], "label: tab:2-1")
        self.assertEqual(lines[4], "label: fig:5-11-3")


if __name__ == "__main__":
    unittest.main()
