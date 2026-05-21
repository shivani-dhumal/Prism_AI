"""
Task-5: UI Consistency Rules
============================
All checks in one file (does NOT overwrite ui_consistency_checker.py).

Sections
--------
3.1  Button Style Consistency
3.2  Header Presence & Format
3.3  Spelling & Text Validation
3.4  Alignment & Layout Consistency
3.5  Font & Color Consistency

Entry point: run_ui_consistency_rules()
"""

import os
import sys
import mysql.connector

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_CONFIG
from database_ops import save_ui_consistency_report
from scanners.spell_checker import check_spelling


# ============================================================
# 3.1  BUTTON STYLE CONSISTENCY
# ============================================================

def check_button_css(elements, rule):
    """
    Rule: All buttons must share a common CSS class set.
    Defect: More than 3 distinct CSS classes found on <button> elements.
    """
    styles = [
        el.get("css_class")
        for el in elements
        if (el.get("tag_name") or "").lower() == "button" and el.get("css_class")
    ]
    unique = set(styles)
    if len(unique) > 3:
        return {
            "expected": "Buttons should share a common CSS class",
            "actual": f"Different button styles detected: {', '.join(sorted(unique))}",
            "severity": "HIGH"
        }
    return None


def check_button_capitalization(elements, rule):
    """
    Rule: Button labels should follow Title Case or Sentence case — not ALL CAPS / all lowercase.
    Defect: Labels that are fully uppercase or fully lowercase (more than one word).
    """
    issues = []
    for el in elements:
        if (el.get("tag_name") or "").lower() != "button":
            continue
        text = (el.get("text_value") or "").strip()
        if not text or len(text) < 2:
            continue
        if "{{" in text:
            continue
        words = text.split()
        if len(words) >= 2:
            if text == text.upper() and text.isalpha():
                issues.append(f"ALL-CAPS button label: '{text}'")
            elif text == text.lower():
                issues.append(f"All-lowercase button label: '{text}'")

    if issues:
        return {
            "expected": "Button labels should use Title Case or Sentence case",
            "actual": "; ".join(issues),
            "severity": "MEDIUM"
        }
    return None


def check_button_icon_alignment(elements, rule):
    """
    Rule: Icons inside buttons must be left-aligned before the label text.
    Defect: Button text starts with an icon glyph/class on the right side of the label.
    """
    issues = []
    for el in elements:
        if (el.get("tag_name") or "").lower() != "button":
            continue
        css = el.get("css_class") or ""
        if "icon-right" in css or "fa-right" in css:
            issues.append(f"Button '{el.get('text_value', '').strip()}' has right-aligned icon")

    if issues:
        return {
            "expected": "Icons inside buttons must be left-aligned before the text",
            "actual": "; ".join(issues),
            "severity": "MEDIUM"
        }
    return None


def check_button_label_class_consistency(components, rule):
    """
    Cross-page rule: A button label must always map to exactly one CSS class
    across ALL pages/components.

    No hardcoded labels, no hardcoded classes, no hardcoded limits.
    Everything is learned from the data itself.

    PASS: "submit" → btn-primary on every page
    FAIL: "submit" → btn-primary on page1, btn-success on page3
    """
    label_to_classes = {}   # { "submit": {"btn-primary", "btn-success"} }
    label_class_pages = {}  # { "submit": {"btn-primary": ["page1", "page3"]} }

    for comp_id, elements in components.items():
        file_path = elements[0].get("file_path", str(comp_id))
        for el in elements:
            if (el.get("tag_name") or "").lower() != "button":
                continue
            label = (el.get("text_value") or "").strip().lower()
            css   = (el.get("css_class") or "").strip()
            if not label or not css:
                continue

            label_to_classes.setdefault(label, set()).add(css)
            label_class_pages.setdefault(label, {}).setdefault(css, []).append(file_path)

    issues = []
    for label, classes in label_to_classes.items():
        if len(classes) > 1:
            breakdown = []
            for cls in sorted(classes):
                pages = label_class_pages[label][cls]
                breakdown.append(f"'{cls}' on [{', '.join(pages)}]")
            issues.append(
                f"Button '{label}' is inconsistent → " + " | ".join(breakdown)
            )

    if issues:
        return {
            "expected": "Every button label must use the same CSS class across all pages",
            "actual":   "\n".join(issues),
            "severity": "HIGH"
        }
    return None


