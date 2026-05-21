"""
app.py — Flask Web Server for the AI Code Scanner Dashboard.

Provides a REST API + Server-Sent Events for the Vue.js frontend.
Run with:  python app.py
Open:      http://localhost:5000
"""

import os
import sys
import json
import time
import uuid
import threading
import traceback
import webbrowser
import requests
from datetime import datetime, timedelta
from functools import lru_cache

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template, Response, send_file, stream_with_context
from jinja2 import TemplateNotFound

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROJECT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "ShivaniD")
CURRENT_PROJECT_DIR = DEFAULT_PROJECT_DIR


def render_template_or_file(template_name, *fallback_parts):
    """Render a normal template, or serve a generated standalone HTML file."""
    try:
        return render_template(template_name)
    except TemplateNotFound:
        if not fallback_parts:
            raise

        fallback_path = os.path.join(BASE_DIR, *fallback_parts)
        if os.path.exists(fallback_path):
            return send_file(fallback_path)

        raise


def get_active_project_dir():
    """Return the currently selected/scanned project directory."""
    global CURRENT_PROJECT_DIR
    if CURRENT_PROJECT_DIR and os.path.isdir(CURRENT_PROJECT_DIR):
        return CURRENT_PROJECT_DIR
    try:
        from database_ops import get_db
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT target_directory
            FROM scans
            WHERE target_directory IS NOT NULL AND target_directory != ''
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and row.get("target_directory") and os.path.isdir(row["target_directory"]):
            CURRENT_PROJECT_DIR = row["target_directory"]
            return CURRENT_PROJECT_DIR
    except Exception:
        pass
    return DEFAULT_PROJECT_DIR if os.path.isdir(DEFAULT_PROJECT_DIR) else BASE_DIR

# ── Rate Limiting & Quota Protection ──
class RateLimiter:
    """Prevent API quota exhaustion with intelligent throttling"""
    def __init__(self):
        self.last_call_time = 0
        self.call_count = 0
        self.reset_time = time.time()
        self.min_delay = 2.0  # Minimum 2 seconds between API calls
        self.hourly_limit = 50  # Max 50 calls per hour

    def wait_if_needed(self):
        """Throttle API calls to prevent quota exhaustion"""
        now = time.time()

        # Reset hourly counter
        if now - self.reset_time > 3600:
            self.call_count = 0
            self.reset_time = now

        # Check hourly limit
        if self.call_count >= self.hourly_limit:
            wait_time = 3600 - (now - self.reset_time)
            raise Exception(f"API quota limit ({self.hourly_limit}/hour) exceeded. Wait {int(wait_time)}s")

        # Enforce minimum delay between calls
        elapsed = now - self.last_call_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)

        self.last_call_time = time.time()
        self.call_count += 1

    def get_status(self):
        return {
            "calls_this_hour": self.call_count,
            "limit": self.hourly_limit,
            "remaining": max(0, self.hourly_limit - self.call_count)
        }

api_limiter = RateLimiter()

# ── Only one scan at a time ──
scan_lock = threading.Lock()

# ── Clear stuck scans on startup ──
def _clear_stuck_scans_on_startup():
    """Clear any scans stuck in RUNNING state from previous sessions"""
    try:
        from database_ops import clear_stuck_scans
        affected = clear_stuck_scans()
        if affected > 0:
            print(f"[STARTUP] Cleared {affected} stuck scan(s) from previous session")
    except Exception as e:
        print(f"[STARTUP] Error clearing stuck scans: {e}")

_clear_stuck_scans_on_startup()

# ──────────────────────────────────────────────────────────────────
# SINGLE PROJECT PROMPT — used by every AI feature in this app
# (chat, fix generation, ollama, streaming). Keep one source of truth.
# ──────────────────────────────────────────────────────────────────
PROJECT_PROMPT = (
    "You are PrismAI, the AI engine behind PrismAI Code Analyzer — a tool that "
    "audits codebases, surfaces bugs, security flaws, and anti-patterns, and "
    "helps developers fix them inline. Your job is to review code, explain "
    "issues clearly, and produce precise, minimal, actionable fixes. "
    "Be concise. Use markdown with fenced code blocks tagged by language. "
    "When asked to fix code, return ONLY the corrected code section — no line "
    "numbers, no fence markers, no commentary — unless the user is asking for "
    "an explanation."
)


# ──────────────────────────────────────────────────────────────────
# WEB PAGES
# ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/audit-report")
def audit_report():
    return render_template_or_file("audit_report.html", "reports", "audit_report.html")


@app.route("/issues")
def issues_page():
    return render_template("issues.html")


@app.route("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")


@app.route("/architecture")
def architecture():
    return render_template("architecture.html")


@app.route("/dependency-graph")
def dependency_graph():
    """Interactive dependency visualization with dark/light theme"""
    return render_template("dependency_graph.html")


# ──────────────────────────────────────────────────────────────────
# API: DEPENDENCY GRAPH DATA
# ──────────────────────────────────────────────────────────────────

@app.route("/api/dependencies")
def get_dependencies():
    """Return dependency graph as JSON (nodes + edges)"""
    from collections import defaultdict

    deps = defaultdict(set)
    file_types = {'.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.go', '.java'}
    ignore_dirs = {'__pycache__', '.git', 'node_modules', '.venv', 'venv', '.env', '.pytest_cache', '.vscode', 'dist', 'build'}
    scanned_files = []
    requested_root = request.args.get("root", "").strip()
    scan_root = requested_root or get_active_project_dir()
    if not os.path.isdir(scan_root):
        scan_root = BASE_DIR

    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if any(file.endswith(ext) for ext in file_types):
                file_path = os.path.join(root, file)
                scanned_files.append(file_path)

    rel_by_abs = {
        os.path.normpath(path): os.path.relpath(path, scan_root).replace('\\', '/')
        for path in scanned_files
    }

    for file_path in scanned_files:
        rel_path = rel_by_abs[os.path.normpath(file_path)]
        deps[rel_path]
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            imports = _parse_imports(content)
            for imp in imports:
                resolved = _resolve_import(imp, file_path, scanned_files)
                if resolved:
                    target = rel_by_abs.get(os.path.normpath(resolved))
                    if target and target != rel_path:
                        deps[rel_path].add(target)
        except Exception:
            pass

    # Build nodes and edges
    nodes = []
    edges = []
    all_files = set(deps.keys())
    for file_deps in deps.values():
        all_files.update(file_deps)

    for file in all_files:
        label = file.split('/')[-1]
        nodes.append({'data': {'id': file, 'label': label}})

    for source, targets in deps.items():
        for target in targets:
            edges.append({'data': {'source': source, 'target': target}})

    return jsonify({
        'project_root': scan_root,
        'project_name': os.path.basename(os.path.normpath(scan_root)),
        'nodes': nodes,
        'edges': edges
    })


# ──────────────────────────────────────────────────────────────────
# API: PROJECT ARCHITECTURE / DEPENDENCY GRAPH
# ──────────────────────────────────────────────────────────────────
import re as _re

