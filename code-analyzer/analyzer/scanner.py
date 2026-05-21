import os
from typing import List, Tuple


IGNORED_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".next",
    "out",
}

SOURCE_EXTS = {
    ".vue",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".scss",
}


def discover_source_files(project_path: str) -> Tuple[List[str], List[str]]:
    """
    Stage 1 — discover candidate files to parse/analyze.
    Returns: (files, folders)
    """
    files: List[str] = []
    folders: List[str] = []

    for root, dirs, filenames in os.walk(project_path):
        # In-place prune for speed
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        if root not in folders:
            folders.append(root)

        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in SOURCE_EXTS:
                files.append(os.path.join(root, name))

    return files, folders

