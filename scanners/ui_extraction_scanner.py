"""
ui_extraction_scanner.py — Extract UI text elements via html.parser DOM tree.
NO regex used anywhere.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import save_ui_extraction
from scanners.ast_utils import (
    extract_template_block,
    build_template_tree,
    walk_tree,
    get_node_text,
    strip_vue_bindings,
    strip_html_tags,
)

_ALLOWED_TAGS = {"button", "p", "span", "label",
                 "h1", "h2", "h3", "h4", "h5", "h6"}


def _nearest_div_id(node: dict):
    """Walk up the parent chain and return the first ancestor div's id, or None."""
    parent = node.get('parent')
    while parent:
        if parent.get('tag') == 'div':
            div_id = parent.get('attrs', {}).get('id')
            if div_id:
                return div_id
        parent = parent.get('parent')
    return None


def scan_ui_extraction(component_id: int, file_path: str, content: str) -> None:
    template_html = extract_template_block(content)
    if not template_html:
        return

    tree = build_template_tree(template_html)
    seen = set()

    for node in walk_tree(tree):
        tag = node.get('tag', '')
        if tag not in _ALLOWED_TAGS:
            continue

        # Collect text — strip Vue bindings and nested HTML tags (no regex)
        raw_text = get_node_text(node)
        text = strip_vue_bindings(raw_text)
        text = strip_html_tags(text)

        if not text:
            continue

        css_class = node.get('attrs', {}).get('class', '')
        div_id = _nearest_div_id(node)
        
        start_line = node.get('line', 0)
        end_line = node.get('end_line', start_line)
        line_num = f"{start_line}-{end_line}"

        key = (component_id, tag, text, css_class, div_id, line_num)
        if key in seen:
            continue
        seen.add(key)

        save_ui_extraction(
            component_id=component_id,
            file_path=file_path,
            tag_name=tag,
            text_value=text,
            css_class=css_class,
            div_id=div_id,
            line_number=line_num
        )