_IMPORT_PATTERNS = [
    # JS / TS / Vue
    _re.compile(r"""(?:import|from)\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""", _re.MULTILINE),
    _re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""", _re.MULTILINE),
    # Python
    _re.compile(r"""^\s*from\s+([\w.]+)\s+import""", _re.MULTILINE),
    _re.compile(r"""^\s*import\s+([\w.]+)""", _re.MULTILINE),
]


def _parse_imports(content: str):
    out = set()
    if not content:
        return out
    for pat in _IMPORT_PATTERNS:
        for m in pat.finditer(content):
            out.add(m.group(1).strip())
    return out


def _resolve_import(spec: str, src_path: str, all_paths):
    """Resolve an import spec to one of the known scanned file paths. Returns None if external."""
    if not spec:
        return None
    # Skip obvious externals: bare module name with no relative prefix and no slash
    is_relative = spec.startswith(".") or spec.startswith("/") or "\\" in spec or "/" in spec
    src_dir = os.path.dirname(src_path)

    # Build candidate paths
    candidates = []
    if is_relative and (spec.startswith(".") or spec.startswith("/")):
        base = os.path.normpath(os.path.join(src_dir, spec))
        candidates.append(base)
        for ext in (".vue", ".js", ".ts", ".jsx", ".tsx", ".py", ".css"):
            candidates.append(base + ext)
        for idx in ("index.js", "index.ts", "index.vue"):
            candidates.append(os.path.join(base, idx))
    else:
        # Try matching by basename (for Python "from package.module" style)
        last = spec.split(".")[-1]
        for p in all_paths:
            name = os.path.splitext(os.path.basename(p))[0]
            if name == last or name == spec:
                return p
        return None

    # Match a candidate against the scanned file set
    norm_all = {os.path.normpath(p).lower(): p for p in all_paths}
    for c in candidates:
        key = os.path.normpath(c).lower()
        if key in norm_all:
            return norm_all[key]
    return None


@app.route("/api/architecture")
def api_architecture():
    """Return the project dependency graph: nodes (files) + edges (imports)."""
    from database_ops import get_file_tree
    try:
        files = get_file_tree()
    except Exception as e:
        return jsonify({"error": str(e), "nodes": [], "edges": []}), 500

    all_paths = [f["file_path"] for f in files if f.get("file_path")]
    nodes = []
    edges = []
    seen_edges = set()

    for f in files:
        fp = f.get("file_path")
        if not fp:
            continue
        bug_count = int(f.get("bug_count") or 0)
        crit = int(f.get("critical_count") or 0)
        high = int(f.get("high_count") or 0)
        med  = int(f.get("medium_count") or 0)
        low  = int(f.get("low_count") or 0)
        top_sev = (
            "CRITICAL" if crit else
            "HIGH" if high else
            "MEDIUM" if med else
            "LOW" if low else None
        )
        nodes.append({
            "id": fp,
            "label": f.get("file_name") or os.path.basename(fp),
            "file_path": fp,
            "extension": f.get("extension") or os.path.splitext(fp)[1].lstrip("."),
            "bug_count": bug_count,
            "top_severity": top_sev,
        })

        # Parse file content for imports
        try:
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            else:
                continue
        except Exception:
            continue

        for spec in _parse_imports(content):
            target = _resolve_import(spec, fp, all_paths)
            if target and target != fp:
                key = (fp, target)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"source": fp, "target": target})

    return jsonify({"nodes": nodes, "edges": edges})


def _read_report_file(filename, fallback):
    path = os.path.join(BASE_DIR, "reports", filename)
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Could not read reports/{filename}: {exc}")
        return fallback


def _normalize_report_issue(item, source):
    return {
        "id": f"{source}-{item.get('id', uuid.uuid4().hex[:8])}",
        "source": source,
        "file_path": item.get("file_path") or "Unknown",
        "rule_name": item.get("rule_name") or item.get("title") or "Issue",
        "status": item.get("status") or "OPEN",
        "severity": (item.get("severity") or "MEDIUM").upper(),
        "line_number": str(item.get("line_number") or item.get("line") or "0-0"),
        "actual_result": item.get("actual_result") or item.get("description") or "",
        "recommendation": item.get("recommendation") or item.get("fix_suggestion") or "",
        "created_at": item.get("created_at") or "",
    }


@app.route("/api/audit/issues")
def audit_issues():
    """Return all report issues shown by the audit page."""
    accessibility = [
        _normalize_report_issue(item, "accessibility")
        for item in _read_report_file("accessibility_report.json", [])
        if isinstance(item, dict)
    ]
    ui_consistency = [
        _normalize_report_issue(item, "ui_consistency")
        for item in _read_report_file("ui_consistency_report.json", [])
        if isinstance(item, dict)
    ]

    bugs = []
    try:
        from database_ops import get_db
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, file_path, file_name, title, severity, line_number,
                   description, fix_suggestion, status, bug_category, confidence
            FROM bug_detections
            WHERE (bug_category IS NULL OR bug_category != 'ai_configuration')
            ORDER BY FIELD(severity,'CRITICAL','HIGH','MEDIUM','LOW'),
                     file_name, line_number
        """)
        for row in cursor.fetchall() or []:
            bugs.append(_normalize_report_issue({
                "id": row.get("id"),
                "file_path": row.get("file_path"),
                "rule_name": row.get("title") or row.get("bug_category"),
                "status": row.get("status"),
                "severity": row.get("severity"),
                "line_number": row.get("line_number"),
                "actual_result": row.get("description"),
                "recommendation": row.get("fix_suggestion"),
            }, "code"))
        cursor.close()
        conn.close()
    except Exception as exc:
        print(f"Could not read DB bug issues: {exc}")

    issues = accessibility + ui_consistency + bugs
    summary = {
        "total": len(issues),
        "accessibility": len(accessibility),
        "ui_consistency": len(ui_consistency),
        "code": len(bugs),
        "critical": sum(1 for i in issues if i["severity"] == "CRITICAL"),
        "high": sum(1 for i in issues if i["severity"] == "HIGH"),
        "medium": sum(1 for i in issues if i["severity"] == "MEDIUM"),
        "low": sum(1 for i in issues if i["severity"] == "LOW"),
        "failed": sum(1 for i in issues if str(i["status"]).upper() in ("FAIL", "OPEN")),
    }
    return jsonify({"summary": summary, "issues": issues})


# ──────────────────────────────────────────────────────────────────
# API: BUG DETECTION DATA (Gemini Bug Detector)
# ──────────────────────────────────────────────────────────────────

@app.route("/api/bugs")
def get_bugs():
    """Return all detected bugs from the latest scan."""
    from scanners.ollama_bug_detector import get_all_bugs
    bugs = get_all_bugs()
    return jsonify(bugs)


@app.route("/api/bugs/summary")
def get_bugs_summary():
    """Return aggregated bug stats."""
    from scanners.ollama_bug_detector import get_bug_summary
    summary = get_bug_summary()
    return jsonify(summary)


