"""
ast_utils.py — Shared AST utilities for the folder analysyis scanner suite.
NO regex (re module) used anywhere.

Strategy
--------
* Vue <script> blocks  → parsed via `esprima` (JS AST)
* Vue <template> HTML  → walked via Python's built-in `html.parser`
* Block extraction     → plain string search (find/split) — no regex
"""

import ast
import esprima
from html.parser import HTMLParser


# ─────────────────────────────────────────────
# VUE BLOCK EXTRACTORS  (string-only, no regex)
# ─────────────────────────────────────────────

def _extract_block_with_line(content: str, open_tag: str, close_tag: str) -> tuple[str, int]:
    """
    Returns the block text and the line offset (0-indexed) where the inner text starts.
    """
    low = content.lower()
    start_pos = low.find(open_tag.lower())
    if start_pos == -1:
        return "", 0
    gt_pos = content.find('>', start_pos)
    if gt_pos == -1:
        return "", 0
    inner_start = gt_pos + 1
    end_pos = low.find(close_tag.lower(), inner_start)
    if end_pos == -1:
        return "", 0
    line_offset = content[:inner_start].count('\n')
    return content[inner_start:end_pos], line_offset

def _extract_block(content: str, open_tag: str, close_tag: str) -> str:
    text, _ = _extract_block_with_line(content, open_tag, close_tag)
    return text


def extract_template_block_with_line(content: str) -> tuple[str, int]:
    return _extract_block_with_line(content, '<template>', '</template>')

def extract_style_block_with_line(content: str) -> tuple[str, int]:
    return _extract_block_with_line(content, '<style', '</style>')

def extract_script_block(content: str) -> str:
    """Return the raw JS inside the first <script> tag of a Vue SFC."""
    return _extract_block(content, '<script', '</script>').strip()


def extract_template_block(content: str) -> str:
    """Return the raw HTML inside the <template> tag of a Vue SFC."""
    return _extract_block(content, '<template>', '</template>')


def extract_style_block(content: str) -> str:
    """Return the raw CSS inside the <style> tag of a Vue SFC."""
    return _extract_block(content, '<style', '</style>')


# ─────────────────────────────────────────────
# JAVASCRIPT AST (via esprima)
# ─────────────────────────────────────────────

def parse_js_ast(js_code: str):
    """
    Parse a JS/TS string with esprima and return the Script AST.
    Returns None on parse failure.
    """
    try:
        return esprima.parseScript(js_code, tolerant=True, loc=True)
    except Exception:
        try:
            return esprima.parseModule(js_code, tolerant=True, loc=True)
        except Exception:
            return None


def walk_ast(node):
    """Recursively yield every node in an esprima AST tree."""
    if node is None:
        return
    yield node
    if hasattr(node, '__dict__'):
        children = node.__dict__.values()
    elif isinstance(node, dict):
        children = node.values()
    else:
        children = []

    for child in children:
        if hasattr(child, 'type'):
            yield from walk_ast(child)
        elif isinstance(child, list):
            for item in child:
                if hasattr(item, 'type') or isinstance(item, dict):
                    yield from walk_ast(item)


def get_string_value(node) -> str:
    """Safely extract a string literal value from an esprima Literal node."""
    if node is None:
        return ""
    if hasattr(node, 'type') and node.type == 'Literal':
        v = node.value
        return str(v) if isinstance(v, str) else ""
    return ""


def get_callee_name(node) -> str:
    """
    Given a CallExpression node, return a dotted string like 'axios.get' or 'fetch'.
    """
    callee = getattr(node, 'callee', None)
    if callee is None:
        return ""
    if callee.type == 'Identifier':
        return callee.name
    if callee.type == 'MemberExpression':
        obj = getattr(callee, 'object', None)
        prop = getattr(callee, 'property', None)
        obj_name = obj.name if obj and obj.type == 'Identifier' else ""
        prop_name = prop.name if prop and prop.type == 'Identifier' else ""
        return f"{obj_name}.{prop_name}" if obj_name and prop_name else ""
    return ""


def is_ancestor_loop(node, parent_map: dict) -> bool:
    """Return True if `node` has a loop ancestor in the parent_map."""
    loop_types = {'ForStatement', 'ForInStatement', 'ForOfStatement', 'WhileStatement'}
    current = parent_map.get(id(node))
    while current is not None:
        if getattr(current, 'type', '') in loop_types:
            return True
        current = parent_map.get(id(current))
    return False


