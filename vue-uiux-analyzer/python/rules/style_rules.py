"""
Style Rules - Detects inline style overuse and font inconsistencies.
"""

import re
from typing import List, Set
from .base_rule import BaseRule, ScanIssue, IssueFix


class InlineStyleOveruseRule(BaseRule):
    """Detects excessive use of inline styles."""

    def __init__(self):
        super().__init__()
        self._id = 'inline-style-overuse'
        self._name = 'Inline Style Overuse'
        self._description = 'Inline styles reduce maintainability and override CSS specificity. Use classes instead.'
        self._severity = 'medium'
        self._category = 'style'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Count inline styles in the content
        inline_style_pattern = re.compile(
            r'<[a-z][\w-]*\b[^>]*\bstyle\s*=\s*["\']([^"\']+)["\']',
            re.IGNORECASE | re.DOTALL
        )

        matches = list(inline_style_pattern.finditer(content))

        # If more than 3 inline styles, flag all of them
        threshold = 3
        if len(matches) > threshold:
            for match in matches:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())
                style_value = match.group(1)

                # Suggest extracting to a CSS class
                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Inline style detected ({len(matches)} total inline styles in file)',
                    description=f'Found style="{style_value[:50]}{"..." if len(style_value) > 50 else ""}". '
                                f'Extract inline styles to CSS classes for better maintainability.',
                ))
        elif matches:
            # If just a few, flag only those with complex styles (multiple properties)
            for match in matches:
                style_value = match.group(1)
                prop_count = len([p for p in style_value.split(';') if p.strip()])
                if prop_count >= 3:
                    line, col = self._find_line_col(content, match.start())
                    end_line, end_col = self._find_line_col(content, match.end())

                    issues.append(self.create_issue(
                        file_path=file_path,
                        line=line,
                        column=col,
                        end_line=end_line,
                        end_column=end_col,
                        message=f'Complex inline style with {prop_count} properties',
                        description=f'Inline styles with multiple properties should be extracted to a CSS class.',
                        severity='low'
                    ))

        # Also check Vue :style bindings with hardcoded values
        vue_style_pattern = re.compile(
            r':style\s*=\s*["\']?\{([^}]+)\}',
            re.IGNORECASE
        )
        for match in vue_style_pattern.finditer(content):
            style_obj = match.group(1)
            prop_count = len([p for p in style_obj.split(',') if p.strip()])
            if prop_count >= 3:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Complex :style binding with {prop_count} properties',
                    description='Consider using CSS classes with dynamic class binding (:class) instead of inline :style.',
                    severity='low'
                ))

        return issues


class FontInconsistencyRule(BaseRule):
    """Detects too many different font families used in styles."""

    def __init__(self):
        super().__init__()
        self._id = 'font-inconsistency'
        self._name = 'Font Inconsistency'
        self._description = 'Using too many different font families creates visual inconsistency.'
        self._severity = 'low'
        self._category = 'style'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Find all font-family declarations
        font_pattern = re.compile(
            r'font-family\s*:\s*([^;}\n]+)',
            re.IGNORECASE
        )

        fonts_found: Set[str] = set()
        font_locations = []

        for match in font_pattern.finditer(content):
            font_value = match.group(1).strip().strip('"\'')
            # Normalize: take the primary font family
            primary_font = font_value.split(',')[0].strip().strip('"\'').lower()
            fonts_found.add(primary_font)
            font_locations.append({
                'font': primary_font,
                'match': match
            })

        # Flag if more than 3 different font families
        max_fonts = 3
        if len(fonts_found) > max_fonts:
            for loc in font_locations:
                line, col = self._find_line_col(content, loc['match'].start())
                end_line, end_col = self._find_line_col(content, loc['match'].end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'{len(fonts_found)} different font families used (max recommended: {max_fonts})',
                    description=f'Font "{loc["font"]}" is one of {len(fonts_found)} different fonts. '
                                f'Standardize on 2-3 font families for visual consistency.',
                ))

        return issues