@app.route("/api/bugs/file")
def get_bugs_by_file():
    """Return bugs for a specific file path (query param: ?path=...)."""
    file_path = request.args.get("path", "")
    if not file_path:
        return jsonify([])

    from database_ops import get_db
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM bug_detections
        WHERE file_path = %s
        ORDER BY FIELD(severity, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'), line_number
    """, (file_path,))
    bugs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(bugs)


# ──────────────────────────────────────────────────────────────────
# API: START A NEW SCAN
# ──────────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def start_scan():
    global CURRENT_PROJECT_DIR
    if not scan_lock.acquire(blocking=False):
        return jsonify({"error": "A scan is already running. Please wait for it to finish."}), 409

    try:
        data = request.json or {}
        folder_path = data.get("folder_path", "").strip()
        scan_name = data.get("scan_name", "").strip() or os.path.basename(folder_path)

        # Validate directory
        if not folder_path:
            scan_lock.release()
            return jsonify({"error": "Folder path is required."}), 400

        if not os.path.isdir(folder_path):
            scan_lock.release()
            return jsonify({"error": f"Directory not found: {folder_path}"}), 400

        # Create scan record in DB
        from database_ops import create_scan
        scan_id = create_scan(scan_name, folder_path)

        # Override target directory at runtime
        import config
        config.TARGET_DIRECTORY = folder_path
        CURRENT_PROJECT_DIR = folder_path

        # Launch pipeline in background thread
        thread = threading.Thread(
            target=_run_pipeline_thread,
            args=(folder_path, scan_id),
            daemon=True
        )
        thread.start()

        return jsonify({"scan_id": scan_id, "status": "started"})

    except Exception as e:
        scan_lock.release()
        return jsonify({"error": str(e)}), 500


def _run_pipeline_thread(folder_path, scan_id):
    """Background thread: Stage 1 = file discovery, Stage 2 = Gemini bug detection."""
    from database_ops import update_scan_progress, complete_scan, fail_scan, get_scan_summary
    import signal

    start_time = time.time()
    SCAN_TIMEOUT = 1800  # 30 minutes timeout

    def timeout_handler(signum, frame):
        raise TimeoutError("Scan exceeded 30 minute timeout")

    def prog(stage, pct, msg=""):
        elapsed = int(time.time() - start_time)
        print(f"  [{pct:3d}%] {stage}" + (f" — {msg}" if msg else "") + f" ({elapsed}s)")
        try:
            update_scan_progress(scan_id, stage, pct, msg)
        except Exception as ex:
            print(f"  [WARNING] Could not update progress: {ex}")

    try:
        # Set timeout
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(SCAN_TIMEOUT)
        except Exception:
            pass  # Timeout not supported on all platforms

        # ── Stage 1: File discovery via PrismAI pipeline ──
        prog("FILE_DISCOVERY", 5, "Scanning directory structure")
        try:
            from main import run_scan as _discover
            import scanners.ollama_bug_detector as _obd

            _orig = _obd.run_bug_detection
            _obd.run_bug_detection = lambda *a, **kw: 0   # no-op during stage 1

            _discover(folder_path, scan_id,
                      lambda sid, stage, pct, msg="": prog(stage, pct, msg))

            _obd.run_bug_detection = _orig               # restore
        except Exception as e:
            print(f"[WARN] File discovery error (continuing): {e}")
            prog("FILE_DISCOVERY", 40, f"Partial: {str(e)[:80]}")

        prog("FILE_DISCOVERY", 40, "File discovery complete")

        # ── Stage 2: Ollama AI bug detection (always runs) ──
        prog("AI_ANALYSIS", 42, "Starting Ollama AI bug detection")
        total_bugs = 0
        try:
            from database_ops import get_db

            # Clear previous bugs for a clean re-scan
            try:
                _conn = get_db()
                _cur = _conn.cursor()
                _cur.execute("DELETE FROM bug_detections")
                _conn.commit()
                _cur.close()
                _conn.close()
                print("  [Bug Detector] Cleared previous bug_detections")
            except Exception as _de:
                print(f"  [Bug Detector] Could not clear old bugs: {_de}")

            from scanners.ollama_bug_detector import run_bug_detection

            total_bugs = run_bug_detection(
                folder_path,
                lambda pct, msg: prog("AI_ANALYSIS", 42 + int(pct * 0.55), msg),
            )
            prog("AI_ANALYSIS", 98, f"Complete — {total_bugs} issues found")
        except TimeoutError as te:
            print(f"[ERROR] Ollama bug detection timeout: {te}")
            prog("AI_ANALYSIS", 98, "Timeout: Analysis took too long")
            fail_scan(scan_id, "Scan timeout: Analysis exceeded 30 minutes")
            return
        except Exception as e:
            print(f"[ERROR] Ollama bug detection failed: {e}")
            traceback.print_exc()
            prog("AI_ANALYSIS", 98, f"Error: {str(e)[:100]}")

        # ── Finalise ──
        summary = get_scan_summary()
        complete_scan(
            scan_id,
            total_issues=summary.get("total", total_bugs),
            high=summary.get("high", 0),
            medium=summary.get("medium", 0),
            low=summary.get("low", 0),
        )
        prog("COMPLETED", 100, f"Done — {summary.get('total', total_bugs)} issues")
        print(f"\n✅ Scan {scan_id} completed: {summary}")

    except TimeoutError as te:
        print(f"\n⏱️ Scan {scan_id} timeout: {te}")
        try:
            fail_scan(scan_id, "Scan timeout: Exceeded 30 minute limit")
        except Exception:
            pass
    except Exception as e:
        print(f"\n❌ Scan {scan_id} failed: {e}")
        traceback.print_exc()
        try:
            fail_scan(scan_id, str(e))
        except Exception as fail_ex:
            print(f"  [ERROR] Could not mark scan as failed: {fail_ex}")

    finally:
        # Cancel alarm
        try:
            signal.alarm(0)
        except Exception:
            pass

        scan_lock.release()
        elapsed = int(time.time() - start_time)
        print(f"[SCAN] Scan {scan_id} pipeline completed in {elapsed}s")


# ──────────────────────────────────────────────────────────────────
# API: SCAN STATUS (polling)
# ──────────────────────────────────────────────────────────────────

@app.route("/api/scan/<int:scan_id>/status")
def scan_status(scan_id):
    from database_ops import get_scan_status
    status = get_scan_status(scan_id)
    return jsonify(status)


# ──────────────────────────────────────────────────────────────────
# API: SCAN STATUS STREAM (Server-Sent Events for live progress)
# ──────────────────────────────────────────────────────────────────

@app.route("/api/scan/<int:scan_id>/stream")
def scan_stream(scan_id):
    def event_stream():
        from database_ops import get_scan_status
        while True:
            status = get_scan_status(scan_id)
            yield f"data: {json.dumps(status, default=str)}\n\n"
            if status.get("status") in ("COMPLETED", "FAILED"):
                break
            time.sleep(1)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


# ──────────────────────────────────────────────────────────────────
# API: LIST ALL SCANS
# ──────────────────────────────────────────────────────────────────

@app.route("/api/scans")
def list_scans():
    from database_ops import get_all_scans
    scans = get_all_scans()
    return jsonify(scans)


# ──────────────────────────────────────────────────────────────────
# API: SERVE A SCAN'S HTML REPORT
# ──────────────────────────────────────────────────────────────────

@app.route("/api/scan/<int:scan_id>/report")
def serve_report(scan_id):
    # Try scan-specific report first, fall back to generic
    specific = os.path.join(BASE_DIR, "reports", f"scan_{scan_id}_report.html")
    generic = os.path.join(BASE_DIR, "code_report.html")

    path = specific if os.path.exists(specific) else generic
    if os.path.exists(path):
        return send_file(path)
    return jsonify({"error": "Report not found"}), 404


# ──────────────────────────────────────────────────────────────────
# API: DELETE A SCAN
# ──────────────────────────────────────────────────────────────────

@app.route("/api/scan/<int:scan_id>", methods=["DELETE"])
def delete_scan_route(scan_id):
    from database_ops import delete_scan
    delete_scan(scan_id)

    # Remove report file if it exists
    report_path = os.path.join(BASE_DIR, "reports", f"scan_{scan_id}_report.html")
    if os.path.exists(report_path):
        try:
            os.remove(report_path)
        except Exception:
            pass

    return jsonify({"status": "deleted"})


# ──────────────────────────────────────────────────────────────────
# API: VALIDATE A FOLDER PATH
# ──────────────────────────────────────────────────────────────────

@app.route("/api/validate-path", methods=["POST"])
def validate_path():
    data = request.json or {}
    path = data.get("path", "").strip()

    if not path:
        return jsonify({"valid": False, "file_count": 0})

    exists = os.path.isdir(path)
    file_count = 0

    if exists:
        skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__", ".idea", ".vscode"}
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            file_count += len(files)
            if file_count > 50000:
                break

    return jsonify({"valid": exists, "file_count": file_count})


# ──────────────────────────────────────────────────────────────────
# WEB PAGE: CODE VIEWER
# ──────────────────────────────────────────────────────────────────

@app.route("/code-viewer")
def code_viewer():
    return render_template_or_file("code_viewer.html", "reports", "code_viewer_report.html")


# ──────────────────────────────────────────────────────────────────
# API: CODE VIEWER ENDPOINTS
# ──────────────────────────────────────────────────────────────────

@app.route("/api/file-tree")
def file_tree():
    """Return all scanned files with bug counts for the file tree."""
    files = _get_code_viewer_files()
    return jsonify(files)


@app.route("/api/quota-status")
def quota_status():
    """Check remaining API quota"""
    return jsonify(api_limiter.get_status())


@app.route("/api/dashboard-data")
def dashboard_data():
    """Return the complete dashboard model used by the CodeLens frontend."""
    files = _get_code_viewer_files()
    summary = _build_dashboard_summary(files)
    project = _build_project_meta(files)
    return jsonify({
        "project": project,
        "summary": summary,
        "files": files,
        "worst_files": sorted(files, key=lambda f: (f.get("bug_count") or 0), reverse=True)[:8],
        "recommendations": _build_recommendations(summary),
    })


@app.route("/api/current-project")
def current_project():
    project_dir = get_active_project_dir()
    return jsonify({
        "project_root": project_dir,
        "project_name": os.path.basename(os.path.normpath(project_dir)) or "Project",
    })


# ──────────────────────────────────────────────────────────────────
# API: GET FILE CONTENT
# ──────────────────────────────────────────────────────────────────
@app.route("/api/file/content")
def file_content():
    """Return source code content for a given file path."""
    from urllib.parse import unquote

    file_path = request.args.get("path", "").strip()

    # Decode URL-encoded path
    if file_path:
        file_path = unquote(file_path)

    if not file_path:
        return jsonify({"error": "File path is required", "content": "", "lines": 0}), 400

    try:
        # Normalize path for current OS
        file_path = os.path.normpath(file_path)

        if os.path.isfile(file_path):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        else:
            content = _load_analyzer_source(file_path)
            if content is None:
                return jsonify({"error": f"File not found: {file_path}", "content": "", "lines": 0}), 404

        return jsonify({
            "content": content,
            "lines": content.count("\n") + 1,
            "extension": os.path.splitext(file_path)[1].lstrip(".")
        })
    except FileNotFoundError:
        return jsonify({"error": f"File not found: {file_path}", "content": "", "lines": 0}), 404
    except PermissionError:
        return jsonify({"error": f"Permission denied: {file_path}", "content": "", "lines": 0}), 403
    except Exception as e:
        print(f"[ERROR] file_content: {str(e)}")
        return jsonify({"error": str(e), "content": "", "lines": 0}), 500


# ──────────────────────────────────────────────────────────────────
# API: GET FILE ANNOTATIONS (DB + fallback)
# ──────────────────────────────────────────────────────────────────
@app.route("/api/file/annotations")
def file_annotations():
    """Return bug annotations for a specific file — DB only, no stale JSON fallback."""
    from urllib.parse import unquote

    file_path = request.args.get("path", "").strip()

    # Decode URL-encoded path
    if file_path:
        file_path = unquote(file_path)

    if not file_path:
        return jsonify([])

    # Normalize path for current OS
    file_path = os.path.normpath(file_path)

    annotations = []
    try:
        from database_ops import get_file_annotations
        annotations = get_file_annotations(file_path)
    except Exception as exc:
        print(f"[ERROR] Could not read DB annotations: {exc}")

    # If DB returned nothing, also try alternate path separator
    if not annotations:
        try:
            from database_ops import get_db
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            # Try both path separators
            alt_path = file_path.replace("/", "\\") if "\\" not in file_path else file_path.replace("\\", "/")

            cursor.execute("""
                SELECT id, file_path, file_name, title, severity, line_number,
                       description, fix_suggestion, status, bug_category, confidence, fixed_code
                FROM bug_detections
                WHERE file_path = %s OR file_path = %s
                ORDER BY CAST(line_number AS UNSIGNED) ASC, severity DESC
            """, (file_path, alt_path))
            annotations = cursor.fetchall() or []
            cursor.close()
            conn.close()
        except Exception as exc2:
            print(f"[ERROR] Alt-path annotations query failed: {exc2}")

    return jsonify(annotations)


# ──────────────────────────────────────────────────────────────────
# CODE VIEWER UTILITIES & FALLBACK LOADER
# ──────────────────────────────────────────────────────────────────
def _get_code_viewer_files():
    """Return scanned files from the DB only — never fall back to old code-analyzer JSON reports."""
    files = []
    try:
        from database_ops import get_file_tree
        files = get_file_tree()
    except Exception as exc:
        print(f"Could not read DB file tree: {exc}")
    return files


def _build_project_meta(files):
    paths = [f.get("file_path", "") for f in files if f.get("file_path")]
    try:
        common = os.path.commonpath(paths) if paths else ""
    except ValueError:
        common = os.path.dirname(paths[0]) if paths else ""
    exts = sorted({(f.get("extension") or "").lower() for f in files if f.get("extension")})
    stack = []
    if "vue" in exts:
        stack.append("Vue")
    if "js" in exts:
        stack.append("JavaScript")
    if "ts" in exts:
        stack.append("TypeScript")
    if "py" in exts:
        stack.append("Python")
    return {
        "name": os.path.basename(common) if common else "Project",
        "root": common,
        "stack": " - ".join(stack) if stack else "Codebase",
        "file_count": len(files),
        "extensions": exts,
    }


def _build_dashboard_summary(files):
    summary = {
        "total": 0,
        "open": 0,
        "fixed": 0,
        "ignored": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "health_score": 100,
    }
    for f in files:
        summary["total"] += int(f.get("bug_count") or 0)
        summary["open"] += int(f.get("open_count") or 0)
        summary["fixed"] += int(f.get("fixed_count") or 0)
        summary["ignored"] += int(f.get("ignored_count") or 0)
        summary["critical"] += int(f.get("critical_count") or 0)
        summary["high"] += int(f.get("high_count") or 0)
        summary["medium"] += int(f.get("medium_count") or 0)
        summary["low"] += int(f.get("low_count") or 0)
    density = summary["total"] / max(len(files), 1)
    summary["health_score"] = max(10, min(95, 100 - round(density * 12)))
    return summary


def _build_recommendations(summary):
    recs = []
    if summary["high"] or summary["critical"]:
        recs.append("Open the highest severity files first and fix highlighted lines before lower-risk cleanup.")
    if summary["medium"]:
        recs.append("Review medium severity findings after critical fixes and group similar fixes by component.")
    if summary["open"]:
        recs.append("Re-run the scan after applying fixes so the backend report and tree counts refresh together.")
    if not recs:
        recs.append("No open issues were found in the current report data.")
    return recs


def _json_report_path(filename):
    return os.path.join(BASE_DIR, "code-analyzer", "backend", "json_reports", filename)


def _read_json_report(filename, fallback):
    path = _json_report_path(filename)
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Could not read {filename}: {exc}")
        return fallback


def _load_analyzer_file_tree():
    """Build file records from PrismAI JSON reports when DB rows are unavailable."""
    report = _read_json_report("files.json", [])
    ai_report = _read_json_report("ai_report.json", {})
    ai_by_path = {item.get("file_path"): item for item in ai_report.get("files", [])}
    rows = []
    for idx, item in enumerate(report if isinstance(report, list) else []):
        path = item.get("path") or item.get("file_path")
        if not path:
            continue
        ext = (item.get("ext") or os.path.splitext(path)[1].lstrip(".")).lower()
        ai = ai_by_path.get(path, {})
        flagged = ai.get("status") == "FLAGGED" or bool(ai.get("ai_error"))
        rows.append({
            "file_id": item.get("id") or idx + 1,
            "file_name": os.path.basename(path),
            "file_path": path,
            "extension": ext,
            "folder_path": os.path.dirname(path),
            "bug_count": 1 if flagged else 0,
            "critical_count": 0,
            "high_count": 1 if flagged else 0,
            "medium_count": 0,
            "low_count": 0,
            "open_count": 1 if flagged else 0,
            "fixed_count": 0,
            "ignored_count": 0,
        })
    return rows


def _load_analyzer_source(file_path):
    report = _read_json_report("files.json", [])
    for item in report if isinstance(report, list) else []:
        path = item.get("path") or item.get("file_path")
        if path == file_path:
            return item.get("content") or item.get("content_truncated") or ""
    return None


def _load_analyzer_annotations(file_path):
    ai_report = _read_json_report("ai_report.json", {})
    annotations = []
    for idx, item in enumerate(ai_report.get("files", []) if isinstance(ai_report, dict) else []):
        if item.get("file_path") != file_path:
            continue
        for defect in item.get("logic_defects", []) + item.get("ui_accessibility_defects", []):
            annotations.append({
                "id": f"json-{idx}-{len(annotations)}",
                "bug_category": defect.get("category", "ai_review"),
                "title": defect.get("title", "AI finding"),
                "severity": defect.get("severity", "MEDIUM"),
                "line_number": int(defect.get("line_number") or 1),
                "description": defect.get("description", ""),
                "fix_suggestion": defect.get("fix_suggestion", ""),
                "confidence": defect.get("confidence", 0),
                "status": "OPEN",
                "fixed_code": None,
            })
        if item.get("ai_error"):
            annotations.append({
                "id": f"json-ai-error-{idx}",
                "bug_category": "ai_configuration",
                "title": "AI analysis did not run for this file",
                "severity": "HIGH",
                "line_number": 1,
                "description": item.get("ai_error"),
                "fix_suggestion": "Set the missing AI configuration, then run the scan again.",
                "confidence": 1,
                "status": "OPEN",
                "fixed_code": None,
            })
    return annotations


# ──────────────────────────────────────────────────────────────────
# API: LIST ALL DETECTED BUGS DIRECT
# ──────────────────────────────────────────────────────────────────
@app.route("/api/all-bugs")
def all_bugs_direct():
    """Return every row in bug_detections — used by the frontend to filter client-side."""
    try:
        project_dir = get_active_project_dir()
        norm_project = project_dir.replace("\\", "/").rstrip("/").lower()
        from database_ops import get_db
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, file_path, file_name, title, severity, line_number,
                   description, fix_suggestion, status, bug_category,
                   confidence, fixed_code
            FROM bug_detections
            WHERE (bug_category IS NULL OR bug_category != 'ai_configuration')
            ORDER BY FIELD(severity,'CRITICAL','HIGH','MEDIUM','LOW'),
                     file_name, line_number
        """)
        bugs = cursor.fetchall() or []
        cursor.close()
        conn.close()
        filtered = [
            b for b in bugs
            if (b.get("file_path") or "").replace("\\", "/").lower().startswith(norm_project)
        ]
        if filtered or bugs:
            return jsonify(filtered or bugs)
    except Exception as e:
        print(f"all-bugs error: {e}")

    project_dir = get_active_project_dir()
    norm_project = project_dir.replace("\\", "/").rstrip("/").lower()
    fallback = []
    for source, filename in (
        ("accessibility", "accessibility_report.json"),
        ("ui_consistency", "ui_consistency_report.json"),
    ):
        for item in _read_report_file(filename, []):
            if not isinstance(item, dict):
                continue
            file_path = item.get("file_path") or ""
            if file_path and file_path != "cross-page":
                norm_path = file_path.replace("\\", "/").lower()
                if norm_project and not norm_path.startswith(norm_project):
                    continue
            fallback.append({
                "id": f"{source}-{item.get('id', uuid.uuid4().hex[:8])}",
                "source": source,
                "file_path": file_path,
                "file_name": os.path.basename(file_path) if file_path and file_path != "cross-page" else "Cross-page",
                "title": item.get("rule_name") or "Issue",
                "severity": (item.get("severity") or "MEDIUM").upper(),
                "line_number": item.get("line_number") or 1,
                "description": item.get("actual_result") or "",
                "fix_suggestion": item.get("recommendation") or "Ask the chatbot for a targeted fix.",
                "status": item.get("status") or "OPEN",
                "bug_category": source,
                "confidence": None,
                "fixed_code": None,
            })
    return jsonify(fallback)


