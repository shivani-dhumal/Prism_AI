"""
Responsive Rules - Detects non-responsive layouts and missing viewport meta.
"""

import re
from typing import List
from .base_rule import BaseRule, ScanIssue, IssueFix


class NonResponsiveLayoutRule(BaseRule):
    """Detects fixed-width layouts that break responsiveness."""

    def __init__(self):
        super().__init__()
        self._id = 'non-responsive-layout'
        self._name = 'Non-Responsive Layout'
        self._description = 'Fixed pixel widths on containers can break responsive design. Use relative units or max-width.'
        self._severity = 'medium'
        self._category = 'responsive'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Detect large fixed widths in CSS (> 500px on width property)
        width_pattern = re.compile(
            r'(?<!\bmax-)(?<!\bmin-)width\s*:\s*(\d+)px',
            re.IGNORECASE
        )

        for match in width_pattern.finditer(content):
            px_value = int(match.group(1))
            if px_value > 500:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                original = match.group(0)
                replacement = f'max-width: {px_value}px; width: 100%'

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Fixed width of {px_value}px may break on smaller screens',
                    description=f'width: {px_value}px creates a rigid layout. Use max-width instead to allow responsive shrinking.',
                    fix=IssueFix(
                        description='Replace with max-width and width: 100%',
                        original=original,
                        replacement=replacement,
                        line=line, column=col,
                        end_line=end_line, end_column=end_col
                    )
                ))

        # Detect inline width attributes with large values
        attr_width_pattern = re.compile(
            r'width\s*=\s*["\'](\d+)["\']',
            re.IGNORECASE
        )
        for match in attr_width_pattern.finditer(content):
            px_value = int(match.group(1))
            if px_value > 500:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'HTML width attribute of {px_value} may not be responsive',
                    description='Use CSS with relative units instead of HTML width attributes for responsive design.',
                    severity='low'
                ))

        # Detect position: absolute/fixed without responsive considerations
        position_pattern = re.compile(
            r'position\s*:\s*(absolute|fixed)\s*;[^}]*(?:left|right|top|bottom)\s*:\s*(\d+)px',
            re.IGNORECASE | re.DOTALL
        )
        for match in position_pattern.finditer(content):
            px_value = int(match.group(2))
            if px_value > 300:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Large fixed position offset ({px_value}px) may break responsiveness',
                    description='Fixed/absolute positioning with large pixel offsets can cause layout issues on different screen sizes.',
                    severity='low'
                ))

        return issues


class MissingViewportRule(BaseRule):
    """Detects HTML files missing the responsive viewport meta tag."""

    def __init__(self):
        super().__init__()
        self._id = 'missing-viewport'
        self._name = 'Missing Viewport Meta Tag'
        self._description = 'HTML documents should include a viewport meta tag for responsive design.'
        self._severity = 'high'
        self._category = 'responsive'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Only check HTML files (not Vue component templates)
        if not file_path.lower().endswith(('.html', '.htm')):
            return issues

        # Check for <head> section
        head_match = re.search(r'<head\b[^>]*>', content, re.IGNORECASE)
        if not head_match:
            return issues

        # Check for viewport meta tag
        viewport_pattern = re.compile(
            r'<meta\b[^>]*name\s*=\s*["\']viewport["\'][^>]*>',
            re.IGNORECASE
        )

        if not viewport_pattern.search(content):
            line, col = self._find_line_col(content, head_match.end())
            end_line = line
            end_col = col

            viewport_tag = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'

            issues.append(self.create_issue(
                file_path=file_path,
                line=line,
                column=col,
                end_line=end_line,
                end_column=end_col,
                message='Missing viewport meta tag',
                description='Add a viewport meta tag to enable responsive design on mobile devices.',
                fix=IssueFix(
                    description='Add viewport meta tag after <head>',
                    original=head_match.group(0),
                    replacement=head_match.group(0) + '\n  ' + viewport_tag,
                    line=line - 1, column=1,
                    end_line=line, end_column=end_col
                )
            ))

        return issues
