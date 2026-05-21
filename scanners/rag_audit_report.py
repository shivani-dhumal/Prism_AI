"""
RAG-Based AI Audit Report Generator
Loads all scan data from DB + reads actual source code,
sends BATCHED prompts to Google Gemini API for recommendations,
and generates a styled HTML report.
"""

import os
import sys
import json
import re
import mysql.connector
import google.generativeai as genai

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG, TARGET_DIRECTORY

# ──────────────────────────────────────────────────────────────────
# Gemini setup  –  put your API key in config.py as GEMINI_API_KEY
# ──────────────────────────────────────────────────────────────────
try:
    from config import GEMINI_API_KEY
except ImportError:
    GEMINI_API_KEY = ""

genai.configure(api_key=GEMINI_API_KEY)
MODEL = genai.GenerativeModel("gemini-2.5-flash")


# ──────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def load_all_scan_data():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    tables = {
        "files":                "SELECT id, file_name, file_path, extension FROM files",
        "components":           "SELECT id, file_id, component_name FROM components",
        "apis":                 "SELECT id, file_id, method, url, payload FROM apis",
        "file_flags":           "SELECT * FROM file_flags",
        "component_complexity": "SELECT * FROM component_complexity",
        "ui_consistency":       "SELECT * FROM ui_consistency_report WHERE status='FAIL'",
        "accessibility":        "SELECT * FROM accessibility_report  WHERE status='FAIL'",
    }
    data = {}
    for key, query in tables.items():
        cur.execute(query)
        data[key] = cur.fetchall()
    cur.close()
    conn.close()
    return data


# ──────────────────────────────────────────────────────────────────
# Source-code reader (cached per file)
# ──────────────────────────────────────────────────────────────────
_file_cache = {}

def read_source(path, max_lines=120):
    if path in _file_cache:
        return _file_cache[path]
    try:
        if not os.path.isfile(path):
            _file_cache[path] = None
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        snippet = "".join(lines[:max_lines])
        if len(lines) > max_lines:
            snippet += f"\n... ({len(lines)-max_lines} more lines)"
        _file_cache[path] = snippet
        return snippet
    except Exception:
        _file_cache[path] = None
        return None


