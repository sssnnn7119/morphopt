"""Optimization scheme policies and starter snippets for the definition UI."""

from .base import (
    BUILTIN_SCHEMES,
    BuiltinSchemeTemplate,
    LEGACY_SCHEME_POLICIES,
    SchemeTemplate,
    SCHEME_REGISTRY,
    available_templates,
    get_template,
    scheme_label,
)
from .snippets import CodeSnippet, SnippetParameter

__all__ = [
    "BUILTIN_SCHEMES",
    "BuiltinSchemeTemplate",
    "CodeSnippet",
    "LEGACY_SCHEME_POLICIES",
    "SCHEME_REGISTRY",
    "SchemeTemplate",
    "SnippetParameter",
    "available_templates",
    "get_template",
    "scheme_label",
]
