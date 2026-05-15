---
name: sit-thesis-auto-ai
description: 极简论文转换 skill：自动把 Word/Markdown 转成 LaTeX/PDF；若 LaTeX 编译或版面检查出现问题，再让 AI 根据报告做最小排版修复。
---

# 论文自动转换 + AI 修复

这是一个完全独立的极简 skill。它只做两件事：

1. **自动转换**
   用脚本完成 `Word/Markdown -> 标准 Markdown -> 参考文献 GB/T 7714-2005 规范化/校验 -> LaTeX -> PDF`。

2. **AI 自动修复 LaTeX 问题**
   如果自动报告发现编译错误、缺字、正文 overfull、表格 overfull、图片缺失等问题，AI 必须立刻修复 LaTeX/模板/断行规则，并重新运行流水线验证。

## 禁止

- 不改论文正文内容。
- 不改参考文献条目内容。
- 不替用户补写、改写、润色。
- 不让 AI 参与正常转换主流程。

## 使用

```bash
python scripts/auto_thesis.py thesis.docx --output build/thesis-latex --compile
```

输出：

- `main.pdf`
- `pipeline-report.json`
- `ai-review.md`

如果 `issues` 不为空，不要把 `ai-review.md` 交给用户后停止；继续由 AI 自动修改并重跑，直到问题消失，或明确说明剩余问题为什么不能自动修。

## 内置组件

- `scripts/auto_thesis.py`：唯一推荐入口。
- `scripts/run_thesis_pipeline.py`：自动流水线。
- `scripts/word_to_standard_md.py`：Word 抽取。
- `scripts/md_to_latex.py`：Markdown 转 LaTeX。
- `assets/sit-latex-thesis-template/sithesis.cls`：LaTeX 模板。

## 参考文献 GB/T 7714-2005

流水线会在生成 LaTeX 前运行 `scripts/gb7714_2005_refs.py`：

- 只做确定性格式清理和校验，不编造缺失信息。
- 可自动统一空格、类型标识 `[J]`/`[M]`/`[EB/OL]`、标点和结尾句点等格式噪声。
- 会检查常见 GB/T 7714-2005 结构：期刊、专著、学位论文、报告、在线资源等。
- 缺年份、缺文献类型、在线资源缺 URL 等会写入 `*.gb7714-2005-report.json` 和 `pipeline-report.json`。
- 缺页码、缺出版地/出版社、在线资源缺引用日期等会作为 warning；不能自动补写，需人工确认或联网查证。

## AI 介入条件

只有报告里出现以下问题才让 AI 处理：

- LaTeX 编译失败
- 缺字
- 正文 overfull
- 表格 overfull
- 图片缺失
- 用户指出某页版面异常

宽表已自动换行的提示只做记录；真正的 LaTeX overfull 必须自动修复。
