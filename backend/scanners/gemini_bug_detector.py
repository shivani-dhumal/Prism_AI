"""
gemini_bug_detector.py — Deep Bug Detection using Google Gemini API.

This scanner sends source code to Gemini and asks it to find real bugs:
  • Logic errors, off-by-one, race conditions
  • Null/undefined dereferences
  • Resource leaks (unclosed connections, files, streams)
  • Security vulnerabilities (XSS, injection, hardcoded secrets)
  • Error handling gaps (missing try/catch, swallowed exceptions)
  • Type mismatches and incorrect API usage
  • Dead code paths and unreachable code
  • Concurrency issues

Results are stored in the `bug_detections` DB table and surfaced
in the Audit Report frontend.
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
from database_ops import get_db

# ─────────────────────────────────────────────
# GEMINI CONFIG
# ─────────────────────────────────────────────

MODEL_NAME = "gemini-2.5-flash"

_client = genai.Client(api_key=GEMINI_API_KEY)
_gen_config = types.GenerateContentConfig(
    temperature=0.15,
    response_mime_type="application/json",
)


# ─────────────────────────────────────────────
# BUG DETECTION PROMPT
# ─────────────────────────────────────────────

BUG_DETECT_PROMPT = """You are a senior software engineer and bug hunter.
Analyze the following source code and find ONLY **critical, provable bugs** — NOT style issues, NOT suggestions, NOT potential issues.

FILE: {file_name}  (extension: .{ext})
─────────────────────────────────
{code}
─────────────────────────────────

A BUG is code that WILL FAIL or BREAK at runtime. Examples:
✓ Variable accessed before initialization → CRASH
✓ Null reference dereference → CRASH
✓ Unclosed resource (connection, file) → LEAK
✓ SQL injection → SECURITY BREACH
✓ Race condition → DATA CORRUPTION
✓ Missing error handler on async → UNHANDLED REJECTION

NOT bugs (do NOT report):
✗ "Could be null" without evidence it IS null
✗ "Missing try/catch" on every API call
✗ "Console.log should be removed"
✗ "Use const instead of let"
✗ Potential future issues
✗ "What if this parameter is undefined?" without proof
✗ Code smells or style preferences

For EACH REAL bug found, return:
- "bug_category": "logic_error", "null_deref", "resource_leak", "security", "error_handling", "type_error", "api_misuse", "concurrency", "dead_code", or "data_flow"
- "title": exact bug name (e.g. "Variable 'x' accessed before assignment on line 42")
- "severity": "CRITICAL" (will crash), "HIGH" (breaks feature), "MEDIUM" (workaround exists), or "LOW" (edge case)
- "line_number": exact line where bug occurs
- "description": PROOF of the bug with evidence from the code
- "fix_suggestion": concrete code fix
- "confidence": 0.9-1.0 ONLY for real bugs you are certain about

Return JSON: {{"bugs": [...]}}
If no bugs found, return {{"bugs": []}}.

