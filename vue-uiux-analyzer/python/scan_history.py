"""
Scan History - Stores and retrieves previous scan results.
"""

import os
import json
import time
from typing import List, Optional


class ScanHistory:
    """Manages scan history with local JSON storage."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = storage_dir
        else:
            home = os.path.expanduser('~')
            self.storage_dir = os.path.join(home, '.vue-uiux-analyzer', 'history')

        os.makedirs(self.storage_dir, exist_ok=True)
        self.history_file = os.path.join(self.storage_dir, 'history.json')
        self._history: List[dict] = []
        self._load()

    def _load(self):
        """Load history from disk."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self._history = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._history = []

    def _save(self):
        """Save history to disk."""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self._history, f, indent=2)
        except IOError:
            pass

    def add_entry(self, scan_result: dict):
        """
        Add a scan result to history.
        
        Args:
            scan_result: The scan result dictionary from ScannerEngine
        """
        summary = scan_result.get('summary', {})
        entry = {
            'id': f"scan_{int(time.time())}_{len(self._history)}",
            'timestamp': scan_result.get('timestamp', time.time()),
            'project_path': scan_result.get('project_path', ''),
            'total_issues': summary.get('total', 0),
            'high_count': summary.get('high', 0),
            'medium_count': summary.get('medium', 0),
            'low_count': summary.get('low', 0),
            'file_count': scan_result.get('file_count', 0),
            'scan_duration': scan_result.get('scan_duration', 0),
            'files_scanned': scan_result.get('files_scanned', [])
        }

        self._history.insert(0, entry)

        # Keep only last 50 entries
        if len(self._history) > 50:
            self._history = self._history[:50]

        self._save()

        # Also save the full scan result
        self._save_full_result(entry['id'], scan_result)

    def _save_full_result(self, scan_id: str, scan_result: dict):
        """Save the full scan result for later retrieval."""
        result_file = os.path.join(self.storage_dir, f'{scan_id}.json')
        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(scan_result, f, indent=2)
        except IOError:
            pass

    def get_history(self, limit: int = 20) -> List[dict]:
        """Get recent scan history entries."""
        return self._history[:limit]

    def get_full_result(self, scan_id: str) -> Optional[dict]:
        """Get the full scan result for a history entry."""
        result_file = os.path.join(self.storage_dir, f'{scan_id}.json')
        if os.path.exists(result_file):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
        return None

    def clear(self):
        """Clear all history."""
        self._history = []
        self._save()

        # Remove all result files
        for filename in os.listdir(self.storage_dir):
            if filename.startswith('scan_') and filename.endswith('.json'):
                try:
                    os.remove(os.path.join(self.storage_dir, filename))
                except OSError:
                    pass
