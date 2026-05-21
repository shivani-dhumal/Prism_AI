import re
from typing import Any, Dict, List


def find_http_calls(code: str) -> List[Dict[str, Any]]:
    """
    Small helper used by Stage 2/metrics.
    Extracts HTTP-ish calls in a best-effort way.
    """
    calls: List[Dict[str, Any]] = []

    for m in re.finditer(r"fetch\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*(\{|\[))?", code):
        url = m.group(1)
        has_payload = bool(m.group(2))
        calls.append({"method": "fetch", "url": url, "has_payload": has_payload})

    for m in re.finditer(r"axios\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", code):
        calls.append({"method": m.group(1).upper(), "url": m.group(2), "has_payload": False})

    for m in re.finditer(
        r"axios\(\s*{[^}]*method\s*:\s*['\"](GET|POST|PUT|DELETE|PATCH)['\"][^}]*url\s*:\s*['\"]([^'\"]+)['\"]",
        code,
        re.DOTALL,
    ):
        calls.append({"method": m.group(1), "url": m.group(2), "has_payload": True})

    return calls

import re
from typing import Any, Dict, List


def find_api_patterns(content: str) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    text = content or ""

    for match in re.finditer(r"fetch\(\s*['\"]([^'\"]+)['\"]", text):
        patterns.append({"method": "fetch", "url": match.group(1), "offset": match.start()})

    for match in re.finditer(r"\baxios\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", text):
        patterns.append({"method": match.group(1).upper(), "url": match.group(2), "offset": match.start()})

    return patterns
