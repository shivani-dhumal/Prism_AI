"""
accessibility_checker.py — Accessibility checks using html.parser + string ops.
NO regex (re module) used anywhere.

Strategy
--------
* Template & style blocks  → ast_utils.extract_template_block / extract_style_block
* Element finding           → ast_utils.collect_elements_with_inner (html.parser)
* CSS parsing               → ast_utils.parse_css_blocks / get_css_property
* Attribute checks          → dict lookups and plain string 'in' tests
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mysql.connector
import webcolors

from config import DB_CONFIG
from database_ops import save_accessibility_report
from scanners.ast_utils import (
    extract_template_block,
    extract_style_block,
    extract_template_block_with_line,
    extract_style_block_with_line,
    collect_elements_with_inner,
    collect_template_tags,
    parse_css_blocks,
    get_css_property,
    strip_html_tags,
    strip_vue_bindings,
)


# ─────────────────────────────────────────────
# COLOUR HELPERS  (no regex)
# ─────────────────────────────────────────────

# No hardcoded color map — webcolors handles all 148 CSS named colors


def hex_to_rgb(hex_color):
    """Convert hex color #rrggbb or #rgb to (r, g, b) tuple 0-255."""
    hex_color = hex_color.strip().lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        return None
    try:
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def relative_luminance(rgb):
    """Calculate relative luminance per WCAG 2.1 formula."""
    r, g, b = [v / 255.0 for v in rgb]
    def linearize(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(color1_hex, color2_hex):
    """Calculate WCAG contrast ratio between two hex colors. Returns ratio or None."""
    rgb1 = hex_to_rgb(color1_hex)
    rgb2 = hex_to_rgb(color2_hex)
    if not rgb1 or not rgb2:
        return None
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def resolve_color(color_str: str):
    """
    Normalise a CSS color string to hex.
    Handles: #rrggbb, #rgb, named colours, rgb(r,g,b).
    No regex — uses string find/split only.
    """
    if not color_str:
        return None
    color_str = color_str.strip().lower()

    if color_str.startswith('#'):
        return color_str if hex_to_rgb(color_str) else None

    # Use webcolors for all CSS named colors (no hardcoded map)
    try:
        return webcolors.name_to_hex(color_str)
    except (ValueError, AttributeError):
        pass

    if color_str == 'transparent':
        return '#ffffff'

    # rgb(r, g, b) — parse with string ops
    if color_str.startswith('rgb(') and color_str.endswith(')'):
        inner = color_str[4:-1]          # "r, g, b"
        parts = inner.split(',')
        if len(parts) == 3:
            try:
                r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                return '#{:02x}{:02x}{:02x}'.format(r, g, b)
            except ValueError:
                pass

    return None


# ─────────────────────────────────────────────
# ATTRIBUTE HELPERS  (no regex)
# ─────────────────────────────────────────────

def _attr(el, key: str, default='') -> str:
    """Return attribute value from parsed attrs_dict, case-insensitive."""
    d = el.get('attrs_dict', {})
    return d.get(key) or d.get(key.lower()) or default


def _has_attr(el, key: str) -> bool:
    """True if element has the attribute (case-insensitive)."""
    d = el.get('attrs_dict', {})
    return key in d or key.lower() in d


def _attrs_str(el) -> str:
    """Return raw attrs string of an element."""
    return el.get('attrs', '')


def _inner(el) -> str:
    """Return inner HTML string of an element."""
    return el.get('inner', '')


def get_el_id(el) -> str:
    """Return a human-readable identifier string for an element."""
    tag = el.get('tag', 'unknown')
    id_val = _attr(el, 'id')
    cls_val = _attr(el, 'class')
    parts = []
    if id_val:
        parts.append(f"id='{id_val}'")
    if cls_val:
        parts.append(f"class='{cls_val}'")
    return f"<{tag} {' '.join(parts)}>" if parts else f"<{tag}>"


def _inner_text(el) -> str:
    """Return visible text inside element with Vue bindings and tags stripped."""
    raw = _inner(el)
    return strip_html_tags(strip_vue_bindings(raw)).strip()


def _has_icon(inner_html: str) -> bool:
    """Check whether inner HTML contains a likely icon tag by tag name + class."""
    icon_classes = ('icon', 'fa-', 'material', 'mdi', 'bi-')
    icon_tags = ('i', 'span', 'svg', 'img')
    tags = collect_elements_with_inner(inner_html, 'i')
    for t in ('span', 'svg', 'img'):
        tags += collect_elements_with_inner(inner_html, t)
    for tag_el in tags:
        cls = _attr(tag_el, 'class', '').lower()
        if any(ic in cls for ic in icon_classes):
            return True
    return False


# ─────────────────────────────────────────────
# 3.1 COLOR CONTRAST COMPLIANCE
# ─────────────────────────────────────────────

def check_color_contrast(template, style, file_path, screen):
    issues = []

    # Rule 1 & 2: WCAG ratio from CSS rules
    for block in parse_css_blocks(style):
        selector = block['selector']
        body = block['body']

        fg_raw = get_css_property(body, 'color')
        bg_raw = get_css_property(body, 'background-color') or get_css_property(body, 'background')
        font_size_raw = get_css_property(body, 'font-size')

        if fg_raw:
            fg = resolve_color(fg_raw)
            bg = resolve_color(bg_raw) if bg_raw else '#ffffff'
            if fg and bg:
                ratio = contrast_ratio(fg, bg)
                if ratio is not None:
                    # parse font-size digits
                    font_px = 16
                    if font_size_raw:
                        digits = ''.join(c for c in font_size_raw if c.isdigit())
                        if digits:
                            font_px = int(digits)
                    min_ratio = 3.0 if font_px >= 18 else 4.5
                    text_size = "large text" if font_px >= 18 else "normal text"
                    if ratio < min_ratio:
                        issues.append({
                            "line": "0-0",
                            "rule_category": "Color Contrast",
                            "rule_name": "WCAG contrast ratio violation" if bg_raw else "Low contrast text color",
                            "severity": "HIGH" if bg_raw else "MEDIUM",
                            "expected": f"Contrast ratio must be at least {min_ratio}:1 for {text_size}",
                            "actual": f"CSS '{selector.strip()}' has contrast ratio {ratio:.2f}:1 (fg:{fg}, bg:{bg})"
                        })

    # Rule 3: Inline style color contrast — check all tags that carry style=
    for tag_info in collect_template_tags(template):
        style_val = tag_info['attrs'].get('style', '')
        if not style_val:
            continue
        # Parse inline style as mini CSS body
        fg_raw = get_css_property(style_val, 'color')
        bg_raw = get_css_property(style_val, 'background-color') or get_css_property(style_val, 'background')
        if fg_raw:
            fg = resolve_color(fg_raw)
            bg = resolve_color(bg_raw) if bg_raw else '#ffffff'
            if fg and bg:
                ratio = contrast_ratio(fg, bg)
                if ratio is not None and ratio < 4.5:
                    issues.append({
                        "line": tag_info.get("line", "0-0") if isinstance(tag_info, dict) else "0-0",
                        "rule_category": "Color Contrast",
                        "rule_name": "Low contrast inline style",
                        "severity": "HIGH",
                        "expected": "Inline color contrast must be at least 4.5:1",
                        "actual": f"<{tag_info['tag']}> inline style has contrast ratio {ratio:.2f}:1 (fg:{fg}, bg:{bg})"
                    })

    # Rule 4: Color-only error indicators — look for elements with 'error' in class
    for tag_info in collect_template_tags(template):
        cls = tag_info['attrs'].get('class', '').lower()
        if 'error' not in cls:
            continue
        els = collect_elements_with_inner(template, tag_info['tag'])
        for el in els:
            if 'error' not in _attr(el, 'class', '').lower():
                continue
            if not _has_icon(_inner(el)):
                issues.append({
                    "line": el.get("line", "0-0") if isinstance(el, dict) else "0-0",
                    "rule_category": "Color Contrast",
                    "rule_name": "Color-only error indicator",
                    "severity": "HIGH",
                    "expected": "Error messages should use color + icon + text (not color alone)",
                    "actual": f"<{tag_info['tag']}> with error styling uses color only to convey meaning"
                })
            break  # one report per tag type

    # Rule 5: Buttons — check hover/focus states in CSS
    css_blocks = parse_css_blocks(style)           # cache once
    style_lower = style.lower()
    btn_selectors = set()
    for block in css_blocks:
        sel = block['selector'].strip().lower()
        if 'button' in sel or 'btn' in sel:
            btn_selectors.add(sel)
    for sel in btn_selectors:
        hover_found = any(
            (sel + ':hover') in b['selector'].lower()
            for b in css_blocks
        )
        focus_found = any(
            (sel + ':focus') in b['selector'].lower()
            for b in css_blocks
        )
        # Also check within the style text by plain substring
        if not hover_found:
            hover_found = (sel + ':hover') in style_lower
        if not focus_found:
            focus_found = (sel + ':focus') in style_lower

        if not hover_found:
            issues.append({
                "line": "0-0",
                "rule_category": "Color Contrast",
                "rule_name": "Button missing hover state",
                "severity": "MEDIUM",
                "expected": "Buttons must have a visible hover state",
                "actual": f"No :hover style found for '{sel}'"
            })
        if not focus_found:
            issues.append({
                "line": "0-0",
                "rule_category": "Color Contrast",
                "rule_name": "Button missing focus state",
                "severity": "MEDIUM",
                "expected": "Buttons must have a visible focus state",
                "actual": f"No :focus style found for '{sel}'"
            })

    return issues


# ─────────────────────────────────────────────
# 3.2 KEYBOARD NAVIGATION
# ─────────────────────────────────────────────

def check_keyboard_navigation(template, style, file_path, screen):
    issues = []
    _INTERACTIVE = {'button', 'a', 'input', 'select', 'textarea'}

    # Rule 1: Interactive elements with tabindex="-1"
    for tag in _INTERACTIVE:
        for el in collect_elements_with_inner(template, tag):
            if _attr(el, 'tabindex') == '-1':
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Keyboard Navigation",
                    "rule_name": "Interactive element removed from tab order",
                    "severity": "HIGH",
                    "expected": "All interactive elements must be reachable via Tab key",
                    "actual": f"{get_el_id(el)} has tabindex='-1' making it unreachable by keyboard"
                })

    # Rule 2: Click handlers on div/span/p without tabindex
    for tag in ('div', 'span', 'p'):
        for el in collect_elements_with_inner(template, tag):
            attrs = el.get('attrs_dict', {})
            has_click = any(
                k in ('@click', 'v-on:click', 'onclick') for k in attrs
            )
            if has_click and not _has_attr(el, 'tabindex'):
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Keyboard Navigation",
                    "rule_name": "Non-interactive element with click handler",
                    "severity": "HIGH",
                    "expected": f"<{tag}> with click handler must have tabindex='0' for keyboard access",
                    "actual": f"{get_el_id(el)} has click handler but no tabindex — cannot be reached via Tab"
                })

    # Rule 3: Modals without keyboard close
    for tag in collect_template_tags(template):
        cls = tag['attrs'].get('class', '').lower()
        if 'modal' not in cls and 'dialog' not in tag['tag']:
            continue
        els = collect_elements_with_inner(template, tag['tag'])
        for el in els:
            if 'modal' not in _attr(el, 'class', '').lower() and 'dialog' not in el.get('tag', ''):
                continue
            inner_all = _inner(el) + _attrs_str(el)
            esc_keys = ('@keydown.esc', '@keyup.esc', 'v-on:keydown.esc', 'escape')
            has_esc = any(k in inner_all.lower() for k in esc_keys)
            # Check for close button by text
            btn_els = collect_elements_with_inner(_inner(el), 'button')
            has_close_btn = any(
                any(word in _inner_text(b).lower() for word in ('close', '×', '✕', '✖', 'x'))
                for b in btn_els
            )
            if not has_esc and not has_close_btn:
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Keyboard Navigation",
                    "rule_name": "Modal without keyboard close",
                    "severity": "HIGH",
                    "expected": "Users must be able to close modals using keyboard (Escape key)",
                    "actual": f"Modal <{el.get('tag')}> has no Escape key handler or close button"
                })

    # Rule 4: Custom dropdowns missing keyboard handler or ARIA role
    for tag in ('div', 'ul', 'span'):
        for el in collect_elements_with_inner(template, tag):
            cls = _attr(el, 'class', '').lower()
            if 'dropdown' not in cls and 'custom-select' not in cls:
                continue
            attrs = el.get('attrs_dict', {})
            has_keydown = any(k.startswith('@keydown') or k.startswith('@keyup') or k.startswith('v-on:key') for k in attrs)
            role = _attr(el, 'role', '').lower()
            has_role = role in ('listbox', 'combobox', 'menu')
            if not has_keydown or not has_role:
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Keyboard Navigation",
                    "rule_name": "Custom dropdown not keyboard accessible",
                    "severity": "HIGH",
                    "expected": "Custom dropdowns must handle keyboard events and have role='listbox' or 'combobox'",
                    "actual": f"{get_el_id(el)} is a custom dropdown missing keyboard handler or ARIA role"
                })

    # Rule 5: Positive tabindex (> 0) breaks natural tab order
    for tag_info in collect_template_tags(template):
        tabval = tag_info['attrs'].get('tabindex', '')
        try:
            if tabval and int(tabval) > 0:
                issues.append({
                    "line": tag_info.get("line", 0) if isinstance(tag_info, dict) else "0-0",
                    "rule_category": "Keyboard Navigation",
                    "rule_name": "Non-zero tabindex breaks tab order",
                    "severity": "MEDIUM",
                    "expected": "Use tabindex='0' to keep natural tab order; avoid positive tabindex values",
                    "actual": f"<{tag_info['tag']}> has tabindex='{tabval}' which disrupts visual tab order"
                })
        except ValueError:
            pass

    # Rule 6: @click without @keydown.enter on non-native elements
    for tag in ('div', 'span', 'li'):
        for el in collect_elements_with_inner(template, tag):
            attrs = el.get('attrs_dict', {})
            has_click = '@click' in attrs or 'v-on:click' in attrs
            if not has_click:
                continue
            has_enter = any(
                k in ('@keydown.enter', '@keyup.enter', '@keydown.space', '@keyup.space')
                for k in attrs
            )
            if not has_enter:
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Keyboard Navigation",
                    "rule_name": "Missing Enter/Space keyboard activation",
                    "severity": "HIGH",
                    "expected": f"<{tag}> with @click must also handle @keydown.enter and @keydown.space",
                    "actual": f"{get_el_id(el)} has @click but no keyboard activation handler (Enter/Space)"
                })

    # Rule 7: Keyboard trap in modal (multiple focusable elements, no focus-trap)
    focusable_tags = ('input', 'button', 'select', 'textarea', 'a')
    for el in collect_elements_with_inner(template, 'div'):
        if 'modal' not in _attr(el, 'class', '').lower():
            continue
        inner_html = _inner(el)
        focusable_count = sum(
            len(collect_elements_with_inner(inner_html, ft)) for ft in focusable_tags
        )
        inner_all = inner_html + _attrs_str(el)
        focus_trap_keywords = ('@keydown', '@keyup', 'v-on:key', 'focustrap', 'usefocustrap')
        has_ft = any(kw in inner_all.lower() for kw in focus_trap_keywords)
        if focusable_count > 2 and not has_ft:
            issues.append({
                "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                "rule_category": "Keyboard Navigation",
                "rule_name": "Potential keyboard trap in modal",
                "severity": "HIGH",
                "expected": "Modals with multiple focusable elements must manage focus trapping properly",
                "actual": f"<div> modal has {focusable_count} focusable elements but no focus-trap management detected"
            })

    return issues


