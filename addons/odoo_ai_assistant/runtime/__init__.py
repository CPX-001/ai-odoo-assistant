"""Embedded Odoo AI Assistant runtime infrastructure."""

from .codex import CodexStatus, detect_codex
from .paths import RuntimePathError, RuntimePaths

__all__ = ["CodexStatus", "RuntimePathError", "RuntimePaths", "detect_codex"]