def build_parent_map(root) -> dict:
    """Walk the AST and build a dict mapping id(child) → parent."""
    parent_map = {}
    def _walk(node, parent):
        parent_map[id(node)] = parent
        if hasattr(node, '__dict__'):
            children = node.__dict__.values()
        elif isinstance(node, dict):
            children = node.values()
        else:
            return
        for child in children:
            if hasattr(child, 'type'):
                _walk(child, node)
            elif isinstance(child, list):
                for item in child:
                    if hasattr(item, 'type'):
                        _walk(item, node)
    _walk(root, None)
    return parent_map


def count_properties_in_object_key(script_ast, key_name: str) -> int:
    """
    Walk the JS AST and count child properties inside the ObjectExpression
    whose key matches key_name (e.g. 'methods', 'computed', 'watch').
    """
    for node in walk_ast(script_ast):
        if not (hasattr(node, 'type') and node.type == 'Property'):
            continue
        prop_key = getattr(node, 'key', None)
        if prop_key is None:
            continue
        key = getattr(prop_key, 'name', None) or get_string_value(prop_key)
        if key != key_name:
            continue
        val = getattr(node, 'value', None)
        if val and val.type == 'ObjectExpression':
            return len(val.properties)
    return 0


def get_object_properties_details(script_ast, key_name: str) -> list:
    """
    Walk the JS AST and find child properties inside the ObjectExpression
    whose key matches key_name (e.g. 'methods').
    Returns a list of dicts: {"name": str, "line_start": int, "line_end": int}
    """
    details = []
    for node in walk_ast(script_ast):
        if not (hasattr(node, 'type') and node.type == 'Property'):
            continue
        prop_key = getattr(node, 'key', None)
        if prop_key is None:
            continue
        key = getattr(prop_key, 'name', None) or get_string_value(prop_key)
        if key != key_name:
            continue
        val = getattr(node, 'value', None)
        if val and val.type == 'ObjectExpression':
            for sub_prop in getattr(val, 'properties', []):
                sub_key = getattr(sub_prop, 'key', None)
                if sub_key:
                    m_name = getattr(sub_key, 'name', None) or get_string_value(sub_key)
                    loc = getattr(sub_prop, 'loc', None)
                    line_start = loc.start.line if loc and hasattr(loc, 'start') else 0
                    line_end = loc.end.line if loc and hasattr(loc, 'end') else 0
                    if m_name:
                        details.append({
                            "name": m_name,
                            "line_start": line_start,
                            "line_end": line_end
                        })
            return details
    return details


# ─────────────────────────────────────────────
# HTML / TEMPLATE AST (via html.parser)
# ─────────────────────────────────────────────

class _TagCollector(HTMLParser):
    """Collect all opening tags with their attributes."""
    def __init__(self, offset=0):
        super().__init__()
        self.tags = []
        self.offset = offset

    def handle_starttag(self, tag, attrs):
        self.tags.append({'tag': tag.lower(), 'attrs': dict(attrs), 'raw_attrs': attrs, 'line': self.getpos()[0] + self.offset})


class _TemplateTreeBuilder(HTMLParser):
    """Build a lightweight parent-linked DOM tree from HTML content."""
    def __init__(self, offset=0):
        super().__init__()
        self.root = {'tag': '__root__', 'attrs': {}, 'children': [], 'text': '', 'parent': None}
        self._stack = [self.root]
        self._void = {
            'area','base','br','col','embed','hr','img','input',
            'link','meta','param','source','track','wbr'
        }
        self.offset = offset

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0] + self.offset
        node = {
            'tag': tag.lower(),
            'attrs': dict(attrs),
            'children': [],
            'text': '',
            'line': line,
            'parent': self._stack[-1]
        }
        self._stack[-1]['children'].append(node)
        if tag.lower() not in self._void:
            self._stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i]['tag'] == tag.lower():
                self._stack[i]['end_line'] = self.getpos()[0] + self.offset
                self._stack = self._stack[:i]
                break

    def handle_data(self, data):
        text = data.strip()
        if text and len(self._stack) > 1:
            self._stack[-1]['text'] += text + ' '


def collect_template_tags(template_html: str, offset: int = 0) -> list:
    """Return a list of all opening tags as {'tag', 'attrs'} dicts."""
    collector = _TagCollector(offset)
    try:
        collector.feed(template_html)
    except Exception:
        pass
    return collector.tags


def build_template_tree(template_html: str, offset: int = 0) -> dict:
    """Return the root DOM tree node for template HTML."""
    builder = _TemplateTreeBuilder(offset)
    try:
        builder.feed(template_html)
    except Exception:
        pass
    return builder.root