CRITICAL RULE:
Only confidence >= 0.9 for bugs that WILL CRASH or WILL BREACH SECURITY.
Lower confidence should NOT be reported — it means it's not a real bug.
Empty bugs array is CORRECT if code is safe.
"""


# ─────────────────────────────────────────────
# LLM CALL WITH RETRY
# ─────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAY = 3


def _call_gemini_bug_detect(file_name: str, ext: str, code: str) -> list:
    """Send code to Gemini for bug detection. Returns list of bug dicts."""

    max_chars = 30000
    if len(code) > max_chars:
        truncated_lines = code[:max_chars].count('\n')
        code = code[:max_chars] + f"\n\n... [TRUNCATED — file too large. Lines above: {truncated_lines}] ..."

    prompt = BUG_DETECT_PROMPT.format(file_name=file_name, ext=ext, code=code)

    for attempt in range(MAX_RETRIES):
        try:
            response = _client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=_gen_config,
            )
            text = response.text.strip()

            data = json.loads(text)
            bugs = data.get("bugs", [])

            valid = []
            for bug in bugs:
                if not isinstance(bug, dict):
                    continue
                if "title" not in bug or "description" not in bug:
                    continue

                # Normalize fields
                bug.setdefault("bug_category", "logic_error")
                bug.setdefault("severity", "MEDIUM")
                bug.setdefault("line_number", 0)
                # If fix_suggestion is empty/missing, improve it based on category
                if "fix_suggestion" not in bug or not bug.get("fix_suggestion", "").strip():
                    category = bug.get("bug_category", "logic_error")
                    suggestions = {
                        "null_deref": "Add null/undefined checks before accessing properties.",
                        "resource_leak": "Ensure resources are properly closed/cleaned up (use finally or try-finally).",
                        "security": "Review for security implications and apply appropriate sanitization/validation.",
                        "error_handling": "Wrap in try/catch and handle potential errors explicitly.",
                        "type_error": "Fix type mismatch — ensure arguments match expected types.",
                        "api_misuse": "Correct the API usage according to the API documentation.",
                        "concurrency": "Use locks or async patterns to prevent race conditions.",
                        "dead_code": "Remove unreachable code or fix the logic that makes it dead.",
                        "data_flow": "Initialize variables before use and check variable scope.",
                    }
                    bug["fix_suggestion"] = suggestions.get(category, "Fix the identified issue according to the bug description.")
                bug.setdefault("confidence", 0.5)

                # Validate severity
                if bug["severity"] not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    bug["severity"] = "MEDIUM"

                # Validate confidence and REJECT low-confidence hallucinations
                try:
                    confidence = min(1.0, max(0.0, float(bug["confidence"])))
                    bug["confidence"] = confidence
                except (ValueError, TypeError):
                    bug["confidence"] = 0.5

                # FILTER: Only accept bugs with confidence >= 0.75 to avoid hallucinations
                if bug["confidence"] >= 0.75:
                    valid.append(bug)

            return valid

        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            print(f"      [WARN] Could not parse Gemini bug-detect response for {file_name}")
            return []

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                err_str = str(e)
                if "429" in err_str or "Quota" in err_str:
                    wait = 15
                    print(f"\n      [RATE LIMIT] Waiting {wait}s... (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            print(f"      [WARN] Gemini API error for {file_name}: {e}")
            return []


# ─────────────────────────────────────────────
# DATABASE PERSISTENCE
# ─────────────────────────────────────────────

def save_bug_detection(file_id, file_name, file_path, bug: dict):
    """Insert one bug detection row into the database."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO bug_detections
        (file_id, file_name, file_path, bug_category, title, severity,
         line_number, description, fix_suggestion, confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        file_id,
        file_name,
        file_path,
        bug.get("bug_category", "logic_error"),
        bug.get("title", "Unknown Bug"),
        bug.get("severity", "MEDIUM"),
        bug.get("line_number", 0),
        bug.get("description", ""),
        bug.get("fix_suggestion", ""),
        bug.get("confidence", 0.5),
    ))

    conn.commit()
    cursor.close()
    conn.close()


# ─────────────────────────────────────────────
# PUBLIC SCANNER ENTRY POINT
# ─────────────────────────────────────────────

def detect_bugs_in_file(file_id: int, file_name: str, file_path: str,
                        content: str, ext: str) -> int:
    """Scan a single file for bugs using Gemini. Returns count of bugs found."""
    if not content or not content.strip():
        return 0

    bugs = _call_gemini_bug_detect(file_name, ext, content)

    for bug in bugs:
        save_bug_detection(file_id, file_name, file_path, bug)

    return len(bugs)