# ─────────────────────────────────────────────
# 3.3 FOCUS VISIBILITY
# ─────────────────────────────────────────────

def check_focus_visibility(template, style, file_path, screen):
    issues = []
    style_lower = style.lower()

    # Rule 1: outline:none / outline:0 without replacement
    for block in parse_css_blocks(style):
        outline_val = get_css_property(block['body'], 'outline').lower()
        if outline_val in ('none', '0'):
            body_lower = block['body'].lower()
            has_alt = 'box-shadow' in body_lower or 'border' in body_lower
            if not has_alt:
                issues.append({
                    "line": "0-0",
                    "rule_category": "Focus Visibility",
                    "rule_name": "Focus outline removed",
                    "severity": "HIGH",
                    "expected": "Every clickable element must show a visible focus outline",
                    "actual": f"CSS '{block['selector'].strip()}' removes outline without providing alternative focus indicator"
                })

    # Rule 2: Interactive selectors should have :focus / :focus-visible
    interactive_keywords = ('button', 'input', 'select', 'textarea', '.btn', 'a')
    for kw in interactive_keywords:
        if kw not in style_lower:
            continue
        has_focus = (kw + ':focus') in style_lower or (kw + ':focus-visible') in style_lower
        if not has_focus:
            issues.append({
                "line": "0-0",
                "rule_category": "Focus Visibility",
                "rule_name": "Missing focus style",
                "severity": "MEDIUM",
                "expected": f"'{kw}' should have a :focus or :focus-visible style",
                "actual": f"No focus style defined for '{kw}'"
            })

    return issues


