import os
import re
from typing import Any, Dict, List, Optional, Tuple


_RE_SINGLE_LINE_COMMENT = re.compile(r"//.*?$", re.MULTILINE)
_RE_MULTI_LINE_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(code: str) -> str:
    code = _RE_MULTI_LINE_COMMENT.sub("", code)
    code = _RE_SINGLE_LINE_COMMENT.sub("", code)
    return code


def _extract_vue_section(content: str, tag: str) -> str:
    # Basic, tolerant extraction for <template>, <script>, <style>.
    pattern = re.compile(rf"<{tag}[^>]*>(.*?)</{tag}>", re.DOTALL | re.IGNORECASE)
    m = pattern.search(content)
    return m.group(1) if m else ""


def _parse_imports(code: str) -> List[str]:
    imports: List[str] = []

    # import x from 'y'
    for m in re.finditer(r"import\s+[^;]*?\s+from\s+['\"]([^'\"]+)['\"]", code):
        imports.append(m.group(1))

    # import 'y'
    for m in re.finditer(r"import\s+['\"]([^'\"]+)['\"]", code):
        imports.append(m.group(1))

    # require('y')
    for m in re.finditer(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", code):
        imports.append(m.group(1))

    return sorted(set(imports))


def _parse_exports(code: str) -> List[str]:
    exports: List[str] = []

    # export default function/class/name
    for m in re.finditer(
        r"export\s+default\s+(?:function\s+([A-Za-z0-9_$]+)|class\s+([A-Za-z0-9_$]+)|([A-Za-z0-9_$]+))",
        code,
    ):
        exports.extend([x for x in m.groups() if x])

    # export function foo / export const foo / export class Foo
    for m in re.finditer(
        r"export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z0-9_$]+)",
        code,
    ):
        exports.append(m.group(1))

    # export { a, b as c }
    for m in re.finditer(r"export\s*{\s*([^}]+)\s*}", code):
        inner = m.group(1)
        # Split on commas, then strip aliases.
        for part in inner.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                exports.append(part.split(" as ")[0].strip())
                exports.append(part.split(" as ")[1].strip())
            else:
                exports.append(part)

    # module.exports = { ... } is too hard to reliably parse; keep simple.
    return sorted(set(exports))


def _parse_functions(code: str) -> List[Dict[str, Any]]:
    """
    Best-effort function/method discovery using regex.
    Returns a list with {name, kind}.
    """
    results: List[Dict[str, Any]] = []

    # function foo(
    for m in re.finditer(r"\bfunction\s+([A-Za-z0-9_$]+)\s*\(", code):
        results.append({"name": m.group(1), "kind": "function"})

    # const foo = (...) =>   (arrow function)
    for m in re.finditer(r"\b([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\(?[^\n=]*?\)?\s*=>", code):
        # This can over-match; keep it tolerant.
        results.append({"name": m.group(1), "kind": "arrow"})

    # class Foo { bar(...) { ... } } and object-style methods.
    # Python regex lookbehinds must be fixed-width, so filter control words after matching.
    control_words = {"if", "for", "while", "switch", "catch", "function", "class", "else"}
    for m in re.finditer(r"\b([A-Za-z0-9_$]+)\s*\([^;]*?\)\s*{", code):
        name = m.group(1)
        if name and name not in control_words:
            results.append({"name": name, "kind": "method"})

    # Deduplicate by (name, kind)
    dedup: List[Dict[str, Any]] = []
    seen = set()
    for r in results:
        key = (r["name"], r["kind"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    return dedup


def _parse_http_calls(code: str) -> List[Dict[str, Any]]:
    """
    Best-effort HTTP API call extraction.
    Returns a list with {method, url, has_payload}.
    """
    calls: List[Dict[str, Any]] = []

    # fetch('url', payload?)
    for m in re.finditer(r"fetch\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*(\{|\[))?", code):
        url = m.group(1)
        has_payload = bool(m.group(2))
        calls.append({"method": "fetch", "url": url, "has_payload": has_payload})

    # axios.get('url' ...)
    for m in re.finditer(r"axios\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", code):
        calls.append({"method": m.group(1).upper(), "url": m.group(2), "has_payload": False})

    # axios({ method: 'POST', url: '...' , data: ... })
    for m in re.finditer(
        r"axios\(\s*{[^}]*method\s*:\s*['\"](GET|POST|PUT|DELETE|PATCH)['\"][^}]*url\s*:\s*['\"]([^'\"]+)['\"]",
        code,
        re.DOTALL,
    ):
        calls.append({"method": m.group(1), "url": m.group(2), "has_payload": True})

    return calls


def _extract_ui_elements(template: str) -> List[Dict[str, Any]]:
    """
    Extract UI element hints from HTML/Vue template.
    This is heuristic: it looks for common tags and accessibility attributes.
    """
    elems: List[Dict[str, Any]] = []

    tag_names = ["button", "input", "img", "a", "select", "textarea", "label", "form", "span", "div"]

    for tag in tag_names:
        for m in re.finditer(rf"<{tag}\b([^>]*)>", template, re.IGNORECASE):
            attrs = m.group(1) or ""
            # Collect some attribute presence flags.
            aria_label = bool(re.search(r"\baria-label\s*=", attrs))
            role = bool(re.search(r"\brole\s*=", attrs))
            click_handler = bool(re.search(r"(@click|v-on:click)\s*=", attrs))
            elems.append(
                {
                    "tag": tag,
                    "has_aria_label": aria_label,
                    "has_role": role,
                    "has_click_handler": click_handler,
                }
            )

    return elems


def parse_script_file(path: str, content: str, ext: str) -> Dict[str, Any]:
    """
    Stage 2 — parse source for:
    - imports
    - exports
    - defined functions/methods
    - HTTP call patterns
    - UI elements
    For Vue: also extract <template>/<script>/<style>.
    """
    raw = content or ""
    code = _strip_comments(raw)

    parsed: Dict[str, Any] = {
        "path": path,
        "ext": ext,
        "imports": [],
        "exports": [],
        "functions": [],
        "http_calls": [],
        "ui_elements": [],
        "vue": None,
        "parse_anomalies": [],
    }

    script_code = code
    template_code = ""
    style_code = ""

    if ext == "vue":
        template_code = _extract_vue_section(raw, "template")
        script_code = _extract_vue_section(raw, "script")
        style_code = _extract_vue_section(raw, "style")

        parsed["vue"] = {
            "has_template": bool(template_code.strip()),
            "has_script": bool(script_code.strip()),
            "has_style": bool(style_code.strip()),
        }

        if not template_code.strip():
            parsed["parse_anomalies"].append("Missing <template> section")
        if not script_code.strip():
            parsed["parse_anomalies"].append("Missing <script> section")

        # For HTTP + functions/imports, prioritize <script>.
        # For UI extraction, prioritize <template>.
        parsed["ui_elements"] = _extract_ui_elements(template_code)
    else:
        # For non-Vue, treat entire file as both code and template.
        template_code = raw
        parsed["ui_elements"] = _extract_ui_elements(template_code)

    parsed["imports"] = _parse_imports(script_code)
    parsed["exports"] = _parse_exports(script_code)
    parsed["functions"] = _parse_functions(script_code)
    parsed["http_calls"] = _parse_http_calls(script_code)

    # Small anomaly: empty file
    if not raw.strip():
        parsed["parse_anomalies"].append("Empty file content")

    return parsed
