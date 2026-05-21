import argparse
import os
from typing import Optional

from scanner import discover_source_files
from script_parser import parse_script_file
from metrics_extractor import compute_metrics
from storage import JsonStore
from ai_reporter import analyze_defects_for_files
from dependency_graph import build_dependency_graph
from ai_dependency_builder import infer_semantic_edges
from ai_architecture_analyzer import analyze_architecture
from mcp_index_builder import build_mcp_index


def _read_text(path: str, max_bytes: int = 2_000_000) -> str:
    # Keep reads robust: ignore encoding errors and cap size.
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        return data[:max_bytes] + "\n\n... [TRUNCATED]"
    return data


def run_pipeline(project_path: str, backend_reports_dir: str, max_workers: int = 4) -> None:
    project_path = os.path.abspath(project_path)
    store = JsonStore(backend_reports_dir=backend_reports_dir)

    # Stage 1 — discovery
    files, folders = discover_source_files(project_path)
    store.add_project(project_path=project_path, folders=folders)

    # Stage 2/3 — parse + metrics
    for path in files:
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        content = _read_text(path)

        parsed = parse_script_file(path=path, content=content, ext=ext)
        metrics = compute_metrics(path=path, content=content, parsed=parsed, ext=ext)

        store.upsert_file_record(path=path, ext=ext, content=content, parsed=parsed, metrics=metrics)

    store.export_tables()

    # Stage 5 — AI defect reporter (with gating)
    analyze_defects_for_files(
        store=store,
        backend_reports_dir=backend_reports_dir,
        max_workers=max_workers,
    )

    # Build static dependency graph, then (optionally) add semantic edges.
    dep_graph_static = build_dependency_graph(store=store)
    dep_graph = infer_semantic_edges(dep_graph_static, backend_reports_dir=backend_reports_dir)
    store.set_dependency_graph(dep_graph)
    store.export_tables()

    # Stage 6 — architecture auditor
    analyze_architecture(
        store=store,
        backend_reports_dir=backend_reports_dir,
    )
    store.export_tables()

    # Stage 7 — MCP index builder
    build_mcp_index(backend_reports_dir=backend_reports_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="PrismAI Code Analyzer — multi-stage static analysis pipeline")
    parser.add_argument("project_path", help="Path to the frontend codebase to scan")
    parser.add_argument(
        "--backend-reports-dir",
        default=os.path.join("backend", "json_reports"),
        help="Where to write JSON reports (default: backend/json_reports)",
    )
    parser.add_argument("--max-workers", type=int, default=4, help="Max parallel workers for AI batching")
    args = parser.parse_args()

    backend_reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", args.backend_reports_dir))
    run_pipeline(args.project_path, backend_reports_dir=backend_reports_dir, max_workers=args.max_workers)


if __name__ == "__main__":
    main()