# ─────────────────────────────────────────────
# 3.4 SCREEN READER COMPATIBILITY
# ─────────────────────────────────────────────

def check_screen_reader(template, style, file_path, screen):
    issues = []

    # Rule 1: Images missing alt
    for img in collect_elements_with_inner(template, 'img'):
        if not _has_attr(img, 'alt'):
            issues.append({
                "line": img.get("line", 0) if isinstance(img, dict) else "0-0",
                "rule_category": "Screen Reader",
                "rule_name": "Image missing alt text",
                "severity": "HIGH",
                "expected": "All <img> elements must have an alt attribute",
                "actual": f"{get_el_id(img)} is missing alt attribute"
            })

    # Rule 2: Icon-only buttons missing aria-label
    for btn in collect_elements_with_inner(template, 'button'):
        text = _inner_text(btn)
        has_icon_el = _has_icon(_inner(btn))
        has_aria = _has_attr(btn, 'aria-label')
        has_title = _has_attr(btn, 'title')
        if has_icon_el and not text and not has_aria and not has_title:
            issues.append({
                "line": btn.get("line", 0) if isinstance(btn, dict) else "0-0",
                "rule_category": "Screen Reader",
                "rule_name": "Icon button missing accessible label",
                "severity": "HIGH",
                "expected": "Buttons with only icons must have aria-label or title",
                "actual": f"{get_el_id(btn)} is an icon-only button without accessible name"
            })

    # Rule 3: Links without meaningful text
    for link in collect_elements_with_inner(template, 'a'):
        text = _inner_text(link)
        has_aria = _has_attr(link, 'aria-label')
        if not text and not has_aria:
            issues.append({
                "line": link.get("line", 0) if isinstance(link, dict) else "0-0",
                "rule_category": "Screen Reader",
                "rule_name": "Link missing accessible text",
                "severity": "HIGH",
                "expected": "<a> elements must have visible text or aria-label",
                "actual": f"{get_el_id(link)} has no accessible text"
            })

    # Rule 4: aria-hidden on interactive elements
    for tag in ('button', 'a', 'input', 'select', 'textarea'):
        for el in collect_elements_with_inner(template, tag):
            if _attr(el, 'aria-hidden', '').lower() == 'true':
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Screen Reader",
                    "rule_name": "Interactive element hidden from screen reader",
                    "severity": "CRITICAL",
                    "expected": "Interactive elements must NOT have aria-hidden='true'",
                    "actual": f"{get_el_id(el)} is hidden from screen readers"
                })

    # Rule 5: Dynamic v-if/v-show message areas missing aria-live
    msg_keywords = ('error', 'alert', 'message', 'success', 'warning', 'notification')
    for tag in ('div', 'span', 'p', 'section'):
        for el in collect_elements_with_inner(template, tag):
            attrs = el.get('attrs_dict', {})
            has_dynamic = 'v-if' in attrs or 'v-show' in attrs
            if not has_dynamic:
                continue
            attrs_str_low = _attrs_str(el).lower()
            is_msg = any(kw in attrs_str_low for kw in msg_keywords)
            if is_msg and not _has_attr(el, 'aria-live'):
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Screen Reader",
                    "rule_name": "Dynamic content missing aria-live",
                    "severity": "HIGH",
                    "expected": "Dynamic message areas (errors/alerts via v-if) must use aria-live='polite' or 'assertive'",
                    "actual": f"{get_el_id(el)} is a dynamic message area without aria-live attribute"
                })

    return issues


