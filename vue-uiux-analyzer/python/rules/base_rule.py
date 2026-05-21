"""
Base Rule - Abstract base class for all UI/UX analysis rules.
"""

import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class IssueFix:
    """Represents an automatic fix for a detected issue."""
    description: str
    original: str
    replacement: str
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass
class ScanIssue:
    """Represents a single detected UI/UX issue."""
    rule_id: str
    severity: str  # 'low', 'medium', 'high'
    category: str
    message: str
    description: str
    file: str
    line: int
    column: int
    end_line: int
    end_column: int
    fix: Optional[IssueFix] = None
    ignored: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        if self.fix is None:
            result['fix'] = None
        return result


class BaseRule(ABC):
    """
    Abstract base class for all UI/UX analysis rules.
    
    Every rule must implement:
      - detect(): Find issues in the given content
      - Each rule should also provide fix suggestions where possible
    """

    def __init__(self):
        self._id: str = ''
        self._name: str = ''
        self._description: str = ''
        self._severity: str = 'medium'
        self._category: str = 'general'

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def severity(self) -> str:
        return self._severity

    @property
    def category(self) -> str:
        return self._category

    @abstractmethod
    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        """
        Detect issues in the given content.
        
        Args:
            content: The file content to analyze
            file_path: Path to the file being analyzed
            **kwargs: Additional context (e.g., parsed Vue sections)
            
        Returns:
            List of detected ScanIssue objects
        """
        pass

    def create_issue(
        self,
        file_path: str,
        line: int,
        column: int,
        end_line: int,
        end_column: int,
        message: str = '',
        description: str = '',
        fix: Optional[IssueFix] = None,
        severity: Optional[str] = None
    ) -> ScanIssue:
        """Helper to create a ScanIssue with this rule's metadata."""
        return ScanIssue(
            rule_id=self._id,
            severity=severity or self._severity,
            category=self._category,
            message=message or self._name,
            description=description or self._description,
            file=file_path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
            fix=fix
        )

    def _find_line_col(self, content: str, pos: int):
        """Convert a string position to line and column numbers (1-indexed)."""
        lines = content[:pos].split('\n')
        line = len(lines)
        col = len(lines[-1]) + 1 if lines else 1
        return line, col

    def _get_line_end_col(self, content: str, line_num: int) -> int:
        """Get the end column of a specific line (1-indexed)."""
        lines = content.split('\n')
        if 1 <= line_num <= len(lines):
            return len(lines[line_num - 1]) + 1
        return 1
