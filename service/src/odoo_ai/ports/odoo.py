"""Safe, technology-neutral residual boundary for read-only Odoo callbacks."""

from typing import Protocol

from odoo_ai.contracts import Evidence, InstanceInventory, NavigationSnapshot, RecordRef, RecordSnapshot


class ModelMetadataGateway(Protocol):
    """Minimal runtime metadata boundary for residual source/explain workflows."""

    async def get_model_metadata(self, model: str) -> Evidence: ...


class OdooGatewayError(RuntimeError):
    """Sanitized failure shared by narrow Odoo gateway adapters."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OdooGateway(ModelMetadataGateway, Protocol):
    """Expose only bounded reads, navigation and metadata discovery."""

    async def read_records(
        self,
        records: list[RecordRef],
        fields: list[str],
    ) -> list[RecordSnapshot]: ...

    async def get_navigation(self) -> NavigationSnapshot: ...


class OdooInstanceGateway(Protocol):
    """Expose only non-business runtime metadata under machine authentication."""

    async def get_instance_inventory(self) -> InstanceInventory: ...
