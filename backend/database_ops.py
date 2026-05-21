# database_ops.py

import mysql.connector
import json
from config import DB_CONFIG



# DATABASE CONNECTION
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# TRUNCATE TABLES
def truncate_tables():
    """Wipe all data so every scan starts clean"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    # Order matters: children before parents
    tables = [
        "bug_detections", "code_metrics", "component_methods", "ai_risk_predictions", "ai_project_report",
        "accessibility_report", "ui_consistency_report",
        "file_flags", "ui_extraction", "component_complexity",
        "apis", "ui_elements", "components", "files", "folders"
    ]
    for t in tables:
        try:
            cursor.execute(f"DELETE FROM {t}")
            cursor.execute(f"ALTER TABLE {t} AUTO_INCREMENT = 1")
        except Exception:
            pass   # table may not exist yet on first run

    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    conn.commit()
    cursor.close()
    conn.close()


# CLEAR STUCK SCANS
def clear_stuck_scans():
    """Clear scans that are stuck in RUNNING state"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE scans
            SET status = 'FAILED',
                error_message = 'Cleared due to timeout',
                completed_at = NOW()
            WHERE status = 'RUNNING'
        """)
        affected = cursor.rowcount
        conn.commit()
        return affected
    finally:
        cursor.close()
        conn.close()


# SAVE FOLDER


def save_folder(name, path):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO folders (folder_name, folder_path) VALUES (%s, %s)",
        (name, path)
    )

    conn.commit()
    last_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return last_id


# SAVE FILE


def save_file(folder_id, name, path, ext):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO files (folder_id, file_name, file_path, extension) VALUES (%s, %s, %s, %s)",
        (folder_id, name, path, ext)
    )

    conn.commit()
    last_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return last_id



# SAVE COMPONENT


def save_component(file_id, name):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO components (file_id, component_name) VALUES (%s, %s)",
        (file_id, name)
    )

    conn.commit()
    last_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return last_id


# SAVE UI


def save_ui(component_id, tag, action_type, handler):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO ui_elements (component_id, tag_name, action_type, action_handler) VALUES (%s, %s, %s, %s)",
        (component_id, tag, action_type, handler)
    )

    conn.commit()
    cursor.close()
    conn.close()


# SAVE API 

def save_api(file_id, method, url, payload):
    conn = get_db()
    cursor = conn.cursor()

    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)

    cursor.execute(
        "INSERT INTO apis (file_id, method, url, payload) VALUES (%s, %s, %s, %s)",
        (file_id, method, url, payload)
    )

    conn.commit()
    cursor.close()
    conn.close()



# GET API COUNT


def get_api_count(file_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM apis WHERE file_id = %s",
        (file_id,)
    )

    result = cursor.fetchone()
    count = result[0] if result else 0

    cursor.close()
    conn.close()

    return count



# SAVE FILE FLAGS

def save_file_flags(file_id, metrics, flag_groups):
    conn = get_db()
    cursor = conn.cursor()

    safe_flags = {
        "api": flag_groups.get("api", []),
        "payload": flag_groups.get("payload", []),
        "complexity": flag_groups.get("complexity", []),
        "risk": flag_groups.get("risk", []),
        "pattern": flag_groups.get("pattern", []),
        "ui": flag_groups.get("ui", [])
    }

    query = """
    INSERT INTO file_flags (
        file_id,
        api_count,
        payload_keys_max,
        loc,
        api_flags,
        payload_flags,
        complexity_flags,
        risk_flags,
        pattern_flags,
        ui_flags
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        api_count = VALUES(api_count),
        payload_keys_max = VALUES(payload_keys_max),
        loc = VALUES(loc),
        api_flags = VALUES(api_flags),
        payload_flags = VALUES(payload_flags),
        complexity_flags = VALUES(complexity_flags),
        risk_flags = VALUES(risk_flags),
        pattern_flags = VALUES(pattern_flags),
        ui_flags = VALUES(ui_flags)
    """

    values = (
        int(file_id),
        int(metrics.get("api_count", 0)),
        int(metrics.get("payload_keys_max", 0)),
        int(metrics.get("loc", 0)),
        ", ".join(safe_flags["api"]) if safe_flags["api"] else "",
        ", ".join(safe_flags["payload"]) if safe_flags["payload"] else "",
        ", ".join(safe_flags["complexity"]) if safe_flags["complexity"] else "",
        ", ".join(safe_flags["risk"]) if safe_flags["risk"] else "",
        ", ".join(safe_flags["pattern"]) if safe_flags["pattern"] else "",
        ", ".join(safe_flags["ui"]) if safe_flags["ui"] else ""
    )

   


    cursor.execute(query, values)
    conn.commit()

    cursor.close()
    conn.close()
def save_component_complexity(
    component_id,
    totallines,
    methods,
    computed,
    watchers,
    template_lines,
    child_components,
    flags
):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO component_complexity (
            component_id,
            totallines,
            methods,
            computed,
            watchers,
            template_lines,
            child_components,
            flags
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        component_id,
        totallines,
        methods,
        computed,
        watchers,
        template_lines,
        child_components,
        flags
    ))

    conn.commit()
    cursor.close()
    conn.close()

def save_ui_extraction(component_id, file_path, tag_name, text_value, css_class, div_id, line_number='0-0'):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ui_extraction
        (component_id, file_path, tag_name, text_value, css_class, div_id, line_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        component_id,
        file_path,
        tag_name,
        text_value,
        css_class,
        div_id,
        line_number
    ))

    conn.commit()
    cursor.close()
    conn.close()

# SAVE UI CONSISTENCY REPORT (Unified TASK-5)

# ⚡ SPEED: Persistent connections to avoid open/close overhead per insert
_ui_conn = None
_acc_conn = None

def _get_ui_conn():
    global _ui_conn
    try:
        if _ui_conn is None or not _ui_conn.is_connected():
            _ui_conn = mysql.connector.connect(**DB_CONFIG)
    except Exception:
        _ui_conn = mysql.connector.connect(**DB_CONFIG)
    return _ui_conn

def _get_acc_conn():
    global _acc_conn
    try:
        if _acc_conn is None or not _acc_conn.is_connected():
            _acc_conn = mysql.connector.connect(**DB_CONFIG)
    except Exception:
        _acc_conn = mysql.connector.connect(**DB_CONFIG)
    return _acc_conn


def save_ui_consistency_report(component_id, file_path, rule_name, status, actual_result, severity="MEDIUM", recommendation="N/A", line_number='0-0'):
    conn = _get_ui_conn()
    cursor = conn.cursor()

    # The database expects an INT or NULL for component_id.
    # If a string like "ALL" or "LANG_FILE" is passed, convert to None (NULL in SQL).
    try:
        if component_id is not None:
            component_id = int(component_id)
    except (ValueError, TypeError):
        component_id = None

    cursor.execute("""
        INSERT INTO ui_consistency_report
        (component_id, file_path, rule_name, status, actual_result, severity, recommendation, line_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        component_id,
        file_path,
        rule_name,
        status,
        actual_result,
        severity,
        recommendation,
        line_number
    ))

    conn.commit()
    cursor.close()


