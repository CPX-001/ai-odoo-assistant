import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response

from odoo_ai.api import create_app
from odoo_ai.contracts import (
    ActionCommandReceipt,
    ActionDecisionCommandRequest,
    ActionProposalState,
)
from odoo_ai.security import SHARED_SECRET_HEADER

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PROPOSAL_ID = UUID("f0000000-0000-4000-8000-00000000000f")
SECRET = "action-command-secret-" + "s" * 48


class StubCommandService:
    def __init__(self) -> None:
        self.requests: list[ActionDecisionCommandRequest] = []

    async def decide_and_execute(
        self, request: ActionDecisionCommandRequest
    ) -> ActionCommandReceipt:
        self.requests.append(request)
        return ActionCommandReceipt(
            proposal_id=request.proposal_id,
            state=ActionProposalState.REJECTED,
            payload_fingerprint="action-payload:v1:sha256:" + "a" * 64,
            completed_at=NOW,
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "shared-secret"
    path.write_text(SECRET, encoding="utf-8")
    path.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(path))


def _payload(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "proposal_id": str(PROPOSAL_ID),
        "decision": "reject",
        "actor": {
            "database": "fixture-db",
            "uid": 17,
            "company_id": 3,
            "allowed_company_ids": [3],
        },
    }
    result.update(updates)
    return result


async def _post(app: object, payload: dict[str, object], *, auth: bool = True) -> Response:
    transport = ASGITransport(app=app)
    headers = {SHARED_SECRET_HEADER: SECRET} if auth else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/v1/actions/decision-execute", json=payload, headers=headers
        )


def test_command_accepts_only_minimal_decision_plus_odoo_actor() -> None:
    service = StubCommandService()
    app = create_app(action_command_service=service)  # type: ignore[arg-type]

    valid = asyncio.run(_post(app, _payload()))
    injected = asyncio.run(_post(app, _payload(values={"name": "evil"})))
    unauthenticated = asyncio.run(_post(app, _payload(), auth=False))

    assert valid.status_code == 200
    assert valid.json()["state"] == "rejected"
    assert injected.status_code == 422
    assert unauthenticated.status_code == 401
    assert len(service.requests) == 1
