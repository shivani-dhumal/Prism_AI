"""
Semantic HTML Rules - Detects non-semantic tags and heading hierarchy issues.
"""

import re
from typing import List
from .base_rule import BaseRule, ScanIssue, IssueFix


# Map of commonly misused div/span patterns to semantic alternatives
SEMANTIC_SUGGESTIONS = {
    'nav': [r'class\s*=\s*["\'][^"\']*\b(nav|navigation|menu|navbar|sidebar)\b'],
    'header': [r'class\s*=\s*["\'][^"\']*\b(header|page-header|site-header|top-bar)\b'],
    'footer': [r'class\s*=\s*["\'][^"\']*\b(footer|page-footer|site-footer|bottom-bar)\b'],
    'main': [r'class\s*=\s*["\'][^"\']*\b(main|main-content|content|page-content)\b'],
    'aside': [r'class\s*=\s*["\'][^"\']*\b(sidebar|aside|side-panel|widget)\b'],
    'article': [r'class\s*=\s*["\'][^"\']*\b(article|post|blog-post|card|entry)\b'],
    'section': [r'class\s*=\s*["\'][^"\']*\b(section|block|segment)\b'],
}


class NonSemanticTagRule(BaseRule):
    """Detects div/span tags that should be semantic HTML elements."""

    def __init__(self):
        super().__init__()
        self._id = 'non-semantic-tag'
        self._name = 'Non-Semantic HTML Tag'
        self._description = 'Use semantic HTML elements instead of generic <div> or <span> when the purpose is clear.'
        self._severity = 'medium'
        self._category = 'semantics'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Find <div> tags with class names suggesting semantic usage
        div_pattern = re.compile(
            r'<div\b([^>]*)>',
            re.IGNORECASE | re.DOTALL
        )

        for match in div_pattern.finditer(content):
            attrs = match.group(1)

            for semantic_tag, patterns in SEMANTIC_SUGGESTIONS.items():
                for pattern in patterns:
                    if re.search(pattern, attrs, re.IGNORECASE):
                        line, col = self._find_line_col(content, match.start())
                        end_line, end_col = self._find_line_col(content, match.end())

                        original = match.group(0)
                        replacement = original.replace('<div', f'<{semantic_tag}', 1)

                        issues.append(self.create_issue(
                            file_path=file_path,
                            line=line,
                            column=col,
                            end_line=end_line,
                            end_column=end_col,
                            message=f'Consider using <{semantic_tag}> instead of <div>',
                            description=f'The class name suggests this element serves as a {semantic_tag}. '
                                        f'Using <{semantic_tag}> improves accessibility and SEO.',
                            fix=IssueFix(
                                description=f'Replace <div> with <{semantic_tag}>',
                                original=original,
                                replacement=replacement,
                                line=line, column=col,
                                end_line=end_line, end_column=end_col
                            )
                        ))
                        break  # Only one suggestion per div

        return issues


class MissingHeadingHierarchyRule(BaseRule):
    """Detects skipped heading levels (e.g., h1 -> h3 without h2)."""

    def __init__(self):
        super().__init__()
        self._id = 'heading-hierarchy'
        self._name = 'Heading Hierarchy Issue'
        self._description = 'Heading levels should not be skipped. Use h1 -> h2 -> h3 in sequence.'
        self._severity = 'medium'
        self._category = 'semantics'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        heading_pattern = re.compile(r'<(h[1-6])\b[^>]*>', re.IGNORECASE)
        headings = []

        for match in heading_pattern.finditer(content):
            level = int(match.group(1)[1])
            line, col = self._find_line_col(content, match.start())
            end_line, end_col = self._find_line_col(content, match.end())
            headings.append({
                'level': level,
                'line': line,
                'col': col,
                'end_line': end_line,
                'end_col': end_col,
                'match': match
            })

        # Check for skipped levels
        for i in range(1, len(headings)):
            prev_level = headings[i - 1]['level']
            curr_level = headings[i]['level']

            if curr_level > prev_level + 1:
                h = headings[i]
                expected = f'h{prev_level + 1}'
                actual = f'h{curr_level}'

                original = h['match'].group(0)
                replacement = original.replace(f'<{actual}', f'<{expected}', 1)

                issues.append(self.create_issue(
                    file_path=file_path,
                    line=h['line'],
                    column=h['col'],
                    end_line=h['end_line'],
                    end_column=h['end_col'],
                    message=f'Heading level skipped: <{actual}> after <h{prev_level}>',
                    description=f'Expected <{expected}> after <h{prev_level}>. Skipping heading levels confuses screen readers.',
                    fix=IssueFix(
                        description=f'Change <{actual}> to <{expected}>',
                        original=original,
                        replacement=replacement,
                        line=h['line'], column=h['col'],
                        end_line=h['end_line'], end_column=h['end_col']
                    )
                ))

        # Check for multiple h1 tags
        h1_count = sum(1 for h in headings if h['level'] == 1)
        if h1_count > 1:
            for h in headings[1:]:
                if h['level'] == 1:
                    issues.append(self.create_issue(
                        file_path=file_path,
                        line=h['line'],
                        column=h['col'],
                        end_line=h['end_line'],
                        end_column=h['end_col'],
                        message='Multiple <h1> tags found',
                        description='A page should typically have only one <h1> tag for proper document structure.',
                        severity='low'
                    ))

        return issues