# ─────────────────────────────────────────────
# 3.5 FORM ACCESSIBILITY
# ─────────────────────────────────────────────

def _label_exists_for(inp_id: str, template: str) -> bool:
    """Return True if a <label for="inp_id"> exists in template."""
    for lbl in collect_elements_with_inner(template, 'label'):
        if _attr(lbl, 'for') == inp_id:
            return True
    return False


def check_form_accessibility(template, style, file_path, screen):
    issues = []
    skip_types = {'hidden', 'submit', 'button'}

    inputs = collect_elements_with_inner(template, 'input')

    # Rule 1: Input without label
    for inp in inputs:
        inp_type = _attr(inp, 'type', '').lower()
        if inp_type in skip_types:
            continue
        inp_id = _attr(inp, 'id')
        has_aria_label = _has_attr(inp, 'aria-label')
        has_aria_labelledby = _has_attr(inp, 'aria-labelledby')
        has_label = _label_exists_for(inp_id, template) if inp_id else False
        if not has_label and not has_aria_label and not has_aria_labelledby:
            issues.append({
                "line": inp.get("line", 0) if isinstance(inp, dict) else "0-0",
                "rule_category": "Form Accessibility",
                "rule_name": "Input missing label",
                "severity": "HIGH",
                "expected": "Every input field must have a matching <label for='...'> or aria-label",
                "actual": f"<input{' id=' + repr(inp_id) if inp_id else ''} type='{inp_type}'> has no associated label"
            })

    # Rule 2: Placeholder used as only label
    for inp in inputs:
        inp_type = _attr(inp, 'type', '').lower()
        if inp_type in skip_types:
            continue
        has_placeholder = _has_attr(inp, 'placeholder') or _has_attr(inp, ':placeholder')
        has_aria_label = _has_attr(inp, 'aria-label')
        inp_id = _attr(inp, 'id')
        has_label = _label_exists_for(inp_id, template) if inp_id else False
        if has_placeholder and not has_label and not has_aria_label:
            issues.append({
                "line": inp.get("line", 0) if isinstance(inp, dict) else "0-0",
                "rule_category": "Form Accessibility",
                "rule_name": "Placeholder used instead of label",
                "severity": "MEDIUM",
                "expected": "Placeholder text must NOT replace labels — use <label> element",
                "actual": f"<input type='{inp_type}'> uses placeholder without a proper label"
            })

    # Rule 3: Select / textarea without label
    for tag in ('select', 'textarea'):
        for el in collect_elements_with_inner(template, tag):
            has_aria_label = _has_attr(el, 'aria-label')
            el_id = _attr(el, 'id')
            has_label = _label_exists_for(el_id, template) if el_id else False
            if not has_label and not has_aria_label:
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Form Accessibility",
                    "rule_name": f"{tag.capitalize()} missing label",
                    "severity": "HIGH",
                    "expected": f"<{tag}> must have a matching <label for='...'> or aria-label",
                    "actual": f"<{tag}{' id=' + repr(el_id) if el_id else ''}> has no associated label"
                })

    # Rule 4: Required fields not announced via aria-required
    for tag in ('input', 'select', 'textarea'):
        for el in collect_elements_with_inner(template, tag):
            attrs = el.get('attrs_dict', {})
            is_required = 'required' in attrs or ':required' in attrs
            if not is_required:
                continue
            has_aria_required = _attr(el, 'aria-required', '').lower() == 'true'
            if not has_aria_required:
                issues.append({
                    "line": el.get("line", 0) if isinstance(el, dict) else "0-0",
                    "rule_category": "Form Accessibility",
                    "rule_name": "Required field not announced",
                    "severity": "MEDIUM",
                    "expected": "Required fields should have aria-required='true' for screen readers",
                    "actual": f"{get_el_id(el)} is required but missing aria-required attribute"
                })

    # Rule 5: Error message not linked via aria-describedby
    error_id_suffixes = ('-error', 'err', '_error')
    for inp in inputs:
        inp_type = _attr(inp, 'type', '').lower()
        if inp_type in skip_types:
            continue
        inp_id = _attr(inp, 'id')
        if not inp_id:
            continue
        if _has_attr(inp, 'aria-describedby'):
            continue
        # Check if an error element with matching id exists
        error_ids = [
            inp_id + '-error',
            'error-' + inp_id,
            inp_id + 'Err',
            inp_id + '_error',
        ]
        template_lower = template.lower()
        has_error_el = any(('id="' + eid.lower() + '"') in template_lower or
                           ("id='" + eid.lower() + "'") in template_lower
                           for eid in error_ids)
        if has_error_el:
            issues.append({
                "line": "0-0",
                "rule_category": "Form Accessibility",
                "rule_name": "Error message not linked to input",
                "severity": "HIGH",
                "expected": f"<input id='{inp_id}'> should have aria-describedby pointing to its error element",
                "actual": f"<input id='{inp_id}'> has a nearby error element but no aria-describedby linking them"
            })

    return issues


