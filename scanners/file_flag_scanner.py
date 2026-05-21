"""
file_flag_scanner.py — Generate per-file quality flags using JS AST + html.parser.
NO regex used anywhere.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import save_file_flags
from scanners.ast_utils import (
    extract_script_block,
    extract_template_block,
    parse_js_ast,
    walk_ast,
    get_string_value,
    get_callee_name,
    build_parent_map,
    is_ancestor_loop,
    count_properties_in_object_key,
    collect_template_tags,
    find_pascal_tags,
    count_vue_directives,
)

_HTTP_METHODS = {'get', 'post', 'put', 'delete', 'patch'}
_WRAPPER_PREFIXES = {'api', 'service', 'http'}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _is_api_call(node) -> bool:
    callee_str = get_callee_name(node).lower()
    parts = callee_str.split('.')
    if callee_str == 'fetch':
        return True
    if len(parts) == 2:
        return (parts[0] == 'axios' and parts[1] in _HTTP_METHODS) or \
               (parts[0] in _WRAPPER_PREFIXES and parts[1] in _HTTP_METHODS)
    return False


def _obj_key_count(node) -> int:
    if node and getattr(node, 'type', '') == 'ObjectExpression':
        return len(getattr(node, 'properties', []))
    return 0


def _obj_nesting_depth(node, depth=0) -> int:
    if node is None:
        return depth
    if getattr(node, 'type', '') == 'ObjectExpression':
        depth += 1
        max_child = depth
        for prop in getattr(node, 'properties', []):
            val = getattr(prop, 'value', None)
            max_child = max(max_child, _obj_nesting_depth(val, depth))
        return max_child
    return depth


# ─────────────────────────────────────────────
# MAIN SCANNER
# ─────────────────────────────────────────────

def scan_flags(file_id: int, content: str, ext: str, api_count: int) -> None:
    if ext not in ["vue", "js", "ts", "go"]:
        return

    loc = len(content.splitlines())
    metrics = {"api_count": api_count, "payload_keys_max": 0, "loc": loc}
    flags = {"api": [], "payload": [], "complexity": [], "pattern": [], "ui": [], "risk": []}

    # ── Parse script AST ─────────────────────────────────────────────────────
    script_js = extract_script_block(content) if ext == 'vue' else content
    script_ast = None
    if script_js:
        script_ast = parse_js_ast(script_js)

    # ═══════════════════════════════════════════
    # API FLAGS
    # ═══════════════════════════════════════════
    if api_count >= 3 and api_count < 5:
        flags["api"].append("HIGH_API_USAGE")
    elif api_count >= 5 and api_count < 8:
        flags["api"].append("VERY_HIGH_API_USAGE")
    elif api_count >= 8:
        flags["api"].append("EXCESSIVE_API_USAGE")

    # HEAVY_MOUNTED_API
    if ext == "vue" and script_ast:
        for node in walk_ast(script_ast):
            if getattr(node, 'type', '') != 'Property':
                continue
            key = getattr(getattr(node, 'key', None), 'name', '')
            if key != 'mounted':
                continue
            val = getattr(node, 'value', None)
            if val is None:
                continue
            mounted_api = sum(
                1 for n in walk_ast(val)
                if getattr(n, 'type', '') == 'CallExpression' and _is_api_call(n)
            )
            if mounted_api >= 3:
                flags["api"].append("HEAVY_MOUNTED_API")
            break

    # ═══════════════════════════════════════════
    # PAYLOAD FLAGS   (from AST argument nodes)
    # ═══════════════════════════════════════════
    payload_keys_max = 0
    payload_depth_max = 0
    payload_size_total = 0

    if script_ast:
        for node in walk_ast(script_ast):
            if getattr(node, 'type', '') != 'CallExpression':
                continue
            if not _is_api_call(node):
                continue
            args = getattr(node, 'arguments', [])
            payload_node = args[1] if len(args) > 1 else None
            if payload_node is None:
                continue
            keys  = _obj_key_count(payload_node)
            depth = _obj_nesting_depth(payload_node)
            size  = len(str(payload_node))
            payload_keys_max   = max(payload_keys_max, keys)
            payload_depth_max  = max(payload_depth_max, depth)
            payload_size_total += size

    metrics["payload_keys_max"] = payload_keys_max

    if payload_keys_max > 20:
        flags["payload"].append("VERY_COMPLEX_PAYLOAD")
    elif payload_keys_max > 10:
        flags["payload"].append("COMPLEX_PAYLOAD")
    if payload_depth_max > 3:
        flags["payload"].append("DEEP_NESTED_PAYLOAD")
    if payload_size_total > 1_000_000:
        flags["payload"].append("LARGE_PAYLOAD")

    # ═══════════════════════════════════════════
    # COMPLEXITY FLAGS
    # ═══════════════════════════════════════════
    if loc > 500:
        flags["complexity"].append("LARGE_COMPONENT")

    if script_ast:
        if count_properties_in_object_key(script_ast, 'methods') > 15:
            flags["complexity"].append("MANY_METHODS")
        if count_properties_in_object_key(script_ast, 'computed') > 10:
            flags["complexity"].append("MANY_COMPUTED")
        if count_properties_in_object_key(script_ast, 'watch') > 5:
            flags["complexity"].append("MANY_WATCHERS")

    # ═══════════════════════════════════════════
    # PATTERN FLAGS
    # ═══════════════════════════════════════════
    if script_ast:
        parent_map = build_parent_map(script_ast)
        api_urls = []
        has_then = False
        total_api_nodes = 0

        for node in walk_ast(script_ast):
            if getattr(node, 'type', '') != 'CallExpression':
                continue
            callee_name = get_callee_name(node)
            if callee_name.endswith('.then'):
                has_then = True
            if not _is_api_call(node):
                continue
            total_api_nodes += 1
            if is_ancestor_loop(node, parent_map):
                if "API_IN_LOOP" not in flags["pattern"]:
                    flags["pattern"].append("API_IN_LOOP")
            args = getattr(node, 'arguments', [])
            if args:
                url = get_string_value(args[0])
                if url:
                    api_urls.append(url)

        if total_api_nodes >= 2:
            flags["pattern"].append("API_CHAINING")
        if has_then:
            flags["pattern"].append("DEPENDENT_API_CALLS")
        if len(api_urls) != len(set(api_urls)):
            flags["pattern"].append("DUPLICATE_API_CALLS")

    # ═══════════════════════════════════════════
    # UI FLAGS  (html.parser + string scan — no regex)
    # ═══════════════════════════════════════════
    if ext == "vue":
        template_html = extract_template_block(content)
        if template_html:
            tpl_lines = len(template_html.splitlines())
            if tpl_lines > 200:
                flags["ui"].append("COMPLEX_TEMPLATE")

            # v-if / v-for count via string scanning (count_vue_directives)
            directive_count = count_vue_directives(template_html)
            if directive_count > 3:
                flags["ui"].append("DEEP_NESTED_TEMPLATE")

            # Pascal-case child components via character scanning (find_pascal_tags)
            pascal_children = find_pascal_tags(template_html)
            if len(pascal_children) > 5:
                flags["ui"].append("MANY_CHILDREN")

    # ═══════════════════════════════════════════
    # RISK FLAGS
    # ═══════════════════════════════════════════
    api_flags = flags["api"]
    payload_flags = flags["payload"]
    complexity_flags = flags["complexity"]

    if "HIGH_API_USAGE" in api_flags and "COMPLEX_PAYLOAD" in payload_flags:
        flags["risk"].append("HIGH_RISK_COMPONENT")
    if "VERY_HIGH_API_USAGE" in api_flags and "VERY_COMPLEX_PAYLOAD" in payload_flags:
        flags["risk"].append("CRITICAL_COMPONENT")
    if "HIGH_API_USAGE" in api_flags and "LARGE_COMPONENT" in complexity_flags:
        flags["risk"].append("HEAVY_COMPONENT")
    if ("EXCESSIVE_API_USAGE" in api_flags and
            "VERY_COMPLEX_PAYLOAD" in payload_flags and
            "LARGE_COMPONENT" in complexity_flags):
        flags["risk"].append("MONOLITH_COMPONENT")

    categories = [
        bool(flags["api"]), bool(flags["payload"]), bool(flags["complexity"]),
        bool(flags["pattern"]), bool(flags["ui"])
    ]
    if sum(categories) >= 3:
        flags["risk"].append("COMPLEX_HEAVY_COMPONENT")
    if flags["api"] and flags["payload"] and flags["complexity"]:
        flags["risk"].append("ARCHITECTURE_CONCERN")

    save_file_flags(file_id, metrics, flags)
