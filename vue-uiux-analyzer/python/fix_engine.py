"""
Fix Engine - Applies automatic fixes to detected issues.
"""

import os
from typing import Optional, Tuple
from rules.base_rule import ScanIssue, IssueFix


class FixEngine:
    """Applies fixes to source files based on detected issues."""

    @staticmethod
    def apply_fix(file_path: str, issue: dict) -> dict:
        """
        Apply a fix for a single issue.
        
        Args:
            file_path: Path to the file to fix
            issue: Issue dictionary containing fix information
            
        Returns:
            Result dictionary with success status and new content
        """
        fix = issue.get('fix')
        if not fix:
            return {
                'success': False,
                'error': 'No fix available for this issue',
                'issue_id': issue.get('id', '')
            }

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original = fix.get('original', '')
            replacement = fix.get('replacement', '')

            if not original:
                return {
                    'success': False,
                    'error': 'Fix has no original text to replace',
                    'issue_id': issue.get('id', '')
                }

            if original not in content:
                return {
                    'success': False,
                    'error': 'Original text not found in file (file may have changed)',
                    'issue_id': issue.get('id', '')
                }

            # Apply the replacement
            new_content = content.replace(original, replacement, 1)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return {
                'success': True,
                'issue_id': issue.get('id', ''),
                'description': fix.get('description', 'Fix applied'),
                'file': file_path
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'issue_id': issue.get('id', '')
            }

    @staticmethod
    def apply_all_fixes(file_path: str, issues: list) -> dict:
        """
        Apply all available fixes for a file.
        
        Fixes are applied in reverse line order to preserve positions.
        
        Args:
            file_path: Path to the file
            issues: List of issue dictionaries
            
        Returns:
            Result dictionary with counts
        """
        # Filter issues that have fixes
        fixable = [i for i in issues if i.get('fix') and i.get('file') == file_path]

        if not fixable:
            return {
                'success': True,
                'fixed': 0,
                'skipped': len(issues),
                'errors': []
            }

        # Sort by line number descending to preserve positions
        fixable.sort(key=lambda i: i.get('line', 0), reverse=True)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'fixed': 0,
                'skipped': len(fixable),
                'errors': [str(e)]
            }

        fixed_count = 0
        errors = []

        for issue in fixable:
            fix = issue['fix']
            original = fix.get('original', '')
            replacement = fix.get('replacement', '')

            if original and original in content:
                content = content.replace(original, replacement, 1)
                fixed_count += 1
            else:
                errors.append(f"Could not apply fix for {issue.get('rule_id', 'unknown')} at line {issue.get('line', '?')}")

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'fixed': 0,
                'skipped': len(fixable),
                'errors': [str(e)]
            }

        return {
            'success': True,
            'fixed': fixed_count,
            'skipped': len(fixable) - fixed_count,
            'errors': errors,
            'file': file_path
        }

    @staticmethod
    def preview_fix(content: str, issue: dict) -> Optional[str]:
        """
        Preview what the content would look like after applying a fix.
        
        Args:
            content: Current file content
            issue: Issue dictionary with fix
            
        Returns:
            Preview of fixed content, or None if fix can't be applied
        """
        fix = issue.get('fix')
        if not fix:
            return None

        original = fix.get('original', '')
        replacement = fix.get('replacement', '')

        if original and original in content:
            return content.replace(original, replacement, 1)
        return None
