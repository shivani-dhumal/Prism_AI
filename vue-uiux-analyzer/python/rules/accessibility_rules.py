"""
Accessibility Rules - Detects missing alt tags, aria labels, and lang attributes.
"""

import re
from typing import List
from .base_rule import BaseRule, ScanIssue, IssueFix


class MissingAltTagRule(BaseRule):
    """Detects <img> tags without alt attributes."""

    def __init__(self):
        super().__init__()
        self._id = 'missing-alt-tag'
        self._name = 'Missing Alt Tag'
        self._description = 'Images must have alt attributes for screen readers and accessibility compliance (WCAG 2.1 Level A).'
        self._severity = 'high'
        self._category = 'accessibility'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []
        # Match <img> tags without alt attribute
        img_pattern = re.compile(r'<img\b([^>]*?)/?>', re.IGNORECASE | re.DOTALL)

        for match in img_pattern.finditer(content):
            attrs = match.group(1)
            if not re.search(r'\balt\s*=', attrs, re.IGNORECASE):
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                # Build fix: add alt="" to the tag
                original = match.group(0)
                if original.endswith('/>'):
                    replacement = original[:-2].rstrip() + ' alt="" />'
                else:
                    replacement = original[:-1].rstrip() + ' alt="">'

                fix = IssueFix(
                    description='Add empty alt attribute',
                    original=original,
                    replacement=replacement,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col
                )

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'<img> tag is missing alt attribute',
                    description='Every image must have an alt attribute. Use alt="" for decorative images or provide descriptive text for meaningful images.',
                    fix=fix
                ))

        return issues


class MissingAriaLabelRule(BaseRule):
    """Detects interactive elements without aria-label or accessible text."""

    def __init__(self):
        super().__init__()
        self._id = 'missing-aria-label'
        self._name = 'Missing ARIA Label'
        self._description = 'Interactive elements should have accessible labels for assistive technology.'
        self._severity = 'high'
        self._category = 'accessibility'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Check buttons without text content or aria-label
        button_pattern = re.compile(
            r'<button\b([^>]*)>(.*?)</button>',
            re.IGNORECASE | re.DOTALL
        )
        for match in button_pattern.finditer(content):
            attrs = match.group(1)
            inner = match.group(2).strip()

            # Skip if has aria-label, aria-labelledby, or meaningful text
            has_aria = re.search(r'\baria-label(ledby)?\s*=', attrs, re.IGNORECASE)
            has_title = re.search(r'\btitle\s*=', attrs, re.IGNORECASE)
            # Strip HTML tags from inner to check for text
            text_only = re.sub(r'<[^>]+>', '', inner).strip()

            if not has_aria and not has_title and not text_only:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                original = match.group(0)
                # Add aria-label to opening tag
                replacement = original.replace('<button', '<button aria-label="Button action"', 1)

                fix = IssueFix(
                    description='Add aria-label attribute',
                    original=original,
                    replacement=replacement,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col
                )

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message='Button has no accessible label',
                    description='Buttons with only icon content need aria-label for screen reader users.',
                    fix=fix
                ))

        # Check <a> tags without text or aria-label
        link_pattern = re.compile(
            r'<a\b([^>]*)>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        for match in link_pattern.finditer(content):
            attrs = match.group(1)
            inner = match.group(2).strip()
            has_aria = re.search(r'\baria-label(ledby)?\s*=', attrs, re.IGNORECASE)
            text_only = re.sub(r'<[^>]+>', '', inner).strip()

            if not has_aria and not text_only:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message='Link has no accessible text',
                    description='Links must have descriptive text or aria-label for accessibility.',
                    fix=IssueFix(
                        description='Add aria-label to link',
                        original=match.group(0),
                        replacement=match.group(0).replace('<a', '<a aria-label="Link description"', 1),
                        line=line, column=col, end_line=end_line, end_column=end_col
                    )
                ))

        # Check <input> without label association
        input_pattern = re.compile(
            r'<input\b([^>]*?)/?>', re.IGNORECASE | re.DOTALL
        )
        for match in input_pattern.finditer(content):
            attrs = match.group(1)
            has_aria = re.search(r'\baria-label(ledby)?\s*=', attrs, re.IGNORECASE)
            has_id = re.search(r'\bid\s*=', attrs, re.IGNORECASE)
            has_placeholder = re.search(r'\bplaceholder\s*=', attrs, re.IGNORECASE)
            is_hidden = re.search(r'\btype\s*=\s*["\']hidden["\']', attrs, re.IGNORECASE)

            if not has_aria and not has_id and not is_hidden:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                original = match.group(0)
                replacement = original.replace('<input', '<input aria-label="Input field"', 1)

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message='Input field has no accessible label',
                    description='Input fields need an associated <label>, aria-label, or aria-labelledby attribute.',
                    fix=IssueFix(
                        description='Add aria-label to input',
                        original=original,
                        replacement=replacement,
                        line=line, column=col, end_line=end_line, end_column=end_col
                    )
                ))

        return issues


class MissingLangAttributeRule(BaseRule):
    """Detects HTML documents missing the lang attribute."""

    def __init__(self):
        super().__init__()
        self._id = 'missing-lang-attribute'
        self._name = 'Missing Language Attribute'
        self._description = 'The <html> tag should have a lang attribute specifying the page language.'
        self._severity = 'medium'
        self._category = 'accessibility'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        html_pattern = re.compile(r'<html\b([^>]*)>', re.IGNORECASE)
        match = html_pattern.search(content)

        if match:
            attrs = match.group(1)
            if not re.search(r'\blang\s*=', attrs, re.IGNORECASE):
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                original = match.group(0)
                replacement = original.replace('<html', '<html lang="en"', 1)

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message='<html> tag is missing lang attribute',
                    description='The lang attribute helps screen readers determine the correct pronunciation and assists search engines.',
                    fix=IssueFix(
                        description='Add lang="en" attribute',
                        original=original,
                        replacement=replacement,
                        line=line, column=col, end_line=end_line, end_column=end_col
                    )
                ))

        return issues
