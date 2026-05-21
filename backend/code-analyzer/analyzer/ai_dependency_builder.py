import json
import os
from typing import Any, Dict, List, Optional

from ai_config import call_ai_json


def infer_semantic_edges(
    static_dependency_graph: Dict[str, Any],
    *,
    backend_reports_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ask the local LLM to infer semantic dependencies not visible as imports.
    Falls back to the static graph when OpenWebUI is not configured or unavailable.
    """
    prompt = [
        {
            "role": "system",
            "content": "You infer semantic frontend dependency edges. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "static_dependency_graph": static_dependency_graph,
                    "task": (
                        "Infer semantic edges such as shared state, event bus patterns, "
                        "implicit API/data coupling, routing relationships, and UI workflow coupling."
                    ),
                    "output_schema": {
                        "semantic_connections": [
                            {
                                "from": "file path",
                                "to": "file path",
                                "relationship": "shared_state|event_bus|implicit_api|routing|workflow|other",
                                "confidence": 0.0,
                                "reason": "string",
                            }
                        ]
                    },
                },
                default=str,
            ),
        },
    ]

    semantic_connections: List[Dict[str, Any]] = []
    merged = dict(static_dependency_graph)
    try:
        ai_json = call_ai_json(prompt, max_retries=5)
        if isinstance(ai_json, dict):
            semantic_connections = [
                edge for edge in ai_json.get("semantic_connections", []) or [] if isinstance(edge, dict)
            ]
    except Exception as exc:
        merged["semantic_error"] = str(exc)

    merged["semantic_connections"] = semantic_connections
    merged["connections"] = list(static_dependency_graph.get("connections", []) or []) + [
        {**edge, "semantic": True} for edge in semantic_connections
    ]

    if backend_reports_dir:
        out_path = os.path.join(backend_reports_dir, "dependency_graph.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, default=str)

    return merged
