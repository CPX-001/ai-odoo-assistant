import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.contracts import (
    ContextReadTurnRequest,
    DelegationClaims,
    DelegationScope,
    OdooGatewayReference,
    ScreenContext,
    UserExecutionContext,
    export_public_json_schemas,
)

TURN_ID = UUID("12345678-1234-5678-1234-567812345678")


def _claims(**overrides: object) -> DelegationClaims:
    values = {
        "format_version": 1,
        "jti": "jti_0123456789abcdefghij",
        "turn_id": TURN_ID,
        "database": "customer-db",
        "uid": 17,
        "company_id": 3,
        "allowed_company_ids": [3, 5],
        "lang": "es_ES",
        "model": "sale.order",
        "record_ids": [4832],
        "scopes": [DelegationScope.FIELDS_GET, DelegationScope.READ_RECORDS],
        "issued_at": 1_787_337_600,
        "expires_at": 1_787_337_660,
        "max_records": 1,
        "max_fields": 32,
    }
    values.update(overrides)
    return DelegationClaims.model_validate(values)


def test_m2_claims_are_strict_bounded_and_serializable() -> None:
    claims = _claims()

    serialized = claims.model_dump_json()
    assert DelegationClaims.model_validate_json(serialized) == claims
    assert json.loads(serialized)["scopes"] == ["fields_get", "read_records"]

    with pytest.raises(ValidationError):
        _claims(record_ids=list(range(1, 10)))
    with pytest.raises(ValidationError):
        _claims(uid=True)
    with pytest.raises(ValidationError):
        _claims(admin=True)


def test_context_read_request_reuses_screen_and_server_identity() -> None:
    token = "v1.opaque.signature"
    request = ContextReadTurnRequest(
        turn_id=TURN_ID,
        message="¿Qué estado tiene este pedido?",
        screen=ScreenContext(
            model="sale.order",
            res_id=4832,
            captured_at=datetime(2026, 8, 21, tzinfo=UTC),
        ),
        user=UserExecutionContext(
            uid=17,
            company_id=3,
            allowed_company_ids=[3, 5],
            lang="es_ES",
        ),
        delegation_token=token,
        gateway=OdooGatewayReference(database="customer-db"),
    )

    assert request.screen.model == "sale.order"
    assert request.user.uid == 17
    assert request.delegation_token.get_secret_value() == token
    assert token not in repr(request)
    assert token not in request.model_dump_json()


def test_public_schema_export_contains_m2_transport_contracts() -> None:
    schemas = export_public_json_schemas()

    assert {"ContextReadTurnRequest", "DelegationClaims", "OdooGatewayReference"} <= set(
        schemas
    )
    serialized = json.dumps(schemas, sort_keys=True)
    assert "delegation_token" in serialized
    assert '"writeOnly": true' in serialized
