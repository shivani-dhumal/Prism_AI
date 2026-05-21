"""
api_scanner.py — Detect API calls using the JS AST (esprima).

Strategy
--------
Parse the <script> block of a Vue SFC (or raw JS/TS) with esprima, then walk every
CallExpression node to detect:
  1. axios.METHOD(url, payload)
  2. fetch(url, { method, body })
  3. new MQL().setActivity(...).setData(...).fetch()   [chained]
  4. api/service/http.METHOD(url, payload)             [wrapper]

URL and payload are harvested directly from the AST argument nodes.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import save_api
from .ast_utils import (
    extract_script_block,
    parse_js_ast,
    walk_ast,
    get_string_value,
    get_callee_name,
)

import esprima
import json


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

_HTTP_METHODS = {'get', 'post', 'put', 'delete', 'patch', 'head', 'options'}
_WRAPPER_PREFIXES = {'api', 'service', 'http'}


def _node_to_source(node, var_map=None, depth=0) -> str:
    """
    Best-effort serialization of an argument AST node to a readable string.
    Handles: Literal, Identifier, ObjectExpression (shallow), TemplateLiteral.
    """
    if node is None or depth > 6:
        return "N/A"
    t = getattr(node, 'type', '')

    if t == 'Literal':
        return str(node.value)

    if t == 'Identifier':
        if var_map and node.name in var_map:
            return _node_to_source(var_map[node.name], var_map, depth + 1)
        return node.name

    if t == 'ObjectExpression':
        pairs = []
        for prop in getattr(node, 'properties', []):
            k = getattr(getattr(prop, 'key', None), 'name', '?')
            v = _node_to_source(getattr(prop, 'value', None), var_map, depth + 1)
            pairs.append(f"{k}: {v}")
        return '{' + ', '.join(pairs) + '}'

    if t == 'TemplateLiteral':
        quasis = getattr(node, 'quasis', [])
        return '`' + ''.join(getattr(q, 'value', {}).get('raw', '') for q in quasis) + '`'

    if t == 'CallExpression':
        return get_callee_name(node) + '(...)'

    if t == 'MemberExpression':
        obj = _node_to_source(getattr(node, 'object', None), var_map, depth + 1)
        prop = getattr(node, 'property', None)
        if getattr(node, 'computed', False):
            prop_str = _node_to_source(prop, var_map, depth + 1)
            return f"{obj}[{prop_str}]"
        else:
            prop_name = getattr(prop, 'name', '?') if getattr(prop, 'type', '') == 'Identifier' else _node_to_source(prop, var_map, depth + 1)
            return f"{obj}.{prop_name}"

    if t == 'ThisExpression':
        return 'this'

    return "N/A"


def _extract_fetch_options(options_node) -> tuple:
    """
    Given the second argument to fetch() (an ObjectExpression), extract
    (method, payload) strings.
    """
    method = "GET"
    payload = "N/A"

    if options_node is None or getattr(options_node, 'type', '') != 'ObjectExpression':
        return method, payload

    for prop in getattr(options_node, 'properties', []):
        key = getattr(getattr(prop, 'key', None), 'name', '')
        val = getattr(prop, 'value', None)
        if key == 'method':
            method = get_string_value(val).upper() or method
        elif key == 'body':
            payload = _node_to_source(val, var_map=None)

    return method, payload


# ─────────────────────────────────────────────
# MQL CHAIN DETECTION
# ─────────────────────────────────────────────

def _find_mql_chains(script_ast, var_map=None) -> list:
    """
    Find patterns like:  new MQL().setActivity('X').setData({...}).fetch()
    Returns list of (activity, payload) tuples.
    """
    results = []
    for node in walk_ast(script_ast):
        if getattr(node, 'type', '') != 'CallExpression':
            continue
        callee = getattr(node, 'callee', None)
        if callee is None:
            continue
        # The outer call must end with .fetch()
        if callee.type != 'MemberExpression':
            continue
        prop = getattr(callee, 'property', None)
        if not prop or getattr(prop, 'name', '') != 'fetch':
            continue

        # Walk up the chain to collect .setActivity and .setData calls
        activity = "UNKNOWN_ACTIVITY"
        payload = "N/A"
        chain_node = callee.object  # the part before .fetch()

        while chain_node and getattr(chain_node, 'type', '') == 'CallExpression':
            chain_callee = getattr(chain_node, 'callee', None)
            if chain_callee and chain_callee.type == 'MemberExpression':
                method_name = getattr(getattr(chain_callee, 'property', None), 'name', '')
                args = getattr(chain_node, 'arguments', [])
                if method_name == 'setActivity' and args:
                    activity = get_string_value(args[0]) or activity
                elif method_name == 'setData' and args:
                    payload = _node_to_source(args[0], var_map)
                chain_node = chain_callee.object
            else:
                break

        # Confirm there's a `new MQL()` at the root of the chain
        root = chain_node
        if root and getattr(root, 'type', '') == 'NewExpression':
            ctor = getattr(root, 'callee', None)
            if ctor and getattr(ctor, 'name', '') == 'MQL':
                results.append((activity, payload))

    return results


# ─────────────────────────────────────────────
# MAIN SCANNER
# ─────────────────────────────────────────────

def _build_variable_map(script_ast) -> dict:
    """
    Build a mapping of variable names to their AST nodes for payload resolution.
    Looks for VariableDeclarator nodes.
    """
    var_map = {}
    for node in walk_ast(script_ast):
        if getattr(node, 'type', '') == 'VariableDeclarator':
            id_node = getattr(node, 'id', None)
            init_node = getattr(node, 'init', None)
            if id_node and getattr(id_node, 'type', '') == 'Identifier' and init_node:
                var_map[id_node.name] = init_node
    return var_map


def scan_apis(file_id: int, content: str, ext: str = None) -> int:
    """
    Parse the JS script block with esprima, walk every CallExpression, and save
    detected API calls.  Returns the total number of API calls found.
    Falls back to text-search when esprima cannot parse the file.
    """
    api_count = 0

    script_js = extract_script_block(content) if ext == 'vue' else content
    if not script_js:
        return 0

    script_ast = parse_js_ast(script_js)

    # ── FALLBACK: text scan when AST fails ───────────────────────────────────
    if script_ast is None:
        return _scan_by_text(file_id, script_js)

    var_map = _build_variable_map(script_ast)

    # ── 1. MQL chains (need separate traversal) ──────────────────────────────
    for activity, payload in _find_mql_chains(script_ast, var_map):
        save_api(file_id, "POST", activity, payload)
        api_count += 1

    # ── 2. Walk every CallExpression ─────────────────────────────────────────
    for node in walk_ast(script_ast):
        if getattr(node, 'type', '') != 'CallExpression':
            continue

        callee_str = get_callee_name(node)
        args = getattr(node, 'arguments', [])

        # axios.METHOD(url, payload)
        parts = callee_str.lower().split('.')
        if len(parts) == 2 and parts[0] == 'axios' and parts[1] in _HTTP_METHODS:
            method = parts[1].upper()
            url = get_string_value(args[0]) if args else "N/A"
            payload = _node_to_source(args[1], var_map) if len(args) > 1 else "N/A"
            save_api(file_id, method, url, payload)
            api_count += 1
            continue

        # fetch(url, options)
        if callee_str.lower() == 'fetch':
            url = get_string_value(args[0]) if args else "N/A"
            options = args[1] if len(args) > 1 else None
            method, payload = _extract_fetch_options(options)
            save_api(file_id, method, url, payload)
            api_count += 1
            continue

        # api/service/http.METHOD(url, payload)
        if (len(parts) == 2
                and parts[0] in _WRAPPER_PREFIXES
                and parts[1] in _HTTP_METHODS):
            method = parts[1].upper()
            url = get_string_value(args[0]) if args else "N/A"
            payload = _node_to_source(args[1], var_map) if len(args) > 1 else "N/A"
            save_api(file_id, method, url, payload)
            api_count += 1
            continue

    return api_count


# ─────────────────────────────────────────────
# TEXT-SCAN FALLBACK  (for files esprima cannot parse)
# ─────────────────────────────────────────────

def _scan_by_text(file_id: int, script_js: str) -> int:
    """
    Line-by-line text scan fallback used when esprima fails.
    Detects:
      • new MQL()  …  .setActivity('X')  …  .fetch()
      • axios.METHOD(url)
      • fetch(url)
      • api/service/http.METHOD(url)
    Returns the number of API calls saved.
    """
    api_count = 0
    lines = script_js.splitlines()

    # ── MQL: collect setActivity + setData values between new MQL() and .fetch()
    in_mql = False
    activity = "UNKNOWN_ACTIVITY"
    payload = "N/A"

    # Pre-scan: build a simple variable map from lines like: let data = {...}
    text_var_map = {}
    brace_collector = None   # (var_name, collected_text, brace_depth)
    for line in lines:
        s = line.strip()
        # Detect: let/const/var xyz = { ... }
        for kw in ('let ', 'const ', 'var '):
            if s.startswith(kw) and '=' in s:
                after_kw = s[len(kw):].strip()
                eq_idx = after_kw.find('=')
                if eq_idx > 0:
                    var_name = after_kw[:eq_idx].strip()
                    rhs = after_kw[eq_idx+1:].strip()
                    if rhs.startswith('{'):
                        if rhs.endswith('}') or rhs.endswith('};') or rhs.endswith('},'):
                            text_var_map[var_name] = rhs.rstrip(';').rstrip(',')
                        else:
                            brace_collector = (var_name, rhs, rhs.count('{') - rhs.count('}'))
                    elif not rhs.startswith('{'):
                        text_var_map[var_name] = rhs.rstrip(';').rstrip(',')
                break
        # Continue collecting multi-line objects
        if brace_collector and not s.startswith(('let ', 'const ', 'var ')):
            vn, collected, depth = brace_collector
            collected += ' ' + s
            depth += s.count('{') - s.count('}')
            if depth <= 0:
                text_var_map[vn] = collected.rstrip(';').rstrip(',')
                brace_collector = None
            else:
                brace_collector = (vn, collected, depth)

    for line in lines:
        s = line.strip()
        # Detect start of a new MQL() chain
        if 'new MQL(' in s or 'new MQL()' in s:
            in_mql = True
            activity = "UNKNOWN_ACTIVITY"
            payload = "N/A"
        if in_mql:
            # Extract .setActivity('...')
            if '.setActivity(' in s:
                for q in ('"', "'"):
                    inner_start = s.find('.setActivity(') + len('.setActivity(')
                    chunk = s[inner_start:]
                    qi = chunk.find(q)
                    if qi != -1:
                        qi2 = chunk.find(q, qi + 1)
                        if qi2 != -1:
                            activity = chunk[qi + 1:qi2]
                            break

            # Extract .setData({...}) or .setData(varName)
            if '.setData(' in s:
                data_start = s.find('.setData(') + len('.setData(')
                data_chunk = s[data_start:].strip()
                if data_chunk.startswith('{'):
                    # Inline object — grab until matching }
                    depth = 0
                    end_idx = 0
                    for ci, ch in enumerate(data_chunk):
                        if ch == '{': depth += 1
                        elif ch == '}': depth -= 1
                        if depth == 0:
                            end_idx = ci + 1
                            break
                    if end_idx > 0:
                        payload = data_chunk[:end_idx]
                    else:
                        payload = data_chunk.rstrip(')').rstrip(',')
                else:
                    # Variable name — resolve it
                    var_name = data_chunk.split(')')[0].strip()
                    if var_name in text_var_map:
                        payload = text_var_map[var_name]
                    else:
                        payload = var_name

            # Detect .fetch() ending the chain
            if s.startswith('.fetch(') or s == '.fetch()':
                save_api(file_id, "POST", activity, payload)
                api_count += 1
                in_mql = False
                activity = "UNKNOWN_ACTIVITY"
                payload = "N/A"

    # ── axios.METHOD / api.METHOD / service.METHOD ────────────────────────────
    for line in lines:
        s = line.strip()
        for prefix in ('axios', 'api', 'service', 'http'):
            for method in _HTTP_METHODS:
                pattern = f'{prefix}.{method}('
                if pattern in s.lower():
                    # Extract URL: first string literal argument
                    idx = s.lower().find(pattern) + len(pattern)
                    chunk = s[idx:].strip()
                    url = "N/A"
                    for q in ('"', "'", '`'):
                        if chunk.startswith(q):
                            end = chunk.find(q, 1)
                            if end != -1:
                                url = chunk[1:end]
                            break
                    save_api(file_id, method.upper(), url, "N/A")
                    api_count += 1

    # ── standalone fetch(url) ─────────────────────────────────────────────────
    for line in lines:
        s = line.strip()
        if s.startswith('fetch(') or ' fetch(' in s or '=fetch(' in s.replace(' ', ''):
            # skip .fetch() — already caught above
            if '.fetch(' in s:
                continue
            idx = s.find('fetch(') + len('fetch(')
            chunk = s[idx:].strip()
            url = "N/A"
            for q in ('"', "'", '`'):
                if chunk.startswith(q):
                    end = chunk.find(q, 1)
                    if end != -1:
                        url = chunk[1:end]
                    break
            save_api(file_id, "GET", url, "N/A")
            api_count += 1

    return api_count

