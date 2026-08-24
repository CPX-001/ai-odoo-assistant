"""Safe, technology-neutral boundary for reading from Odoo."""

from typing import Protocol

from odoo_ai.contracts import (
    ActionCommitResult,
    ActionCreateCommitResult,
    ActionCreatePreview,
    ActionCreateVerificationResult,
    ActionPreview,
    ActionProposalPayload,
    ActionVerificationResult,
    AgentModelSearchRequest,
    AgentModelSearchResult,
    AggregateRecordsRequest,
    AggregateRecordsResult,
    BusinessActionCommitResult,
    BusinessActionPreview,
    BusinessActionProposalPayload,
    BusinessActionVerificationResult,
    Evidence,
    InstanceInventory,
    NavigationSnapshot,
    QueryRecordsRequest,
    QueryRecordsResult,
    RecordCreateProposalPayload,
    RecordRef,
    RecordSnapshot,
)


class ModelMetadataGateway(Protocol):
    """Minimal runtime metadata boundary shared by exact-read and QUERY tokens."""

    async def get_model_metadata(self, model: str) -> Evidence: ...


class OdooGatewayError(RuntimeError):
    """Sanitized failure shared by all narrow Odoo gateway adapters."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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

    async def search_agent_models(
        self, request: AgentModelSearchRequest
    ) -> AgentModelSearchResult: ...


class OdooActionPreviewGateway(Protocol):
    """Separate p1 boundary for write metadata and effect-free preview only."""

    async def get_write_model_metadata(self, model: str) -> Evidence: ...

    async def preview_record_patch(
        self,
        payload: ActionProposalPayload,
        *,
        payload_fingerprint: str,
    ) -> ActionPreview: ...

    async def preview_record_create(
        self,
        payload: RecordCreateProposalPayload,
        *,
        payload_fingerprint: str,
    ) -> ActionCreatePreview: ...

    async def preview_business_action(
        self,
        payload: BusinessActionProposalPayload,
        *,
        payload_fingerprint: str,
    ) -> BusinessActionPreview: ...


class OdooActionGateway(Protocol):
    """One a1-bound write or reread; implementations expose no generic method."""

    async def commit_record_patch(self, payload: ActionProposalPayload) -> ActionCommitResult: ...

    async def verify_record_patch(
        self, payload: ActionProposalPayload
    ) -> ActionVerificationResult: ...

    async def commit_record_create(
        self, payload: RecordCreateProposalPayload
    ) -> ActionCreateCommitResult: ...

    async def verify_record_create(
        self, payload: RecordCreateProposalPayload
    ) -> ActionCreateVerificationResult: ...

    async def commit_business_action(
        self, payload: BusinessActionProposalPayload
    ) -> BusinessActionCommitResult: ...

    async def verify_business_action(
        self, payload: BusinessActionProposalPayload
    ) -> BusinessActionVerificationResult: ...


class OdooActionGatewayFactory(Protocol):
    def for_action(self, *, authority_token: str) -> OdooActionGateway: ...
