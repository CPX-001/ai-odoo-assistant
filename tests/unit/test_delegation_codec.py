import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from odoo_ai.contracts import (
    ActionPreviewDelegationClaims as TransportActionPreviewDelegationClaims,
)
from odoo_ai.contracts import (
    DelegationClaims as TransportDelegationClaims,
)
from odoo_ai.contracts import (
    QueryDelegationClaims as TransportQueryDelegationClaims,
)


def _load_delegation_module() -> ModuleType:
    path = Path(__file__).parents[2] / "addons/odoo_ai_assistant/security/delegation.py"
    spec = importlib.util.spec_from_file_location("odoo_ai_test_delegation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


delegation = _load_delegation_module()
DelegationCodec = delegation.DelegationCodec
DelegationPayload = delegation.DelegationPayload
DelegationTokenError = delegation.DelegationTokenError
QueryDelegationCodec = delegation.QueryDelegationCodec
QueryDelegationPayload = delegation.QueryDelegationPayload
ActionPreviewDelegationCodec = delegation.ActionPreviewDelegationCodec
ActionPreviewDelegationPayload = delegation.ActionPreviewDelegationPayload

NOW = 1_787_337_600
SECRET = b"addon-only-delegation-secret-" + b"s" * 48
OTHER_SECRET = b"different-addon-delegation-secret-" + b"x" * 48


def _payload(**overrides: object):
    values = {
        "format_version": 1,
        "jti": "jti_0123456789abcdefghij",
        "turn_id": UUID("12345678-1234-5678-1234-567812345678"),
        "database": "customer-db",
        "uid": 17,
        "company_id": 3,
        "allowed_company_ids": (3, 5),
        "lang": "es_ES",
        "model": "sale.order",
        "record_ids": (4832,),
        "scopes": ("fields_get", "read_records"),
        "issued_at": NOW,
        "expires_at": NOW + 60,
        "max_records": 1,
        "max_fields": 32,
    }
    values.update(overrides)
    return DelegationPayload(**values)


def _codec(secret: bytes = SECRET, *, now: int = NOW):
    return DelegationCodec(secret, clock=lambda: now)


def _query_payload(**overrides: object):
    values = {
        "format_version": 1,
        "jti": "query_0123456789abcdefgh",
        "turn_id": UUID("12345678-1234-5678-1234-567812345678"),
        "database": "customer-db",
        "uid": 17,
        "company_id": 3,
        "allowed_company_ids": (3, 5),
        "lang": "es_ES",
        "model": "sale.order",
        "allowed_fields": ("id", "amount_total", "name", "partner_id"),
        "scopes": ("query_schema", "query_records", "aggregate_records"),
        "issued_at": NOW,
        "expires_at": NOW + 60,
        "max_records": 50,
        "max_fields": 4,
        "max_conditions": 8,
        "max_groups": 50,
        "max_aggregates": 8,
        "policy_revision": "m5-query-read-v1",
    }
    values.update(overrides)
    return QueryDelegationPayload(**values)


def _query_codec(secret: bytes = SECRET, *, now: int = NOW):
    return QueryDelegationCodec(secret, clock=lambda: now)


def _action_preview_payload(**overrides: object):
    values = {
        "format_version": 1,
        "jti": "preview_0123456789abcdefg",
        "turn_id": UUID("12345678-1234-5678-1234-567812345678"),
        "database": "customer-db",
        "uid": 17,
        "company_id": 3,
        "allowed_company_ids": (3, 5),
        "lang": "es_ES",
        "model": "sale.order",
        "record_id": 4832,
        "allowed_fields": ("client_order_ref", "partner_id"),
        "scopes": ("action_write_schema", "action_preview"),
        "issued_at": NOW,
        "expires_at": NOW + 60,
        "max_fields": 2,
        "policy_revision": "m6-record-patch-v1",
    }
    values.update(overrides)
    return ActionPreviewDelegationPayload(**values)


def _action_preview_codec(secret: bytes = SECRET, *, now: int = NOW):
    return ActionPreviewDelegationCodec(secret, clock=lambda: now)


def _resign_payload(token: str, payload: dict[str, object]) -> str:
    prefix, _, _ = token.split(".")
    payload_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    encoded = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    signed = f"{prefix}.{encoded}".encode("ascii")
    signature = __import__("hmac").digest(
        _codec()._signing_key, signed, __import__("hashlib").sha256
    )
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{prefix}.{encoded}.{encoded_signature}"


def _sign_raw_payload(payload_bytes: bytes) -> str:
    encoded = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    signed = f"v1.{encoded}".encode("ascii")
    signature = __import__("hmac").digest(
        _codec()._signing_key, signed, __import__("hashlib").sha256
    )
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"v1.{encoded}.{encoded_signature}"


def test_delegation_token_round_trip_is_deterministic() -> None:
    codec = _codec()
    token = codec.encode(_payload())

    assert codec.decode(token) == _payload()
    assert codec.encode(codec.decode(token)) == token


def test_addon_payload_matches_the_public_transport_contract() -> None:
    serialized = json.dumps(_payload().to_mapping(), sort_keys=True)
    claims = TransportDelegationClaims.model_validate_json(serialized)

    assert claims.turn_id == _payload().turn_id
    assert claims.scopes == ["fields_get", "read_records"]


def test_navigation_scope_is_explicit_and_transport_compatible() -> None:
    payload = _payload(scopes=("navigation",))
    token = _codec().encode(payload)
    claims = TransportDelegationClaims.model_validate_json(
        json.dumps(_codec().decode(token).to_mapping(), sort_keys=True)
    )

    assert claims.scopes == ["navigation"]


def test_query_authority_is_a_separate_transport_compatible_token_family() -> None:
    payload = _query_payload()
    token = _query_codec().encode(payload)
    claims = TransportQueryDelegationClaims.model_validate_json(
        json.dumps(_query_codec().decode(token).to_mapping(), sort_keys=True)
    )

    assert token.startswith("q1.")
    assert claims.model == "sale.order"
    assert claims.allowed_fields == ["id", "amount_total", "name", "partner_id"]
    assert claims.scopes == ["query_schema", "query_records", "aggregate_records"]
    with pytest.raises(DelegationTokenError, match="unknown_version"):
        _codec().decode(token)
    with pytest.raises(DelegationTokenError, match="unknown_version"):
        _query_codec().decode(_codec().encode(_payload()))


def test_action_preview_authority_is_a_third_transport_compatible_family() -> None:
    payload = _action_preview_payload()
    token = _action_preview_codec().encode(payload)
    claims = TransportActionPreviewDelegationClaims.model_validate_json(
        json.dumps(_action_preview_codec().decode(token).to_mapping(), sort_keys=True)
    )

    assert token.startswith("p1.")
    assert claims.record_id == 4832
    assert claims.allowed_fields == ["client_order_ref", "partner_id"]
    assert claims.scopes == ["action_write_schema", "action_preview"]
    with pytest.raises(DelegationTokenError, match="unknown_version"):
        _codec().decode(token)
    with pytest.raises(DelegationTokenError, match="unknown_version"):
        _query_codec().decode(token)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("allowed_fields", ("partner_id", "client_order_ref")),
        ("allowed_fields", ("partner_id", "partner_id")),
        ("record_id", 0),
        ("scopes", ("action_preview", "read_records")),
        ("max_fields", 3),
        ("policy_revision", ""),
    ],
)
def test_action_preview_authority_limits_fail_closed(claim: str, value: object) -> None:
    with pytest.raises(DelegationTokenError, match="invalid_action_preview_claims"):
        _action_preview_payload(**{claim: value})


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("allowed_fields", ("name", "id")),
        ("allowed_fields", ("id", "name", "name")),
        ("scopes", ("query_records", "read_records")),
        ("max_records", 51),
        ("max_fields", 5),
        ("max_conditions", 9),
        ("max_groups", 51),
        ("max_aggregates", 9),
    ],
)
def test_query_authority_limits_fail_closed(claim: str, value: object) -> None:
    with pytest.raises(DelegationTokenError, match="invalid_query_claims"):
        _query_payload(**{claim: value})