def walk_tree(node: dict):
    """Recursively yield every node in a DOM tree."""
    yield node
    for child in node.get('children', []):
        yield from walk_tree(child)


def get_node_text(node: dict) -> str:
    """Return combined text of a DOM node and all its descendants."""
    parts = [node.get('text', '').strip()]
    for child in node.get('children', []):
        parts.append(get_node_text(child))
    return ' '.join(p for p in parts if p).strip()


# ─────────────────────────────────────────────
# PASCAL-CASE TAG DETECTOR  (no regex)
# ─────────────────────────────────────────────

def find_pascal_tags(html: str) -> set:
    """
    Return the set of Pascal-cased component tag names found in raw HTML.
    e.g. <MyComponent> → 'MyComponent'.
    Uses string scanning only — no regex.
    """
    pascal = set()
    i = 0
    while i < len(html):
        if html[i] == '<':
            j = i + 1
            # skip optional closing slash
            if j < len(html) and html[j] == '/':
                j += 1
            # collect tag name characters
            name_start = j
            while j < len(html) and html[j] not in (' ', '\t', '\n', '/', '>'):
                j += 1
            name = html[name_start:j]
            if name and name[0].isupper():
                pascal.add(name)
        i += 1
    return pascal


# ─────────────────────────────────────────────
# VUE BINDING STRIPPER  (no regex)
# ─────────────────────────────────────────────

def strip_vue_bindings(text: str) -> str:
    """Remove {{ ... }} interpolations from text using plain string ops."""
    result = []
    i = 0
    while i < len(text):
        if text[i:i+2] == '{{':
            end = text.find('}}', i + 2)
            if end != -1:
                i = end + 2
                continue
        result.append(text[i])
        i += 1
    return ''.join(result).strip()


# ─────────────────────────────────────────────
# DIRECTIVE COUNTER  (no regex)
# ─────────────────────────────────────────────

def count_vue_directives(template_html: str) -> int:
    """Count occurrences of v-if and v-for attributes using string search."""
    count = 0
    for directive in ('v-if', 'v-for'):
        pos = 0
        while True:
            pos = template_html.find(directive, pos)
            if pos == -1:
                break
            count += 1
            pos += len(directive)
    return count


# ─────────────────────────────────────────────
# INLINE TAG STRIPPER  (no regex)
# ─────────────────────────────────────────────

def strip_html_tags(text: str) -> str:
    """Remove <...> tags from a string using plain string scanning."""
    result = []
    inside = False
    for ch in text:
        if ch == '<':
            inside = True
        elif ch == '>':
            inside = False
        elif not inside:
            result.append(ch)
    return ''.join(result).strip()


# ─────────────────────────────────────────────
# ELEMENT COLLECTOR WITH INNER HTML  (no regex)
# ─────────────────────────────────────────────

class _ElementWithInnerCollector(HTMLParser):
    """
    Collect all occurrences of a specific tag, capturing:
      - attrs as a raw string (reconstructed from html.parser tokens)
      - attrs as a parsed dict
      - inner HTML content between opening and closing tag
    """
    def __init__(self, target_tag: str, offset=0):
        super().__init__()
        self.target = target_tag.lower()
        self.offset = offset
        self.results = []
        self._depth = 0          # nesting depth of target tag
        self._collecting = False
        self._inner_parts = []
        self._current_attrs_str = ""
        self._current_attrs_dict = {}
        self._void = {
            'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'
        }

    def handle_starttag(self, tag, attrs):
        tag_l = tag.lower()
        if tag_l == self.target:
            if self._depth == 0:
                # Start a new capture
                self._current_attrs_dict = dict(attrs)
                self._start_line = self.getpos()[0] + self.offset
                # Reconstruct a raw attrs string for compat with old API
                parts = []
                for k, v in attrs:
                    if v is None:
                        parts.append(k)
                    else:
                        parts.append(f'{k}="{v}"')
                self._current_attrs_str = ' ' + ' '.join(parts) if parts else ''
                self._collecting = True
                self._inner_parts = []
            self._depth += 1
        elif self._collecting:
            # re-emit the tag into inner
            attr_str = ''
            for k, v in attrs:
                attr_str += f' {k}="{v}"' if v is not None else f' {k}'
            if tag_l in self._void:
                self._inner_parts.append(f'<{tag}{attr_str}/>')
            else:
                self._inner_parts.append(f'<{tag}{attr_str}>')

    def handle_endtag(self, tag):
        tag_l = tag.lower()
        if tag_l == self.target and self._depth > 0:
            self._depth -= 1
            if self._depth == 0 and self._collecting:
                end_line = self.getpos()[0] + self.offset
                self.results.append({
                    'tag': self.target,
                    'attrs':     self._current_attrs_str,
                    'attrs_dict': self._current_attrs_dict,
                    'inner':     ''.join(self._inner_parts).strip(),
                    'line': f"{self._start_line}-{end_line}"
                })
                self._collecting = False
                self._inner_parts = []
        elif self._collecting:
            self._inner_parts.append(f'</{tag}>')

    def handle_data(self, data):
        if self._collecting and self._depth > 0:
            self._inner_parts.append(data)

    def handle_startendtag(self, tag, attrs):
        """Self-closing tags like <input />."""
        if self._collecting:
            attr_str = ''
            for k, v in attrs:
                attr_str += f' {k}="{v}"' if v is not None else f' {k}'
            self._inner_parts.append(f'<{tag}{attr_str}/>')
        if tag.lower() == self.target:
            # A self-closing target tag counts as an empty element
            self._current_attrs_dict = dict(attrs)
            parts = []
            for k, v in attrs:
                if v is None:
                    parts.append(k)
                else:
                    parts.append(f'{k}="{v}"')
            self._current_attrs_str = ' ' + ' '.join(parts) if parts else ''
            hl = self.getpos()[0] + self.offset
            self.results.append({
                'tag': self.target,
                'attrs':     self._current_attrs_str,
                'attrs_dict': self._current_attrs_dict,
                'inner':     '',
                'line': f"{hl}-{hl}"
            })


