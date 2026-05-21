"""
ui_scanner.py — Extract interactive UI elements from Vue template using html.parser.

Strategy
--------
1. Extract the <template> block.
2. Build a DOM tree with html.parser.
3. Walk every node; for each tag that is a form element or has an event binding
   (@click, v-on:click, etc.) record (tag, action_type, action_handler).
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import save_ui
from scanners.ast_utils import (
    extract_template_block,
    collect_template_tags,
)

_INTERACTIVE_TAGS = {'button', 'input', 'form', 'select', 'textarea'}


def _parse_event_attrs(attrs: dict) -> tuple:
    """
    Given an attribute dict from html.parser, find the first Vue event binding.
    Returns (action_type, action_handler) or ("None", "None").
    """
    for key, val in attrs.items():
        # @click="handler"  or  v-on:click="handler"
        if key.startswith('@'):
            event = key[1:]
            return event, (val or "None")
        if key.startswith('v-on:'):
            event = key[5:]
            return event, (val or "None")
    return "None", "None"


def scan_ui_elements(component_id: int, content: str) -> None:
    template_html = extract_template_block(content)
    if not template_html:
        return

    tags = collect_template_tags(template_html)

    for entry in tags:
        tag = entry['tag']
        attrs = entry['attrs']

        action_type, action_handler = _parse_event_attrs(attrs)

        # Only save interactive or event-bound elements
        if action_type != "None" or tag in _INTERACTIVE_TAGS:
            save_ui(component_id, tag, action_type, action_handler)