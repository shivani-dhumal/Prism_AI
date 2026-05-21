import argparse
import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_index_builder import build_mcp_index


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_REPORTS_DIR = os.path.join(ROOT, "backend", "json_reports")
DEFAULT_INDEX_PATH = os.path.join(ROOT, "backend", "mcp_index", "index.json")
load_dotenv(os.path.join(ROOT, ".env"), override=False)

mcp = FastMCP("PrismAI Code Analyzer", stateless_http=True, json_response=True)
_INDEX: Dict[str, Any] | None = None
_REPORTS_DIR = DEFAULT_REPORTS_DIR
_INDEX_PATH = DEFAULT_INDEX_PATH


def _index() -> Dict[str, Any]:
    global _INDEX
    if _INDEX is None:
        path = _INDEX_PATH
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _INDEX = json.load(f)
        else:
            _INDEX = build_mcp_index(_REPORTS_DIR)
    return _INDEX


@mcp.tool()
def get_file_metrics(file_path: str) -> Dict[str, Any]:
    """Return metrics for a scanned file path."""
    idx = _index()
    return ((idx.get("files_by_path") or {}).get(file_path) or {}).get("metrics", {}) or {}


@mcp.tool()
def list_defects(file_path: str = "") -> Any:
    """Return defects for one file, or all defects when file_path is empty."""
    defects = _index().get("defects_by_file", {})
    if file_path:
        return defects.get(file_path, {})
    return defects


@mcp.tool()
def get_dependencies(file_path: str) -> Dict[str, Any]:
    """Return incoming and outgoing dependency edges for a file."""
    idx = _index()
    dep_graph = idx.get("dependency_graph") or {}
    connections = dep_graph.get("connections", []) or []
    outgoing: List[Dict[str, Any]] = [c for c in connections if c.get("from") == file_path]
    incoming: List[Dict[str, Any]] = [c for c in connections if c.get("to") == file_path]
    return {"from": file_path, "outgoing": outgoing, "incoming": incoming}


@mcp.tool()
def architecture_summary() -> Dict[str, Any]:
    """Return the architecture audit report."""
    return _index().get("ai_architecture", {}) or {}


def main() -> None:
    global _REPORTS_DIR, _INDEX_PATH
    parser = argparse.ArgumentParser(description="PrismAI MCP server")
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--http", action="store_true", help="Run HTTP transport instead of stdio")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_SERVER_PORT", "8892")))
    args = parser.parse_args()

    _REPORTS_DIR = os.path.abspath(args.reports_dir)
    _INDEX_PATH = os.path.join(os.path.abspath(os.path.join(_REPORTS_DIR, "..")), "mcp_index", "index.json")
    if args.http:
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