# Semantic button types to check for consistency
_BUTTON_TYPES = ('primary', 'secondary', 'success', 'danger', 'warning', 'info', 'light', 'dark', 'link', 'default')


def check_button_type_class_consistency(components, rule):
    """
    Cross-page rule: Buttons of the same semantic type (primary, danger, etc.)
    must always use the same CSS class across ALL pages.

    PASS: All primary buttons use 'btn-primary' everywhere
    FAIL: Some pages use 'btn-primary', others use 'button-primary' or 'primary-btn'
    """
    # { 'primary': { 'btn-primary': ['Login.vue'], 'button-primary': ['Home.vue'] } }
    type_class_pages = {}

    for comp_id, elements in components.items():
        file_path = elements[0].get("file_path", str(comp_id))
        page_name = file_path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]

        for el in elements:
            if (el.get("tag_name") or "").lower() != "button":
                continue
            css = (el.get("css_class") or "").strip().lower()
            if not css:
                continue

            # Detect which semantic type this button belongs to
            for btn_type in _BUTTON_TYPES:
                if btn_type in css:
                    type_class_pages.setdefault(btn_type, {}).setdefault(css, set()).add(page_name)
                    break

    issues = []
    for btn_type, class_map in type_class_pages.items():
        if len(class_map) > 1:
            breakdown = []
            for cls, pages in sorted(class_map.items()):
                breakdown.append(f"'{cls}' on [{', '.join(sorted(pages))}]")
            issues.append(
                f"'{btn_type}' buttons use different classes → " + " | ".join(breakdown)
            )

    if issues:
        return {
            "expected": "Buttons of the same type (primary, danger, etc.) must use the same CSS class across all pages",
            "actual": "\n".join(issues),
            "severity": "HIGH"
        }
    return None


def check_button_type_color_consistency(components, rule):
    """
    Cross-page rule: All buttons of the same semantic type should map to
    the same background-color in their component's <style>.

    Reads the source file to extract CSS, finds the background-color for
    each button class, and flags inconsistencies.
    """
    import os
    from scanners.ast_utils import extract_style_block, parse_css_blocks, get_css_property

    # { 'primary': { '#007bff': ['Login.vue'], '#0d6efd': ['Home.vue'] } }
    type_color_pages = {}

    for comp_id, elements in components.items():
        file_path = elements[0].get("file_path", str(comp_id))
        page_name = file_path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]

        # Read file for style block
        style = ""
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    style = extract_style_block(f.read())
            except Exception:
                pass

        if not style:
            continue

        # Build a map of CSS class → background-color from this file's styles
        class_to_bg = {}
        for block in parse_css_blocks(style):
            bg = get_css_property(block['body'], 'background-color') or get_css_property(block['body'], 'background')
            if bg:
                class_to_bg[block['selector'].strip().lower()] = bg.strip().lower()

        for el in elements:
            if (el.get("tag_name") or "").lower() != "button":
                continue
            css = (el.get("css_class") or "").strip().lower()
            if not css:
                continue

            for btn_type in _BUTTON_TYPES:
                if btn_type not in css:
                    continue

                # Find matching background color from the style
                for css_class in css.split():
                    selector = '.' + css_class
                    if selector in class_to_bg:
                        color = class_to_bg[selector]
                        type_color_pages.setdefault(btn_type, {}).setdefault(color, set()).add(page_name)
                break

    issues = []
    for btn_type, color_map in type_color_pages.items():
        if len(color_map) > 1:
            breakdown = []
            for color, pages in sorted(color_map.items()):
                breakdown.append(f"'{color}' on [{', '.join(sorted(pages))}]")
            issues.append(
                f"'{btn_type}' buttons have different colors → " + " | ".join(breakdown)
            )

    if issues:
        return {
            "expected": "Buttons of the same type must use the same background color across all pages",
            "actual": "\n".join(issues),
            "severity": "HIGH"
        }
    return None


# Button-type keywords to strip out when extracting layout classes
_BTN_KEYWORDS = {'btn', 'button'} | set(_BUTTON_TYPES) | {f'btn-{t}' for t in _BUTTON_TYPES}


