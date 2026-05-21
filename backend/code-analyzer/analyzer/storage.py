import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


@dataclass
class FileRecord:
    id: str
    path: str
    ext: str
    parsed: Dict[str, Any]
    metrics: Dict[str, Any]
    content: str

    def export_json(self) -> Dict[str, Any]:
        # Keep exports lightweight; avoid dumping full source.
        return {
            "id": self.id,
            "path": self.path,
            "ext": self.ext,
            "parsed": self.parsed,
            "metrics": self.metrics,
            "content_truncated": self.content[:25_000],
        }


class JsonStore:
    """
    Stage 4 — in-memory dict-based store + JSON export.
    """

    def __init__(self, backend_reports_dir: str):
        self.backend_reports_dir = backend_reports_dir
        os.makedirs(self.backend_reports_dir, exist_ok=True)

        self.tables: Dict[str, Any] = {
            "projects": [],
            "folders": [],
            "files": [],
            "api_calls": [],
            "dependency_graph": None,
            "ai_report": None,
            "ai_architecture": None,
        }

        self._files_by_path: Dict[str, FileRecord] = {}

    def add_project(self, project_path: str, folders: List[str]) -> None:
        project_id = _stable_id(project_path)
        self.tables["projects"] = [{"id": project_id, "path": project_path}]

        # Store folders for debugging and potential UI display.
        unique_folders = sorted(set(folders))
        self.tables["folders"] = [{"path": f, "id": _stable_id(f)} for f in unique_folders]

    def upsert_file_record(self, path: str, ext: str, content: str, parsed: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        file_id = _stable_id(path)
        rec = FileRecord(
            id=file_id,
            path=path,
            ext=ext,
            parsed=parsed,
            metrics=metrics,
            content=content,
        )
        self._files_by_path[path] = rec

        # Update api_calls table each time to stay consistent with parsed/http_calls.
        http_calls = parsed.get("http_calls", []) or []
        for c in http_calls:
            self.tables["api_calls"].append(
                {
                    "id": _stable_id(path + "|" + json.dumps(c, sort_keys=True)),
                    "file_path": path,
                    "method": c.get("method"),
                    "url": c.get("url"),
                    "has_payload": c.get("has_payload", False),
                }
            )

    @property
    def files(self) -> List[FileRecord]:
        return list(self._files_by_path.values())

    def iter_files(self) -> Iterable[FileRecord]:
        return self.files

    def set_dependency_graph(self, dep_graph: Dict[str, Any]) -> None:
        self.tables["dependency_graph"] = dep_graph

    def set_ai_report(self, ai_report: Dict[str, Any]) -> None:
        self.tables["ai_report"] = ai_report

    def set_ai_architecture(self, ai_architecture: Dict[str, Any]) -> None:
        self.tables["ai_architecture"] = ai_architecture

    def consistency_check(self) -> List[str]:
        issues: List[str] = []
        file_paths = set(self._files_by_path.keys())

        # api_calls should reference known files.
        for call in self.tables.get("api_calls", []) or []:
            if call.get("file_path") not in file_paths:
                issues.append(f"Orphan api_call for file_path={call.get('file_path')}")

        return issues

    def export_tables(self) -> None:
        # Keep api_calls stable: rebuild from current parsed data rather than appending duplicates.
        self.tables["api_calls"] = []
        for rec in self._files_by_path.values():
            parsed = rec.parsed or {}
            http_calls = parsed.get("http_calls", []) or []
            for c in http_calls:
                self.tables["api_calls"].append(
                    {
                        "id": _stable_id(rec.path + "|" + json.dumps(c, sort_keys=True)),
                        "file_path": rec.path,
                        "method": c.get("method"),
                        "url": c.get("url"),
                        "has_payload": c.get("has_payload", False),
                    }
                )

        self.tables["files"] = [rec.export_json() for rec in self._files_by_path.values()]

        problems = self.consistency_check()
        if problems:
            self.tables["consistency_issues"] = problems

        def _write(name: str, obj: Any) -> None:
            with open(os.path.join(self.backend_reports_dir, name), "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, default=str)

        _write("projects.json", self.tables["projects"])
        _write("folders.json", self.tables["folders"])
        _write("files.json", self.tables["files"])
        _write("api_calls.json", self.tables["api_calls"])

        if self.tables.get("dependency_graph") is not None:
            _write("dependency_graph.json", self.tables["dependency_graph"])

        if self.tables.get("ai_report") is not None:
            _write("ai_report.json", self.tables["ai_report"])

        if self.tables.get("ai_architecture") is not None:
            _write("ai_architecture.json", self.tables["ai_architecture"])

