import os
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from ai_reporter import _analyze_one
from metrics_extractor import compute_metrics
from script_parser import parse_script_file
from storage import FileRecord, _stable_id


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"), override=False)

app = Flask(__name__)


@app.post("/analyze")
def analyze_file():
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    file_path = body.get("file_path") or "inline.js"
    content = body.get("content") or ""
    ext = os.path.splitext(file_path)[1].lstrip(".").lower() or "js"

    parsed = parse_script_file(path=file_path, content=content, ext=ext)
    metrics = compute_metrics(path=file_path, content=content, parsed=parsed, ext=ext)
    rec = FileRecord(
        id=_stable_id(file_path),
        path=file_path,
        ext=ext,
        parsed=parsed,
        metrics=metrics,
        content=content,
    )

    defects = _analyze_one(rec)
    return jsonify({"file_path": file_path, "parsed": parsed, "metrics": metrics, "ai_report": defects})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "PrismAI Code Analyzer"})


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "7891"))
    app.run(host="0.0.0.0", port=port)