# SAVE ACCESSIBILITY REPORT (TASK-6)

def save_accessibility_report(component_id, file_path, rule_name, status, actual_result, severity="MEDIUM", line_number='0-0'):
    conn = _get_acc_conn()
    cursor = conn.cursor()

    try:
        if component_id is not None:
            component_id = int(component_id)
    except (ValueError, TypeError):
        component_id = None

    cursor.execute("""
        INSERT INTO accessibility_report
        (component_id, file_path, rule_name, status, actual_result, severity, line_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        component_id,
        file_path,
        rule_name,
        status,
        actual_result,
        severity,
        line_number
    ))

    conn.commit()
    cursor.close()


# SAVE AI RISK PREDICTION (TASK-8)

def save_ai_risk_prediction(component_id, file_path, predicted_risk, confidence, reason, suggestions):
    conn = get_db()
    cursor = conn.cursor()

    if isinstance(suggestions, list):
        suggestions = json.dumps(suggestions)

    cursor.execute("""
        INSERT INTO ai_risk_predictions
        (component_id, file_path, predicted_risk, confidence, reason, suggestions)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        component_id,
        file_path,
        predicted_risk,
        confidence,
        reason,
        suggestions
    ))

    conn.commit()
    cursor.close()
    conn.close()


def save_component_method(component_id, method_name, method_lines, total_lines):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO component_methods
        (component_id, method_name, method_lines, total_lines)
        VALUES (%s, %s, %s, %s)
    """, (component_id, method_name, method_lines, total_lines))

    conn.commit()
    cursor.close()
    conn.close()


# ──────────────────────────────────────────────────────────────────
# SCAN MANAGEMENT (Web Dashboard)
# ──────────────────────────────────────────────────────────────────

def create_scan(scan_name, target_directory):
    """Create a new scan record and return its ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scans (scan_name, target_directory, status, current_stage, progress)
        VALUES (%s, %s, 'RUNNING', 'Starting', 0)
    """, (scan_name, target_directory))
    conn.commit()
    scan_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return scan_id


def update_scan_progress(scan_id, stage, progress, message=""):
    """Update the current progress of a running scan."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE scans SET current_stage=%s, progress=%s, message=%s
        WHERE id=%s
    """, (stage, min(progress, 99), message, scan_id))
    conn.commit()
    cursor.close()
    conn.close()


def complete_scan(scan_id, total_issues=0, high=0, medium=0, low=0):
    """Mark a scan as completed with final issue counts."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE scans
        SET status='COMPLETED', progress=100, current_stage='Complete',
            total_issues=%s, high_count=%s, medium_count=%s, low_count=%s,
            completed_at=NOW()
        WHERE id=%s
    """, (total_issues, high, medium, low, scan_id))
    conn.commit()
    cursor.close()
    conn.close()


def fail_scan(scan_id, error_message):
    """Mark a scan as failed with an error message."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE scans SET status='FAILED', current_stage='Failed',
        error_message=%s, completed_at=NOW()
        WHERE id=%s
    """, (str(error_message)[:2000], scan_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_scan_status(scan_id):
    """Get the current status of a scan."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM scans WHERE id=%s", (scan_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result or {}


def get_all_scans():
    """Get all scans ordered by most recent first."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM scans ORDER BY started_at DESC LIMIT 50")
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def get_scan_summary():
    """Count issues from the current DB state (after a scan completes)."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT severity, COUNT(*) as cnt
        FROM accessibility_report WHERE status='FAIL'
        GROUP BY severity
    """)
    sev = {r["severity"]: r["cnt"] for r in cursor.fetchall()}

    cursor.execute("""
        SELECT severity, COUNT(*) as cnt
        FROM ui_consistency_report WHERE status='FAIL'
        GROUP BY severity
    """)
    for r in cursor.fetchall():
        sev[r["severity"]] = sev.get(r["severity"], 0) + r["cnt"]

    cursor.close()
    conn.close()

    high = sev.get("HIGH", 0)
    medium = sev.get("MEDIUM", 0)
    low = sev.get("LOW", 0)
    return {
        "total": high + medium + low,
        "high": high,
        "medium": medium,
        "low": low,
    }


def delete_scan(scan_id):
    """Delete a scan record."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scans WHERE id=%s", (scan_id,))
    conn.commit()
    cursor.close()
    conn.close()


