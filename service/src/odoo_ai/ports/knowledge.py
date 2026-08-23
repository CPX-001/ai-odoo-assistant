"""Technology-neutral configured knowledge provider boundary."""

from typing import Protocol

from odoo_ai.contracts.knowledge import KnowledgeProviderResult


class KnowledgeProvider(Protocol):
    """Return one bounded snapshot from administrator-configured sources."""

    def scan(self) -> KnowledgeProviderResult: ...