@app.route("/api/bugs/<int:bug_id>/status", methods=["PATCH"])
def update_bug_status_route(bug_id):
    """Update a bug's status (OPEN, FIXED, IGNORED)"""
    data = request.json or {}
    status = data.get("status", "OPEN").upper()

    if status not in ("OPEN", "FIXED", "IGNORED"):
        return jsonify({"error": "Invalid status"}), 400

    try:
        from database_ops import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_detections SET status = %s WHERE id = %s",
            (status, bug_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────
# CHATBOT (Ollama-powered)
# ──────────────────────────────────────────────────────────────────

# In-memory chat storage
chatbot_conversations = {}


@app.route("/api/chatbot/conversations", methods=["GET"])
def chatbot_list_conversations():
    conv_list = []
    for cid, conv in chatbot_conversations.items():
        conv_list.append({
            "id": conv["id"],
            "title": conv["title"],
            "created_at": conv["created_at"],
            "message_count": len(conv["messages"]),
        })
    conv_list.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(conv_list)


@app.route("/api/chatbot/conversations", methods=["POST"])
def chatbot_create_conversation():
    new_id = str(uuid.uuid4())[:8]
    chatbot_conversations[new_id] = {
        "id": new_id,
        "title": "New Chat",
        "created_at": datetime.now().isoformat(),
        "messages": [],
        "history": [],
    }
    return jsonify({"id": new_id, "title": "New Chat"})


@app.route("/api/chatbot/conversations/<conv_id>", methods=["GET"])
def chatbot_get_conversation(conv_id):
    if conv_id not in chatbot_conversations:
        return jsonify({"error": "Conversation not found"}), 404
    conv = chatbot_conversations[conv_id]
    return jsonify({
        "id": conv["id"],
        "title": conv["title"],
        "created_at": conv["created_at"],
        "messages": conv["messages"],
    })


@app.route("/api/chatbot/conversations/<conv_id>", methods=["DELETE"])
def chatbot_delete_conversation(conv_id):
    if conv_id in chatbot_conversations:
        del chatbot_conversations[conv_id]
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────────
# API: REPORT DOWNLOAD (HTML / JSON)
# ──────────────────────────────────────────────────────────────────
@app.route("/api/report/download")
def download_report():
    """Generate a highly polished, offline-ready HTML audit report for the codebase."""
    try:
        from database_ops import get_db
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM bug_detections")
        bugs = cursor.fetchall() or []
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Could not read DB: {e}")
        bugs = []

    files = _get_code_viewer_files()
    stats = _build_dashboard_summary(files)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    file_rows = ""
    for f in files:
        file_rows += f"""<tr>
            <td style="font-family:monospace;font-size:11px;color:#818cf8">{f.get('file_name','')}</td>
            <td>{f.get('bug_count',0)}</td>
            <td>{f.get('open_count',0)}</td>
            <td>{f.get('fixed_count',0)}</td>
            <td>{f.get('ignored_count',0)}</td>
        </tr>"""

    sev_colors = {"CRITICAL": "#ef4444", "HIGH": "#f97316", "MEDIUM": "#eab308", "LOW": "#3b82f6"}
    status_colors = {"OPEN": "#ef4444", "FIXED": "#10b981", "IGNORED": "#64748b"}

    bug_rows = ""
    for b in bugs:
        sc = sev_colors.get(b.get("severity", ""), "#64748b")
        stc = status_colors.get(b.get("status", "OPEN"), "#64748b")
        bug_rows += f"""<tr>
            <td style="font-family:monospace;font-size:11px;color:#818cf8;max-width:180px;word-break:break-all">{b.get('file_name','')}</td>
            <td><span style="background:rgba({','.join(str(int(sc.lstrip('#')[i:i+2],16)) for i in (0,2,4))},.12);color:{sc};padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700">{b.get('severity','')}</span></td>
            <td style="font-weight:600">{b.get('title','')}</td>
            <td style="font-family:monospace">{b.get('line_number','')}</td>
            <td><span style="background:rgba({','.join(str(int(stc.lstrip('#')[i:i+2],16)) for i in (0,2,4))},.12);color:{stc};padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700">{b.get('status','')}</span></td>
            <td>{b.get('description','')}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CodeLens Pro — Bug Audit Report</title>
<style>
body{{background:#0f172a;color:#f1f5f9;font-family:'Inter',system-ui,sans-serif;padding:40px;margin:0}}
h1{{font-size:32px;font-weight:800;background:linear-gradient(to right,#818cf8,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0 0 8px 0}}
.sub{{color:#64748b;font-size:12px;margin-bottom:32px}}
.stats{{display:flex;gap:12px;margin-bottom:32px}}
.stat{{background:rgba(17,24,39,.85);border:1px solid rgba(30,41,59,.6);border-radius:12px;padding:18px 22px;flex:1;text-align:center}}
.stat .v{{font-size:28px;font-weight:800;line-height:1}}
.stat .l{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.6px;margin-top:4px}}
table{{width:100%;border-collapse:collapse;margin-bottom:32px}}
th{{background:rgba(22,26,39,.9);text-align:left;padding:10px 14px;font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid #1e293b}}
td{{padding:10px 14px;border-bottom:1px solid rgba(30,41,59,.4);font-size:12px;vertical-align:top}}
tr:hover td{{background:rgba(255,255,255,.02)}}
.section{{background:rgba(17,24,39,.85);border:1px solid rgba(30,41,59,.6);border-radius:12px;overflow:hidden;margin-bottom:24px}}
.section-hdr{{padding:14px 20px;border-bottom:1px solid rgba(30,41,59,.6);font-size:14px;font-weight:700}}
footer{{text-align:center;padding:24px;color:#64748b;font-size:11px;border-top:1px solid rgba(30,41,59,.6);margin-top:40px}}
</style></head><body>
<h1>CodeLens Pro — Bug Audit Report</h1>
<p class="sub">Generated {now} · Powered by Google Gemini AI</p>
<div class="stats">
<div class="stat"><div class="v" style="color:#818cf8">{stats.get('total',0)}</div><div class="l">Total Bugs</div></div>
<div class="stat"><div class="v" style="color:#ef4444">{stats.get('open_count',0)}</div><div class="l">Open</div></div>
<div class="stat"><div class="v" style="color:#10b981">{stats.get('fixed_count',0)}</div><div class="l">Fixed</div></div>
<div class="stat"><div class="v" style="color:#64748b">{stats.get('ignored_count',0)}</div><div class="l">Ignored</div></div>
<div class="stat"><div class="v" style="color:#dc2626">{stats.get('critical',0)}</div><div class="l">Critical</div></div>
<div class="stat"><div class="v" style="color:#ef4444">{stats.get('high',0)}</div><div class="l">High</div></div>
<div class="stat"><div class="v" style="color:#f59e0b">{stats.get('medium',0)}</div><div class="l">Medium</div></div>
<div class="stat"><div class="v" style="color:#3b82f6">{stats.get('low',0)}</div><div class="l">Low</div></div>
</div>
<div class="section"><div class="section-hdr">File Summary</div>
<table><thead><tr><th>File</th><th>Total</th><th>Open</th><th>Fixed</th><th>Ignored</th></tr></thead>
<tbody>{file_rows}</tbody></table></div>
<div class="section"><div class="section-hdr">All Detected Bugs</div>
<table><thead><tr><th>File</th><th>Severity</th><th>Title</th><th>Line</th><th>Status</th><th>Description</th></tr></thead>
<tbody>{bug_rows}</tbody></table></div>
<footer>CodeLens Pro · AI-Powered Analysis Engine · {now}</footer>
</body></html>"""

    preview = request.args.get("preview", "").lower() == "true"
    headers = {} if preview else {"Content-Disposition": "attachment; filename=codeguard_report.html"}
    return Response(html, mimetype="text/html", headers=headers)


# ──────────────────────────────────────────────────────────────────
# API: LOCAL OLLAMA / GEMMA CHAT
# ──────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────
# API: GEMINI AI CHAT
# ──────────────────────────────────────────────────────────────────
@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """Gemini-powered chatbot endpoint."""
    try:
        from google import genai
        from google.genai import types
        from config import GEMINI_API_KEY
    except Exception as e:
        return jsonify({"error": f"Required dependencies or config missing: {str(e)}"}), 500

    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured in .env file"}), 400

    data = request.json or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    file_context = data.get("file_context", "")
    issue_context = data.get("issue_context")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Build system instruction and content history
    system_parts = [PROJECT_PROMPT]
    if file_context:
        system_parts.append(f"\nFile in view:\n```\n{file_context[:5000]}\n```")
    if issue_context:
        system_parts.append(
            f"\nSelected issue:\n"
            f"- Title: {issue_context.get('title','')}\n"
            f"- Severity: {issue_context.get('severity','')}\n"
            f"- Line: {issue_context.get('line_number','')}\n"
            f"- Description: {issue_context.get('description','')}\n"
            f"- Fix suggestion: {issue_context.get('fix_suggestion','')}"
        )
    system_instruction = "\n".join(system_parts)

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Format history for google-genai
        contents = []
        for h in history[-10:]:
            role = "user" if h.get("role") == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=h.get("content", ""))]))
            
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        return jsonify({"response": response.text or "No response received."})
    except Exception as e:
        print(f"[Gemini Chat Error] {e}")
        return jsonify({"error": f"Gemini API error: {str(e)}"}), 500


