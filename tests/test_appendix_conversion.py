#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from md_to_latex import parse_document, generate_main_tex  # noqa: E402


class AppendixConversionTests(unittest.TestCase):
    def test_appendix_python_comments_are_not_sections(self) -> None:
        md = """---
schema: sit-thesis-md/v2
title: 测试
---

# 1 绪论

正文。

# 附录

import pandas as pd

# 读取原始数据

df = pd.DataFrame()
"""
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "sample.md"
            md_path.write_text(md, encoding="utf-8")
            parts = parse_document(md_path)
            tex, _ = generate_main_tex(parts, md_path.parent)

        appendix = tex.split(r"\begin{appendixmaterial}", 1)[1].split(r"\end{appendixmaterial}", 1)[0]
        self.assertNotIn(r"\section{读取原始数据}", appendix)
        self.assertIn(r"\# 读取原始数据", appendix)


if __name__ == "__main__":
    unittest.main()