def test_modified_token_and_wrong_signing_key_are_rejected() -> None:
    token = _codec().encode(_payload())
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(DelegationTokenError, match="invalid_signature"):
        _codec().decode(token[:-1] + replacement)
    with pytest.raises(DelegationTokenError, match="invalid_signature"):
        _codec(OTHER_SECRET).decode(token)


def test_expired_future_and_unknown_version_tokens_are_rejected() -> None:
    token = _codec().encode(_payload())

    with pytest.raises(DelegationTokenError, match="expired"):
        _codec(now=NOW + 60).decode(token)
    with pytest.raises(DelegationTokenError, match="not_yet_valid"):
        _codec(now=NOW - 6).decode(token)
    with pytest.raises(DelegationTokenError, match="unknown_version"):
        _codec().decode("v2.a.b")


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("allowed_company_ids", tuple(range(1, 18))),
        ("record_ids", tuple(range(1, 10))),
        ("scopes", ("fields_get", "read_records", "search")),
        ("expires_at", NOW + 121),
        ("max_fields", 65),
    ],
)
def test_claim_limits_are_enforced(claim: str, value: object) -> None:
    with pytest.raises(DelegationTokenError, match="invalid_claims"):
        _payload(**{claim: value})


def test_signed_unknown_claim_is_rejected_even_with_a_valid_signature() -> None:
    codec = _codec()
    payload = _payload().to_mapping()
    payload["admin"] = 1
    token = _resign_payload(codec.encode(_payload()), payload)

    with pytest.raises(DelegationTokenError, match="invalid_claims"):
        codec.decode(token)


