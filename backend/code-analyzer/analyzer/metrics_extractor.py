import re
from typing import Any, Dict, List


_RE_DECISION_IF = re.compile(r"\bif\s*\(")
_RE_DECISION_ELSE_IF = re.compile(r"\belse\s+if\s*\(")
_RE_DECISION_FOR = re.compile(r"\bfor\s*\(")
_RE_DECISION_WHILE = re.compile(r"\bwhile\s*\(")
_RE_DECISION_CASE = re.compile(r"\bcase\s+")
_RE_DECISION_CATCH = re.compile(r"\bcatch\s*\(")
_RE_DECISION_TERNARY = re.compile(r"\?\s*[^:\n]+:")  # very rough


def _count_hex_colors(s: str) -> int:
    # Counts things like #fff / #ffffff
    return len(re.findall(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})(?![0-9a-fA-F])", s))


def _max_brace_depth(code: str) -> int:
    depth = 0
    max_depth = 0
    in_string: str | None = None
    escape = False

    for ch in code:
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == in_string:
                in_string = None
            continue

        if ch in ("'", '"', "`"):
            in_string = ch
            continue

        if ch == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "}":
            depth = max(0, depth - 1)

    return max_depth


def _approx_cyclomatic_complexity(code: str) -> int:
    # Start from 1 baseline (common CC convention).
    branches = 0
    branches += len(_RE_DECISION_IF.findall(code))
    branches += len(_RE_DECISION_ELSE_IF.findall(code))
    branches += len(_RE_DECISION_FOR.findall(code))
    branches += len(_RE_DECISION_WHILE.findall(code))
    branches += len(_RE_DECISION_CASE.findall(code))
    branches += len(_RE_DECISION_CATCH.findall(code))

    # Logical operators often increase branching.
    branches += code.count("&&")
    branches += code.count("||")
    branches += len(_RE_DECISION_TERNARY.findall(code))

    return max(1, 1 + branches)


def _approx_cognitive_complexity(code: str) -> int:
    """
    Approximation:
    - count decisions
    - add nesting depth penalty (decision nested deeper -> higher score)
    """
    max_depth = _max_brace_depth(code)

    # Decision density.
    decisions = (
        len(_RE_DECISION_IF.findall(code))
        + len(_RE_DECISION_ELSE_IF.findall(code))
        + len(_RE_DECISION_FOR.findall(code))
        + len(_RE_DECISION_WHILE.findall(code))
        + len(_RE_DECISION_CASE.findall(code))
        + len(_RE_DECISION_CATCH.findall(code))
        + code.count("&&")
        + code.count("||")
        + len(_RE_DECISION_TERNARY.findall(code))
    )

    # Nesting penalty (stronger than baseline cyclomatic to reflect “cognitive” intent).
    nesting_penalty = max_depth * 2

    return decisions + nesting_penalty


def _extract_template_like_sections(content: str, ext: str) -> Dict[str, str]:
    if ext != "vue":
        return {"template": content}
    # Minimal extraction of <template> for A11Y checks.
    m = re.search(r"<template[^>]*>(.*?)</template>", content, flags=re.DOTALL | re.IGNORECASE)
    template = m.group(1) if m else ""
    return {"template": template}


def _accessibility_metrics(content: str, parsed: Dict[str, Any], ext: str) -> Dict[str, Any]:
    sections = _extract_template_like_sections(content, ext=ext)
    template = sections["template"] or content

    # Missing alt on <img>
    missing_alt = 0
    for m in re.finditer(r"<img\b([^>]*)>", template, re.IGNORECASE):
        attrs = m.group(1) or ""
        has_alt = bool(re.search(r"\balt\s*=", attrs, flags=re.IGNORECASE))
        if not has_alt:
            missing_alt += 1

    # Unlabeled <input>
    unlabeled_inputs = 0
    for m in re.finditer(r"<input\b([^>]*)>", template, re.IGNORECASE):
        attrs = m.group(1) or ""
        has_aria_label = bool(re.search(r"\baria-label\s*=", attrs, flags=re.IGNORECASE))
        has_aria_labelledby = bool(re.search(r"\baria-labelledby\s*=", attrs, flags=re.IGNORECASE))
        has_placeholder = bool(re.search(r"\bplaceholder\s*=", attrs, flags=re.IGNORECASE))
        has_id_or_name = bool(re.search(r"\b(id|name)\s*=", attrs, flags=re.IGNORECASE))
        if not (has_aria_label or has_aria_labelledby or has_placeholder or has_id_or_name):
            unlabeled_inputs += 1

    # Clickable elements without aria-label/role
    clickable_without_aria = 0
    for e in parsed.get("ui_elements", []) or []:
        if e.get("has_click_handler") and not (e.get("has_aria_label") or e.get("has_role")):
            clickable_without_aria += 1

    # Inline hardcoded colors (style="...")
    # Covers hex colors and common CSS color patterns.
    inline_styles = re.findall(r'\bstyle\s*=\s*["\']([^"\']*)["\']', content, flags=re.IGNORECASE)
    inline_color_hits = 0
    for st in inline_styles:
        if re.search(r"(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})|color\s*:|background\s*:|rgba?\(|hsla?\()", st):
            inline_color_hits += 1
    inline_hardcoded_colors = inline_color_hits + _count_hex_colors(content)

    # Return flags for gating.
    flags: List[str] = []
    if missing_alt > 0:
        flags.append("missing_alt_tags")
    if unlabeled_inputs > 0:
        flags.append("unlabeled_inputs")
    if clickable_without_aria > 0:
        flags.append("clickable_without_aria")
    if inline_hardcoded_colors > 0:
        flags.append("hardcoded_inline_colors")

    return {
        "missing_alt_tags": missing_alt,
        "unlabeled_inputs": unlabeled_inputs,
        "clickable_without_aria": clickable_without_aria,
        "hardcoded_inline_colors": inline_hardcoded_colors,
        "flags": flags,
    }


def compute_metrics(path: str, content: str, parsed: Dict[str, Any], ext: str) -> Dict[str, Any]:
    """
    Stage 3 — compute per-file quality metrics and accessibility heuristics.
    """
    code = content or ""

    cyclomatic = _approx_cyclomatic_complexity(code)
    cognitive = _approx_cognitive_complexity(code)
    max_depth = _max_brace_depth(code)

    method_count = len(parsed.get("functions", []) or [])
    api_coupling_count = len(parsed.get("http_calls", []) or [])

    a11y = _accessibility_metrics(content=code, parsed=parsed, ext=ext)
    anomalies = parsed.get("parse_anomalies", []) or []

    metrics: Dict[str, Any] = {
        "path": path,
        "ext": ext,
        "cyclomatic_complexity": cyclomatic,
        "cognitive_complexity": cognitive,
        "max_nesting_depth": max_depth,
        "method_count": method_count,
        "api_coupling_count": api_coupling_count,
        "accessibility": a11y,
        "parse_anomalies": anomalies,
    }

    return metrics

