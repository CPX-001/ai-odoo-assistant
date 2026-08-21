"""Authentication helpers for the local Assistant Service boundary."""

from odoo_ai.security.shared_secret import require_shared_secret

__all__ = ["require_shared_secret"]
