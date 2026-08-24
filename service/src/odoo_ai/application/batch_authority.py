"""Canonical fingerprints for exact batch chunks sent to Odoo."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from odoo_ai.contracts.action import Fingerprint
from odoo_ai.contracts.batch import BatchMutationRequest


def batch_chunk_fingerprint(request: BatchMutationRequest) -> Fingerprint:
    payload = {
        "failure_mode": request.failure_mode.value,
        "items": [item.model_dump(mode="json") for item in request.items],
        "model": request.model,
        "operation": request.operation.value,
        "schema_id": request.schema_id,
    }
    body = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return cast(
        Fingerprint,
        f"batch-chunk:v1:sha256:{hashlib.sha256(body).hexdigest()}",
    )
