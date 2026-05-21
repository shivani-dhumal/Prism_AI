"""
Clickable Area Rules - Detects small clickable targets that fail accessibility guidelines.
"""

import re
from typing import List
from .base_rule import BaseRule, ScanIssue, IssueFix


class SmallClickableAreaRule(BaseRule):
    """Detects clickable elements with potentially small touch targets."""

    def __init__(self):
        super().__init__()
        self._id = 'small-clickable-area'
        self._name = 'Small Clickable Area'
        self._description = 'Interactive elements should have a minimum touch target size of 44x44px (WCAG 2.5.5).'
        self._severity = 'medium'
        self._category = 'accessibility'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Check for icon-only buttons/links with small dimensions in CSS
        # Look for clickable elements (a, button) with small explicit sizes
        small_size_pattern = re.compile(
            r'(?:(?:width|height)\s*:\s*(\d+)px)',
            re.IGNORECASE
        )

        # Check CSS blocks for interactive element styling
        block_pattern = re.compile(
            r'([^{}]+)\{([^{}]+)\}',
            re.DOTALL
        )

        interactive_selectors = ['button', 'a', '.btn', '.link', '[role="button"]',
                                  'input[type="submit"]', 'input[type="button"]',
                                  '.clickable', '.icon-btn', '.icon-button']

        for block_match in block_pattern.finditer(content):
            selector = block_match.group(1).strip().lower()
            properties = block_match.group(2)

            # Check if selector targets interactive elements
            is_interactive = any(s in selector for s in interactive_selectors)
            if not is_interactive:
                continue

            # Check for small width or height
            width_match = re.search(r'width\s*:\s*(\d+)px', properties, re.IGNORECASE)
            height_match = re.search(r'height\s*:\s*(\d+)px', properties, re.IGNORECASE)

            if width_match:
                width = int(width_match.group(1))
                if width < 44:
                    line, col = self._find_line_col(content, width_match.start() + block_match.start() + len(block_match.group(1)) + 1)
                    end_line, end_col = self._find_line_col(content, width_match.end() + block_match.start() + len(block_match.group(1)) + 1)

                    original = width_match.group(0)
                    replacement = f'width: 44px'

                    issues.append(self.create_issue(
                        file_path=file_path,
                        line=line,
                        column=col,
                        end_line=end_line,
                        end_column=end_col,
                        message=f'Clickable element width ({width}px) is below 44px minimum',
                        description=f'The selector "{selector.strip()}" has width: {width}px. '
                                    f'WCAG 2.5.5 recommends a minimum target size of 44x44px for touch accessibility.',
                        fix=IssueFix(
                            description='Set minimum width to 44px',
                            original=original,
                            replacement=replacement,
                            line=line, column=col,
                            end_line=end_line, end_column=end_col
                        )
                    ))

            if height_match:
                height = int(height_match.group(1))
                if height < 44:
                    line, col = self._find_line_col(content, height_match.start() + block_match.start() + len(block_match.group(1)) + 1)
                    end_line, end_col = self._find_line_col(content, height_match.end() + block_match.start() + len(block_match.group(1)) + 1)

                    original = height_match.group(0)
                    replacement = f'height: 44px'

                    issues.append(self.create_issue(
                        file_path=file_path,
                        line=line,
                        column=col,
                        end_line=end_line,
                        end_column=end_col,
                        message=f'Clickable element height ({height}px) is below 44px minimum',
                        description=f'The selector "{selector.strip()}" has height: {height}px. '
                                    f'Minimum touch target height should be 44px.',
                        fix=IssueFix(
                            description='Set minimum height to 44px',
                            original=original,
                            replacement=replacement,
                            line=line, column=col,
                            end_line=end_line, end_column=end_col
                        )
                    ))

        # Check for inline-style small clickable elements in HTML
        inline_interactive = re.compile(
            r'<(?:button|a)\b[^>]*style\s*=\s*["\']([^"\']*(?:width|height)\s*:\s*\d+px[^"\']*)["\']',
            re.IGNORECASE | re.DOTALL
        )

        for match in inline_interactive.finditer(content):
            style = match.group(1)
            w_match = re.search(r'width\s*:\s*(\d+)px', style)
            h_match = re.search(r'height\s*:\s*(\d+)px', style)

            small_dims = []
            if w_match and int(w_match.group(1)) < 44:
                small_dims.append(f'width: {w_match.group(1)}px')
            if h_match and int(h_match.group(1)) < 44:
                small_dims.append(f'height: {h_match.group(1)}px')

            if small_dims:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Small clickable element: {", ".join(small_dims)}',
                    description='Inline-styled interactive element has dimensions below the 44px minimum touch target.',
                    severity='medium'
                ))

        return issues
