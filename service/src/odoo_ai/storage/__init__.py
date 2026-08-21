"""PostgreSQL persistence infrastructure for the Assistant Service."""

from odoo_ai.storage.base import Base
from odoo_ai.storage.config import DatabaseConfigurationError, DatabaseSettings
from odoo_ai.storage.database import create_database_engine, create_session_factory, session_scope

__all__ = [
    "Base",
    "DatabaseConfigurationError",
    "DatabaseSettings",
    "create_database_engine",
    "create_session_factory",
    "session_scope",
]