@app.route("/api/ollama/chat", methods=["POST"])
def ollama_chat():
    """Proxy to local Ollama (Gemma 3) for offline AI assistance, with a seamless fallback to Gemini."""
    try:
        import requests as _req
    except ImportError:
        return jsonify({"error": "requests library not installed. Run: pip install requests"}), 500

    from config import OLLAMA_URL, OLLAMA_MODEL

    data = request.json or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    file_context = data.get("file_context", "")
    issue_context = data.get("issue_context")
    model = data.get("model", OLLAMA_MODEL)

    if not message:
        return jsonify({"error": "Message is required"}), 400

    system_content = PROJECT_PROMPT
    if file_context:
        system_content += f"\n\nCurrent file content (truncated):\n```\n{file_context[:3500]}\n```"
    if issue_context:
        system_content += (
            f"\n\nSelected issue:\n"
            f"- Title: {issue_context.get('title', '')}\n"
            f"- Severity: {issue_context.get('severity', '')}\n"
            f"- Line: {issue_context.get('line_number', '')}\n"
            f"- Description: {issue_context.get('description', '')}\n"
            f"- Fix Suggestion: {issue_context.get('fix_suggestion', '')}"
        )

    # Format history for Ollama chat API format
    messages = [{"role": "system", "content": system_content}]
    for h in history[-8:]:
        role = h.get("role", "user")
        # Ollama expects user/assistant role names
        if role == "model":
            role = "assistant"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    # Try Ollama first (with a generous timeout to allow local model boot/generation time)
    try:
        resp = _req.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
            },
            timeout=180
        )
        if resp.status_code == 200:
            result = resp.json()
            content = result.get("message", {}).get("content", "No response received.")
            return jsonify({"response": content, "model": model})
    except Exception as e:
        print(f"[Ollama check] Offline or error connecting to Ollama: {e}")

    # Seamless Fallback to Gemini
    from config import GEMINI_API_KEY
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            contents = []
            for h in history[-10:]:
                role = "user" if h.get("role") == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=h.get("content", ""))]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_content,
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )
            return jsonify({"response": response.text or "No response received.", "model": "gemini-2.5-flash-fallback"})
        except Exception as gem_err:
            print(f"[Gemini Fallback Error] {gem_err}")

    return jsonify({
        "error": f"Cannot connect to Ollama at {OLLAMA_URL} and Gemini fallback failed. "
                 f"Make sure Ollama is running ('ollama serve') or configured in .env."
    }), 503


