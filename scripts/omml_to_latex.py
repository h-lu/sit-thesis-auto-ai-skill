#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert Word Office Math (OMML) fragments to LaTeX.

This is intentionally deterministic and local: no AI, no network calls.
It covers the OMML structures commonly produced by Word's equation editor
(fractions, scripts, radicals, n-ary operators, delimiters, functions,
accents, bars, matrices and equation arrays). Unknown structural tags are
not silently discarded: their text children are preserved and the tag is
reported in ``unsupported_tags`` for audit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

try:  # python-docx depends on lxml, but keep import local and explicit.
    from lxml import etree
except Exception:  # pragma: no cover
    etree = None  # type: ignore[assignment]

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass
class OmmlConversionStats:
    detected: int = 0
    converted: int = 0
    unsupported_tags: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def unsupported(self, tag: str) -> None:
        self.unsupported_tags[tag] = self.unsupported_tags.get(tag, 0) + 1


LATEX_MATH_CHARS = {
    "\\": r"\backslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
}

SYMBOLS = {
    "×": r"\times", "÷": r"\div", "·": r"\cdot", "⋅": r"\cdot", "±": r"\pm", "∓": r"\mp",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\ne", "≈": r"\approx", "≡": r"\equiv", "∝": r"\propto",
    "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla", "∑": r"\sum", "∏": r"\prod", "∫": r"\int",
    "√": r"\sqrt{}", "→": r"\rightarrow", "←": r"\leftarrow", "↔": r"\leftrightarrow", "⇒": r"\Rightarrow",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq", "∪": r"\cup", "∩": r"\cap",
    "∧": r"\land", "∨": r"\lor", "¬": r"\neg", "∀": r"\forall", "∃": r"\exists",
    "°": r"^\circ", "′": "'", "″": "''",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon", "ζ": r"\zeta",
    "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau",
    "υ": r"\upsilon", "φ": r"\varphi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi",
    "Σ": r"\Sigma", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}

NARY_OPS = {
    "∑": r"\sum", "∏": r"\prod", "∐": r"\coprod", "∫": r"\int", "∮": r"\oint", "⋂": r"\bigcap", "⋃": r"\bigcup",
}

ACCENTS = {
    "̂": r"\hat", "^": r"\hat", "¯": r"\bar", "ˉ": r"\bar", "→": r"\vec", "⃗": r"\vec", "~": r"\tilde", "˜": r"\tilde",
    "˙": r"\dot", "¨": r"\ddot", "⌒": r"\widehat",
}

FUNCTION_NAMES = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "lg", "lim", "max", "min", "sup", "inf"}

IGNORABLE = {
    "argPr", "ctrlPr", "rPr", "naryPr", "fPr", "sSupPr", "sSubPr", "sSubSupPr", "radPr", "dPr", "funcPr",
    "limLowPr", "limUppPr", "accPr", "barPr", "mPr", "mrPr", "eqArrPr", "groupChrPr", "boxPr", "borderBoxPr",
    "phantPr", "degHide", "show", "grow", "brk", "aln", "alnScr", "baseJc", "jc", "lit", "nor", "scr", "sty",
}


def local_name(el) -> str:
    tag = getattr(el, "tag", "")
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def attr_val(el, name: str, default: str = "") -> str:
    if el is None:
        return default
    return el.get(f"{{{M_NS}}}{name}") or el.get(f"{{{W_NS}}}{name}") or el.get(name) or default


def child(el, name: str):
    for c in el:
        if local_name(c) == name:
            return c
    return None


def children(el, name: str) -> list:
    return [c for c in el if local_name(c) == name]