# ─────────────────────────────────────────────
# 3.6 RESPONSIVE & ZOOM TESTING
# ─────────────────────────────────────────────

def check_responsive(template, style, file_path, screen):
    issues = []

    for block in parse_css_blocks(style):
        sel = block['selector'].strip()
        body = block['body']

        # Rule 1: Fixed widths ≥ 1000px
        width_val = get_css_property(body, 'width')
        if width_val and 'px' in width_val:
            digits = ''.join(c for c in width_val if c.isdigit())
            if digits and int(digits) >= 1000:
                issues.append({
                    "line": "0-0",
                    "rule_category": "Responsive & Zoom",
                    "rule_name": "Large fixed width",
                    "severity": "MEDIUM",
                    "expected": "Use relative units (%, vw, rem) instead of large fixed pixel widths",
                    "actual": f"CSS '{sel}' uses fixed width: {width_val.strip()}"
                })

        # Rule 2: overflow: hidden
        overflow_val = get_css_property(body, 'overflow').lower()
        if overflow_val == 'hidden':
            issues.append({
                "line": "0-0",
                "rule_category": "Responsive & Zoom",
                "rule_name": "Overflow hidden may clip content",
                "severity": "LOW",
                "expected": "Avoid overflow:hidden on text containers — use overflow:auto if needed",
                "actual": f"CSS '{sel}' uses overflow:hidden which may clip content when zoomed"
            })

        # Rule 4: Fixed font-size in px < 18
        font_size_val = get_css_property(body, 'font-size')
        if font_size_val and 'px' in font_size_val:
            digits = ''.join(c for c in font_size_val if c.isdigit())
            if digits and int(digits) < 18:
                issues.append({
                    "line": "0-0",
                    "rule_category": "Responsive & Zoom",
                    "rule_name": "Fixed font-size in px",
                    "severity": "LOW",
                    "expected": "Use rem or em for font-size so text scales correctly at 150%/200% zoom",
                    "actual": f"CSS '{sel}' uses fixed font-size: {digits}px — won't scale for low-vision users"
                })

        # Rule 6: width/min-width > 768px (horizontal scroll risk)
        for prop in ('width', 'min-width'):
            val = get_css_property(body, prop)
            if val and 'px' in val:
                digits = ''.join(c for c in val if c.isdigit())
                if digits and int(digits) > 768:
                    issues.append({
                        "line": "0-0",
                        "rule_category": "Responsive & Zoom",
                        "rule_name": "Horizontal scroll risk",
                        "severity": "MEDIUM",
                        "expected": "Width should not exceed viewport — use max-width or % instead of fixed px",
                        "actual": f"CSS '{sel}' has {prop}: {digits}px which may cause horizontal scrolling on small screens"
                    })

    # Rule 3: No @media queries
    if style.strip() and '@media' not in style.lower():
        issues.append({
            "line": "0-0",
            "rule_category": "Responsive & Zoom",
            "rule_name": "No media queries found",
            "severity": "MEDIUM",
            "expected": "Styles should include @media queries for responsive layouts",
            "actual": "No @media queries detected in component styles"
        })

    return issues


