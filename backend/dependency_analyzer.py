#!/usr/bin/env python3
"""
Dependency Hierarchy Analyzer
Analyzes project files and creates a hierarchical dependency tree showing
which files depend on which other files.
"""

import os
import sys
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, List, Tuple

# Handle Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

class DependencyAnalyzer:
    def __init__(self, root_path: str, ignore_dirs: Set[str] = None):
        self.root_path = Path(root_path)
        self.ignore_dirs = ignore_dirs or {
            '__pycache__', '.git', 'node_modules', '.venv', 'venv',
            '.env', '.pytest_cache', '.vscode', 'dist', 'build'
        }
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.file_types = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java', '.cpp', '.c', '.rb'}

    def analyze(self):
        """Scan project and extract dependencies"""
        print("🔍 Analyzing project dependencies...\n")

        for file_path in self._get_files():
            self._extract_dependencies(file_path)

        return self.dependencies

    def _get_files(self) -> List[Path]:
        """Get all relevant files in project"""
        files = []
        for root, dirs, filenames in os.walk(self.root_path):
            # Remove ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]

            for filename in filenames:
                if any(filename.endswith(ext) for ext in self.file_types):
                    files.append(Path(root) / filename)

        return files

    def _extract_dependencies(self, file_path: Path):
        """Extract imports/dependencies from a file"""
        rel_path = self._get_relative_path(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            imports = self._get_imports(content, file_path.suffix)

            for imp in imports:
                dep_path = self._resolve_import(imp, file_path)
                if dep_path and dep_path != rel_path:
                    self.dependencies[rel_path].add(dep_path)

        except Exception as e:
            pass

    def _get_imports(self, content: str, file_ext: str) -> Set[str]:
        """Extract import statements based on file type"""
        imports = set()

        if file_ext == '.py':
            # Python imports
            patterns = [
                r'from\s+([\w.]+)\s+import',
                r'import\s+([\w.]+)',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    imports.add(match.split('.')[0])

        elif file_ext in {'.js', '.ts', '.jsx', '.tsx'}:
            # JavaScript/TypeScript imports
            patterns = [
                r'import\s+(?:\{[^}]*\}|[^"\'])+\s+from\s+["\']([^"\']+)["\']',
                r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content)
                imports.update(matches)

        elif file_ext in {'.go'}:
            # Go imports
            pattern = r'import\s+["\']([^"\']+)["\']'
            matches = re.findall(pattern, content)
            imports.update(matches)

        elif file_ext in {'.java'}:
            # Java imports
            pattern = r'import\s+([\w.]+);'
            matches = re.findall(pattern, content)
            imports.update(matches)

        return imports

    def _resolve_import(self, imp: str, from_file: Path) -> str:
        """Try to resolve import to actual file path"""
        from_dir = from_file.parent

        # Check various possible paths
        candidates = [
            from_dir / f"{imp}.py",
            from_dir / imp / "__init__.py",
            self.root_path / f"{imp}.py",
            self.root_path / imp / "__init__.py",
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(self._get_relative_path(candidate))

        return None

    def _get_relative_path(self, path: Path) -> str:
        """Get relative path from root"""
        return str(path.relative_to(self.root_path)).replace('\\', '/')

    def build_hierarchy(self) -> str:
        """Build and format hierarchical dependency tree"""
        # Find root files (no dependencies or minimal dependencies)
        all_deps = set()
        all_files = set(self.dependencies.keys())

        for deps in self.dependencies.values():
            all_deps.update(deps)

        root_files = all_files - all_deps

        # Build tree starting from roots
        tree_lines = ["📦 PROJECT DEPENDENCY HIERARCHY\n"]
        tree_lines.append("=" * 60)

        visited = set()
        for root in sorted(root_files):
            tree_lines.append("")
            self._add_tree_node(root, visited, "", tree_lines, is_root=True)

        # Add isolated files (no dependencies and not depended on)
        isolated = all_files - visited - root_files
        if isolated:
            tree_lines.append("\n📄 ISOLATED FILES (no dependencies):")
            for f in sorted(isolated):
                tree_lines.append(f"  └─ {f}")

        return "\n".join(tree_lines)

    def _add_tree_node(self, file_path: str, visited: Set[str], prefix: str,
                       lines: List[str], is_root: bool = False):
        """Recursively add nodes to tree"""
        if file_path in visited:
            return

        visited.add(file_path)

        if is_root:
            lines.append(f"📄 {file_path}")
            new_prefix = "  "
        else:
            connector = "├─" if file_path else "└─"
            lines.append(f"{prefix}{connector} {file_path}")
            new_prefix = prefix + ("│  " if file_path else "   ")

        deps = sorted(self.dependencies.get(file_path, set()))
        for i, dep in enumerate(deps):
            is_last = i == len(deps) - 1
            connector = "└─" if is_last else "├─"
            lines.append(f"{new_prefix}{connector} → {dep}")

            # Recursively add dependencies (limit depth to avoid clutter)
            if len(visited) < 100:
                sub_prefix = new_prefix + ("   " if is_last else "│  ")
                self._add_tree_node(dep, visited, sub_prefix, lines)


def main():
    project_path = os.getcwd()

    analyzer = DependencyAnalyzer(project_path)
    dependencies = analyzer.analyze()

    # Print hierarchy
    hierarchy = analyzer.build_hierarchy()
    print(hierarchy)

    # Print statistics
    print("\n" + "=" * 60)
    print("📊 STATISTICS")
    print("=" * 60)
    print(f"Total files analyzed: {len(dependencies)}")

    total_deps = sum(len(deps) for deps in dependencies.values())
    print(f"Total dependencies: {total_deps}")

    # Most depended files
    dep_count = defaultdict(int)
    for deps in dependencies.values():
        for dep in deps:
            dep_count[dep] += 1

    if dep_count:
        print(f"\n🔥 Most depended files:")
        for file, count in sorted(dep_count.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {file}: {count} dependencies")

    # Save to file
    output_file = Path(project_path) / "DEPENDENCY_REPORT.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(hierarchy)
        f.write(f"\n\n{'='*60}\n")
        f.write(f"Total files: {len(dependencies)}\n")
        f.write(f"Total dependencies: {total_deps}\n")

    print(f"\n✅ Report saved to: {output_file}")


if __name__ == "__main__":
    main()
