# sit-thesis-auto-ai-skill

极简论文转换 skill：自动把 Word/Markdown 转成 LaTeX/PDF；若 LaTeX 编译或版面检查出现问题，再由 AI 根据报告做最小排版修复并重新验证。

## 使用

```bash
python scripts/auto_thesis.py thesis.docx --output build/thesis-latex --compile
```

输出：

- `main.pdf`
- `pipeline-report.json`
- `ai-review.md`

详见 [SKILL.md](SKILL.md)。
