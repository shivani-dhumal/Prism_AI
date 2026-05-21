# scanners/code_metrics_scanner.py
"""
Dynamic Code Metrics Scanner
─────────────────────────────
Analyses every scanned file and computes:
  • total_lines   – raw line count
  • code_lines    – lines that contain actual logic / markup
  • blank_lines   – empty or whitespace-only lines
  • comment_lines – single-line comments (// # <!-- -->)
  • code_ratio    – code_lines / total_lines (0-100 %)

Results are saved to the `code_metrics` table (per-file) and a
summary JSON is exported to reports/code_metrics.json.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_ops import get_db


# ──────────────────────────────────────────────
#  LANGUAGE-AWARE COMMENT DETECTION
# ──────────────────────────────────────────────

# Maps file extension → (single_line_comment_prefixes, block_comment_start, block_comment_end)
_COMMENT_RULES = {
    # JavaScript / TypeScript / Vue / Go
    "js":   (["//"], "/*", "*/"),
    "ts":   (["//"], "/*", "*/"),
    "vue":  (["//"], "/*", "*/"),   # <script> sections
    "go":   (["//"], "/*", "*/"),
    "jsx":  (["//"], "/*", "*/"),
    "tsx":  (["//"], "/*", "*/"),

    # Python
    "py":   (["#"],  '"""', '"""'),

    # HTML / XML
    "html": ([],     "<!--", "-->"),
    "xml":  ([],     "<!--", "-->"),
    "svg":  ([],     "<!--", "-->"),

    # CSS / SCSS / LESS
    "css":  (["//"], "/*", "*/"),
    "scss": (["//"], "/*", "*/"),
    "less": (["//"], "/*", "*/"),

    # Shell / YAML / TOML
    "sh":   (["#"],  None,  None),
    "yaml": (["#"],  None,  None),
    "yml":  (["#"],  None,  None),
    "toml": (["#"],  None,  None),

    # SQL
    "sql":  (["--", "#"], "/*", "*/"),
}


def _get_rules(ext: str):
    """Return comment rules for an extension, with a sensible fallback."""
    return _COMMENT_RULES.get(ext, (["//", "#"], "/*", "*/"))


def analyse_content(content: str, ext: str) -> dict:
    """
    Return a dict with keys:
        total_lines, code_lines, blank_lines, comment_lines, code_ratio
    """
    single_prefixes, block_start, block_end = _get_rules(ext)

    total = 0
    blank = 0
    comment = 0
    in_block = False

    for raw_line in content.splitlines():
        total += 1
        stripped = raw_line.strip()

        # ── blank line ──
        if not stripped:
            blank += 1
            continue

        # ── inside a block comment ──
        if in_block:
            comment += 1
            if block_end and block_end in stripped:
                in_block = False
            continue

        # ── block comment starts on this line ──
        if block_start and stripped.startswith(block_start):
            comment += 1
            if block_end and block_end not in stripped[len(block_start):]:
                in_block = True
            continue

        # ── single-line comment ──
        if any(stripped.startswith(p) for p in single_prefixes):
            comment += 1
            continue

        # ── Vue / HTML: detect <!-- … --> single-line comments in template ──
        if ext == "vue" and stripped.startswith("<!--") and "-->" in stripped:
            comment += 1
            continue

    code = total - blank - comment
    ratio = round((code / total * 100), 1) if total > 0 else 0.0

    return {
        "total_lines":   total,
        "code_lines":    code,
        "blank_lines":   blank,
        "comment_lines": comment,
        "code_ratio":    ratio,
    }


# ──────────────────────────────────────────────
#  DATABASE PERSISTENCE
# ──────────────────────────────────────────────

def save_code_metrics(file_id: int, file_name: str, file_path: str,
                      extension: str, metrics: dict) -> None:
    """Insert one row into `code_metrics`."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO code_metrics
        (file_id, file_name, file_path, extension,
         total_lines, code_lines, blank_lines, comment_lines, code_ratio)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        file_id,
        file_name,
        file_path,
        extension,
        metrics["total_lines"],
        metrics["code_lines"],
        metrics["blank_lines"],
        metrics["comment_lines"],
        metrics["code_ratio"],
    ))

    conn.commit()
    cursor.close()
    conn.close()


# ──────────────────────────────────────────────
#  PUBLIC SCANNER ENTRY-POINT
# ──────────────────────────────────────────────

def scan_code_metrics(file_id: int, file_name: str, file_path: str,
                      content: str, ext: str) -> dict:
    """
    Called from main.py for each file.
    Returns the metrics dict so callers can use it if needed.
    """
    metrics = analyse_content(content, ext)
    save_code_metrics(file_id, file_name, file_path, ext, metrics)
    return metrics


# ──────────────────────────────────────────────
#  JSON REPORT EXPORTER  (called after full scan)
# ──────────────────────────────────────────────

def export_code_metrics_report(report_dir: str = "reports") -> None:
    """
    Read `code_metrics` from DB and write a rich summary JSON to
    reports/code_metrics.json with per-file, per-extension, and
    overall totals.
    """
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM code_metrics ORDER BY code_lines DESC")
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    if not rows:
        print("  [code_metrics] No data to export.")
        return

    # ── per-extension aggregation ──
    ext_agg = {}
    grand = {"files": 0, "total_lines": 0, "code_lines": 0,
             "blank_lines": 0, "comment_lines": 0}

    for r in rows:
        ext = r["extension"]
        if ext not in ext_agg:
            ext_agg[ext] = {"files": 0, "total_lines": 0, "code_lines": 0,
                            "blank_lines": 0, "comment_lines": 0}
        for key in ("total_lines", "code_lines", "blank_lines", "comment_lines"):
            ext_agg[ext][key] += r[key]
            grand[key] += r[key]
        ext_agg[ext]["files"] += 1
        grand["files"] += 1

    # add code_ratio to each aggregation
    for agg in list(ext_agg.values()) + [grand]:
        t = agg["total_lines"]
        agg["code_ratio"] = round(agg["code_lines"] / t * 100, 1) if t else 0.0

    report = {
        "summary": grand,
        "by_extension": ext_agg,
        "files": rows,
    }

    os.makedirs(report_dir, exist_ok=True)
    out_path = os.path.join(report_dir, "code_metrics.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, default=str)

    print(f"  Created: {out_path}")
    print(f"  Total files: {grand['files']}  |  "
          f"Code lines: {grand['code_lines']}  |  "
          f"Comment lines: {grand['comment_lines']}  |  "
          f"Blank lines: {grand['blank_lines']}  |  "
          f"Code ratio: {grand['code_ratio']}%")
