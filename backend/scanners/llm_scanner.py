"""
llm_scanner.py — LLM-powered code scanner using Gemini.

Instead of static rule-based checks, this scanner sends source code
directly to Gemini and asks it to find UI, accessibility, code quality,
and complexity issues.  Results are saved into the same DB tables
(ui_consistency_report, accessibility_report) so the existing HTML
report generator works unchanged.
"""

import os
import sys
import json
import time
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows console encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from google import genai
from google.genai import types
from config import GEMINI_API_KEY, DB_CONFIG
from database_ops import save_ui_consistency_report, save_accessibility_report

# ─────────────────────────────────────────────
# GEMINI CONFIG
# ─────────────────────────────────────────────

MODEL_NAME = "gemini-2.5-flash"

_client = genai.Client(api_key=GEMINI_API_KEY)
_gen_config = types.GenerateContentConfig(
    temperature=0.2,
    response_mime_type="application/json",
)


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

ANALYSIS_PROMPT = """You are an expert frontend code auditor.
Analyze the following source file and report ALL issues you find.

FILE: {file_name}  (extension: .{ext})
─────────────────────────────────
{code}
─────────────────────────────────

Scan the code for issues in these categories:

1. **UI Consistency** — button style mismatches, inconsistent CSS classes, missing headers, label/field alignment issues, capitalization problems, extra whitespace in text, font inconsistency.
2. **Accessibility** — missing alt text on images, missing aria-label on icon buttons, missing labels on form inputs, missing aria-live on dynamic content, color contrast problems, keyboard navigation issues (tabindex, missing @keydown handlers), focus visibility, screen reader compatibility.
3. **Code Quality** — dead code, unused variables/imports, overly complex functions, deeply nested logic, long methods, hardcoded strings/URLs, console.log left in production code, missing error handling, TODO/FIXME comments.
4. **Security** — XSS vulnerabilities (v-html usage), hardcoded secrets/tokens, unsafe external URLs, SQL injection risks, eval() usage.
5. **Performance** — unnecessary watchers, heavy computations in template, large inline styles, missing lazy loading.

For EACH issue found, return a JSON object with these exact fields:
- "category": one of "ui_consistency", "accessibility", "code_quality", "security", "performance"
- "rule_name": a short descriptive rule name (e.g. "Image missing alt text")
- "severity": one of "HIGH", "MEDIUM", "LOW"
- "line_number": the line number where the issue occurs (integer, or 0 if file-level)
- "description": a clear explanation of what is wrong and how to fix it

Return a JSON object with a single key "issues" containing an array of issue objects.
If no issues are found, return {{"issues": []}}.

IMPORTANT:
- Be thorough but do NOT invent issues that don't exist in the code.
- Give accurate line numbers based on the code shown.
- Focus on real, actionable issues — not stylistic preferences.
- For Vue files, check template, script, and style sections.
"""


# ─────────────────────────────────────────────
# LLM CALL WITH RETRY
# ─────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def _call_gemini(file_name: str, ext: str, code: str) -> list:
    """Send code to Gemini and return a list of issue dicts."""

    # Truncate very large files to avoid token limits
    max_chars = 30000
    if len(code) > max_chars:
        code = code[:max_chars] + "\n\n... [TRUNCATED — file too large] ..."

    prompt = ANALYSIS_PROMPT.format(file_name=file_name, ext=ext, code=code)

    for attempt in range(MAX_RETRIES):
        try:
            response = _client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=_gen_config,
            )
            text = response.text.strip()

            # Parse JSON response
            data = json.loads(text)
            issues = data.get("issues", [])

            # Validate each issue has required fields
            valid = []
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                if "rule_name" not in issue or "description" not in issue:
                    continue
                # Normalize fields
                issue.setdefault("category", "code_quality")
                issue.setdefault("severity", "MEDIUM")
                issue.setdefault("line_number", 0)
                # Ensure severity is valid
                if issue["severity"] not in ("HIGH", "MEDIUM", "LOW"):
                    issue["severity"] = "MEDIUM"
                valid.append(issue)

            return valid

        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            print(f"      [WARN] Could not parse Gemini response for {file_name}")
            return []

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            print(f"      [WARN] Gemini API error for {file_name}: {e}")
            return []


