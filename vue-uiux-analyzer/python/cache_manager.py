"""
Cache Manager - Caches scan results for performance with file-hash-based invalidation.
"""

import os
import json
import hashlib
from typing import List, Optional, Dict
from rules.base_rule import ScanIssue


class CacheManager:
    """Manages scan result caching using content hashes for invalidation."""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            # Default cache directory in user's home
            home = os.path.expanduser('~')
            self.cache_dir = os.path.join(home, '.vue-uiux-analyzer', 'cache')

        os.makedirs(self.cache_dir, exist_ok=True)
        self._cache: Dict[str, dict] = {}
        self._load_index()

    def _load_index(self):
        """Load the cache index from disk."""
        index_path = os.path.join(self.cache_dir, 'index.json')
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {}

    def _save_index(self):
        """Save the cache index to disk."""
        index_path = os.path.join(self.cache_dir, 'index.json')
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2)
        except IOError:
            pass

    @staticmethod
    def _file_hash(file_path: str) -> Optional[str]:
        """Calculate MD5 hash of a file's content."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except (IOError, OSError):
            return None

    @staticmethod
    def _content_hash(content: str) -> str:
        """Calculate MD5 hash of content string."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def get_cached_result(self, file_path: str) -> Optional[List[ScanIssue]]:
        """
        Get cached scan results for a file if the file hasn't changed.
        
        Args:
            file_path: Absolute path to the file
            
        Returns:
            List of cached ScanIssue objects, or None if cache miss
        """
        file_path = os.path.abspath(file_path)
        entry = self._cache.get(file_path)

        if not entry:
            return None

        # Check if file has been modified
        current_hash = self._file_hash(file_path)
        if current_hash != entry.get('hash'):
            # File has changed, invalidate cache
            del self._cache[file_path]
            self._save_index()
            return None

        # Reconstruct ScanIssue objects from cached data
        try:
            issues = []
            for issue_data in entry.get('issues', []):
                from rules.base_rule import IssueFix
                fix_data = issue_data.get('fix')
                fix = None
                if fix_data:
                    fix = IssueFix(**fix_data)

                issue = ScanIssue(
                    id=issue_data.get('id', ''),
                    rule_id=issue_data.get('rule_id', ''),
                    severity=issue_data.get('severity', 'medium'),
                    category=issue_data.get('category', ''),
                    message=issue_data.get('message', ''),
                    description=issue_data.get('description', ''),
                    file=issue_data.get('file', file_path),
                    line=issue_data.get('line', 0),
                    column=issue_data.get('column', 0),
                    end_line=issue_data.get('end_line', 0),
                    end_column=issue_data.get('end_column', 0),
                    fix=fix,
                    ignored=issue_data.get('ignored', False)
                )
                issues.append(issue)
            return issues
        except Exception:
            return None

    def cache_result(self, file_path: str, issues: List[ScanIssue]):
        """
        Cache scan results for a file.
        
        Args:
            file_path: Absolute path to the file
            issues: List of ScanIssue objects to cache
        """
        file_path = os.path.abspath(file_path)
        file_hash = self._file_hash(file_path)

        if file_hash is None:
            return

        self._cache[file_path] = {
            'hash': file_hash,
            'issues': [issue.to_dict() for issue in issues]
        }
        self._save_index()

    def invalidate(self, file_path: str):
        """Remove cached results for a specific file."""
        file_path = os.path.abspath(file_path)
        if file_path in self._cache:
            del self._cache[file_path]
            self._save_index()

    def clear(self):
        """Clear all cached results."""
        self._cache = {}
        self._save_index()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            'entries': len(self._cache),
            'cache_dir': self.cache_dir
        }
