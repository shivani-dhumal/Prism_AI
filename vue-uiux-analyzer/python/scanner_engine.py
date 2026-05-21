"""
Scanner Engine - Orchestrates file discovery and analysis.
"""

import os
import time
import fnmatch
from typing import List, Dict, Set, Optional
from rule_engine import RuleEngine
from vue_parser import parse_vue_file, is_vue_file
from rules.base_rule import ScanIssue
from cache_manager import CacheManager


# File extensions to scan
SCANNABLE_EXTENSIONS = {
    '.vue', '.html', '.htm',
    '.css', '.scss', '.sass', '.less',
    '.js', '.ts', '.jsx', '.tsx'
}

# Default exclude patterns
DEFAULT_EXCLUDES = [
    'node_modules', 'dist', 'build', '.nuxt', '.output',
    '.git', '.vscode', '__pycache__', '.cache',
    'coverage', '.nyc_output', 'vendor'
]


class ScannerEngine:
    """Main scanner that orchestrates file discovery and rule execution."""

    def __init__(
        self,
        ignored_rules: Optional[Set[str]] = None,
        min_severity: str = 'low',
        exclude_patterns: Optional[List[str]] = None,
        max_file_size_kb: int = 500,
        cache_dir: Optional[str] = None
    ):
        self.rule_engine = RuleEngine(ignored_rules=ignored_rules, min_severity=min_severity)
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDES
        self.max_file_size_kb = max_file_size_kb
        self.cache_manager = CacheManager(cache_dir) if cache_dir else CacheManager()

    def discover_files(self, project_path: str) -> List[str]:
        """
        Discover all scannable files in a project directory.
        
        Args:
            project_path: Root directory to scan
            
        Returns:
            List of absolute file paths
        """
        files = []

        if os.path.isfile(project_path):
            ext = os.path.splitext(project_path)[1].lower()
            if ext in SCANNABLE_EXTENSIONS:
                return [os.path.abspath(project_path)]
            return []

        for root, dirs, filenames in os.walk(project_path):
            # Filter out excluded directories
            dirs[:] = [
                d for d in dirs
                if not any(
                    fnmatch.fnmatch(d, pat) or d == pat
                    for pat in self.exclude_patterns
                )
            ]

            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in SCANNABLE_EXTENSIONS:
                    filepath = os.path.join(root, filename)

                    # Check file size
                    try:
                        size_kb = os.path.getsize(filepath) / 1024
                        if size_kb <= self.max_file_size_kb:
                            files.append(os.path.abspath(filepath))
                    except OSError:
                        continue

        return sorted(files)

    def scan_file(self, file_path: str, force: bool = False) -> List[ScanIssue]:
        """
        Scan a single file for UI/UX issues.
        
        Args:
            file_path: Path to the file to scan
            force: If True, ignore cache and rescan
            
        Returns:
            List of detected issues
        """
        file_path = os.path.abspath(file_path)

        # Check cache
        if not force:
            cached = self.cache_manager.get_cached_result(file_path)
            if cached is not None:
                return cached

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except (IOError, OSError) as e:
            return []

        # Run rules on the content
        issues = self.rule_engine.run(content, file_path)

        # If it's a Vue file, also parse and analyze sections
        if is_vue_file(file_path):
            parsed = parse_vue_file(file_path, content)
            # Additional Vue-specific context could be passed here
            # Rules already handle .vue files in their detect methods

        # Cache the results
        self.cache_manager.cache_result(file_path, issues)

        return issues

    def scan_project(self, project_path: str, force: bool = False) -> Dict:
        """
        Scan an entire project directory.
        
        Args:
            project_path: Root directory to scan
            force: If True, ignore cache
            
        Returns:
            Scan result dictionary
        """
        start_time = time.time()
        project_path = os.path.abspath(project_path)

        # Discover files
        files = self.discover_files(project_path)

        all_issues: List[ScanIssue] = []
        files_scanned = []

        for file_path in files:
            issues = self.scan_file(file_path, force=force)
            all_issues.extend(issues)
            files_scanned.append(file_path)

        scan_duration = time.time() - start_time

        result = {
            'timestamp': time.time(),
            'project_path': project_path,
            'issues': [issue.to_dict() for issue in all_issues],
            'file_count': len(files_scanned),
            'scan_duration': round(scan_duration, 2),
            'files_scanned': files_scanned,
            'summary': {
                'total': len(all_issues),
                'high': sum(1 for i in all_issues if i.severity == 'high'),
                'medium': sum(1 for i in all_issues if i.severity == 'medium'),
                'low': sum(1 for i in all_issues if i.severity == 'low'),
                'by_category': self._group_by_category(all_issues),
                'by_file': self._group_by_file(all_issues)
            }
        }

        return result

    def _group_by_category(self, issues: List[ScanIssue]) -> Dict[str, int]:
        """Group issue counts by category."""
        groups: Dict[str, int] = {}
        for issue in issues:
            groups[issue.category] = groups.get(issue.category, 0) + 1
        return groups

    def _group_by_file(self, issues: List[ScanIssue]) -> Dict[str, int]:
        """Group issue counts by file."""
        groups: Dict[str, int] = {}
        for issue in issues:
            groups[issue.file] = groups.get(issue.file, 0) + 1
        return groups

    def get_rule_info(self) -> List[dict]:
        """Get information about all available rules."""
        return self.rule_engine.get_rule_info()
