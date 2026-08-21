"""Shared SQLAlchemy metadata for Assistant-owned tables."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for the separate Assistant database."""
