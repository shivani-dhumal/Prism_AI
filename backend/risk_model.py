"""
risk_model.py — Rule-based component risk scorer (no ML).

Scores each component using deterministic thresholds and assigns
LOW / MEDIUM / HIGH risk labels. The RandomForest training logic
has been removed.
"""

import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import mysql.connector
from config import DB_CONFIG


# ──────────────────────────────────────────────────────────────────
# Rule-based risk labeller
# ──────────────────────────────────────────────────────────────────
def assign_label(item):
    """
    Deterministic rule engine that scores a component and returns
    'LOW', 'MEDIUM', or 'HIGH' risk.
    """
    score = 0
    m   = item.get("metrics", {})
    acc = item.get("accessibility", {})
    ui  = item.get("ui", {})
    fl  = item.get("flags", {})

    lines          = m.get("lines", 0)
    methods        = m.get("methods", 0)
    watchers       = m.get("watchers", 0)
    template_lines = m.get("templateLines", 0)
    acc_high       = acc.get("highSeverity", 0)
    acc_total      = acc.get("totalIssues", 0)
    spelling       = ui.get("spellingIssues", 0)

    # Complexity thresholds
    if lines >= 800:   score += 3
    elif lines >= 500: score += 2
    elif lines >= 300: score += 1

    if methods >= 10:  score += 2
    elif methods >= 5: score += 1

    if watchers >= 5:  score += 2
    elif watchers >= 3: score += 1

    if template_lines >= 200: score += 2
    elif template_lines >= 100: score += 1

    # Accessibility risk
    if acc_high >= 10:  score += 3
    elif acc_high >= 5: score += 2
    elif acc_high >= 1: score += 1

    if acc_total >= 15: score += 1

    # UI issues
    if spelling >= 3:        score += 1
    if ui.get("missingHeader"): score += 1

    # Complexity flags
    cflags = fl.get("complexityFlags", "")
    if "VERY_LARGE" in cflags: score += 2
    elif "LARGE" in cflags:    score += 1

    if score >= 7:   return "HIGH"
    elif score >= 4: return "MEDIUM"
    else:            return "LOW"


# ──────────────────────────────────────────────────────────────────
# Save predictions to DB
# ──────────────────────────────────────────────────────────────────
def save_predictions_to_db(results):
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, file_id, component_name FROM components")
    components = cursor.fetchall()

    cursor.execute("SELECT id, file_path FROM files")
    files = cursor.fetchall()

    fp_to_fid  = {f["file_path"]: f["id"] for f in files}
    fid_to_cid = {c["file_id"]: c["id"] for c in components}

    inserted = 0
    for r in results:
        file_path = r.get("file", "")
        file_id   = fp_to_fid.get(file_path)
        comp_id   = fid_to_cid.get(file_id) if file_id else None

        cursor.execute("""
            INSERT INTO ai_risk_predictions
            (component_id, file_path, predicted_risk, confidence, reason, suggestions)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            comp_id,
            file_path,
            str(r.get("predictedRisk", "LOW")),
            float(r.get("confidence", 1.0)),
            "",
            "[]"
        ))
        inserted += 1

    high  = sum(1 for r in results if str(r.get("predictedRisk")) == "HIGH")
    med   = sum(1 for r in results if str(r.get("predictedRisk")) == "MEDIUM")
    score = max(0, int(100 - high * 5 - med * 2))
    risk_level = "LOW" if score >= 80 else "MEDIUM" if score >= 60 else "HIGH"

    cursor.execute("""
        INSERT INTO ai_project_report (projectScore, riskLevel, totalIssues)
        VALUES (%s, %s, %s)
    """, (score, risk_level, high + med))

    conn.commit()
    cursor.close()
    conn.close()

    print(f"   [Risk] Saved {inserted} predictions — score={score}, risk={risk_level}")


# ──────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────
def run():
    input_path = os.path.join("reports", "ai_input_data.json")

    if not os.path.isfile(input_path):
        print("   [Risk] ai_input_data.json not found — skipping.")
        return None

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"   [Risk] Scoring {len(data)} components with rule-based engine...")

    results = []
    for item in data:
        label = assign_label(item)
        results.append({**item, "predictedRisk": label, "confidence": 1.0})

    os.makedirs("reports", exist_ok=True)
    pred_path = os.path.join("reports", "ai_risk_predictions.json")
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, default=str)
    print(f"   [Risk] Predictions saved → {os.path.abspath(pred_path)}")

    risk_counts = {}
    for r in results:
        risk_counts[r["predictedRisk"]] = risk_counts.get(r["predictedRisk"], 0) + 1
    print(f"   [Risk] Summary: {risk_counts}")

    return results


if __name__ == "__main__":
    run()