# ─────────────────────────────────────────────
# SAVE ISSUES TO DB
# ─────────────────────────────────────────────

def _save_issues(component_id, file_path, issues: list):
    """Save LLM-detected issues to the appropriate DB tables."""
    acc_categories = {"accessibility"}
    
    for issue in issues:
        category = issue.get("category", "code_quality")
        rule_name = issue.get("rule_name", "LLM Detected Issue")
        severity = issue.get("severity", "MEDIUM")
        description = issue.get("description", "")
        line_num = issue.get("line_number", 0)
        line_str = f"{line_num}-{line_num}" if line_num else "0-0"

        # Prefix rule name with category icon for clarity in report
        prefix = {
            "ui_consistency": "[UI]",
            "accessibility":  "[A11Y]",
            "code_quality":   "[CODE]",
            "security":       "[SEC]",
            "performance":    "[PERF]",
        }.get(category, "[LLM]")
        
        full_rule = f"{prefix} {rule_name}"

        if category in acc_categories:
            save_accessibility_report(
                component_id,
                file_path,
                full_rule,
                "FAIL",
                description,
                severity,
                line_str,
            )
        else:
            save_ui_consistency_report(
                component_id,
                file_path,
                full_rule,
                "FAIL",
                description,
                severity,
                "N/A",
                line_str,
            )


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def llm_scan_file(component_id, file_id, file_name: str, file_path: str,
                  content: str, ext: str) -> int:
    """
    Scan a single file using the LLM.
    Returns the number of issues found.
    """
    if not content or not content.strip():
        return 0

    issues = _call_gemini(file_name, ext, content)

    if issues:
        _save_issues(component_id, file_path, issues)

    return len(issues)


def run_llm_scan():
    """
    Standalone entry point: read all files from DB and scan each via LLM.
    This is an alternative to calling llm_scan_file() per-file in main.py.
    """
    import mysql.connector
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT f.id AS file_id, f.file_name, f.file_path, f.extension,
               c.id AS component_id
        FROM files f
        LEFT JOIN components c ON c.file_id = f.id
        WHERE f.extension = 'vue'
        ORDER BY f.file_name
        LIMIT 15
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    total_issues = 0
    total_files = len(rows)
    consecutive_quota_errors = 0
    MAX_CONSECUTIVE_QUOTA_ERRORS = 3

    print(f"   [LLM Scanner] Scanning {total_files} files via Gemini ({MODEL_NAME})...")

    for idx, row in enumerate(rows, 1):
        fp = row["file_path"]
        fn = row["file_name"]
        ext = row["extension"]
        comp_id = row.get("component_id")

        # Read source file
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            print(f"      [{idx}/{total_files}] SKIP {fn} (cannot read)")
            continue

        print(f"      [{idx}/{total_files}] Scanning {fn}...", end="", flush=True)

        # Retry logic for handling 429 Quota errors specifically
        max_retries = 3
        count = 0
        hit_quota = False
        for attempt in range(max_retries):
            try:
                count = llm_scan_file(comp_id, row["file_id"], fn, fp, content, ext)
                consecutive_quota_errors = 0  # Reset on success
                break  # Success
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota exceeded" in err_str:
                    hit_quota = True
                    print(f"\n      [RATE LIMIT] Hit quota on {fn}. Waiting 15 seconds to cool down... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(15)
                else:
                    print(f" -> FAILED ({err_str[:50]})")
                    break

        if hit_quota:
            consecutive_quota_errors += 1
        
        total_issues += count
        print(f" -> {count} issues", flush=True)

        # Abort early if quota is fully exhausted
        if consecutive_quota_errors >= MAX_CONSECUTIVE_QUOTA_ERRORS:
            print(f"\n   [LLM Scanner] SKIPPING remaining files - Gemini API daily quota exhausted ({consecutive_quota_errors} consecutive 429 errors)")
            break

        # Free Tier Rate Limiting (~15 RPM = 4 seconds per request)
        if idx < total_files:
            time.sleep(4.5)

    print(f"   [LLM Scanner] Done. Total issues found: {total_issues}")
    return total_issues
