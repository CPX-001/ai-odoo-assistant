"""Safe, technology-neutral boundary for reading from Odoo."""

from typing import Protocol

from odoo_ai.contracts import (
    Evidence,
    InstanceInventory,
    NavigationSnapshot,
    RecordRef,
    RecordSnapshot,
)


class OdooGateway(Protocol):
    """Expose only bounded record reads and runtime metadata discovery."""

    async def read_records(
        self,
        records: list[RecordRef],
        fields: list[str],
    ) -> list[RecordSnapshot]: ...

    async def get_model_metadata(self, model: str) -> Evidence: ...

    async def get_navigation(self) -> NavigationSnapshot: ...


class OdooInstanceGateway(Protocol):
    """Expose only non-business runtime metadata under machine authentication."""

    async def get_instance_inventory(self) -> InstanceInventory: ...
