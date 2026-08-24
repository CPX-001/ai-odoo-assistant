"""Port for effect-free Odoo validation of already-normalized batch rows."""

from __future__ import annotations

from typing import Protocol

from odoo_ai.contracts.batch import BatchMutationRequest
from odoo_ai.contracts.batch_preflight import BatchPreflightResult


class BatchPreflightGateway(Protocol):
    async def preflight_batch(
        self,
        request: BatchMutationRequest,
    ) -> BatchPreflightResult: ...