def _get_layout_classes(css: str) -> str:
    """
    Extract layout/modifier classes from a button's CSS by removing
    all button-type-related classes. No hardcoded alignment keywords.
    Returns sorted remaining classes as a single string.
    """
    classes = css.lower().split()
    layout = [c for c in classes if c not in _BTN_KEYWORDS]
    return ' '.join(sorted(layout)) if layout else "none"


def check_button_type_alignment_consistency(components, rule):
    """
    Cross-page rule: Buttons of the same semantic type must have the same
    layout/alignment classes across ALL pages.

    Dynamically extracts non-button CSS classes and compares them.
    No hardcoded alignment keywords.

    PASS: All 'success' buttons use same layout classes on every page
    FAIL: 'success' buttons use 'text-center' on Login.vue but 'float-right' on Home.vue
    """
    # { 'success': { 'text-center mt-3': {'Login.vue'}, 'float-right': {'Home.vue'} } }
    type_layout_pages = {}

    for comp_id, elements in components.items():
        file_path = elements[0].get("file_path", str(comp_id))
        page_name = file_path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]

        for el in elements:
            if (el.get("tag_name") or "").lower() != "button":
                continue
            css = (el.get("css_class") or "").strip()
            if not css:
                continue

            layout = _get_layout_classes(css)

            for btn_type in _BUTTON_TYPES:
                if btn_type in css.lower():
                    type_layout_pages.setdefault(btn_type, {}).setdefault(layout, set()).add(page_name)
                    break

    issues = []
    for btn_type, layout_map in type_layout_pages.items():
        if len(layout_map) > 1:
            breakdown = []
            for layout, pages in sorted(layout_map.items()):
                label = f"'{layout}'" if layout != "none" else "no layout classes"
                breakdown.append(f"{label} on [{', '.join(sorted(pages))}]")
            issues.append(
                f"'{btn_type}' buttons have different layout → " + " | ".join(breakdown)
            )

    if issues:
        return {
            "expected": "Buttons of the same type must use the same layout/alignment classes across all pages",
            "actual": "\n".join(issues),
            "severity": "HIGH"
        }
    return None


# ============================================================
# 3.2  HEADER PRESENCE & FORMAT
# ============================================================

HEADER_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def check_header_presence(elements, rule):
    """
    Rule: Every screen must contain at least one header tag (h1–h6).
    """
    if elements:
        file_path = elements[0].get("file_path", "")
        if "footer" in file_path.lower():
            return None

    found = any((el.get("tag_name") or "").lower() in HEADER_TAGS for el in elements)
    if not found:
        return {
            "expected": "Screen should contain at least one header (h1-h6)",
            "actual": "No header tag found on this screen",
            "severity": "HIGH"
        }
    return None


def check_header_hierarchy(elements, rule):
    """
    Rule: An <h1> must be present if any <h2> or <h3> exists (proper hierarchy).
    """
    tags = [(el.get("tag_name") or "").lower() for el in elements if (el.get("tag_name") or "").lower() in HEADER_TAGS]
    has_h1    = "h1" in tags
    has_lower = any(t in tags for t in ["h2", "h3", "h4", "h5", "h6"])

    if has_lower and not has_h1:
        return {
            "expected": "An <h1> must exist before secondary headers (H2/H3…)",
            "actual": "h2/h3 headers present but h1 is missing — improper header hierarchy",
            "severity": "MEDIUM"
        }
    return None


def check_header_font_consistency(elements, rule):
    """
    Rule: Headers must share a consistent font-size/style class.
    Defect: More than 2 distinct CSS classes used across header elements.
    """
    header_classes = [
        el.get("css_class")
        for el in elements
        if (el.get("tag_name") or "").lower() in HEADER_TAGS and el.get("css_class")
    ]
    if len(set(header_classes)) > 2:
        return {
            "expected": "Headers should use at most 2 distinct CSS classes for font styling",
            "actual": f"Found {len(set(header_classes))} different header classes: {', '.join(set(header_classes))}",
            "severity": "MEDIUM"
        }
    return None