# ──────────────────────────────────────────────────────────────────
# API: GENERATE AI FIX FOR A BUG (Gemma)
# ──────────────────────────────────────────────────────────────────
@app.route("/api/bugs/<int:bug_id>/ai-fix", methods=["POST"])
def generate_ai_fix(bug_id):
    """Generate AI fix for a bug using local Ollama (Gemma 3:12B)."""
    try:
        OLLAMA_URL = "http://localhost:11434"
        OLLAMA_MODEL = "gemma3:12b"

        data = request.json or {}
        file_content = data.get("file_content", "").strip()

        # Validate file content
        if not file_content:
            return jsonify({"error": "No file content. Load the file first."}), 400

        # Get bug info
        bug = None
        try:
            from database_ops import get_db
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM bug_detections WHERE id = %s", (bug_id,))
            bug = cursor.fetchone()
            cursor.close()
            conn.close()
        except:
            pass

        if not bug:
            bug = {
                "title": data.get("title", "Issue"),
                "description": data.get("description", ""),
                "fix_suggestion": data.get("fix_suggestion", ""),
                "severity": data.get("severity", "MEDIUM"),
                "line_number": data.get("line_number", 1),
                "file_path": data.get("file_path", ""),
            }

        line_num = max(1, int(bug.get("line_number") or 1))
        file_path = bug.get("file_path", "")
        ext = os.path.splitext(file_path)[1].lstrip(".") if file_path else ""

        # Extract code around bug
        all_lines = file_content.split("\n")
        bug_idx = line_num - 1

        if bug_idx < 0 or bug_idx >= len(all_lines):
            return jsonify({"error": f"Line {line_num} not in file"}), 400

        # Use a focused replacement window so large methods do not exceed model output limits.
        start = max(0, bug_idx - 30)
        end = min(len(all_lines), bug_idx + 31)

        original_code = "\n".join(all_lines[start:end])
        target_offset = bug_idx - start + 1
        total_lines = end - start

        prompt = f"""You are a code fixer. Fix the bug and return the COMPLETE replacement for the provided code block.

BUG TITLE: {bug.get('title')}
BUG LINE IN FILE: {line_num}
BUG LINE INSIDE BLOCK: {target_offset}
BUG DESCRIPTION: {bug.get('description')}
SUGGESTED FIX: {bug.get('fix_suggestion')}

CODE BLOCK TO REPLACE ({total_lines} lines, no line numbers):
```{ext}
{original_code}
```

REQUIREMENTS:
1. Return the COMPLETE replacement block, not a snippet.
2. Keep unrelated lines exactly the same.
3. Preserve indentation and formatting.
4. Do not include line numbers.
5. Return only code in one fenced code block.
"""

        # Call Ollama for fix generation
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1,
                },
                timeout=120
            )

            if response.status_code != 200:
                err_msg = response.json().get("error", response.text) if response.text else "Unknown error"
                return jsonify({"error": f"Ollama API error: {err_msg}"}), 500

            data = response.json()
            fixed = (data.get("response", "")).strip("\r\n")

        except requests.exceptions.ConnectionError:
            return jsonify({
                "error": f"Cannot connect to Ollama at {OLLAMA_URL}. Make sure Ollama is running ('ollama serve')."
            }), 503
        except requests.exceptions.Timeout:
            return jsonify({"error": "Ollama request timed out. Try again or check if Ollama is responsive."}), 504
        except Exception as e:
            return jsonify({"error": f"Ollama error: {str(e)}"}), 500

        # Extract code from fences
        if "```" in fixed:
            parts = fixed.split("```")
            if len(parts) >= 3:
                fixed = parts[1]
            elif len(parts) >= 2:
                fixed = parts[1]

            lines = fixed.split("\n")
            if lines and lines[0].strip().lower() in ('python', 'py', 'js', 'jsx', 'ts', 'tsx', 'vue', 'java', 'go', 'javascript', ext):
                fixed = "\n".join(lines[1:])

            if "```" in fixed:
                fixed = fixed.split("```")[0]

        fixed = fixed.strip("\r\n")
        fixed_lines_raw = fixed.split("\n") if fixed else []
        numbered_count = sum(1 for l in fixed_lines_raw if _re.match(r"^\s*\d+\s*:\s?", l))
        if fixed_lines_raw and numbered_count >= max(1, len(fixed_lines_raw) // 2):
            fixed = "\n".join(_re.sub(r"^\s*\d+\s*:\s?", "", l) for l in fixed_lines_raw)

        if not fixed:
            return jsonify({"error": "AI returned empty code"}), 500

        fixed_line_count = len(fixed.split("\n"))
        can_apply = fixed_line_count >= total_lines * 0.5

        # Save fixed code to database
        try:
            from database_ops import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE bug_detections SET fixed_code = %s WHERE id = %s",
                (fixed[:10000], bug_id)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_err:
            print(f"[WARNING] Could not save fixed code to DB: {db_err}")

        if not can_apply:
            return jsonify({
                "fixed_code": fixed,
                "original_code": original_code,
                "line_start": start + 1,
                "line_end": end,
                "can_apply": False,
                "warning": f"AI returned a partial fix preview ({fixed_line_count} lines vs expected ~{total_lines}). Review the fixed code, then generate again for an apply-ready patch."
            })

        return jsonify({
            "fixed_code": fixed,
            "original_code": original_code,
            "line_start": start + 1,
            "line_end": end,
            "can_apply": True,
        })

    except Exception as e:
        print(f"[ERROR] Fix generation failed: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Fix failed: {str(e)}"}), 500


