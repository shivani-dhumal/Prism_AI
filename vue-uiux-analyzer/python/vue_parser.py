"""
Vue Parser - Extracts template, script, and style sections from .vue files.
"""

import re
from typing import Dict, Optional, Tuple


class VueFileSection:
    """Represents a section of a Vue single-file component."""

    def __init__(self, content: str, start_line: int, end_line: int, attrs: Dict[str, str] = None):
        self.content = content
        self.start_line = start_line
        self.end_line = end_line
        self.attrs = attrs or {}


class ParsedVueFile:
    """Parsed representation of a .vue file."""

    def __init__(self, file_path: str, raw_content: str):
        self.file_path = file_path
        self.raw_content = raw_content
        self.template: Optional[VueFileSection] = None
        self.script: Optional[VueFileSection] = None
        self.style: Optional[VueFileSection] = None
        self.styles: list = []  # Multiple style blocks
        self.lines = raw_content.split('\n')

    def get_line(self, line_number: int) -> str:
        """Get content at a specific line (1-indexed)."""
        if 1 <= line_number <= len(self.lines):
            return self.lines[line_number - 1]
        return ''

    @property
    def has_template(self) -> bool:
        return self.template is not None

    @property
    def has_script(self) -> bool:
        return self.script is not None

    @property
    def has_style(self) -> bool:
        return self.style is not None

    @property
    def has_scoped_style(self) -> bool:
        return any(s.attrs.get('scoped') is not None for s in self.styles)


def parse_vue_file(file_path: str, content: str) -> ParsedVueFile:
    """
    Parse a Vue single-file component into its sections.
    
    Args:
        file_path: Path to the .vue file
        content: Raw file content
        
    Returns:
        ParsedVueFile with template, script, and style sections
    """
    parsed = ParsedVueFile(file_path, content)

    # Parse template section
    template_match = re.search(
        r'<template(\s[^>]*)?>(.+?)</template>',
        content, re.DOTALL
    )
    if template_match:
        attrs = _parse_attributes(template_match.group(1) or '')
        inner = template_match.group(2)
        start_line = content[:template_match.start()].count('\n') + 1
        end_line = content[:template_match.end()].count('\n') + 1
        parsed.template = VueFileSection(inner, start_line, end_line, attrs)

    # Parse script section(s)
    script_matches = re.finditer(
        r'<script(\s[^>]*)?>(.+?)</script>',
        content, re.DOTALL
    )
    for match in script_matches:
        attrs = _parse_attributes(match.group(1) or '')
        inner = match.group(2)
        start_line = content[:match.start()].count('\n') + 1
        end_line = content[:match.end()].count('\n') + 1
        section = VueFileSection(inner, start_line, end_line, attrs)
        if parsed.script is None:
            parsed.script = section

    # Parse style section(s)
    style_matches = re.finditer(
        r'<style(\s[^>]*)?>(.+?)</style>',
        content, re.DOTALL
    )
    for match in style_matches:
        attrs = _parse_attributes(match.group(1) or '')
        inner = match.group(2)
        start_line = content[:match.start()].count('\n') + 1
        end_line = content[:match.end()].count('\n') + 1
        section = VueFileSection(inner, start_line, end_line, attrs)
        parsed.styles.append(section)
        if parsed.style is None:
            parsed.style = section

    return parsed


def _parse_attributes(attr_string: str) -> Dict[str, str]:
    """Parse HTML attributes from a tag string."""
    attrs = {}
    if not attr_string:
        return attrs

    # Handle boolean attributes (e.g., 'scoped')
    boolean_attrs = re.findall(r'\b(\w[\w-]*)\b(?!=)', attr_string)
    for attr in boolean_attrs:
        if attr not in ('setup', 'lang', 'scoped', 'module', 'src'):
            continue
        if f'{attr}=' not in attr_string:
            attrs[attr] = ''

    # Handle key=value attributes
    kv_attrs = re.findall(r'(\w[\w-]*)=["\']([^"\']*)["\']', attr_string)
    for key, value in kv_attrs:
        attrs[key] = value

    # Handle boolean without value explicitly
    if 'scoped' in attr_string and 'scoped' not in attrs:
        attrs['scoped'] = ''
    if 'setup' in attr_string and 'setup' not in attrs:
        attrs['setup'] = ''

    return attrs


def is_vue_file(file_path: str) -> bool:
    """Check if a file is a Vue single-file component."""
    return file_path.lower().endswith('.vue')


def get_template_line_offset(parsed: ParsedVueFile) -> int:
    """Get the line offset for the template section."""
    if parsed.template:
        return parsed.template.start_line
    return 0