# ─────────────────────────────────────────────
# 3.7 CLICK TARGET SIZE
# ─────────────────────────────────────────────

def check_click_target(template, style, file_path, screen):
    issues = []

    # Rule 1: Icon-only buttons without explicit min size in CSS
    for btn in collect_elements_with_inner(template, 'button'):
        text = _inner_text(btn)
        if not _has_icon(_inner(btn)) or text:
            continue
        cls_name = _attr(btn, 'class', '')
        has_min_size = False
        for cn in cls_name.split():
            for block in parse_css_blocks(style):
                if ('.' + cn) in block['selector']:
                    body = block['body'].lower()
                    if any(p in body for p in ('min-width', 'min-height', 'width', 'height')):
                        has_min_size = True
                        break
            if has_min_size:
                break
        if not has_min_size:
            issues.append({
                "line": "0-0",
                "rule_category": "Click Target Size",
                "rule_name": "Small icon button",
                "severity": "MEDIUM",
                "expected": "Minimum touch target size should be 44x44 pixels",
                "actual": f"{get_el_id(btn)} is icon-only button without explicit min size"
            })

    # Rule 2: Adjacent links with very short text
    links = collect_elements_with_inner(template, 'a')
    for i in range(len(links) - 1):
        if len(_inner_text(links[i])) <= 3 and len(_inner_text(links[i + 1])) <= 3:
            issues.append({
                "line": "0-0",
                "rule_category": "Click Target Size",
                "rule_name": "Links too close together",
                "severity": "MEDIUM",
                "expected": "Links should not be placed too close together — add spacing",
                "actual": "Adjacent <a> elements with very short text may be hard to tap on mobile"
            })

    # Rule 3: CSS width/height < 44px on interactive selectors
    for block in parse_css_blocks(style):
        sel = block['selector'].strip().lower()
        is_interactive = 'button' in sel or '.btn' in sel or sel == 'a' or '.link' in sel
        if not is_interactive:
            continue
        for prop in ('width', 'height'):
            val = get_css_property(block['body'], prop)
            if val and 'px' in val:
                digits = ''.join(c for c in val if c.isdigit())
                if digits and int(digits) < 44:
                    issues.append({
                        "line": "0-0",
                        "rule_category": "Click Target Size",
                        "rule_name": "Click target below 44px minimum",
                        "severity": "MEDIUM",
                        "expected": "Minimum touch target is 44x44 pixels (WCAG 2.5.5)",
                        "actual": f"CSS '{sel}' has {prop}: {digits}px — below the 44px WCAG minimum"
                    })
                    break

    return issues


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

