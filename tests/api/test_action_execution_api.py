import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response

from odoo_ai.api import create_app
from odoo_ai.contracts import (
    ActionExecutionReceipt,
    ActionProposalState,
    ExecuteApprovedActionRequest,
)
from odoo_ai.security import SHARED_SECRET_HEADER

SECRET = "action-execution-api-secret-" + "x" * 48
APPROVAL_ID = UUID("44444444-4444-4444-8444-444444444444")


class FakeExecutionService:
    def __init__(self) -> None:
        self.requests: list[ExecuteApprovedActionRequest] = []

    async def execute(
        self, request: ExecuteApprovedActionRequest
    ) -> ActionExecutionReceipt:
        self.requests.append(request)
        return ActionExecutionReceipt(
            proposal_id=UUID("11111111-1111-4111-8111-111111111111"),
            approval_id=request.approval_id,
            attempt_id=UUID("55555555-5555-4555-8555-555555555555"),
            state=ActionProposalState.VERIFIED,
            payload_fingerprint="action-payload:v1:sha256:" + "a" * 64,
            completed_at=datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
            evidence_id=UUID("66666666-6666-4666-8666-666666666666"),
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "shared-secret"
    path.write_text(SECRET, encoding="utf-8")
    path.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(path))


def _payload(**extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "approval_id": str(APPROVAL_ID),
        "actor": {
            "instance_id": "odoo-production",
            "database": "acme",
            "uid": 17,
            "company_id": 1,
            "allowed_company_ids": [1, 3],
        },
    }
    result.update(extra)
    return result


async def _post(
    service: FakeExecutionService, payload: dict[str, object], *, auth: bool = True
) -> Response:
    app = create_app(action_execution_service=service)  # type: ignore[arg-type]
    transport = ASGITransport(app=app)
    headers = {SHARED_SECRET_HEADER: SECRET} if auth else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/v1/actions/commits", json=payload, headers=headers)


def test_commit_endpoint_accepts_only_opaque_approval_and_server_actor() -> None:
    service = FakeExecutionService()

    response = asyncio.run(_post(service, _payload()))
    tampered = asyncio.run(_post(service, _payload(values={"name": "evil"})))
    unauthenticated = asyncio.run(_post(service, _payload(), auth=False))

    assert response.status_code == 200
    assert response.json()["state"] == "verified"
    assert tampered.status_code == 422
    assert unauthenticated.status_code == 401
    assert len(service.requests) == 1
