"""
spell_checker.py — Spell and grammar checking using the pyspellchecker library.
NO regex used anywhere.
"""

import os
import json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spellchecker import SpellChecker
from config import TARGET_DIRECTORY

spell = SpellChecker()

SPELL_CHECK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "span", "p", "button", "label"}
VALID_LANG_KEYS = set()


def _extract_keys(d):
    keys = set()
    for k, v in d.items():
        keys.add(k.lower())
        if isinstance(v, dict):
            keys.update(_extract_keys(v))
    return keys


def _load_lang_keys():
    for root, dirs, files in os.walk(TARGET_DIRECTORY):
        if os.path.basename(root) == 'lang':
            for f in files:
                if f.endswith('.json'):
                    try:
                        with open(os.path.join(root, f), 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                            if isinstance(data, dict):
                                VALID_LANG_KEYS.update(_extract_keys(data))
                    except Exception:
                        pass


_load_lang_keys()


# ─────────────────────────────────────────────
# STRING-ONLY HELPERS  (no regex)
# ─────────────────────────────────────────────

def _has_multiple_spaces(text: str) -> bool:
    """Return True if text contains two or more consecutive spaces."""
    return '  ' in text


def _extract_alpha_words(text: str) -> list:
    """
    Extract word tokens that contain only ASCII letters.
    Uses plain character scanning — no regex.
    """
    words = []
    current = []
    for ch in text:
        if ch.isalpha():
            current.append(ch)
        else:
            if current:
                words.append(''.join(current))
                current = []
    if current:
        words.append(''.join(current))
    return words


def _split_camel_case(word: str) -> list:
    """
    Split a camelCase or PascalCase word into its component parts.
    Also splits on hyphens and underscores.
    Uses plain character iteration — no regex.
    """
    # First replace separators with spaces
    cleaned = word.replace('-', ' ').replace('_', ' ')

    # Now split camelCase boundaries by character scanning
    result = []
    current = []
    chars = list(cleaned)
    for i, ch in enumerate(chars):
        if ch == ' ':
            if current:
                result.append(''.join(current))
                current = []
        elif ch.isupper():
            # Boundary: previous was lowercase, or next is lowercase after a run of caps
            if current:
                prev_lower = chars[i - 1].islower() if i > 0 and chars[i - 1] != ' ' else False
                next_lower = chars[i + 1].islower() if i + 1 < len(chars) else False
                if prev_lower or (not prev_lower and next_lower and len(current) > 1):
                    result.append(''.join(current))
                    current = []
            current.append(ch)
        else:
            current.append(ch)
    if current:
        result.append(''.join(current))

    return [p.lower() for p in result if len(p) > 1]


def _is_connected_word(token: str) -> bool:
    """
    Return True if all sub-parts of a camelCase / hyphenated token are
    known dictionary words (indicating it is a valid compound word).
    """
    parts = _split_camel_case(token)
    return len(parts) >= 2 and len(spell.unknown(parts)) == 0


def check_grammar(text: str) -> list:
    """Basic grammar checks using string operations only."""
    issues = []
    if _has_multiple_spaces(text):
        issues.append("Contains multiple consecutive spaces")
    return issues


def correct_text(text: str) -> list:
    """Check text for spelling and grammar issues without regex."""
    words = _extract_alpha_words(text)
    words_to_check = [w.lower() for w in words if len(w) > 1]
    original_case = {w.lower(): w for w in words if len(w) > 1}

    raw_misspelled = spell.unknown(words_to_check)

    misspelled = [
        w for w in raw_misspelled
        if w not in VALID_LANG_KEYS
        and not _is_connected_word(original_case.get(w, w))
    ]

    grammar_issues = check_grammar(text)
    issues = []

    if misspelled:
        corrections = [f"'{word}'" for word in misspelled]
        issues.append(f"Misspelled words: {', '.join(corrections)}")

    if grammar_issues:
        issues.extend(grammar_issues)

    return issues


def get_el_id(el) -> str:
    """Build a readable identifier string for a UI element."""
    tag = el.get("tag_name") or "unknown"
    div_id = el.get("div_id")
    css = el.get("css_class")
    parts = []
    if div_id:
        parts.append(f"id='{div_id}'")
    if css:
        parts.append(f"class='{css}'")
    return f"<{tag} {' '.join(parts)}>" if parts else f"<{tag}>"


def check_spelling(el, rule) -> dict | None:
    """Check a single UI element for spelling / grammar issues."""
    tag = (el.get("tag_name") or "").lower()
    if tag not in SPELL_CHECK_TAGS:
        return None

    text = (el.get("text_value") or "").strip()
    if not text or len(text) < 2:
        return None

    # Skip template variables
    if "{{" in text and "}}" in text:
        return None

    # Skip strings that have fewer than 2 alphabetic characters
    alpha_count = sum(1 for ch in text if ch.isalpha())
    if alpha_count < 2:
        return None

    issues = correct_text(text)

    if issues:
        return {
            "expected": "Text should be free of spelling and grammar errors.",
            "actual": f"{get_el_id(el)} issue(s): {'; '.join(issues)}. Original text: '{text}'"
        }

    return None


# ─────────────────────────────────────────────
# LANGUAGE FILE SCANNER
# ─────────────────────────────────────────────

def _check_json_values(d, path=""):
    """Recursively checks spelling for string values in a JSON dict."""
    issues = []
    for k, v in d.items():
        current_path = f"{path}.{k}" if path else k
        if isinstance(v, dict):
            issues.extend(_check_json_values(v, current_path))
        elif isinstance(v, str):
            # Check the translated string!
            alpha_count = sum(1 for ch in v if ch.isalpha())
            if alpha_count >= 2 and "{{" not in v:
                errs = correct_text(v)
                if errs:
                    issues.append((current_path, v, errs))
    return issues


def check_language_files():
    """Scans all JSON files in lang/ folders and checks spelling of their values."""
    from database_ops import save_ui_consistency_report
    for root, dirs, files in os.walk(TARGET_DIRECTORY):
        if os.path.basename(root) == 'lang':
            for f in files:
                if f.endswith('.json'):
                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                            if isinstance(data, dict):
                                issues = _check_json_values(data)
                                for json_path, original_text, errs in issues:
                                    save_ui_consistency_report(
                                        component_id="LANG_FILE",
                                        file_path=os.path.join(os.path.basename(os.path.dirname(root)), "lang", f),
                                        rule_name="Language File Spell Check",
                                        status="FAIL",
                                        actual_result=f"Key '{json_path}' issue(s): {'; '.join(errs)}. Text: '{original_text}'",
                                        severity="MEDIUM",
                                        recommendation="Language translations should be free of spelling/grammar errors."
                                    )
                    except Exception:
                        pass