# ──────────────────────────────────────────────────────────────────
# Gemini – ask for recommendations (BATCHED per file)
# ──────────────────────────────────────────────────────────────────
def ask_gemini(prompt, max_retries=4):
    import time
    for attempt in range(max_retries):
        try:
            resp = MODEL.generate_content(prompt)
            return resp.text
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < max_retries - 1:
                wait = 25 * (attempt + 1)
                print(f"      ⏳ Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                return f"[Gemini Error] {e}"


def generate_recommendations(issues, issue_type):
    """Group issues by file → one Gemini call per file → parse back."""
    # Limit number of issues to avoid rate limits
    issues = issues[:3]

    # Group by file_path
    by_file = {}
    for issue in issues:
        fp = issue.get("file_path", "unknown")
        by_file.setdefault(fp, []).append(issue)

    all_recs = []

    for fp, file_issues in by_file.items():
        fname = os.path.basename(fp)
        source = read_source(fp)
        code_block = ""
        if source:
            code_block = f"\n\nSource code of `{fname}`:\n```\n{source}\n```"

        issue_lines = ""
        for idx, iss in enumerate(file_issues, 1):
            issue_lines += f"{idx}. Rule: {iss.get('rule_name','')} | Finding: {iss.get('actual_result','')} | Severity: {iss.get('severity','MEDIUM')}\n"

        prompt = f"""You are a senior frontend code reviewer.
Below are {len(file_issues)} {issue_type} issues found in `{fname}` ({fp}):

{issue_lines}
{code_block}

For EACH issue (numbered), give a short actionable recommendation (2-3 sentences max).
Include a small code fix if possible.
Reply as a numbered list matching the issue numbers above. Keep it concise."""

        print(f"   → Gemini: {fname} ({len(file_issues)} {issue_type} issues)")
        response = ask_gemini(prompt)

        # Split response roughly by issue number
        rec_parts = re.split(r'\n(?=\d+[\.\)])', response)
        rec_map = {}
        for part in rec_parts:
            m = re.match(r'^(\d+)[\.\)]\s*(.*)', part, re.DOTALL)
            if m:
                rec_map[int(m.group(1))] = m.group(2).strip()

        for idx, iss in enumerate(file_issues, 1):
            all_recs.append({
                "file":       fp,
                "file_name":  fname,
                "rule":       iss.get("rule_name", ""),
                "finding":    iss.get("actual_result", ""),
                "severity":   iss.get("severity", "MEDIUM"),
                "recommendation": rec_map.get(idx, response.strip()),
            })

    return all_recs


# ──────────────────────────────────────────────────────────────────
# HTML report
# ──────────────────────────────────────────────────────────────────
def _esc(text):
    return (str(text) or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def _badge(sev):
    c = {"HIGH":"#ef4444","MEDIUM":"#f59e0b","LOW":"#3b82f6"}.get(sev,"#6b7280")
    return f'<span class="badge" style="background:{c}">{sev}</span>'

def _rec_html(text):
    t = _esc(text)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    # Handle ```code blocks```
    t = re.sub(r'```(\w*)\n?(.*?)```', r'<pre><code>\2</code></pre>', t, flags=re.DOTALL)
    t = t.replace("\n","<br>")
    return t


def build_html(data, ui_recs, acc_recs):
    import datetime
    from scanners.report_template import HTML_TEMPLATE
    from config import TARGET_DIRECTORY

    total_files = len(data["files"])
    total_js = sum(1 for f in data["files"] if f["file_name"].endswith('.js'))
    total_vue = sum(1 for f in data["files"] if f["file_name"].endswith('.vue'))

    flagged_cx = [c for c in data["component_complexity"] if c.get("flags")]
    flagged_ff = [f for f in data["file_flags"]
                  if any(f.get(k) for k in ["api_flags","complexity_flags","risk_flags","pattern_flags","ui_flags"])]

    high   = sum(1 for r in ui_recs+acc_recs if r["severity"]=="HIGH")
    medium = sum(1 for r in ui_recs+acc_recs if r["severity"]=="MEDIUM")
    low    = sum(1 for r in ui_recs+acc_recs if r["severity"]=="LOW")

    score = max(0, int(100 - high*3 - medium*1 - low*0.5 - len(flagged_cx)*2))
    risk, rc = ("LOW","#38bdf8") if score>=80 else ("MEDIUM","#f59e0b") if score>=60 else ("HIGH","#ff5c5c")

    comp_map = {}
    for comp in data["components"]:
        for fi in data["files"]:
            if fi["id"] == comp["file_id"]:
                comp_map[comp["id"]] = fi["file_name"]; break

    file_map = {f["id"]: f["file_name"] for f in data["files"]}
    path_map = {f["id"]: f["file_path"] for f in data["files"]}

    def get_badge(sev):
        if sev == "HIGH": return '<span class="badge b-high">High</span>'
        if sev == "MEDIUM": return '<span class="badge b-medium">Medium</span>'
        if sev == "LOW": return '<span class="badge b-low">Low</span>'
        return f'<span class="badge b-info">{sev}</span>'

    # UI Rows
    ui_rows = ""
    for i, r in enumerate(ui_recs, 1):
        ui_rows += f'''<tr><td>{i}</td><td class="file-cell">{_esc(r["file_name"])}</td><td class="rule-cell">{_esc(r["rule"])}</td><td class="finding-cell">{_esc(r["finding"])}</td><td>{get_badge(r["severity"])}</td><td class="rec-cell">{_rec_html(r["recommendation"])}</td></tr>\n'''
    if not ui_recs: ui_rows = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--pass)">&#10003; No issues found</td></tr>'

    # A11Y Rows
    a11y_rows = ""
    for i, r in enumerate(acc_recs, 1):
        a11y_rows += f'''<tr><td>{i}</td><td class="file-cell">{_esc(r["file_name"])}</td><td class="rule-cell">{_esc(r["rule"])}</td><td class="finding-cell">{_esc(r["finding"])}</td><td>{get_badge(r["severity"])}</td><td class="rec-cell">{_rec_html(r["recommendation"])}</td></tr>\n'''
    if not acc_recs: a11y_rows = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--pass)">&#10003; No issues found</td></tr>'

    # CX Rows
    cx_rows = ""
    for c in flagged_cx:
        comp_name = _esc(comp_map.get(c['component_id'],'—'))
        flags = c.get('flags','')
        flag_chips = "".join(f'<span class="flag-chip {"sev" if "LARGE" in f or "COMPLEX" in f else ""}">{f.strip()}</span>' for f in flags.split(',') if f.strip())
        val = min(100, c.get('methods',0)*2 + c.get('watchers',0)*3)
        c_color = "var(--high)" if val > 30 else "var(--medium)"
        cx_rows += f'''<tr><td class="file-cell">{comp_name}</td><td>{c.get("totallines",0)}</td><td>{c.get("methods",0)}</td><td>{c.get("watchers",0)}</td><td>{c.get("template_lines",0)}</td><td><div class="flag-chips">{flag_chips}</div></td><td><div class="score-bar-wrap"><div class="score-bar-bg"><div class="score-bar-fill" style="width:{val}%;background:{c_color}"></div></div><span class="score-num" style="color:{c_color}">{val}</span></div></td></tr>\n'''
    if not flagged_cx: cx_rows = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--pass)">&#10003; No issues found</td></tr>'

    # FF Rows
    ff_rows = ""
    for ff in flagged_ff:
        fname = _esc(file_map.get(ff['file_id'],'—'))
        fpath = _esc(path_map.get(ff['file_id'],''))
        if len(fpath) > 30: fpath = '...'+fpath[-30:]
        f_list = [ff.get(k,'') for k in ['api_flags','complexity_flags','risk_flags','pattern_flags','ui_flags']]
        flags = ", ".join(filter(None, f_list))
        flag_chips = "".join(f'<span class="flag-chip {"sev" if "HIGH" in f or "CRITICAL" in f else ""}">{f.strip()}</span>' for f in flags.split(',') if f.strip())
        ff_rows += f'''<tr><td class="file-cell">{fname}</td><td style="color:var(--muted);font-size:11px">{fpath}</td><td>{ff.get("api_count",0)}</td><td>{ff.get("loc",0)}</td><td><div class="flag-chips">{flag_chips}</div></td></tr>\n'''
    if not flagged_ff: ff_rows = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--pass)">&#10003; No issues found</td></tr>'

    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    stroke_offset = 232.48 - (232.48 * score / 100)

    html = HTML_TEMPLATE.format(
        target_dir=_esc(TARGET_DIRECTORY),
        total_components=total_vue,
        total_js_files=total_js,
        score=score,
        risk_color=rc,
        risk_level=risk,
        stroke_offset=stroke_offset,
        date=date_str,
        high_issues=high,
        medium_issues=medium,
        low_issues=low,
        ui_issues=len(ui_recs),
        a11y_issues=len(acc_recs),
        complex_files=len(flagged_cx),
        ui_rows=ui_rows,
        a11y_rows=a11y_rows,
        cx_rows=cx_rows,
        ff_rows=ff_rows
    )

    return html


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────
def generate_rag_audit_report():
    print("   Loading scan data from database...")
    data = load_all_scan_data()

    ui  = data["ui_consistency"]
    acc = data["accessibility"]
    print(f"   Found {len(ui)} UI consistency issues, {len(acc)} accessibility issues")

    print("   Generating AI recommendations for UI Consistency issues...")
    ui_recs = generate_recommendations(ui, "UI Consistency")

    print("   Generating AI recommendations for Accessibility issues...")
    acc_recs = generate_recommendations(acc, "Accessibility")

    print("   Building HTML report...")
    html = build_html(data, ui_recs, acc_recs)

    os.makedirs("reports", exist_ok=True)
    out = os.path.join("reports", "ai_audit_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"   ✅ Report saved: {os.path.abspath(out)}")


if __name__ == "__main__":
    generate_rag_audit_report()
