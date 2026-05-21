import os
from typing import Any, Dict, List, Optional


_RESOLVE_EXTS = [".vue", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]


def _normalize_rel_path(base_file: str, spec: str) -> Optional[str]:
    # Only resolve relative imports. Bare module specifiers are ignored.
    if not spec.startswith("."):
        return None

    base_dir = os.path.dirname(base_file)
    target = os.path.normpath(os.path.join(base_dir, spec))

    # Direct file match with extensions
    if os.path.splitext(target)[1]:
        if os.path.exists(target):
            return target

    for ext in _RESOLVE_EXTS:
        cand = target + ext
        if os.path.exists(cand):
            return cand

    # Index file resolution for directories
    for ext in _RESOLVE_EXTS:
        cand = os.path.join(target, "index" + ext)
        if os.path.exists(cand):
            return cand

    return None


def build_dependency_graph(store: Any) -> Dict[str, Any]:
    """
    Stage (supporting) — build a static import-based graph.
    Nodes = files; directed edges = import relationships.
    """
    file_paths = [rec.path for rec in store.iter_files()]
    file_set = set(file_paths)

    file_map: Dict[str, str] = {p: p for p in file_paths}
    connections: List[Dict[str, Any]] = []

    # Build edges
    for rec in store.iter_files():
        from_path = rec.path
        imports = rec.parsed.get("imports", []) if rec.parsed else []
        for spec in imports or []:
            resolved = _normalize_rel_path(from_path, spec)
            if not resolved:
                continue
            if resolved not in file_set:
                continue
            connections.append(
                {
                    "from": from_path,
                    "to": resolved,
                    "import_specifier": spec,
                }
            )

    return {"file_map": file_map, "connections": connections}

