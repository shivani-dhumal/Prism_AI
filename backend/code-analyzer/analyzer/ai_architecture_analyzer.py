import json
import os
import time
from typing import Any, Dict, List

from ai_config import call_ai_json


def _summarize_ai_report(ai_report: Dict[str, Any]) -> Dict[str, Any]:
    files = ai_report.get("files", []) or []
    flagged = [f for f in files if f.get("status") == "FLAGGED"]
    return {
        "total_files": len(files),
        "flagged_files": len(flagged),
        "clean_files": len(files) - len(flagged),
        "top_flagged_files": [
            {
                "file_path": f.get("file_path"),
                "logic_defect_count": len(f.get("logic_defects", []) or []),
                "ui_accessibility_defect_count": len(f.get("ui_accessibility_defects", []) or []),
            }
            for f in flagged[:50]
        ],
    }


def _fallback_architecture(store: Any, dep_graph: Dict[str, Any], ai_summary: Dict[str, Any]) -> Dict[str, Any]:
    files = []
    for rec in store.iter_files():
        metrics = rec.metrics or {}
        layer = "Utilities"
        path_lower = rec.path.lower()
        if any(x in path_lower for x in ("component", "view", "page", ".vue")):
            layer = "Presentation"
        elif any(x in path_lower for x in ("api", "service", "client", "repository")):
            layer = "Data/API"
        elif any(x in path_lower for x in ("store", "state", "domain", "usecase")):
            layer = "Business Logic"

        files.append(
            {
                "file_path": rec.path,
                "layer": layer,
                "method_count": metrics.get("method_count", 0),
                "api_coupling_count": metrics.get("api_coupling_count", 0),
            }
        )

    god_files = [
        f for f in files if f["method_count"] >= 10 and f["api_coupling_count"] >= 5
    ]
    score = max(0, 100 - len(god_files) * 8 - ai_summary.get("flagged_files", 0) * 2)
    return {
        "project_overview": "Heuristic architecture summary generated without LLM.",
        "architectural_health_score": score,
        "layer_classification": files,
        "macro_trends": {
            "dependency_edges": len(dep_graph.get("connections", []) or []),
            "god_file_candidates": god_files,
        },
        "key_workflows": [],
        "risks": [],
    }


def analyze_architecture(store: Any, backend_reports_dir: str) -> Dict[str, Any]:
    dep_graph = store.tables.get("dependency_graph") or {}
    ai_report = store.tables.get("ai_report") or {}
    ai_summary = _summarize_ai_report(ai_report)

    prompt = [
        {
            "role": "system",
            "content": "You are PrismAI's architecture auditor. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "dependency_graph": dep_graph,
                    "ai_report_summary": ai_summary,
                    "task": (
                        "Identify cross-layer contamination, state management fragility, "
                        "circular dependency vulnerabilities, and God Files. Classify files "
                        "as Presentation, Business Logic, Data/API, or Utilities. Return "
                        "project_overview, architectural_health_score 0-100, "
                        "layer_classification, macro_trends, key_workflows, risks."
                    ),
                },
                default=str,
            ),
        },
    ]

    try:
        result = call_ai_json(prompt, max_retries=5)
        if not isinstance(result, dict):
            raise ValueError("Architecture AI response was not an object")
    except Exception as exc:
        result = _fallback_architecture(store, dep_graph, ai_summary)
        result["ai_error"] = str(exc)

    result["generated_at"] = time.time()
    out_path = os.path.join(backend_reports_dir, "ai_architecture.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    if hasattr(store, "set_ai_architecture"):
        store.set_ai_architecture(result)
    return result