def check_modal_title(elements, rule):
    """
    Rule: Modal/popup wrapper elements must include a title header.
    """
    modal_ids = [
        el.get("div_id")
        for el in elements
        if "modal" in (el.get("css_class") or "").lower()
    ]
    if not modal_ids:
        return None

    header_div_ids = [
        el.get("div_id")
        for el in elements
        if (el.get("tag_name") or "").lower() in HEADER_TAGS
    ]

    missing = [mid for mid in modal_ids if mid and mid not in header_div_ids]
    if missing:
        return {
            "expected": "Modal/popup should have a title header inside it",
            "actual": f"Modal(s) without title: {', '.join(str(m) for m in set(missing))}",
            "severity": "MEDIUM"
        }
    return None





# ============================================================
# 3.4  ALIGNMENT & LAYOUT CONSISTENCY
# ============================================================

def check_button_alignment_class(elements, rule):
    """
    Rule: Buttons must have explicit alignment classes so they don't float randomly.
    """
    ALIGNMENT_KEYWORDS = {"text-right", "text-center", "text-left",
                          "float-right", "float-left", "d-flex",
                          "justify", "mx-auto", "ms-auto", "me-auto"}
    issues = []
    for el in elements:
        if (el.get("tag_name") or "").lower() != "button":
            continue
        css = el.get("css_class") or ""
        has_alignment = any(kw in css for kw in ALIGNMENT_KEYWORDS)
        if not has_alignment:
            label = (el.get("text_value") or "").strip()[:30]
            issues.append(f"Button '{label}' has no alignment class")

    if issues:
        return {
            "expected": "Buttons must have an explicit alignment CSS class",
            "actual": "; ".join(issues[:5]),
            "severity": "MEDIUM"
        }
    return None


def check_label_field_alignment(elements, rule):
    """
    Rule: Labels should be paired with an input/select/textarea in the same container div.
    """
    label_divs = {
        el.get("div_id")
        for el in elements
        if (el.get("tag_name") or "").lower() == "label" and el.get("div_id")
    }
    input_divs = {
        el.get("div_id")
        for el in elements
        if (el.get("tag_name") or "").lower() in {"input", "select", "textarea"} and el.get("div_id")
    }

    orphan_labels = label_divs - input_divs
    if orphan_labels:
        return {
            "expected": "Labels must be paired with an input field in the same container",
            "actual": f"Label(s) with no paired input in div(s): {', '.join(str(d) for d in orphan_labels)}",
            "severity": "MEDIUM"
        }
    return None


# ============================================================
# 3.5  FONT & COLOR CONSISTENCY
# ============================================================

def check_font_consistency(elements, rule):
    """
    Rule: The same font-family class should be used across all components.
    Defect: More than 5 distinct CSS classes detected (indicates font sprawl).
    """
    fonts = [el.get("css_class") for el in elements if el.get("css_class")]
    if len(set(fonts)) > 5:
        return {
            "expected": "Font styles should be consistent (≤5 distinct CSS classes)",
            "actual": f"Too many distinct CSS classes used: {len(set(fonts))} found",
            "severity": "MEDIUM"
        }
    return None


# ============================================================
# RULE REGISTRY
# ============================================================

# ============================================================
# 3.3  SPELLING, TERMINOLOGY & EXTRA SPACES
# ============================================================

def check_extra_spaces(el, rule):
    """
    Rule: UI text should not contain multiple consecutive spaces.
    """
    text = el.get("text_value") or ""
    cleaned_text = text.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ').strip()
    if not cleaned_text:
        return None
    if "  " in cleaned_text:
        return {
            "expected": "Text should not contain multiple consecutive spaces",
            "actual":   f"Extra spaces found in: '{cleaned_text[:60]}'",
            "severity": "LOW",
        }
    return None



