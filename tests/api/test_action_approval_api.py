import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.application import ActionApprovalError
from odoo_ai.contracts import (
    ActionDecisionReceipt,
    ActionDecisionRequest,
    ActionProposalState,
)
from odoo_ai.security import SHARED_SECRET_HEADER

MACHINE_SECRET = "action-approval-secret-" + "s" * 48
PROPOSAL_ID = UUID("11111111-1111-4111-8111-111111111111")
APPROVAL_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
FINGERPRINT = "action-payload:v1:sha256:" + "a" * 64


class FakeApprovalService:
    def __init__(self, *, error: ActionApprovalError | None = None) -> None:
        self.error = error
        self.decisions: list[ActionDecisionRequest] = []

    def decide(self, request: ActionDecisionRequest) -> ActionDecisionReceipt:
        self.decisions.append(request)
        if self.error is not None:
            raise self.error
        return ActionDecisionReceipt(
            proposal_id=request.proposal_id,
            approval_id=APPROVAL_ID,
            state=ActionProposalState.APPROVED,
            payload_fingerprint=FINGERPRINT,
            decided_by_uid=request.actor.uid,
            decided_at=NOW,
            expires_at=NOW + timedelta(minutes=2),
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(MACHINE_SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


def _decision_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "proposal_id": str(PROPOSAL_ID),
        "decision": "approve",
        "actor": {
            "instance_id": "odoo-production",
            "database": "acme",
            "uid": 17,
            "company_id": 1,
            "allowed_company_ids": [1, 3],
        },
    }
    payload.update(updates)
    return payload


async def _post(
    service: FakeApprovalService,
    payload: dict[str, object],
    *,
    authenticated: bool = True,
) -> Response:
    transport = ASGITransport(app=create_app(action_approval_service=service))  # type: ignore[arg-type]
    headers = {SHARED_SECRET_HEADER: MACHINE_SECRET} if authenticated else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/v1/actions/decisions",
            json=payload,
            headers=headers,
        )


def test_authenticated_minimal_decision_returns_opaque_approval() -> None:
    service = FakeApprovalService()

    response = asyncio.run(_post(service, _decision_payload()))

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": str(PROPOSAL_ID),
        "approval_id": str(APPROVAL_ID),
        "state": "approved",
        "payload_fingerprint": FINGERPRINT,
        "decided_by_uid": 17,
        "decided_at": "2026-08-23T12:00:00Z",
        "expires_at": "2026-08-23T12:02:00Z",
    }
    assert len(service.decisions) == 1


def test_decision_rejects_unauthenticated_and_replacement_values() -> None:
    service = FakeApprovalService()

    unauthenticated = asyncio.run(
        _post(service, _decision_payload(), authenticated=False)
    )
    tampered = asyncio.run(
        _post(service, _decision_payload(values={"client_order_ref": "evil"}))
    )

    assert unauthenticated.status_code == 401
    assert tampered.status_code == 422
    assert tampered.json() == {"error": {"code": "invalid_request"}, "ok": False}
    assert service.decisions == []


def test_decision_maps_sanitized_state_machine_error() -> None:
    service = FakeApprovalService(
        error=ActionApprovalError("proposal_already_decided", 409)
    )

    response = asyncio.run(_post(service, _decision_payload()))

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "proposal_already_decided"},
        "ok": False,
    }