@app.route("/api/bugs/<int:bug_id>/apply-fix", methods=["POST"])
def apply_ai_fix(bug_id):
    """Write the AI-generated fixed code back into the source file."""
    data = request.json or {}
    fixed_code = data.get("fixed_code", "")
    line_start  = int(data.get("line_start", 1))
    line_end    = int(data.get("line_end", 1))
    file_path   = data.get("file_path", "")

    if not fixed_code:
        return jsonify({"error": "No fixed_code provided"}), 400
    if not file_path:
        return jsonify({"error": "No file_path provided"}), 400
    if not os.path.isfile(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            original_lines = fh.readlines()

        fixed_lines = fixed_code.splitlines(keepends=False)
        fixed_lines_nl = [l + "\n" for l in fixed_lines]

        new_content = (
            original_lines[: line_start - 1] +
            fixed_lines_nl +
            original_lines[line_end:]
        )

        with open(file_path, "w", encoding="utf-8") as fh:
            fh.writelines(new_content)

        # Mark bug as FIXED in the database
        try:
            from database_ops import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE bug_detections SET status = 'FIXED', fixed_code = %s WHERE id = %s",
                (fixed_code, bug_id),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass

        return jsonify({"success": True, "message": "Fix applied successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chatbot/chat/stream", methods=["POST"])
def chatbot_stream():
    """Stream a response via Ollama (Gemma 3) with SSE."""
    import requests as _req

    from config import OLLAMA_URL, OLLAMA_MODEL

    data = request.json or {}
    user_message = data.get("message", "").strip()
    conv_id = data.get("conversation_id")
    file_context = data.get("file_context", "")
    issue_context = data.get("issue_context")

    if not user_message:
        return jsonify({"error": "Message is required"}), 400

    # Get or create conversation
    if conv_id and conv_id in chatbot_conversations:
        conv = chatbot_conversations[conv_id]
    else:
        conv_id = str(uuid.uuid4())[:8]
        chatbot_conversations[conv_id] = {
            "id": conv_id,
            "title": "New Chat",
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "history": [],
        }
        conv = chatbot_conversations[conv_id]

    if not conv["messages"]:
        conv["title"] = user_message[:50] + ("..." if len(user_message) > 50 else "")

    conv["messages"].append({
        "role": "user",
        "content": user_message,
        "timestamp": datetime.now().isoformat(),
    })

    system_parts = [PROJECT_PROMPT]
    if file_context:
        system_parts.append(f"\nFile in view:\n```\n{file_context[:5000]}\n```")
    if issue_context:
        system_parts.append(
            f"\nSelected issue:\n"
            f"- Title: {issue_context.get('title','')}\n"
            f"- Severity: {issue_context.get('severity','')}\n"
            f"- Line: {issue_context.get('line_number','')}\n"
            f"- Description: {issue_context.get('description','')}\n"
            f"- Fix suggestion: {issue_context.get('fix_suggestion','')}"
        )

    messages = [{"role": "system", "content": "\n".join(system_parts)}]
    for msg in conv["history"][-10:]:
        messages.append({"role": msg["role"], "content": msg["text"]})
    messages.append({"role": "user", "content": user_message})

    def generate():
        full_response = ""
        try:
            yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conv_id, 'title': conv['title']})}\n\n"

            resp = _req.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "stream": True},
                stream=True,
                timeout=120,
            )

            if resp.status_code != 200:
                yield f"data: {json.dumps({'type': 'error', 'content': f'Ollama error {resp.status_code}: {resp.text[:200]}'})}\n\n"
                return

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_response += token
                        yield f"data: {json.dumps({'type': 'chunk', 'content': token})}\n\n"
                    if chunk.get("done"):
                        break
                except Exception:
                    continue

            conv["history"].append({"role": "user", "text": user_message})
            conv["history"].append({"role": "assistant", "text": full_response})
            conv["messages"].append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.now().isoformat(),
            })

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Cannot connect to Ollama. Make sure it is running (ollama serve). Error: {str(e)}'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────────────────────────
# API: CODEBASE-AWARE CHAT (Gemini reads your actual scanned repo)
# ──────────────────────────────────────────────────────────────────
@app.route("/api/codebase/chat", methods=["POST"])
def codebase_chat():
    """
    Codebase-aware Gemini chat.
    Loads file tree + bug list from DB, optionally reads a specific file,
    injects all of it as context, then calls Gemini.
    """
    from config import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured in .env"}), 400

    data = request.json or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    selected_file = data.get("selected_file", "")   # absolute path (optional)

    if not message:
        return jsonify({"error": "Message is required"}), 400

    context_parts = []

    # ── 1. Project-level summary ──────────────────────────────────
    try:
        files = _get_code_viewer_files()
        project_dir = get_active_project_dir()
        project_name = os.path.basename(os.path.normpath(project_dir)) or "Project"

        total_bugs   = sum(int(f.get("bug_count")      or 0) for f in files)
        total_crit   = sum(int(f.get("critical_count") or 0) for f in files)
        total_high   = sum(int(f.get("high_count")     or 0) for f in files)
        total_med    = sum(int(f.get("medium_count")   or 0) for f in files)
        total_low    = sum(int(f.get("low_count")      or 0) for f in files)

        context_parts.append(f"## Scanned Project: {project_name}")
        context_parts.append(f"Root: {project_dir}")
        context_parts.append(f"Files scanned: {len(files)}")
        context_parts.append(
            f"Issues: {total_bugs} total "
            f"(Critical={total_crit}, High={total_high}, "
            f"Medium={total_med}, Low={total_low})"
        )

        # File list (top 60 by bug count)
        sorted_files = sorted(files, key=lambda x: int(x.get("bug_count") or 0), reverse=True)
        context_parts.append("\n### All Scanned Files (sorted by issue count):")
        for f in sorted_files[:60]:
            bugs = int(f.get("bug_count") or 0)
            crit = int(f.get("critical_count") or 0)
            hi   = int(f.get("high_count") or 0)
            tag  = ""
            if crit:
                tag = f" ⚠️ {crit} CRITICAL"
            elif hi:
                tag = f" ❗ {hi} HIGH"
            name = f.get("file_name", "")
            path = f.get("file_path", "")
            context_parts.append(f"  - {name} | {bugs} issue(s){tag} | {path}")
    except Exception as e:
        context_parts.append(f"[File tree unavailable: {e}]")
        files = []

    # ── 2. Bug list ───────────────────────────────────────────────
    try:
        from database_ops import get_db
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT file_name, file_path, title, severity, line_number,
                   description, fix_suggestion, status, bug_category
            FROM bug_detections
            WHERE (bug_category IS NULL OR bug_category != 'ai_configuration')
            ORDER BY FIELD(severity,'CRITICAL','HIGH','MEDIUM','LOW'),
                     file_name, line_number
            LIMIT 120
        """)
        all_bugs = cursor.fetchall() or []
        cursor.close()
        conn.close()

        if all_bugs:
            context_parts.append(f"\n### Detected Issues ({len(all_bugs)} shown):")
            for b in all_bugs:
                desc = (b.get("description") or "")[:120]
                fix  = (b.get("fix_suggestion") or "")[:80]
                context_parts.append(
                    f"  [{b.get('severity')}] {b.get('file_name')}:"
                    f"{b.get('line_number')} — {b.get('title')} | {desc}"
                    + (f" | Fix: {fix}" if fix else "")
                )
    except Exception as e:
        context_parts.append(f"[Bug list unavailable: {e}]")

    # ── 3. Selected file content ──────────────────────────────────
    if selected_file:
        norm = os.path.normpath(selected_file)
        if os.path.isfile(norm):
            try:
                with open(norm, "r", encoding="utf-8", errors="replace") as fh:
                    file_content = fh.read()
                ext = os.path.splitext(norm)[1].lstrip(".")
                context_parts.append(
                    f"\n### Currently Selected File: {os.path.basename(norm)}"
                )
                context_parts.append(f"Path: {norm}")
                context_parts.append(f"```{ext}\n{file_content[:10000]}\n```")
                if len(file_content) > 10000:
                    context_parts.append(
                        f"[File truncated — showing first 10 000 of "
                        f"{len(file_content)} chars]"
                    )
            except Exception as fe:
                context_parts.append(f"[Could not read {selected_file}: {fe}]")
        else:
            context_parts.append(f"[File not found on disk: {selected_file}]")

    # ── 4. Build system instruction ───────────────────────────────
    codebase_ctx = "\n".join(context_parts)
    system_instruction = (
        f"{PROJECT_PROMPT}\n\n"
        "You have DIRECT ACCESS to the developer's scanned codebase. "
        "The data below is live scan output — file names, paths, issue counts, "
        "severity levels, bug descriptions, and (when selected) full file content.\n"
        "Answer questions about this codebase accurately and specifically. "
        "Reference file names, line numbers, and severities from the data.\n"
        "When asked to explain or fix code, use the actual content provided.\n\n"
        f"{codebase_ctx}"
    )

    # ── 5. Call Gemini ────────────────────────────────────────────
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        contents = []
        for h in history[-12:]:
            role = "user" if h.get("role") == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=h.get("content", ""))]
                )
            )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            )
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.6,
                max_output_tokens=8192,
            ),
        )
        return jsonify({"response": response.text or "No response received."})

    except Exception as e:
        print(f"[Codebase Chat Error] {e}")
        return jsonify({"error": f"Gemini API error: {str(e)}"}), 500


# ──────────────────────────────────────────────────────────────────
# STARTUP
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Ensure DB tables exist
    from database_setup import create_tables
    create_tables()

    print("\n" + "=" * 52)
    print("   CodeLens Pro - AI Code Scanner")
    print("   Open http://localhost:5000 in your browser")
    print("=" * 52 + "\n")

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:5000")).start()

    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
