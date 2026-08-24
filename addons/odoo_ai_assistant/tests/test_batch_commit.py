from __future__ import annotations

import base64
import hashlib
import hmac
import json
from contextlib import contextmanager
from uuid import UUID

from odoo.tests.common import TransactionCase

from ..security.batch_authority import BatchAuthorityCodec
from ..services.batch_commit import (
    ApprovedBatchMutationExecutor,
    _batch,
    _chunk_fingerprint,
)
from ..services.orm_tools import OrmToolError

_ROOT_SECRET = b"batch-odoo-test-root-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PURPOSE = b"odoo-ai-assistant/batch-authority/v1"
_NOW = 1_800_000_000
_SCHEMA_ID = "schema:v1:sha256:" + "c" * 64
_JOB_FINGERPRINT = "batch-job:v1:sha256:" + "a" * 64
_JOB_ID = UUID("10000000-0000-0000-0000-000000000001")
_ATTEMPT_ID = UUID("20000000-0000-0000-0000-000000000002")
_AUTHORIZATION_ID = UUID("30000000-0000-0000-0000-000000000003")


class TestBatchCommit(TransactionCase):
    def _executor(self):
        @contextmanager
        def environment_provider(claims):
            self.assertEqual(claims.uid, self.env.uid)
            self.assertEqual(claims.database, self.env.cr.dbname)
            yield self.env

        return ApprovedBatchMutationExecutor(
            codec=BatchAuthorityCodec(_ROOT_SECRET, clock=lambda: _NOW),
            environment_provider=environment_provider,
        )

    def _create_batch(self, name="AI BATCH IDEMPOTENCY"):
        return {
            "operation": "create",
            "model": "res.partner",
            "schema_id": _SCHEMA_ID,
            "failure_mode": "continue_on_error",
            "items": [
                {
                    "operation": "create",
                    "source_ref": "sheet1:2",
                    "values": [
                        {
                            "field": "name",
                            "value": {"kind": "text", "value": name},
                        }
                    ],
                }
            ],
        }

    def _token(self, batch):
        company_id = self.env.company.id
        raw = {
            "allowed_company_ids": [company_id],
            "attempt_id": str(_ATTEMPT_ID),
            "authorization_id": str(_AUTHORIZATION_ID),
            "chunk_fingerprint": _chunk_fingerprint(_batch(batch)),
            "company_id": company_id,
            "database": self.env.cr.dbname,
            "expires_at": _NOW + 60,
            "failure_mode": batch["failure_mode"],
            "fields": ["name"],
            "format_version": 1,
            "instance_id": "odoo-test-instance",
            "issued_at": _NOW,
            "job_fingerprint": _JOB_FINGERPRINT,
            "job_id": str(_JOB_ID),
            "jti": "batchCommitJti_0123456789",
            "model": batch["model"],
            "operation": batch["operation"],
            "policy_revision": "batch-policy-v1",
            "row_count": len(batch["items"]),
            "schema_id": batch["schema_id"],
            "scopes": ["batch_commit"],
            "uid": self.env.uid,
        }
        payload = json.dumps(
            raw,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        encoded = _b64(payload)
        signed = f"b1.{encoded}".encode("ascii")
        key = hmac.digest(_ROOT_SECRET, _PURPOSE, hashlib.sha256)
        signature = _b64(hmac.digest(key, signed, hashlib.sha256))
        return f"b1.{encoded}.{signature}"

    def test_retransmission_returns_same_receipt_without_duplicate_create(self):
        batch = self._create_batch()
        token = self._token(batch)
        partners = self.env["res.partner"]
        before = partners.search_count([("name", "=", "AI BATCH IDEMPOTENCY")])

        first = self._executor().commit(authority_token=token, batch=batch)
        second = self._executor().commit(authority_token=token, batch=batch)

        self.assertEqual(first["results"], second["results"])
        self.assertEqual(first["results"][0]["state"], "applied")
        self.assertGreater(first["results"][0]["record_id"], 0)
        after = partners.search_count([("name", "=", "AI BATCH IDEMPOTENCY")])
        self.assertEqual(after - before, 1)

    def test_signed_chunk_rejects_body_tampering(self):
        batch = self._create_batch()
        token = self._token(batch)
        tampered = self._create_batch(name="CHANGED AFTER AUTHORIZATION")

        with self.assertRaisesRegex(OrmToolError, "scope_denied"):
            self._executor().commit(authority_token=token, batch=tampered)

    def test_parser_accepts_sixty_four_typed_fields(self):
        batch = self._create_batch()
        batch["items"][0]["values"] = [
            {
                "field": f"field_{index:02d}",
                "value": {"kind": "text", "value": str(index)},
            }
            for index in range(64)
        ]

        parsed = _batch(batch)

        self.assertEqual(len(parsed["items"][0]["values"]), 64)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
