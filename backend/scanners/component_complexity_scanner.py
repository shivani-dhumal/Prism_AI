"""
component_complexity_scanner.py — Vue component complexity via JS AST + html.parser.
NO regex used anywhere.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import save_component_complexity, save_component_method
from scanners.ast_utils import (
    extract_script_block,
    extract_template_block,
    parse_js_ast,
    count_properties_in_object_key,
    get_object_properties_details,
    find_pascal_tags,
    collect_template_tags,
)


def scan_component_complexity(component_id: int, content: str) -> None:
    totallines = len(content.splitlines())

    # ── Template metrics via html.parser / string scan ───────────────────────
    template_html = extract_template_block(content)
    template_lines = len(template_html.splitlines()) if template_html else 0

    # Pascal-cased child component tags — string scanner, no regex
    child_set = find_pascal_tags(template_html) if template_html else set()
    child_components = len(child_set)

    # ── Script metrics via esprima AST ───────────────────────────────────────
    methods = 0
    computed = 0
    watchers = 0

    script_js = extract_script_block(content)
    script_line_offset = 0
    
    if script_js:
        idx = content.lower().find('<script')
        if idx != -1:
            script_line_offset = content[:idx].count('\n')
            
        script_ast = parse_js_ast(script_js)
        if script_ast:
            details = get_object_properties_details(script_ast, 'methods')
            methods = len(details)
            
            for m in details:
                mlines = max(1, m['line_end'] - max(0, m['line_start'] - 1))
                method_range = f"{max(1, script_line_offset + m['line_start'])}-{max(1, script_line_offset + m['line_end'])}"
                
                save_component_method(component_id, m['name'], method_range, mlines)

            computed = count_properties_in_object_key(script_ast, 'computed')
            watchers = count_properties_in_object_key(script_ast, 'watch')

    # ── Flags ─────────────────────────────────────────────────────────────────
    flags = []

    if totallines > 800:
        flags.append("VERY_LARGE_COMPONENT")
    elif totallines > 500:
        flags.append("LARGE_COMPONENT")

    if methods > 15:
        flags.append("MANY_METHODS")
    if computed > 10:
        flags.append("MANY_COMPUTED")
    if watchers > 5:
        flags.append("MANY_WATCHERS")
    if template_lines > 200:
        flags.append("COMPLEX_TEMPLATE")
    if child_components > 5:
        flags.append("MANY_CHILDREN")

    save_component_complexity(
        component_id,
        totallines,
        methods,
        computed,
        watchers,
        template_lines,
        child_components,
        ", ".join(flags)
    )
