"""
Rules package - All UI/UX analysis rules.
"""

from .accessibility_rules import MissingAltTagRule, MissingAriaLabelRule, MissingLangAttributeRule
from .semantic_rules import NonSemanticTagRule, MissingHeadingHierarchyRule
from .style_rules import InlineStyleOveruseRule, FontInconsistencyRule
from .responsive_rules import NonResponsiveLayoutRule, MissingViewportRule
from .vue_rules import MissingComponentNameRule, MissingScopedStyleRule, LargeTemplateRule
from .contrast_rules import LowContrastRule
from .clickable_area_rules import SmallClickableAreaRule

ALL_RULES = [
    MissingAltTagRule(),
    MissingAriaLabelRule(),
    MissingLangAttributeRule(),
    NonSemanticTagRule(),
    MissingHeadingHierarchyRule(),
    InlineStyleOveruseRule(),
    FontInconsistencyRule(),
    NonResponsiveLayoutRule(),
    MissingViewportRule(),
    MissingComponentNameRule(),
    MissingScopedStyleRule(),
    LargeTemplateRule(),
    LowContrastRule(),
    SmallClickableAreaRule(),
]

__all__ = ['ALL_RULES']
