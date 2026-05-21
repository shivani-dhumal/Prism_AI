"""
Rule Engine - Manages and executes all UI/UX analysis rules.
"""

from typing import List, Optional, Set
from rules.base_rule import BaseRule, ScanIssue
from rules import ALL_RULES


class RuleEngine:
    """Manages the collection of rules and runs them against file content."""

    def __init__(self, ignored_rules: Optional[Set[str]] = None, min_severity: str = 'low'):
        self.rules: List[BaseRule] = list(ALL_RULES)
        self.ignored_rules = ignored_rules or set()
        self.min_severity = min_severity
        self._severity_order = {'low': 0, 'medium': 1, 'high': 2}

    def get_active_rules(self) -> List[BaseRule]:
        """Get rules that are not ignored."""
        return [r for r in self.rules if r.id not in self.ignored_rules]

    def run(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        """
        Run all active rules against the given file content.
        
        Args:
            content: File content to analyze
            file_path: Path to the file
            **kwargs: Additional context
            
        Returns:
            List of detected issues
        """
        issues = []
        min_level = self._severity_order.get(self.min_severity, 0)

        for rule in self.get_active_rules():
            try:
                rule_issues = rule.detect(content, file_path, **kwargs)
                # Filter by minimum severity
                for issue in rule_issues:
                    issue_level = self._severity_order.get(issue.severity, 0)
                    if issue_level >= min_level:
                        issues.append(issue)
            except Exception as e:
                # Don't let one rule crash the entire analysis
                import sys
                print(f"Warning: Rule '{rule.id}' failed on {file_path}: {e}", file=sys.stderr)

        # Sort by severity (high first), then by line number
        issues.sort(key=lambda i: (-self._severity_order.get(i.severity, 0), i.line))
        return issues

    def get_rule_by_id(self, rule_id: str) -> Optional[BaseRule]:
        """Get a rule by its ID."""
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def get_rules_by_category(self, category: str) -> List[BaseRule]:
        """Get all rules in a category."""
        return [r for r in self.rules if r.category == category]

    def get_categories(self) -> List[str]:
        """Get all unique categories."""
        return list(set(r.category for r in self.rules))

    def get_rule_info(self) -> List[dict]:
        """Get info about all rules for display."""
        return [
            {
                'id': r.id,
                'name': r.name,
                'description': r.description,
                'severity': r.severity,
                'category': r.category,
                'enabled': r.id not in self.ignored_rules
            }
            for r in self.rules
        ]