ALL_CHECKS = [
    check_color_contrast,
    check_keyboard_navigation,
    check_focus_visibility,
    check_screen_reader,
    check_form_accessibility,
    check_responsive,
    check_click_target
]


def check_accessibility():
    """Read ui_extraction data grouped by component to get file paths,
    then re-read the actual source files to run accessibility analysis."""

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT component_id, file_path
        FROM ui_extraction
    """)
    components = cursor.fetchall()
    cursor.close()
    conn.close()

    if not components:
        print("   No components found in ui_extraction table.")
        return

    file_cache = {}
    total_issues = 0

    for comp in components:
        comp_id = comp["component_id"]
        file_path = comp["file_path"]
        screen = os.path.basename(file_path)

        if file_path not in file_cache:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                file_cache[file_path] = raw
            except FileNotFoundError:
                print(f"   [WARN] File not found: {file_path}")
                file_cache[file_path] = None

        content = file_cache[file_path]
        if content is None:
            continue

        template = extract_template_block(content)
        style = extract_style_block(content)

        if not template:
            continue

        for check_fn in ALL_CHECKS:
            try:
                results = check_fn(template, style, file_path, screen)
            except Exception as e:
                print(f"   [WARN] {check_fn.__name__} failed on {screen}: {e}")
                continue
            if results:
                for issue in results:
                    save_accessibility_report(
                        component_id=comp_id,
                        file_path=file_path,
                        rule_name=issue["rule_name"],
                        status="FAIL",
                        actual_result=issue["actual"],
                        severity=issue.get("severity", "MEDIUM"),
                        line_number=issue.get("line", "0-0")
                    )
                    total_issues += 1

    print(f"   Accessibility & usability checks completed. ({total_issues} issues found)")


if __name__ == "__main__":
    check_accessibility()