def run_bug_detection(target_directory=None, progress_fn=None):
    """
    Reads all code files from the DB (optionally filtered by target_directory),
    runs Gemini bug detection on each, and saves results to bug_detections.
    """
    SCANNABLE_EXTS = {'vue', 'js', 'ts', 'jsx', 'tsx', 'py', 'html', 'css', 'scss'}

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id AS file_id, file_name, file_path, extension
        FROM files
        WHERE LOWER(extension) IN ('vue','js','ts','jsx','tsx','py','html','css','scss')
        ORDER BY file_name
    """)
    all_rows = cur.fetchall()
    cur.close()
    conn.close()

    # Optionally filter by target_directory (best-effort, both separator styles)
    if target_directory:
        norm_td = target_directory.replace("\\", "/").rstrip("/").lower()
        rows = [
            r for r in all_rows
            if r.get("file_path", "").replace("\\", "/").lower().startswith(norm_td)
        ]
        if not rows:          # fallback: scan everything if path filter matched nothing
            rows = all_rows
    else:
        rows = all_rows

    total_bugs = 0
    total_files = len(rows)
    consecutive_quota_errors = 0
    MAX_CONSECUTIVE_QUOTA_ERRORS = 3

    print(f"   [Bug Detector] Scanning {total_files} files via Gemini ({MODEL_NAME})...")

    for idx, row in enumerate(rows, 1):
        fp = row["file_path"]
        fn = row["file_name"]
        ext = (row.get("extension") or "").lower()

        # Report progress (0–100 within this stage)
        if progress_fn:
            pct = int((idx - 1) / max(total_files, 1) * 100)
            progress_fn(pct, f"Analyzing {fn} ({idx}/{total_files})")

        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            print(f"      [{idx}/{total_files}] SKIP {fn} (cannot read)")
            continue

        print(f"      [{idx}/{total_files}] Bug scanning {fn}...", end="", flush=True)

        count = 0
        hit_quota = False
        for attempt in range(MAX_RETRIES):
            try:
                count = detect_bugs_in_file(row["file_id"], fn, fp, content, ext)
                consecutive_quota_errors = 0
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota" in err_str or "quota" in err_str.lower():
                    hit_quota = True
                    wait = 20
                    print(f"\n      [RATE LIMIT] Waiting {wait}s... (attempt {attempt+1}/{MAX_RETRIES})")
                    time.sleep(wait)
                else:
                    print(f" -> FAILED ({err_str[:60]})")
                    break

        if hit_quota:
            consecutive_quota_errors += 1

        total_bugs += count
        print(f" -> {count} bugs", flush=True)

        if consecutive_quota_errors >= MAX_CONSECUTIVE_QUOTA_ERRORS:
            print(f"\n   [Bug Detector] Stopping — Gemini quota exhausted after {consecutive_quota_errors} consecutive rate-limit errors.")
            break

        # Respect Gemini free-tier rate limits between files (increased to prevent quota exhaustion)
        if idx < total_files:
            time.sleep(5)  # Increased from 3.5s to 5s to prevent hitting quota

    if progress_fn:
        progress_fn(100, f"Done — {total_bugs} bugs found")

    print(f"   [Bug Detector] Done. Total bugs found: {total_bugs}")
    return total_bugs


# ─────────────────────────────────────────────
# LOAD BUGS FROM DB (for API/report)
# ─────────────────────────────────────────────

def get_all_bugs():
    """Load all bug detections from DB, ordered by severity."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT bd.*, f.extension
        FROM bug_detections bd
        LEFT JOIN files f ON f.id = bd.file_id
        ORDER BY
            FIELD(bd.severity, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'),
            bd.confidence DESC
    """)
    bugs = cursor.fetchall()

    cursor.close()
    conn.close()
    return bugs


def get_bug_summary():
    """Get aggregated bug counts by severity and category."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # By severity
    cursor.execute("""
        SELECT severity, COUNT(*) as count
        FROM bug_detections
        GROUP BY severity
    """)
    by_severity = {r["severity"]: r["count"] for r in cursor.fetchall()}

    # By category
    cursor.execute("""
        SELECT bug_category, COUNT(*) as count
        FROM bug_detections
        GROUP BY bug_category
        ORDER BY count DESC
    """)
    by_category = {r["bug_category"]: r["count"] for r in cursor.fetchall()}

    # By file (top 10 most buggy)
    cursor.execute("""
        SELECT file_name, file_path, COUNT(*) as count,
               SUM(CASE WHEN severity IN ('CRITICAL','HIGH') THEN 1 ELSE 0 END) as critical_high
        FROM bug_detections
        GROUP BY file_name, file_path
        ORDER BY critical_high DESC, count DESC
        LIMIT 10
    """)
    top_files = cursor.fetchall()

    # Total
    cursor.execute("SELECT COUNT(*) as total FROM bug_detections")
    total = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    return {
        "total": total,
        "by_severity": by_severity,
        "by_category": by_category,
        "top_files": top_files,
    }
