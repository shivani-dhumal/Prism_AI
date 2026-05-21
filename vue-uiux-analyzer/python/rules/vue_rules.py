"""
Vue Component Rules - Detects Vue-specific component structure issues.
"""

import re
from typing import List
from .base_rule import BaseRule, ScanIssue, IssueFix


class MissingComponentNameRule(BaseRule):
    """Detects Vue components without an explicit name option."""

    def __init__(self):
        super().__init__()
        self._id = 'missing-component-name'
        self._name = 'Missing Component Name'
        self._description = 'Vue components should have an explicit name for better debugging and DevTools experience.'
        self._severity = 'low'
        self._category = 'vue'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        if not file_path.lower().endswith('.vue'):
            return issues

        # Check for Options API: export default { ... }
        options_pattern = re.compile(
            r'export\s+default\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
            re.DOTALL
        )
        match = options_pattern.search(content)

        if match:
            options_body = match.group(1)
            # Check if name property exists
            has_name = re.search(r'\bname\s*:', options_body)

            # Check if using <script setup> (doesn't need name in Options API style)
            has_setup = re.search(r'<script\s[^>]*\bsetup\b', content, re.IGNORECASE)

            if not has_name and not has_setup:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                # Derive component name from filename
                import os
                basename = os.path.splitext(os.path.basename(file_path))[0]
                component_name = basename

                original_text = 'export default {'
                replacement_text = f"export default {{\n  name: '{component_name}',"

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message='Component is missing explicit name option',
                    description='Adding a name property helps with debugging in Vue DevTools and recursive components.',
                    fix=IssueFix(
                        description=f'Add name: \'{component_name}\'',
                        original=original_text,
                        replacement=replacement_text,
                        line=line, column=col,
                        end_line=line, end_column=col + len(original_text)
                    )
                ))

        # Check for defineComponent without name
        define_pattern = re.compile(
            r'defineComponent\s*\(\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
            re.DOTALL
        )
        dc_match = define_pattern.search(content)
        if dc_match and not re.search(r'\bname\s*:', dc_match.group(1)):
            line, col = self._find_line_col(content, dc_match.start())
            end_line, end_col = self._find_line_col(content, dc_match.end())

            issues.append(self.create_issue(
                file_path=file_path,
                line=line,
                column=col,
                end_line=end_line,
                end_column=end_col,
                message='defineComponent is missing name option',
                description='Add a name property to defineComponent for better debugging.',
                severity='low'
            ))

        return issues


class MissingScopedStyleRule(BaseRule):
    """Detects Vue components with unscoped styles that may leak."""

    def __init__(self):
        super().__init__()
        self._id = 'missing-scoped-style'
        self._name = 'Missing Scoped Style'
        self._description = 'Vue component styles should be scoped to prevent CSS leaking to other components.'
        self._severity = 'medium'
        self._category = 'vue'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        if not file_path.lower().endswith('.vue'):
            return issues

        # Find all <style> blocks
        style_pattern = re.compile(
            r'<style\b([^>]*)>',
            re.IGNORECASE
        )

        for match in style_pattern.finditer(content):
            attrs = match.group(1)
            has_scoped = re.search(r'\bscoped\b', attrs, re.IGNORECASE)
            has_module = re.search(r'\bmodule\b', attrs, re.IGNORECASE)

            if not has_scoped and not has_module:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                original = match.group(0)
                replacement = original.replace('<style', '<style scoped', 1)

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message='Style block is not scoped',
                    description='Unscoped styles can leak to other components. Use <style scoped> or <style module>.',
                    fix=IssueFix(
                        description='Add scoped attribute to style tag',
                        original=original,
                        replacement=replacement,
                        line=line, column=col,
                        end_line=end_line, end_column=end_col
                    )
                ))

        return issues


class LargeTemplateRule(BaseRule):
    """Detects Vue templates that are too large and should be split."""

    def __init__(self):
        super().__init__()
        self._id = 'large-template'
        self._name = 'Large Template'
        self._description = 'Large Vue templates should be split into smaller child components for maintainability.'
        self._severity = 'low'
        self._category = 'vue'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        if not file_path.lower().endswith('.vue'):
            return issues

        template_pattern = re.compile(
            r'<template\b[^>]*>(.*?)</template>',
            re.DOTALL | re.IGNORECASE
        )

        match = template_pattern.search(content)
        if match:
            template_content = match.group(1)
            line_count = template_content.count('\n')

            if line_count > 150:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Template has {line_count} lines (recommended: < 150)',
                    description='Large templates are harder to maintain. Consider extracting sections into child components.',
                ))

        # Count number of elements in template
        if match:
            template_content = match.group(1)
            element_count = len(re.findall(r'<[a-z][\w-]*\b', template_content, re.IGNORECASE))

            if element_count > 50:
                line, col = self._find_line_col(content, match.start())
                end_line, end_col = self._find_line_col(content, match.end())

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=line,
                    column=col,
                    end_line=end_line,
                    end_column=end_col,
                    message=f'Template has {element_count} elements (recommended: < 50)',
                    description='Too many elements suggest the component does too much. Split into smaller components.',
                    severity='low'
                ))

        return issues