def latex_text(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in SYMBOLS:
            out.append(SYMBOLS[ch])
        else:
            out.append(LATEX_MATH_CHARS.get(ch, ch))
    return "".join(out)


def compact_math(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # Cosmetic cleanup around common binary operators/relations.
    s = re.sub(r"\s*([=+\-])\s*", r" \1 ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class OmmlToLatex:
    def __init__(self, stats: OmmlConversionStats | None = None):
        self.stats = stats or OmmlConversionStats()

    def convert_element(self, el) -> str:
        name = local_name(el)
        if name in {"oMath", "oMathPara"}:
            self.stats.detected += 1 if name == "oMath" else 0
            try:
                tex = compact_math(self._convert_children(el))
                if tex:
                    self.stats.converted += 1 if name == "oMath" else 0
                return tex
            except Exception as exc:  # pragma: no cover - defensive; report instead of dropping.
                self.stats.errors.append(f"OMML 转换失败：{exc}")
                return r"\text{[公式转换失败]}"
        return compact_math(self._convert(el))

    def _convert_children(self, el) -> str:
        parts = [self._convert(c) for c in el]
        return "".join(p for p in parts if p)

    def _slot(self, el, name: str) -> str:
        c = child(el, name)
        return self._convert_children(c) if c is not None else ""

    def _convert(self, el) -> str:  # noqa: C901 - OMML is a tag dispatcher by nature.
        name = local_name(el)
        if name in IGNORABLE:
            return ""
        if name in {"oMath", "oMathPara"}:
            return self.convert_element(el)
        if name in {"r", "e", "num", "den", "deg", "sub", "sup", "lim", "fName"}:
            return self._convert_children(el)
        if name == "t":
            return latex_text(el.text or "")
        if name in {"br"}:
            return r"\\"
        if name == "f":
            num = self._slot(el, "num")
            den = self._slot(el, "den")
            return rf"\frac{{{num}}}{{{den}}}"
        if name == "sSup":
            base = self._slot(el, "e")
            sup = self._slot(el, "sup")
            return rf"{{{base}}}^{{{sup}}}"
        if name == "sSub":
            base = self._slot(el, "e")
            sub = self._slot(el, "sub")
            return rf"{{{base}}}_{{{sub}}}"
        if name == "sSubSup":
            base = self._slot(el, "e")
            sub = self._slot(el, "sub")
            sup = self._slot(el, "sup")
            return rf"{{{base}}}_{{{sub}}}^{{{sup}}}"
        if name == "sPre":
            base = self._slot(el, "e")
            sub = self._slot(el, "sub")
            sup = self._slot(el, "sup")
            return rf"{{}}_{{{sub}}}^{{{sup}}}{{{base}}}"
        if name == "rad":
            deg = self._slot(el, "deg")
            body = self._slot(el, "e")
            return rf"\sqrt[{deg}]{{{body}}}" if deg else rf"\sqrt{{{body}}}"
        if name == "nary":
            pr = child(el, "naryPr")
            chr_el = child(pr, "chr") if pr is not None else None
            op = NARY_OPS.get(attr_val(chr_el, "val", "∑"), latex_text(attr_val(chr_el, "val", "∑")))
            sub = self._slot(el, "sub")
            sup = self._slot(el, "sup")
            body = self._slot(el, "e")
            limits = (rf"_{{{sub}}}" if sub else "") + (rf"^{{{sup}}}" if sup else "")
            return f"{op}{limits} {body}".strip()
        if name == "d":
            pr = child(el, "dPr")
            beg_el = child(pr, "begChr") if pr is not None else None
            end_el = child(pr, "endChr") if pr is not None else None
            beg = attr_val(beg_el, "val", "(")
            end = attr_val(end_el, "val", ")")
            body = self._slot(el, "e")
            return rf"\left{beg}{body}\right{end}"
        if name == "func":
            fname = self._slot(el, "fName").strip()
            arg = self._slot(el, "e")
            macro = "\\" + fname if fname in FUNCTION_NAMES else rf"\operatorname{{{fname}}}"
            return f"{macro} {arg}".strip()
        if name == "limLow":
            base = self._slot(el, "e")
            lim = self._slot(el, "lim")
            if base.strip() == r"\lim":
                return rf"\lim_{{{lim}}}"
            return rf"\underset{{{lim}}}{{{base}}}"
        if name == "limUpp":
            base = self._slot(el, "e")
            lim = self._slot(el, "lim")
            return rf"\overset{{{lim}}}{{{base}}}"
        if name == "acc":
            pr = child(el, "accPr")
            chr_el = child(pr, "chr") if pr is not None else None
            accent = ACCENTS.get(attr_val(chr_el, "val", "^"), r"\hat")
            body = self._slot(el, "e")
            return rf"{accent}{{{body}}}"
        if name == "bar":
            pr = child(el, "barPr")
            pos_el = child(pr, "pos") if pr is not None else None
            body = self._slot(el, "e")
            return rf"\underline{{{body}}}" if attr_val(pos_el, "val", "top") == "bot" else rf"\overline{{{body}}}"
        if name == "m":
            rows: list[str] = []
            for mr in children(el, "mr"):
                cells = [self._convert_children(e) for e in children(mr, "e")]
                rows.append(" & ".join(cells))
            return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
        if name == "eqArr":
            lines = [self._convert_children(e) for e in children(el, "e")]
            return r"\begin{aligned}" + r" \\ ".join(lines) + r"\end{aligned}"
        if name == "groupChr":
            pr = child(el, "groupChrPr")
            chr_el = child(pr, "chr") if pr is not None else None
            ch = attr_val(chr_el, "val", "⏞")
            body = self._slot(el, "e")
            macro = r"\underbrace" if ch in {"⏟", "_"} else r"\overbrace"
            return rf"{macro}{{{body}}}"
        if name in {"box", "borderBox", "phant"}:
            return self._slot(el, "e")

        # Preserve any textual descendants but record the unknown structural tag.
        text = self._convert_children(el)
        if text or name:
            self.stats.unsupported(name)
        return text


def convert_omml_xml(xml: str | bytes, stats: OmmlConversionStats | None = None) -> str:
    if etree is None:  # pragma: no cover
        raise RuntimeError("lxml is required for OMML conversion")
    root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    return OmmlToLatex(stats).convert_element(root)


def iter_omath_elements(root) -> Iterable:
    for el in root.iter():
        if local_name(el) == "oMath":
            yield el


__all__ = ["OmmlConversionStats", "OmmlToLatex", "convert_omml_xml", "iter_omath_elements", "local_name"]