def collect_elements_with_inner(html: str, tag: str, offset: int = 0) -> list:
    """
    Return a list of dicts for every occurrence of `tag` in `html`.
    Each dict has:
      'tag'       – lowercased tag name
      'attrs'     – raw attribute string (space-prefixed), e.g. ' id="x" class="y"'
      'attrs_dict'– parsed attribute dict
      'inner'     – inner HTML content as a string
    Uses html.parser — no regex.
    """
    collector = _ElementWithInnerCollector(tag, offset)
    try:
        collector.feed(html)
    except Exception:
        pass
    return collector.results


# ─────────────────────────────────────────────
# CSS BLOCK PARSER  (no regex)
# ─────────────────────────────────────────────

def parse_css_blocks(css_text: str, start_line: int = 1) -> list:
    """
    Split a CSS string into a list of {'selector': str, 'body': str, 'line': str} dicts.
    Uses plain string scanning — no regex.
    Handles: normal rules, nested {} inside @media (shallow), comments stripped.
    """
    # Strip /* ... */ comments first but keep newlines so offset doesn't drift
    cleaned = []
    i = 0
    while i < len(css_text):
        if css_text[i:i+2] == '/*':
            end = css_text.find('*/', i + 2)
            if end != -1:
                newlines = css_text[i:end+2].count('\n')
                cleaned.append('\n' * newlines)
                i = end + 2
            else:
                newlines = css_text[i:].count('\n')
                cleaned.append('\n' * newlines)
                i = len(css_text)
        else:
            cleaned.append(css_text[i])
            i += 1
    css_text = ''.join(cleaned)

    blocks = []
    depth = 0
    selector_buf = []
    body_buf = []
    in_body = False
    
    current_line = start_line
    block_start_line = current_line

    for ch in css_text:
        if ch == '{':
            depth += 1
            if depth == 1:
                in_body = True
                body_buf = []
            else:
                body_buf.append(ch)
        elif ch == '}':
            depth -= 1
            if depth == 0 and in_body:
                selector = ''.join(selector_buf).strip()
                body = ''.join(body_buf).strip()
                if selector and body:
                    blocks.append({'selector': selector, 'body': body, 'line': f"{block_start_line}-{current_line}"})
                selector_buf = []
                in_body = False
                block_start_line = current_line
            elif depth > 0:
                body_buf.append(ch)
        elif in_body:
            body_buf.append(ch)
        else:
            if not selector_buf and ch.strip():
                block_start_line = current_line
            selector_buf.append(ch)
            
        if ch == '\n':
            current_line += 1

    return blocks


def get_css_property(body: str, prop: str) -> str:
    """
    Extract the value of a CSS property from a rule body string.
    e.g. get_css_property('color: red; font-size: 14px', 'color') → 'red'
    Plain string split — no regex.
    """
    prop_lower = prop.lower().strip()
    for declaration in body.split(';'):
        declaration = declaration.strip()
        if ':' not in declaration:
            continue
        key, _, val = declaration.partition(':')
        if key.strip().lower() == prop_lower:
            return val.strip()
    return ''
