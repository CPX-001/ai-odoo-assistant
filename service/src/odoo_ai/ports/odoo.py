"""Safe, technology-neutral boundary for reading from Odoo."""

from typing import Protocol

from odoo_ai.contracts import (
    AggregateRecordsRequest,
    AggregateRecordsResult,
    Evidence,
    InstanceInventory,
    NavigationSnapshot,
    QueryRecordsRequest,
    QueryRecordsResult,
    RecordRef,
    RecordSnapshot,
)


class ModelMetadataGateway(Protocol):
    """Minimal runtime metadata boundary shared by exact-read and QUERY tokens."""

    async def get_model_metadata(self, model: str) -> Evidence: ...


class OdooGateway(ModelMetadataGateway, Protocol):
    """Expose only bounded record reads and runtime metadata discovery."""

    async def read_records(
        self,
        records: list[RecordRef],
        fields: list[str],
    ) -> list[RecordSnapshot]: ...

    async def get_navigation(self) -> NavigationSnapshot: ...


class OdooInstanceGateway(Protocol):
    """Expose only non-business runtime metadata under machine authentication."""

    async def get_instance_inventory(self) -> InstanceInventory: ...


class OdooQueryGateway(Protocol):
    """Separate q1 boundary for schema, search/read, and aggregate only."""

    async def get_query_model_metadata(self, model: str) -> Evidence: ...

    async def query_records(self, request: QueryRecordsRequest) -> QueryRecordsResult: ...

    async def aggregate_records(
        self, request: AggregateRecordsRequest
    ) -> AggregateRecordsResult: ...
