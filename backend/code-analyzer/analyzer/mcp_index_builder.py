import json
import os
from typing import Any, Dict


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_mcp_index(backend_reports_dir: str) -> Dict[str, Any]:
    """
    Stage 7 — build a queryable index from JSON reports.
    Output path (expected by mcp_server.py): code-analyzer/backend/mcp_index/index.json
    """
    files_json = _read_json(os.path.join(backend_reports_dir, "files.json"), default=[])
    dep_graph = _read_json(os.path.join(backend_reports_dir, "dependency_graph.json"), default={})
    ai_report = _read_json(os.path.join(backend_reports_dir, "ai_report.json"), default={"files": []})
    ai_arch = _read_json(os.path.join(backend_reports_dir, "ai_architecture.json"), default={})
    projects = _read_json(os.path.join(backend_reports_dir, "projects.json"), default=[])

    defects_by_file: Dict[str, Any] = {}
    for row in (ai_report.get("files", []) or []):
        fp = row.get("file_path")
        if fp:
            defects_by_file[fp] = row

    files_by_path: Dict[str, Any] = {}
    for f in (files_json or []):
        fp = f.get("path")
        if fp:
            files_by_path[fp] = f

    index = {
        "projects": projects,
        "files_by_path": files_by_path,
        "defects_by_file": defects_by_file,
        "dependency_graph": dep_graph,
        "ai_architecture": ai_arch,
    }

    backend_dir = os.path.abspath(os.path.join(backend_reports_dir, ".."))
    out_dir = os.path.join(backend_dir, "mcp_index")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, default=str)

    return index