UI_RULES = [
    # 3.1 Button Style
    {"level": "component", "check_type": "button_css",         "rule": "Button CSS Style Consistency",            "severity": "HIGH"},
    {"level": "component", "check_type": "button_cap",         "rule": "Button Label Capitalization",             "severity": "MEDIUM"},
    {"level": "component", "check_type": "button_icon_align",  "rule": "Button Icon Alignment",                   "severity": "MEDIUM"},
    # 3.2 Header
    {"level": "component", "check_type": "header_presence",    "rule": "Header Presence",                         "severity": "HIGH"},
    {"level": "component", "check_type": "header_hierarchy",   "rule": "Header Hierarchy",                        "severity": "MEDIUM"},
    {"level": "component", "check_type": "header_font",        "rule": "Header Font Consistency",                 "severity": "MEDIUM"},
    {"level": "component", "check_type": "modal_title",        "rule": "Modal Title Check",                       "severity": "MEDIUM"},
    # 3.3 Spelling & Text
    {"level": "element",   "check_type": "spell",              "rule": "AI Spell & Grammar Check",                "severity": "HIGH"},
    {"level": "element",   "check_type": "extra_spaces",       "rule": "Extra Spaces in Text",                    "severity": "LOW"},
    # 3.4 Alignment
    {"level": "component", "check_type": "button_align_class", "rule": "Button Alignment Class",                  "severity": "MEDIUM"},
    {"level": "component", "check_type": "label_field_align",  "rule": "Label-Field Alignment",                   "severity": "MEDIUM"},
    # 3.5 Font
    {"level": "component", "check_type": "font_consistency",   "rule": "Font Style Consistency",                  "severity": "MEDIUM"},
]

RULE_HANDLERS = {
    # 3.1 Button Style
    "button_css":         check_button_css,
    "button_cap":         check_button_capitalization,
    "button_icon_align":  check_button_icon_alignment,
    # 3.2 Header
    "header_presence":    check_header_presence,
    "header_hierarchy":   check_header_hierarchy,
    "header_font":        check_header_font_consistency,
    "modal_title":        check_modal_title,
    # 3.3 Spelling & Text
    "spell":              check_spelling,
    "extra_spaces":       check_extra_spaces,
    # 3.4 Alignment
    "button_align_class": check_button_alignment_class,
    "label_field_align":  check_label_field_alignment,
    # 3.5 Font
    "font_consistency":   check_font_consistency,
}


# ============================================================
# MAIN RUNNER
# ============================================================

def run_ui_consistency_rules():
    """
    Fetch all extracted UI elements from the database, group them by component,
    run every rule against each component, and save FAIL results.
    """
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT component_id, file_path, tag_name, text_value, css_class, div_id, line_number
        FROM ui_extraction
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Group elements by component
    components: dict = {}
    for row in rows:
        components.setdefault(row["component_id"], []).append(row)

    total_issues = 0

    # ── Cross-page button consistency (runs ONCE across ALL components) ──
    cross_page_checks = [
        ("Button Label-Class Consistency Across Pages",  check_button_label_class_consistency),
        ("Button Type Class Consistency Across Pages",   check_button_type_class_consistency),
        ("Button Type Color Consistency Across Pages",   check_button_type_color_consistency),
        ("Button Type Alignment Consistency Across Pages", check_button_type_alignment_consistency),
    ]
    for rule_name, check_fn in cross_page_checks:
        res = check_fn(components, rule={})
        if res:
            save_ui_consistency_report(
                "ALL",
                "cross-page",
                rule_name,
                "FAIL",
                res["actual"],
                res["severity"],
                res.get("expected", "N/A"),
                "0-0"
            )
            total_issues += 1

    # ── Per-component checks ──
    for comp_id, elements in components.items():
        file_path = elements[0].get("file_path", str(comp_id))

        for rule in UI_RULES:
            handler = RULE_HANDLERS.get(rule["check_type"])
            if handler is None:
                continue

            results = []
            if rule.get("level") == "element":
                for el in elements:
                    res = handler(el, rule)
                    if res:
                        # Append individual line numbers
                        res["line_num"] = el.get("line_number", "0-0")
                        results.append(res)
            else:
                res = handler(elements, rule)
                if res:
                    if isinstance(res, list):
                        results.extend(res)
                    else:
                        results.append(res)

            for issue in results:
                line_num = issue.get("line_num", elements[0].get("line_number", "0-0") if elements else "0-0")
                save_ui_consistency_report(
                    comp_id,
                    file_path,
                    rule["rule"],
                    "FAIL",
                    issue.get("actual", ""),
                    issue.get("severity", rule.get("severity", "MEDIUM")),
                    "N/A",
                    line_num
                )
                total_issues += 1

    print(f"   UI consistency rules completed — {total_issues} issue(s) found.")


if __name__ == "__main__":
    run_ui_consistency_rules()