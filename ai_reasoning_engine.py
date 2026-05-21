"""
Task-8C: AI Reasoning Layer (LLM Integration — No RAG)
Loads risk predictions and sends structured prompts to Google Gemini
to generate human-like explanations and refactoring suggestions.

Output → reports/ai_reasoning_output.json
"""

import os
import sys
import json
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from google import genai
from google.genai import types

try:
    from config import GEMINI_API_KEY
except ImportError:
    GEMINI_API_KEY = "AIzaSyBqQWJhLpCRwpD40d1DXkrji8yT4wA8B5I"

_client = genai.Client(api_key=GEMINI_API_KEY)


# ──────────────────────────────────────────────────────────────────
# Gemini caller with retry
# ──────────────────────────────────────────────────────────────────
def ask_gemini(prompt, max_retries=4):
    for attempt in range(max_retries):
        try:
            resp = _client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return resp.text
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < max_retries - 1:
                wait = 25 * (attempt + 1)
                print(f"      Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                return f"[Gemini Error] {e}"


# ──────────────────────────────────────────────────────────────────
# Prompt builder
# ──────────────────────────────────────────────────────────────────
def build_prompt(item):
    """Build a structured prompt for the LLM from one component's data."""
    m = item.get("metrics", {})
    ui = item.get("ui", {})
    acc = item.get("accessibility", {})
    fl = item.get("flags", {})

    ui_issues = []
    if ui.get("missingHeader"):
        ui_issues.append("Missing header element")
    if ui.get("buttonMismatch"):
        ui_issues.append("Button style mismatch")
    if ui.get("spellingIssues", 0) > 0:
        ui_issues.append(f"{ui['spellingIssues']} spelling issues found")
    if ui.get("fontInconsistency"):
        ui_issues.append("Inconsistent font styles")

    flags_list = []
    for key in ["complexityFlags", "riskFlags", "patternFlags", "uiFlags"]:
        val = fl.get(key, "")
        if val:
            flags_list.append(val)

    prompt = f"""You are a senior Vue.js architect reviewing a component.

Component: {item.get('fileName', 'Unknown')}
File: {item.get('file', 'Unknown')}
Predicted Risk: {item.get('predictedRisk', 'UNKNOWN')}
Confidence: {item.get('confidence', 0)}

Metrics:
- Lines of code: {m.get('lines', 0)}
- Methods: {m.get('methods', 0)}
- Computed properties: {m.get('computed', 0)}
- Watchers: {m.get('watchers', 0)}
- Template lines: {m.get('templateLines', 0)}
- Child components: {m.get('childComponents', 0)}
- API calls: {fl.get('apiCount', 0)}

UI Issues: {', '.join(ui_issues) if ui_issues else 'None'}
Accessibility Issues: {acc.get('totalIssues', 0)} total ({acc.get('highSeverity', 0)} HIGH, {acc.get('mediumSeverity', 0)} MEDIUM)
Flags: {', '.join(flags_list) if flags_list else 'None'}

Tasks:
1. Explain why this component is {item.get('predictedRisk', 'risky')} risk (2-3 sentences)
2. Suggest 3-5 specific refactoring steps
3. Suggest API optimizations (if applicable)
4. Suggest UI/accessibility improvements (if applicable)

Reply in STRICT JSON format (no markdown fences):
{{
  "reason": "...",
  "suggestions": ["...", "...", "..."]
}}"""

    return prompt


# ──────────────────────────────────────────────────────────────────
# Parse LLM response (no regex — uses json + string methods)
# ──────────────────────────────────────────────────────────────────
def parse_response(text):
    """Extract JSON object from the LLM response text using json module only."""
    # Try direct JSON parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown fences if present (e.g. ```json ... ```)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        # Remove closing fence
        last_fence = cleaned.rfind("```")
        if last_fence != -1:
            cleaned = cleaned[:last_fence]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            pass

    # Try to find a JSON object by locating the first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback — return raw text as reason
    return {
        "reason": text.strip()[:500],
        "suggestions": ["See raw AI response above for details"],
    }


# ──────────────────────────────────────────────────────────────────
# Main reasoning engine
# ──────────────────────────────────────────────────────────────────
def generate_reasoning(predictions):
    """Generate AI reasoning for HIGH and MEDIUM risk components."""
    results = []

    # Only send HIGH and MEDIUM risk components to save API calls
    risky = [p for p in predictions if p.get("predictedRisk") in ("HIGH", "MEDIUM")][:10]
    low = [p for p in predictions if p.get("predictedRisk") == "LOW"]

    print(f"   [8C] Processing {len(risky)} HIGH/MEDIUM risk components (skipping {len(low)} LOW)...")

    for idx, item in enumerate(risky):
        fname = item.get("fileName", "?")
        risk = item.get("predictedRisk", "?")
        print(f"   [8C]   → ({idx+1}/{len(risky)}) {fname} [{risk}]")

        prompt = build_prompt(item)
        raw_response = ask_gemini(prompt)
        parsed = parse_response(raw_response)

        results.append({
            "file": item.get("file", ""),
            "fileName": fname,
            "risk": risk,
            "confidence": item.get("confidence", 0),
            "reason": parsed.get("reason", ""),
            "suggestions": parsed.get("suggestions", []),
        })

    # Add LOW risk components with default values (no LLM call needed)
    for item in low:
        results.append({
            "file": item.get("file", ""),
            "fileName": item.get("fileName", ""),
            "risk": "LOW",
            "confidence": item.get("confidence", 0),
            "reason": "Component is within acceptable complexity thresholds.",
            "suggestions": [],
        })

    return results


# ──────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────
def run():
    pred_path = os.path.join("reports", "ai_risk_predictions.json")

    if not os.path.isfile(pred_path):
        print("   [8C] ❌ ai_risk_predictions.json not found. Run risk_model.py first.")
        return None

    print("   [8C] Loading risk predictions...")
    with open(pred_path, "r", encoding="utf-8") as f:
        predictions = json.load(f)

    results = generate_reasoning(predictions)

    os.makedirs("reports", exist_ok=True)
    out_path = os.path.join("reports", "ai_reasoning_output.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, default=str)

    print(f"   [8C] ✅ Reasoning output saved → {os.path.abspath(out_path)}")

    # Summary
    high = sum(1 for r in results if r["risk"] == "HIGH")
    med = sum(1 for r in results if r["risk"] == "MEDIUM")
    low = sum(1 for r in results if r["risk"] == "LOW")
    print(f"   [8C] Summary: HIGH={high}, MEDIUM={med}, LOW={low}")

    return results


if __name__ == "__main__":
    run()
