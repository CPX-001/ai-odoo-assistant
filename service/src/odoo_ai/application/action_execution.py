"""One-shot approved ACTION commit followed by deterministic reread verification."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, Never, cast
from uuid import UUID, uuid4

from odoo_ai.contracts import (
    ActionAuthorityClaims,
    ActionCommitResult,
    ActionCreateCommitResult,
    ActionCreateVerificationResult,
    ActionExecutionReceipt,
    ActionKind,
    ActionProposalPayload,
    ActionProposalState,
    ActionVerificationResult,
    BusinessActionCommitResult,
    BusinessActionProposalPayload,
    BusinessActionVerificationResult,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    ExecuteApprovedActionRequest,
)
from odoo_ai.ports import (
    ActionApprovalStore,
    ActionAuthorityIssuer,
    ActionDecisionOutcome,
    OdooActionGatewayFactory,
    OdooGatewayError,
    StoredActionProposal,
)

_AMBIGUOUS_COMMIT_ERRORS = frozenset(
    {"malformed_response", "response_too_large", "upstream_timeout", "upstream_unavailable"}
)


class ActionExecutionError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class _ActionTokenError(RuntimeError):
    code = "action_authority_unavailable"


class ActionExecutionService:
    """Consume approval once, commit once, then resolve by reread without retry."""

    def __init__(
        self,
        *,
        store: ActionApprovalStore,
        authority_codec: ActionAuthorityIssuer,
        gateway_factory: OdooActionGatewayFactory,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._store = store
        self._codec = authority_codec
        self._gateway_factory = gateway_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory or uuid4

    async def execute(self, request: ExecuteApprovedActionRequest) -> ActionExecutionReceipt:
        started_at = self._now()
        attempt_id = self._uuid_factory()
        try:
            claimed = self._store.claim_execution(
                approval_id=request.approval_id,
                actor=request.actor,
                attempt_id=attempt_id,
                started_at=started_at,
            )
        except Exception:
            raise ActionExecutionError("approval_store_unavailable", 503) from None
        if claimed.outcome is ActionDecisionOutcome.INVALID_STATE and claimed.proposal is not None:
            return await self._resume_without_commit(claimed.proposal)
        if claimed.outcome is not ActionDecisionOutcome.APPLIED or claimed.proposal is None:
            self._raise_claim(claimed.outcome)
        proposal = claimed.proposal

        try:
            commit: ActionCommitResult | ActionCreateCommitResult | BusinessActionCommitResult
            commit_gateway = self._gateway_factory.for_action(
                authority_token=self._token(proposal, attempt_id, "action_commit")
            )
            if isinstance(proposal.payload, ActionProposalPayload):
                commit = await commit_gateway.commit_record_patch(proposal.payload)
            elif not isinstance(proposal.payload, BusinessActionProposalPayload):
                commit = await commit_gateway.commit_record_create(proposal.payload)
            else:
                commit = await commit_gateway.commit_business_action(proposal.payload)
            if (
                commit.proposal_id != proposal.payload.proposal_id
                or commit.attempt_id != attempt_id
                or commit.payload_fingerprint != proposal.payload_fingerprint
                or commit.precondition_fingerprint != proposal.preview.precondition_fingerprint
                or (
                    isinstance(commit, BusinessActionCommitResult)
                    and (
                        not isinstance(proposal.payload, BusinessActionProposalPayload)
                        or commit.action_id != proposal.payload.action_id
                        or commit.record_id != proposal.payload.target.record_id
                    )
                )
            ):
                raise OdooGatewayError("malformed_response")
        except (_ActionTokenError, OdooGatewayError) as error:
            code = error.code
            if code == "stale_precondition":
                return self._finish(
                    proposal, attempt_id, ActionProposalState.STALE, error_code=code
                )
            if code not in _AMBIGUOUS_COMMIT_ERRORS:
                return self._finish(
                    proposal, attempt_id, ActionProposalState.FAILED, error_code=code
                )
            self._transition(
                proposal,
                attempt_id,
                (ActionProposalState.EXECUTING,),
                ActionProposalState.EXECUTION_UNKNOWN,
                error_code="commit_outcome_unknown",
            )
            return await self._verify(proposal, attempt_id, commit_confirmed=False)

        self._transition(
            proposal,
            attempt_id,
            (ActionProposalState.EXECUTING,),
            ActionProposalState.COMMITTED,
        )
        return await self._verify(proposal, attempt_id, commit_confirmed=True)

    async def _resume_without_commit(
        self, proposal: StoredActionProposal
    ) -> ActionExecutionReceipt:
        attempt_id = proposal.attempt_id
        if attempt_id is None:
            raise ActionExecutionError("approval_already_consumed")
        if proposal.state is ActionProposalState.EXECUTING:
            self._transition(
                proposal,
                attempt_id,
                (ActionProposalState.EXECUTING,),
                ActionProposalState.EXECUTION_UNKNOWN,
                error_code="interrupted_commit_outcome_unknown",
            )
            return await self._verify(proposal, attempt_id, commit_confirmed=False)
        if proposal.state is ActionProposalState.EXECUTION_UNKNOWN:
            return await self._verify(proposal, attempt_id, commit_confirmed=False)
        if proposal.state is ActionProposalState.COMMITTED:
            return await self._verify(proposal, attempt_id, commit_confirmed=True)
        if proposal.state in {
            ActionProposalState.VERIFIED,
            ActionProposalState.STALE,
            ActionProposalState.FAILED,
            ActionProposalState.COMMITTED_UNVERIFIED,
        }:
            return self._stored_receipt(proposal)
        raise ActionExecutionError("approval_already_consumed")

    def _stored_receipt(self, proposal: StoredActionProposal) -> ActionExecutionReceipt:
        if (
            proposal.approval_id is None
            or proposal.attempt_id is None
            or proposal.completed_at is None
        ):
            raise ActionExecutionError("approval_store_unavailable", 503)
        evidence: Evidence | None = None
        if proposal.state is ActionProposalState.VERIFIED:
            try:
                evidence = Evidence.model_validate(proposal.verification_payload)
            except ValueError:
                raise ActionExecutionError("approval_store_unavailable", 503) from None
        return ActionExecutionReceipt(
            proposal_id=proposal.payload.proposal_id,
            approval_id=proposal.approval_id,
            attempt_id=proposal.attempt_id,
            state=cast(
                Literal[
                    ActionProposalState.VERIFIED,
                    ActionProposalState.STALE,
                    ActionProposalState.FAILED,
                    ActionProposalState.EXECUTION_UNKNOWN,
                    ActionProposalState.COMMITTED_UNVERIFIED,
                ],
                proposal.state,
            ),
            payload_fingerprint=proposal.payload_fingerprint,
            completed_at=proposal.completed_at,
            evidence_id=proposal.evidence_id,
            evidence=evidence,
            error_code=proposal.error_code,
        )

    async def _verify(
        self,
        proposal: StoredActionProposal,
        attempt_id: UUID,
        *,
        commit_confirmed: bool,
    ) -> ActionExecutionReceipt:
        expected = (
            ActionProposalState.COMMITTED
            if commit_confirmed
            else ActionProposalState.EXECUTION_UNKNOWN
        )
        try:
            verification: (
                ActionVerificationResult
                | ActionCreateVerificationResult
                | BusinessActionVerificationResult
            )
            gateway = self._gateway_factory.for_action(
                authority_token=self._token(proposal, attempt_id, "action_verify")
            )
            if isinstance(proposal.payload, ActionProposalPayload):
                verification = await gateway.verify_record_patch(proposal.payload)
                expected_after = {change.field: change.value for change in proposal.payload.changes}
                record_id = proposal.payload.target.record_id
            elif not isinstance(proposal.payload, BusinessActionProposalPayload):
                verification = await gateway.verify_record_create(proposal.payload)
                expected_after = {value.field: value.value for value in proposal.payload.values}
                record_id = verification.record_id
            else:
                verification = await gateway.verify_business_action(proposal.payload)
                expected_after = None
                record_id = proposal.payload.target.record_id
            if (
                verification.proposal_id != proposal.payload.proposal_id
                or verification.attempt_id != attempt_id
                or (
                    isinstance(verification, BusinessActionVerificationResult)
                    and (
                        not isinstance(proposal.payload, BusinessActionProposalPayload)
                        or verification.action_id != proposal.payload.action_id
                        or verification.record_id != proposal.payload.target.record_id
                    )
                )
            ):
                raise OdooGatewayError("malformed_response")
            exact_match = (
                verification.state in {"sale", "done"}
                if isinstance(verification, BusinessActionVerificationResult)
                else verification.after == expected_after
            )
            if verification.matches is not exact_match:
                raise OdooGatewayError("malformed_response")
            if exact_match:
                evidence_id = self._uuid_factory()
                evidence = Evidence(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.RECORD,
                    status=EvidenceStatus.CHECKED,
                    title=f"Verified ACTION result: {proposal.payload.target.model}",
                    summary=(
                        "The curated action outcome was reread under the approving Odoo user."
                        if isinstance(verification, BusinessActionVerificationResult)
                        else "Affected fields were reread under the approving Odoo user."
                    ),
                    payload={
                        "after": (
                            {"state": verification.state}
                            if isinstance(verification, BusinessActionVerificationResult)
                            else verification.model_dump(mode="json")["after"]
                        ),
                        "action_id": (
                            proposal.payload.action_id
                            if isinstance(proposal.payload, BusinessActionProposalPayload)
                            else None
                        ),
                        "model": proposal.payload.target.model,
                        "record_id": record_id,
                    },
                    pointer={
                        "model": proposal.payload.target.model,
                        "record_id": record_id,
                        "provider": "odoo_action_verify",
                    },
                    observed_at=verification.verified_at,
                    sensitivity=EvidenceSensitivity.NORMAL,
                    fingerprint=proposal.payload_fingerprint,
                )
                return self._finish(
                    proposal,
                    attempt_id,
                    ActionProposalState.VERIFIED,
                    expected=(expected,),
                    evidence_id=evidence_id,
                    evidence=evidence,
                    verification_payload=evidence.model_dump(mode="json"),
                )
            state = (
                ActionProposalState.COMMITTED_UNVERIFIED
                if commit_confirmed
                else ActionProposalState.EXECUTION_UNKNOWN
            )
            return self._finish(
                proposal,
                attempt_id,
                state,
                expected=(expected,),
                error_code="verification_mismatch",
                verification_payload=verification.model_dump(mode="json"),
            )
        except (_ActionTokenError, OdooGatewayError):
            state = (
                ActionProposalState.COMMITTED_UNVERIFIED
                if commit_confirmed
                else ActionProposalState.EXECUTION_UNKNOWN
            )
            return self._finish(
                proposal,
                attempt_id,
                state,
                expected=(expected,),
                error_code="verification_unavailable",
            )

    def _token(
        self,
        proposal: StoredActionProposal,
        attempt_id: UUID,
        scope: Literal[
            "action_commit",
            "action_verify",
            "action_create_commit",
            "action_create_verify",
            "business_action_commit",
            "business_action_verify",
        ],
    ) -> str:
        now = self._now()
        expires = min(now + timedelta(seconds=60), proposal.preview.expires_at)
        if expires <= now:
            raise _ActionTokenError
        payload = proposal.payload
        if isinstance(payload, ActionProposalPayload):
            action_kind = ActionKind.RECORD_PATCH
            action_id = None
            record_id: int | None = payload.target.record_id
            fields = tuple(sorted(change.field for change in payload.changes))
            effective_scope = scope
            revision = payload.schema_revision
        elif not isinstance(payload, BusinessActionProposalPayload):
            action_kind = ActionKind.RECORD_CREATE
            action_id = None
            record_id = None
            fields = tuple(sorted(value.field for value in payload.values))
            effective_scope = (
                "action_create_commit" if scope == "action_commit" else "action_create_verify"
            )
            revision = payload.schema_revision
        else:
            action_kind = ActionKind.BUSINESS_ACTION
            action_id = payload.action_id
            record_id = payload.target.record_id
            fields = ("state",)
            effective_scope = (
                "business_action_commit" if scope == "action_commit" else "business_action_verify"
            )
            revision = payload.action_spec_revision
        claims = ActionAuthorityClaims(
            action_kind=action_kind,
            action_id=action_id,
            jti=secrets.token_urlsafe(18),
            proposal_id=payload.proposal_id,
            approval_id=cast(UUID, proposal.approval_id),
            attempt_id=attempt_id,
            instance_id=payload.instance_id,
            database=payload.database,
            uid=payload.uid,
            company_id=payload.company_id,
            allowed_company_ids=payload.allowed_company_ids,
            model=payload.target.model,
            record_id=record_id,
            fields=fields,
            payload_fingerprint=proposal.payload_fingerprint,
            precondition_fingerprint=proposal.preview.precondition_fingerprint,
            policy_revision=payload.policy_revision,
            schema_revision=revision,
            scopes=(effective_scope,),
            issued_at=int(now.timestamp()),
            expires_at=int(expires.timestamp()),
        )
        try:
            return self._codec.encode(claims)
        except Exception:
            raise _ActionTokenError from None

    def _finish(
        self,
        proposal: StoredActionProposal,
        attempt_id: UUID,
        state: ActionProposalState,
        *,
        expected: tuple[ActionProposalState, ...] = (ActionProposalState.EXECUTING,),
        evidence_id: UUID | None = None,
        evidence: Evidence | None = None,
        error_code: str | None = None,
        verification_payload: dict[str, object] | None = None,
    ) -> ActionExecutionReceipt:
        completed_at = self._now()
        stored = self._transition(
            proposal,
            attempt_id,
            expected,
            state,
            evidence_id=evidence_id,
            error_code=error_code,
            verification_payload=verification_payload,
            occurred_at=completed_at,
        )
        return ActionExecutionReceipt(
            proposal_id=proposal.payload.proposal_id,
            approval_id=cast(UUID, proposal.approval_id),
            attempt_id=attempt_id,
            state=cast(
                Literal[
                    ActionProposalState.VERIFIED,
                    ActionProposalState.STALE,
                    ActionProposalState.FAILED,
                    ActionProposalState.EXECUTION_UNKNOWN,
                    ActionProposalState.COMMITTED_UNVERIFIED,
                ],
                stored.state,
            ),
            payload_fingerprint=proposal.payload_fingerprint,
            completed_at=completed_at,
            evidence_id=evidence_id,
            evidence=evidence,
            error_code=error_code,
        )

    def _transition(
        self,
        proposal: StoredActionProposal,
        attempt_id: UUID,
        expected: tuple[ActionProposalState, ...],
        state: ActionProposalState,
        *,
        occurred_at: datetime | None = None,
        evidence_id: UUID | None = None,
        error_code: str | None = None,
        verification_payload: dict[str, object] | None = None,
    ) -> StoredActionProposal:
        try:
            return self._store.transition_execution(
                proposal_id=proposal.payload.proposal_id,
                attempt_id=attempt_id,
                expected_states=expected,
                state=state,
                occurred_at=occurred_at or self._now(),
                evidence_id=evidence_id,
                error_code=error_code,
                verification_payload=verification_payload,
            )
        except Exception:
            raise ActionExecutionError("approval_store_unavailable", 503) from None

    def _raise_claim(self, outcome: ActionDecisionOutcome) -> Never:
        if outcome is ActionDecisionOutcome.NOT_FOUND:
            raise ActionExecutionError("approval_not_found", 404)
        if outcome is ActionDecisionOutcome.BINDING_MISMATCH:
            raise ActionExecutionError("approval_binding_mismatch", 403)
        if outcome is ActionDecisionOutcome.EXPIRED:
            raise ActionExecutionError("approval_expired", 410)
        raise ActionExecutionError("approval_already_consumed")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ActionExecutionError("clock_unavailable", 503)
        return value.astimezone(UTC)