def test_signed_wrong_version_and_duplicate_json_claim_are_rejected() -> None:
    codec = _codec()
    wrong_version = _payload().to_mapping()
    wrong_version["format_version"] = 2
    with pytest.raises(DelegationTokenError, match="unknown_version"):
        codec.decode(_resign_payload(codec.encode(_payload()), wrong_version))

    canonical = json.dumps(
        _payload().to_mapping(),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    duplicate_uid = canonical.replace('"uid":17}', '"uid":17,"uid":18}')
    with pytest.raises(DelegationTokenError, match="noncanonical_payload"):
        codec.decode(_sign_raw_payload(duplicate_uid.encode("ascii")))


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("allowed_company_ids", (3, 3)),
        ("record_ids", (4832, 4832)),
        ("scopes", ("read_records", "read_records")),
    ],
)
def test_duplicate_authority_claims_are_rejected(claim: str, value: object) -> None:
    with pytest.raises(DelegationTokenError, match="invalid_claims"):
        _payload(**{claim: value})


def test_errors_and_codec_repr_do_not_contain_token_or_secret() -> None:
    codec = _codec()
    token = codec.encode(_payload())

    with pytest.raises(DelegationTokenError) as failure:
        _codec(OTHER_SECRET).decode(token)

    visible = f"{failure.value!r} {failure.value} {codec!r}"
    assert token not in visible
    assert SECRET.decode("ascii") not in visible


def test_secret_file_policy_matches_the_local_secret_boundary(tmp_path: Path) -> None:
    secret_file = tmp_path / "delegation-secret"
    secret_file.write_bytes(SECRET + b"\n")
    secret_file.chmod(0o640)

    assert (
        DelegationCodec.from_secret_file(secret_file, clock=lambda: NOW).decode(
            _codec().encode(_payload())
        )
        == _payload()
    )

    secret_file.chmod(0o644)
    with pytest.raises(DelegationTokenError, match="signing_key_unavailable"):
        DelegationCodec.from_secret_file(secret_file)
