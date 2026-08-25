from __future__ import annotations

from uuid import UUID

import pytest
from odoo_ai.contracts.batch import BatchFailureMode, BatchMutationKind
from odoo_ai.contracts.batch_authority import BatchAuthorityClaims
from odoo_ai.security.action_authority import ActionAuthorityCodec, ActionAuthorityError
from odoo_ai.security.batch_authority import BatchAuthorityCodec, BatchAuthorityError

ROOT_SECRET = b"batch-authority-test-root-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
NOW = 1_800_000_000
JOB_ID = UUID("10000000-0000-0000-0000-000000000001")
ATTEMPT_ID = UUID("20000000-0000-0000-0000-000000000002")
AUTHORIZATION_ID = UUID("30000000-0000-0000-0000-000000000003")
JOB_FINGERPRINT = "batch-job:v1:sha256:" + "a" * 64
CHUNK_FINGERPRINT = "batch-chunk:v1:sha256:" + "b" * 64
SCHEMA_ID = "schema:v1:sha256:" + "c" * 64


def _claims(*, fields: tuple[str, ...] = ("name",)) -> BatchAuthorityClaims:
    return BatchAuthorityClaims(
        jti="batchAuthorityJti_0123456789",
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        authorization_id=AUTHORIZATION_ID,
        job_fingerprint=JOB_FINGERPRINT,
        chunk_fingerprint=CHUNK_FINGERPRINT,
        instance_id="instance-test",
        database="odoo_test",
        uid=7,
        company_id=1,
        allowed_company_ids=(1,),
        operation=BatchMutationKind.CREATE,
        model="res.partner",
        schema_id=SCHEMA_ID,
        fields=fields,
        failure_mode=BatchFailureMode.CONTINUE_ON_ERROR,
        policy_revision="batch-policy-v1",
        row_count=2,
        issued_at=NOW,
        expires_at=NOW + 60,
    )


def test_b1_round_trip_preserves_exact_authority() -> None:
    codec = BatchAuthorityCodec(ROOT_SECRET, clock=lambda: NOW)
    claims = _claims(fields=("email", "name"))

    token = codec.encode(claims)

    assert token.startswith("b1.")
    assert codec.decode(token) == claims


def test_b1_accepts_full_batch_field_scope() -> None:
    fields = tuple(f"field_{index:02d}" for index in range(64))
    codec = BatchAuthorityCodec(ROOT_SECRET, clock=lambda: NOW)

    decoded = codec.decode(codec.encode(_claims(fields=fields)))

    assert decoded.fields == fields
    assert len(decoded.fields) == 64


def test_b1_rejects_tampering() -> None:
    codec = BatchAuthorityCodec(ROOT_SECRET, clock=lambda: NOW)
    token = codec.encode(_claims())
    prefix, payload, signature = token.split(".")
    tampered = f"{prefix}.{payload[:-1]}{'A' if payload[-1] != 'A' else 'B'}.{signature}"

    with pytest.raises(BatchAuthorityError):
        codec.decode(tampered)


def test_b1_is_not_accepted_by_action_authority_family() -> None:
    batch_codec = BatchAuthorityCodec(ROOT_SECRET, clock=lambda: NOW)
    action_codec = ActionAuthorityCodec(ROOT_SECRET, clock=lambda: NOW)

    with pytest.raises(ActionAuthorityError, match="unknown_version"):
        action_codec.decode(batch_codec.encode(_claims()))


def test_b1_expiry_is_enforced_server_side() -> None:
    issuer = BatchAuthorityCodec(ROOT_SECRET, clock=lambda: NOW)
    token = issuer.encode(_claims())
    expired = BatchAuthorityCodec(ROOT_SECRET, clock=lambda: NOW + 61)

    with pytest.raises(BatchAuthorityError, match="expired"):
        expired.decode(token)
