"""
Contrast Rules - Detects potential low color contrast issues.
"""

import re
import math
from typing import List, Tuple, Optional
from .base_rule import BaseRule, ScanIssue, IssueFix


# Common named colors mapped to their hex values
NAMED_COLORS = {
    'white': '#ffffff', 'black': '#000000', 'red': '#ff0000',
    'green': '#008000', 'blue': '#0000ff', 'yellow': '#ffff00',
    'gray': '#808080', 'grey': '#808080', 'silver': '#c0c0c0',
    'orange': '#ffa500', 'purple': '#800080', 'pink': '#ffc0cb',
    'brown': '#a52a2a', 'navy': '#000080', 'teal': '#008080',
    'lime': '#00ff00', 'aqua': '#00ffff', 'maroon': '#800000',
    'olive': '#808000', 'coral': '#ff7f50', 'salmon': '#fa8072',
    'tomato': '#ff6347', 'gold': '#ffd700', 'khaki': '#f0e68c',
    'indigo': '#4b0082', 'violet': '#ee82ee', 'cyan': '#00ffff',
    'magenta': '#ff00ff', 'beige': '#f5f5dc', 'ivory': '#fffff0',
    'linen': '#faf0e6', 'wheat': '#f5deb3', 'tan': '#d2b48c',
    'darkgray': '#a9a9a9', 'darkgrey': '#a9a9a9',
    'lightgray': '#d3d3d3', 'lightgrey': '#d3d3d3',
    'darkblue': '#00008b', 'darkgreen': '#006400',
    'darkred': '#8b0000', 'lightblue': '#add8e6',
    'lightgreen': '#90ee90',
}

# Known low-contrast combinations
LOW_CONTRAST_PAIRS = [
    ('#ffffff', '#ffff00'),  # white on yellow
    ('#ffffff', '#00ffff'),  # white on cyan
    ('#ffffff', '#00ff00'),  # white on lime
    ('#c0c0c0', '#ffffff'),  # silver on white
    ('#808080', '#a9a9a9'),  # gray on darkgray
    ('#f5f5dc', '#ffffff'),  # beige on white
    ('#ffff00', '#ffffff'),  # yellow on white
]


def hex_to_rgb(hex_color: str) -> Optional[Tuple[int, int, int]]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.strip().lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        return None
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


def relative_luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance per WCAG 2.1."""
    def linearize(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(color1: Tuple[int, int, int], color2: Tuple[int, int, int]) -> float:
    """Calculate WCAG contrast ratio between two colors."""
    l1 = relative_luminance(*color1)
    l2 = relative_luminance(*color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def resolve_color(color_str: str) -> Optional[str]:
    """Resolve a color string to hex format."""
    color_str = color_str.strip().lower()

    if color_str in NAMED_COLORS:
        return NAMED_COLORS[color_str]

    if re.match(r'^#([0-9a-f]{3}|[0-9a-f]{6})$', color_str):
        return color_str

    # Try rgb()
    rgb_match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', color_str)
    if rgb_match:
        r, g, b = int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3))
        return f'#{r:02x}{g:02x}{b:02x}'

    return None


class LowContrastRule(BaseRule):
    """Detects potential low color contrast issues in CSS."""

    def __init__(self):
        super().__init__()
        self._id = 'low-contrast'
        self._name = 'Low Color Contrast'
        self._description = 'Text and interactive elements must have sufficient color contrast (WCAG AA: 4.5:1 for normal text).'
        self._severity = 'high'
        self._category = 'accessibility'

    def detect(self, content: str, file_path: str, **kwargs) -> List[ScanIssue]:
        issues = []

        # Parse CSS rule blocks and check color vs background-color pairs
        # This regex finds CSS rule blocks
        block_pattern = re.compile(
            r'([^{}]+)\{([^{}]+)\}',
            re.DOTALL
        )

        for block_match in block_pattern.finditer(content):
            selector = block_match.group(1).strip()
            properties = block_match.group(2)

            # Extract color and background-color
            color_match = re.search(
                r'(?<!\bbackground-)color\s*:\s*([^;}\n]+)',
                properties, re.IGNORECASE
            )
            bg_match = re.search(
                r'background(?:-color)?\s*:\s*([^;}\n]+)',
                properties, re.IGNORECASE
            )

            if color_match and bg_match:
                fg_color = resolve_color(color_match.group(1).strip())
                bg_color = resolve_color(bg_match.group(1).strip())

                if fg_color and bg_color:
                    fg_rgb = hex_to_rgb(fg_color)
                    bg_rgb = hex_to_rgb(bg_color)

                    if fg_rgb and bg_rgb:
                        ratio = contrast_ratio(fg_rgb, bg_rgb)

                        # WCAG AA requires 4.5:1 for normal text
                        if ratio < 4.5:
                            line, col = self._find_line_col(content, color_match.start())
                            end_line, end_col = self._find_line_col(content, color_match.end())

                            issues.append(self.create_issue(
                                file_path=file_path,
                                line=line,
                                column=col,
                                end_line=end_line,
                                end_column=end_col,
                                message=f'Low contrast ratio: {ratio:.1f}:1 (need 4.5:1 for WCAG AA)',
                                description=f'Color {fg_color} on background {bg_color} has a contrast ratio of {ratio:.1f}:1. '
                                            f'WCAG AA requires at least 4.5:1 for normal text and 3:1 for large text.',
                                severity='high' if ratio < 3.0 else 'medium'
                            ))

        # Also check inline styles for color contrast
        inline_pattern = re.compile(
            r'style\s*=\s*["\']([^"\']*color[^"\']*)["\']',
            re.IGNORECASE
        )
        for match in inline_pattern.finditer(content):
            style_value = match.group(1)
            fg_match = re.search(r'(?<!background-)color\s*:\s*([^;]+)', style_value)
            bg_match = re.search(r'background(?:-color)?\s*:\s*([^;]+)', style_value)

            if fg_match and bg_match:
                fg_color = resolve_color(fg_match.group(1).strip())
                bg_color = resolve_color(bg_match.group(1).strip())

                if fg_color and bg_color:
                    fg_rgb = hex_to_rgb(fg_color)
                    bg_rgb = hex_to_rgb(bg_color)

                    if fg_rgb and bg_rgb:
                        ratio = contrast_ratio(fg_rgb, bg_rgb)
                        if ratio < 4.5:
                            line, col = self._find_line_col(content, match.start())
                            end_line, end_col = self._find_line_col(content, match.end())

                            issues.append(self.create_issue(
                                file_path=file_path,
                                line=line,
                                column=col,
                                end_line=end_line,
                                end_column=end_col,
                                message=f'Low contrast in inline style: {ratio:.1f}:1',
                                description=f'Inline color {fg_color} on {bg_color} has contrast ratio {ratio:.1f}:1 (minimum 4.5:1).',
                                severity='high' if ratio < 3.0 else 'medium'
                            ))

        return issues
