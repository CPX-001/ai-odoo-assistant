"""Execute one immutable batch job under an existing AgentPlan authorization."""

from __future__ import annotations

from uuid import UUID

from odoo_ai.application.batch_execution import (
    BatchExecutionError,
    BatchMutationExecutionService,
)
from odoo_ai.application.batch_jobs import (
    BatchJobError,
    BatchMutationJobService,
)
from odoo_ai.contracts.batch_job import (
    BatchCommandReceipt,
    BatchExecutionContext,
)
from odoo_ai.contracts.chat import ChatActor


class BatchCommandError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class BatchCommandService:
    """Run a sealed batch without creating a second approval mechanism.

    ``authorization_id`` is issued by the already-authorized AgentPlan. The batch job
    contributes immutable payload/provenance and an execution attempt; neither can
    expand the authority granted by that plan.
    """

    def __init__(
        self,
        *,
        jobs: BatchMutationJobService,
        execution: BatchMutationExecutionService,
    ) -> None:
        self._jobs = jobs
        self._execution = execution

    async def execute(
        self,
        *,
        job_id: UUID,
        expected_fingerprint: str,
        actor: ChatActor,
        authorization_id: UUID,
    ) -> BatchCommandReceipt:
        try:
            existing = self._jobs.terminal_receipt(
                job_id,
                actor=actor,
                expected_fingerprint=expected_fingerprint,
            )
            if existing is not None:
                return existing
            claimed = self._jobs.claim_execution(
                job_id,
                actor=actor,
                expected_fingerprint=expected_fingerprint,
            )
            snapshot = claimed.snapshot
            attempt_id = snapshot.attempt_id
            if attempt_id is None:
                raise BatchCommandError("batch_job_corrupt", 503)
            request = self._jobs.execution_request(claimed)
            context = BatchExecutionContext(
                job_id=snapshot.job_id,
                attempt_id=attempt_id,
                authorization_id=authorization_id,
                job_fingerprint=snapshot.job_fingerprint,
                instance_id=snapshot.spec.instance_id,
                database=snapshot.spec.actor.database,
                uid=snapshot.spec.actor.uid,
                company_id=snapshot.spec.company_id,
                allowed_company_ids=snapshot.spec.allowed_company_ids,
                policy_revision=snapshot.spec.policy_revision,
            )
        except BatchJobError as error:
            raise BatchCommandError(error.code, error.status_code) from None

        try:
            result = await self._execution.execute(request, context=context)
        except BatchExecutionError:
            self._mark_unknown_best_effort(
                job_id=job_id,
                attempt_id=attempt_id,
            )
            raise BatchCommandError("batch_execution_outcome_unknown", 503) from None
        except Exception:
            self._mark_unknown_best_effort(
                job_id=job_id,
                attempt_id=attempt_id,
            )
            raise BatchCommandError("batch_execution_outcome_unknown", 503) from None

        try:
            return self._jobs.finish_execution(
                job_id=job_id,
                attempt_id=attempt_id,
                result=result,
            )
        except BatchJobError:
            # Another recovery of the same Odoo-idempotent attempt may have persisted
            # the terminal row receipts first. Prefer that durable terminal truth over
            # incorrectly degrading a successful batch to "unknown".
            terminal = self._terminal_receipt_best_effort(
                job_id=job_id,
                actor=actor,
                expected_fingerprint=expected_fingerprint,
            )
            if terminal is not None:
                return terminal
            # Odoo returned row outcomes but Assistant persistence did not complete.
            # Preserve the same attempt for a later idempotent recovery instead of
            # authorizing a fresh attempt that could duplicate creates.
            self._mark_unknown_best_effort(
                job_id=job_id,
                attempt_id=attempt_id,
            )
            raise BatchCommandError("batch_execution_outcome_unknown", 503) from None

    def _terminal_receipt_best_effort(
        self,
        *,
        job_id: UUID,
        actor: ChatActor,
        expected_fingerprint: str,
    ) -> BatchCommandReceipt | None:
        try:
            return self._jobs.terminal_receipt(
                job_id,
                actor=actor,
                expected_fingerprint=expected_fingerprint,
            )
        except BatchJobError:
            return None

    def _mark_unknown_best_effort(self, *, job_id: UUID, attempt_id: UUID) -> None:
        try:
            self._jobs.mark_execution_unknown(
                job_id=job_id,
                attempt_id=attempt_id,
                error_code="batch_execution_outcome_unknown",
            )
        except BatchJobError:
            # If Assistant DB is unavailable too, surfacing anything stronger than
            # unknown would be unsafe. A later recovery must inspect the durable job
            # and Odoo execution receipts before taking further action.
            pass
