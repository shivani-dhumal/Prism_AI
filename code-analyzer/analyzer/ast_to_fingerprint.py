import hashlib
import json
from typing import Any, Dict


def ast_fingerprint(parsed: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    """
    Lightweight fingerprint to detect “structurally similar” files between runs.
    Used for caching/consistency checks in future iterations.
    """
    payload = {
        "parsed": {
            "imports": parsed.get("imports", []),
            "exports": parsed.get("exports", []),
            "functions_count": len(parsed.get("functions", []) or []),
            "http_calls_count": len(parsed.get("http_calls", []) or []),
            "vue": parsed.get("vue"),
        },
        "metrics": {
            "cyclomatic_complexity": metrics.get("cyclomatic_complexity"),
            "cognitive_complexity": metrics.get("cognitive_complexity"),
            "max_nesting_depth": metrics.get("max_nesting_depth"),
            "method_count": metrics.get("method_count"),
            "api_coupling_count": metrics.get("api_coupling_count"),
            "a11y_flags": ((metrics.get("accessibility") or {}).get("flags", []) or []),
        },
    }

    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()

import hashlib
import json
from typing import Any, Dict


def ast_to_fingerprint(parsed: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "imports": parsed.get("imports", []),
        "exports": parsed.get("exports", []),
        "functions": parsed.get("functions", []),
        "http_calls": parsed.get("http_calls", []),
        "metrics": {
            "cyclomatic_complexity": metrics.get("cyclomatic_complexity", 0),
            "cognitive_complexity": metrics.get("cognitive_complexity", 0),
            "max_nesting_depth": metrics.get("max_nesting_depth", 0),
            "method_count": metrics.get("method_count", 0),
            "api_coupling_count": metrics.get("api_coupling_count", 0),
        },
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return {"fingerprint": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "features": payload}
