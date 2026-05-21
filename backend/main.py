import argparse
import importlib.util
import io
import os
import sys
from typing import Optional


# Fix Windows console encoding (cp1252 can't handle Unicode chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


ROOT = os.path.dirname(os.path.abspath(__file__))
PRISMA_ANALYZER_DIR = os.path.join(ROOT, "code-analyzer", "analyzer")
if PRISMA_ANALYZER_DIR not in sys.path:
    sys.path.insert(0, PRISMA_ANALYZER_DIR)


def _load_prism_run_pipeline():
    analyzer_main_path = os.path.join(PRISMA_ANALYZER_DIR, "main.py")
    spec = importlib.util.spec_from_file_location("prisma_analyzer_main", analyzer_main_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load PrismAI analyzer module from {analyzer_main_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_pipeline = getattr(module, "run_pipeline", None)
    if run_pipeline is None:
        raise RuntimeError("PrismAI analyzer main.py does not expose run_pipeline()")
    return run_pipeline


def run_scan(target_directory: str, scan_id: Optional[int] = None, progress_fn=None) -> None:
    """
    Existing-project entrypoint: runs file discovery pipeline then Ollama bug detection.
    Keeps the legacy signature used by app.py.
    """

    def update(stage: str, pct: int, msg: str = "") -> None:
        print(f"  [{pct:3d}%] {stage}" + (f" - {msg}" if msg else ""))
        if progress_fn:
            progress_fn(scan_id, stage, pct, msg)

    # ── Stage 1: File discovery + storage (PrismAI pipeline) ──
    backend_reports_dir = os.path.join(ROOT, "code-analyzer", "backend", "json_reports")
    os.makedirs(backend_reports_dir, exist_ok=True)

    update("FILE_DISCOVERY", 5, "Scanning directory structure")
    update("FILE_DISCOVERY", 10, "Storing files in database")

    try:
        prism_run_pipeline = _load_prism_run_pipeline()
        prism_run_pipeline(
            project_path=target_directory,
            backend_reports_dir=backend_reports_dir,
            max_workers=4,
        )
        update("FILE_DISCOVERY", 40, "File discovery complete")
    except Exception as e:
        print(f"[WARN] PrismAI pipeline error (continuing to bug detection): {e}")
        update("FILE_DISCOVERY", 40, f"File discovery partial: {str(e)[:60]}")

    # ── Stage 2: Ollama AI Bug Detection ──
    update("AI_ANALYSIS", 45, "Starting Ollama AI bug detection")
    try:
        from scanners.ollama_bug_detector import run_bug_detection
        total_bugs = run_bug_detection(
            target_directory,
            lambda pct, msg: update("AI_ANALYSIS", 45 + int(pct * 0.5), msg),
        )
        update("AI_ANALYSIS", 95, f"Bug detection complete — {total_bugs} issues found")
    except Exception as e:
        print(f"[WARN] Ollama bug detection error: {e}")
        update("AI_ANALYSIS", 95, f"Bug detection error: {str(e)[:80]}")

    update("COMPLETED", 100, "Scan complete")
    print("\n[OK] PrismAI + Ollama scan complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PrismAI pipeline using existing project entrypoint")
    parser.add_argument("target_directory", nargs="?", help="Path to scan. Falls back to config TARGET_DIRECTORY.")
    args = parser.parse_args()

    target = args.target_directory
    if not target:
        from config import TARGET_DIRECTORY

        target = TARGET_DIRECTORY

    print(f"Target: {target}")
    run_scan(target)


if __name__ == "__main__":
    main()