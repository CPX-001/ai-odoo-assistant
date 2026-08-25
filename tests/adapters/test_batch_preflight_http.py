from __future__ import annotations

import asyncio
import json
from uuid import UUID

import pytest
from odoo_ai.adapters.batch_preflight_http import (
    BatchPreflightOdooGatewayFactory,
    HttpBatchPreflightGateway,
)
from odoo_ai.adapters.odoo_http import OdooGatewayError, OdooGatewaySettings
from odoo_ai.contracts.batch import (
    BatchDeleteItem,
    BatchMutationKind,
    BatchMutationRequest,
)

SETTINGS = OdooGatewaySettings(base_url="http://127.0.0.1:8069")
TURN_ID = UUID(int=7)


def _request() -> BatchMutationRequest:
    return BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        items=(
            BatchDeleteItem(source_ref="row:1", record_id=11),
            BatchDeleteItem(source_ref="row:2", record_id=12),
        ),
    )


def test_preflight_gateway_parses_strict_json_response(monkeypatch) -> None:
    gateway = HttpBatchPreflightGateway(
        settings=SETTINGS,
        turn_id=TURN_ID,
        delegation_token="ag1.test-token",
        machine_secret="machine-secret",
    )
    raw = json.dumps(
        {
            "ok": True,
            "operation": "delete",
            "model": "res.partner",
            "accepted_source_refs": ["row:1"],
            "issues": [{"source_ref": "row:2", "error_code": "access_denied"}],
        }
    ).encode()
    monkeypatch.setattr(gateway, "_post_json", lambda payload: raw)

    result = asyncio.run(gateway.preflight_batch(_request()))

    assert result.operation is BatchMutationKind.DELETE
    assert result.model == "res.partner"
    assert result.accepted_source_refs == ("row:1",)
    assert result.issues[0].source_ref == "row:2"


def test_preflight_gateway_rejects_malformed_response(monkeypatch) -> None:
    gateway = HttpBatchPreflightGateway(
        settings=SETTINGS,
        turn_id=TURN_ID,
        delegation_token="ag1.test-token",
        machine_secret="machine-secret",
    )
    monkeypatch.setattr(
        gateway,
        "_post_json",
        lambda payload: b'{"ok":true,"operation":"shell","model":"res.partner"}',
    )

    with pytest.raises(OdooGatewayError, match="malformed_response"):
        asyncio.run(gateway.preflight_batch(_request()))


def test_preflight_factory_rejects_non_agent_authority() -> None:
    factory = BatchPreflightOdooGatewayFactory(
        SETTINGS,
        secret_loader=lambda: "machine-secret",
    )

    with pytest.raises(OdooGatewayError, match="invalid_turn_authority"):
        factory.for_turn(turn_id=TURN_ID, delegation_token="a1.not-agent")


def test_preflight_factory_binds_valid_agent_token_without_decoding_it() -> None:
    factory = BatchPreflightOdooGatewayFactory(
        SETTINGS,
        secret_loader=lambda: "machine-secret",
    )

    gateway = factory.for_turn(turn_id=TURN_ID, delegation_token="ag1.opaque-token")

    assert isinstance(gateway, HttpBatchPreflightGateway)
