import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from ai_config import call_ai_json


def _is_clean(metrics: Dict[str, Any]) -> bool:
    a11y = metrics.get("accessibility", {}) or {}
    cyclo = metrics.get("cyclomatic_complexity", 0)
    cognitive = metrics.get("cognitive_complexity", 0)
    depth = metrics.get("max_nesting_depth", 0)
    method_count = metrics.get("method_count", 0)
    api_calls = metrics.get("api_coupling_count", 0)
    parse_anomalies = metrics.get("parse_anomalies", []) or []

    has_accessibility_flags = bool(a11y.get("flags"))
    has_ast_anomalies = bool(parse_anomalies)

    return (
        cyclo < 10
        and cognitive < 10
        and depth < 6
        and method_count <= 10
        and api_calls <= 5
        and not has_accessibility_flags
        and not has_ast_anomalies
    )


def _build_prompt(file_path: str, ext: str, content: str, metrics: Dict[str, Any], parsed: Dict[str, Any]) -> List[Dict[str, str]]:
    cyclo = metrics.get("cyclomatic_complexity", 0)
    cognitive = metrics.get("cognitive_complexity", 0)
    depth = metrics.get("max_nesting_depth", 0)
    method_count = metrics.get("method_count", 0)
    api_calls = metrics.get("api_coupling_count", 0)
    a11y = metrics.get("accessibility", {}) or {}

    # Keep source size reasonable for local models.
    max_chars = 35_000
    src = content if len(content) <= max_chars else content[:max_chars] + "\n\n... [TRUNCATED]"

    system = (
        "You are PrismAI, a strict static analysis engine. "
        "Return only valid JSON (no markdown, no commentary)."
    )

    user = {
        "file_path": file_path,
        "ext": ext,
        "metrics": {
            "cyclomatic_complexity": cyclo,
            "cognitive_complexity": cognitive,
            "max_nesting_depth": depth,
            "method_count": method_count,
            "api_coupling_count": api_calls,
            "accessibility_flags": a11y.get("flags", []),
            "accessibility_counts": a11y,
            "parse_anomalies": metrics.get("parse_anomalies", []),
        },
        "ast_context": {
            "imports": parsed.get("imports", []),
            "exports": parsed.get("exports", []),
            "functions": parsed.get("functions", []),
            "http_calls": parsed.get("http_calls", []),
            "ui_elements": parsed.get("ui_elements", []),
            "vue": parsed.get("vue", None),
        },
        "source_code": src,
        "task": (
            "Identify defects. Separate results into (A) logic/architectural defects and "
            "(B) UI/accessibility defects. For each defect, return these keys exactly: "
            "defect_type, severity, description, affected_location, recommended_fix."
        ),
        "output_schema": {
            "file_path": "string",
            "logic_defects": [
                {
                    "defect_type": "string",
                    "severity": "HIGH|MEDIUM|LOW",
                    "description": "string",
                    "affected_location": "string",
                    "recommended_fix": "string",
                }
            ],
            "ui_accessibility_defects": [
                {
                    "defect_type": "string",
                    "severity": "HIGH|MEDIUM|LOW",
                    "description": "string",
                    "affected_location": "string",
                    "recommended_fix": "string",
                }
            ],
        },
    }

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": str(user)},
    ]
    return messages


def _analyze_one(store_file: Any) -> Dict[str, Any]:
    file_path = store_file.path
    ext = store_file.ext

    parsed = store_file.parsed or {}
    metrics = store_file.metrics or {}
    content = store_file.content or ""

    if _is_clean(metrics):
        return {
            "file_path": file_path,
            "status": "CLEAN",
            "logic_defects": [],
            "ui_accessibility_defects": [],
        }

    prompt = _build_prompt(file_path=file_path, ext=ext, content=content, metrics=metrics, parsed=parsed)
    try:
        ai_json = call_ai_json(prompt, max_retries=5)
    except Exception as exc:
        return {
            "file_path": file_path,
            "status": "FLAGGED",
            "logic_defects": [],
            "ui_accessibility_defects": [],
            "ai_error": str(exc),
        }

    # Normalize some shapes defensively.
    if isinstance(ai_json, dict):
        logic = ai_json.get("logic_defects", []) or []
        ui = ai_json.get("ui_accessibility_defects", []) or []
        return {
            "file_path": ai_json.get("file_path", file_path),
            "status": "FLAGGED",
            "logic_defects": logic,
            "ui_accessibility_defects": ui,
        }

    # Unexpected shape
    return {
        "file_path": file_path,
        "status": "FLAGGED",
        "logic_defects": [],
        "ui_accessibility_defects": [],
        "ai_raw": ai_json,
    }


def analyze_defects_for_files(store: Any, backend_reports_dir: str, max_workers: int = 4) -> None:
    """
    Stage 5 — two-phase AI defect reporter.
    Saves: backend/json_reports/ai_report.json
    """
    files = list(store.iter_files())

    started = time.time()
    results: List[Dict[str, Any]] = []

    # Parallelize LLM calls; RateLimiter in ai_config handles inter-call spacing.
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_analyze_one, f) for f in files]
        for fut in as_completed(futures):
            results.append(fut.result())

    # Deterministic order by file_path for stable diffs
    results.sort(key=lambda x: x.get("file_path", ""))

    report = {
        "generated_at": time.time(),
        "elapsed_seconds": time.time() - started,
        "files": results,
    }

    out_path = os.path.join(backend_reports_dir, "ai_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        import json

        json.dump(report, f, indent=2, default=str)

    # Also store it in the shared JsonStore (optional).
    if hasattr(store, "set_ai_report"):
        store.set_ai_report(report)
