"""
component_scanner.py — Extract Vue component name using the JS AST (esprima).

Strategy
--------
1. Extract the <script> block from the Vue SFC content.
2. Parse it with esprima into a JS AST.
3. Walk every node; find the exported ObjectExpression (default export).
4. Inside that object, look for a Property whose key is 'name'.
5. Return its string literal value as the component name.
Fallback: use the filename stem (same as before).
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import save_component
from scanners.ast_utils import (
    extract_script_block,
    parse_js_ast,
    walk_ast,
    get_string_value,
)


def _find_component_name(script_ast) -> str:
    """
    Walk the JS AST and return the value of the 'name' property
    inside the first ObjectExpression that appears to be a Vue component
    options object (exported or just the first ObjectExpression in the file).
    Returns empty string if not found.
    """
    for node in walk_ast(script_ast):
        node_type = getattr(node, 'type', '')

        # Look for Property nodes with key == 'name' and a string value
        if node_type == 'Property':
            key_node = getattr(node, 'key', None)
            val_node = getattr(node, 'value', None)
            if key_node is None or val_node is None:
                continue

            key_name = getattr(key_node, 'name', None) or get_string_value(key_node)
            if key_name == 'name':
                val = get_string_value(val_node)
                if val:
                    return val

    return ""


def scan_components(file_id, content: str, file_name: str) -> int:
    """
    Determine the Vue component name via AST, save it, and return component_id.
    """
    comp_name = ""

    script_js = extract_script_block(content)
    if script_js:
        script_ast = parse_js_ast(script_js)
        if script_ast:
            comp_name = _find_component_name(script_ast)

    # Fallback: use filename stem
    if not comp_name:
        comp_name = os.path.splitext(file_name)[0]

    return save_component(file_id, comp_name)