# ──────────────────────────────────────────────────────────────────
# CODE VIEWER SUPPORT
# ──────────────────────────────────────────────────────────────────

def update_bug_status(bug_id, status, fixed_code=None):
    """Update the status of a detected bug (OPEN/FIXED/IGNORED)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bug_detections
        SET status=%s, fixed_code=%s, status_updated_at=NOW()
        WHERE id=%s
    """, (status, fixed_code, bug_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_file_tree():
    """Return all scanned files with their bug counts grouped by severity."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            f.id AS file_id,
            f.file_name,
            f.file_path,
            f.extension,
            fld.folder_path,
            COUNT(b.id) AS bug_count,
            CAST(SUM(CASE WHEN b.severity = 'CRITICAL' THEN 1 ELSE 0 END) AS SIGNED) AS critical_count,
            CAST(SUM(CASE WHEN b.severity = 'HIGH' THEN 1 ELSE 0 END) AS SIGNED) AS high_count,
            CAST(SUM(CASE WHEN b.severity = 'MEDIUM' THEN 1 ELSE 0 END) AS SIGNED) AS medium_count,
            CAST(SUM(CASE WHEN b.severity = 'LOW' THEN 1 ELSE 0 END) AS SIGNED) AS low_count,
            CAST(SUM(CASE WHEN b.status = 'OPEN' THEN 1 ELSE 0 END) AS SIGNED) AS open_count,
            CAST(SUM(CASE WHEN b.status = 'FIXED' THEN 1 ELSE 0 END) AS SIGNED) AS fixed_count,
            CAST(SUM(CASE WHEN b.status = 'IGNORED' THEN 1 ELSE 0 END) AS SIGNED) AS ignored_count
        FROM files f
        JOIN folders fld ON f.folder_id = fld.id
        LEFT JOIN bug_detections b ON f.id = b.file_id
        GROUP BY f.id, f.file_name, f.file_path, f.extension, fld.folder_path
        ORDER BY bug_count DESC, f.file_name ASC
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    # Ensure all numeric fields are plain int (not Decimal)
    import decimal
    for row in results:
        for k, v in row.items():
            if isinstance(v, decimal.Decimal):
                row[k] = int(v)
    return results


def get_file_annotations(file_path):
    """Return all bugs for a file as line annotations."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, bug_category, title, severity, line_number,
               description, fix_suggestion, confidence, status, fixed_code
        FROM bug_detections
        WHERE file_path = %s
        ORDER BY line_number ASC
    """, (file_path,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def get_full_report_data():
    """Return complete report data with all bugs, stats, and status breakdown."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # All bugs
    cursor.execute("""
        SELECT id, file_name, file_path, bug_category, title, severity,
               line_number, description, fix_suggestion, confidence, status
        FROM bug_detections
        ORDER BY FIELD(severity, 'CRITICAL','HIGH','MEDIUM','LOW'), file_path, line_number
    """)
    bugs = cursor.fetchall()

    # Stats
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(status='OPEN') AS open_count,
            SUM(status='FIXED') AS fixed_count,
            SUM(status='IGNORED') AS ignored_count,
            SUM(severity='CRITICAL') AS critical,
            SUM(severity='HIGH') AS high,
            SUM(severity='MEDIUM') AS medium,
            SUM(severity='LOW') AS low
        FROM bug_detections
    """)
    stats = cursor.fetchone()

    # Per-file summary
    cursor.execute("""
        SELECT file_name, file_path,
            COUNT(*) AS total,
            SUM(status='OPEN') AS open_count,
            SUM(status='FIXED') AS fixed_count,
            SUM(status='IGNORED') AS ignored_count
        FROM bug_detections
        GROUP BY file_name, file_path
        ORDER BY total DESC
    """)
    file_summary = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "bugs": bugs,
        "stats": {k: int(v or 0) for k, v in (stats or {}).items()},
        "file_summary": file_summary,
    }