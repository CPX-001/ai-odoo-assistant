"""Validate b1 and execute exact batch chunks idempotently under the real Odoo user."""

from __future__ import annotations

import hmac
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from odoo import api
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.modules.registry import Registry

from ..security.batch_authority import BatchAuthorityCodec, BatchAuthorityPayload
from ..security.delegation import DelegationTokenError
from .action_tools import (
    _BLOCKED_FIELDS,
    _BLOCKED_MODELS,
    _BLOCKED_MODEL_PREFIXES,
    _SENSITIVE_FIELD_PARTS,
    _VALUE_KIND_BY_FIELD_TYPE,
    _orm_write_value,
)
from .batch_payload import (
    MAX_BATCH_FIELDS,
    MAX_BATCH_ROWS,
    batch_fields,
    canonical_json,
    chunk_fingerprint,
    item_fingerprint,
    parse_batch,
    values_for_field,
)
from .batch_tools import (
    ATOMIC_CHUNK,
    execute_create_chunk,
    execute_delete_chunk,
    execute_uniform_patch_chunk,
)
from .orm_tools import OrmToolError

# Compatibility aliases for focused addon tests and internal callers. Canonical
# implementations live in batch_payload so preflight and commit cannot drift.
_batch = parse_batch
_chunk_fingerprint = chunk_fingerprint
_item_fingerprint = item_fingerprint
_canonical_json = canonical_json


class BatchEnvironmentProvider(Protocol):
    def __call__(self, claims: BatchAuthorityPayload) -> AbstractContextManager[object]: ...


class ApprovedBatchMutationExecutor:
    """Commit exactly one signed chunk; receipts make retransmission idempotent."""

    def __init__(
        self,
        *,
        codec: BatchAuthorityCodec,
        environment_provider: BatchEnvironmentProvider | None = None,
    ) -> None:
        self._codec = codec
        self._environment_provider = environment_provider or _runtime_batch_environment

    def commit(self, *, authority_token: str, batch: object) -> dict[str, object]:
        parsed = parse_batch(batch)
        try:
            claims = self._codec.decode(authority_token)
        except DelegationTokenError:
            raise OrmToolError("delegation_rejected", 403) from None
        _require_authority(parsed, claims)
        try:
            with self._environment_provider(claims) as env:
                _validate_runtime_fields(env, parsed, claims)
                results = _execute_with_receipts(env, parsed, claims)
        except OrmToolError:
            raise
        except (AccessError, MissingError):
            raise OrmToolError("access_denied", 403) from None
        except ValidationError:
            raise OrmToolError("business_rule_rejected", 409) from None
        return {
            "attempt_id": str(claims.attempt_id),
            "chunk_fingerprint": claims.chunk_fingerprint,
            "job_id": str(claims.job_id),
            "ok": True,
            "results": list(results),
        }


def _execute_with_receipts(env, batch: dict[str, object], claims: BatchAuthorityPayload):
    receipt_model = env["odoo.ai.batch.execution"]
    new_rows = []
    results_by_ref: dict[str, dict[str, object]] = {}
    receipts_by_ref = {}
    for item in batch["items"]:
        fingerprint = item_fingerprint(item)
        receipt, is_new = receipt_model._claim(
            job_id=claims.job_id,
            attempt_id=claims.attempt_id,
            authorization_id=claims.authorization_id,
            job_fingerprint=claims.job_fingerprint,
            operation=claims.operation,
            target_model=claims.model,
            source_ref=item["source_ref"],
            item_fingerprint=fingerprint,
        )
        receipt = receipt._internal()
        if is_new:
            new_rows.append(item)
            receipts_by_ref[item["source_ref"]] = receipt
            continue
        try:
            results_by_ref[item["source_ref"]] = receipt._result()
        except ValidationError:
            raise OrmToolError("execution_in_progress", 409) from None

    if batch["failure_mode"] == ATOMIC_CHUNK and results_by_ref and new_rows:
        raise OrmToolError("batch_atomic_resume_mismatch", 409)

    if new_rows:
        if batch["operation"] == "create":
            raw_results = execute_create_chunk(
                env,
                model=batch["model"],
                rows=tuple(
                    (item["source_ref"], _orm_values(item["values"]))
                    for item in new_rows
                ),
                failure_mode=batch["failure_mode"],
            )
        elif batch["operation"] == "patch":
            signatures = {canonical_json(item["changes"]) for item in new_rows}
            if len(signatures) != 1:
                raise OrmToolError("batch_patch_not_uniform", 422)
            raw_results = execute_uniform_patch_chunk(
                env,
                model=batch["model"],
                rows=tuple(
                    (item["source_ref"], item["record_id"])
                    for item in new_rows
                ),
                values=_orm_values(new_rows[0]["changes"]),
                failure_mode=batch["failure_mode"],
            )
        else:
            raw_results = execute_delete_chunk(
                env,
                model=batch["model"],
                rows=tuple(
                    (item["source_ref"], item["record_id"])
                    for item in new_rows
                ),
                failure_mode=batch["failure_mode"],
            )
        for result in raw_results:
            receipt = receipts_by_ref[result["source_ref"]]
            if result["state"] == "applied":
                receipt._complete_applied(record_id=result["record_id"])
            else:
                receipt._complete_failed(error_code=result["error_code"])
            results_by_ref[result["source_ref"]] = receipt._result()

    ordered = tuple(results_by_ref[item["source_ref"]] for item in batch["items"])
    if len(ordered) != len(batch["items"]):
        raise OrmToolError("invalid_batch_result", 502)
    return ordered


def _validate_runtime_fields(env, batch: dict[str, object], claims: BatchAuthorityPayload) -> None:
    model = batch["model"]
    if model in _BLOCKED_MODELS or any(
        model.startswith(prefix) for prefix in _BLOCKED_MODEL_PREFIXES
    ):
        raise OrmToolError("action_target_not_allowed", 403)
    model_set = env[model]
    if batch["operation"] == "delete":
        model_set.browse().check_access("unlink")
        return
    fields = claims.fields
    if not fields or fields != batch_fields(batch):
        raise OrmToolError("scope_denied", 403)
    model_set.check_field_access_rights("write", list(fields))
    if batch["operation"] == "create":
        model_set.browse().check_access("create")
    else:
        model_set.browse().check_access("write")
    descriptions = model_set.fields_get(
        list(fields),
        attributes=["type", "readonly", "required", "relation", "selection"],
    )
    if not isinstance(descriptions, dict) or set(descriptions) != set(fields):
        raise OrmToolError("field_not_allowed", 403)
    for field in fields:
        if field in _BLOCKED_FIELDS or any(
            part in field.lower() for part in _SENSITIVE_FIELD_PARTS
        ):
            raise OrmToolError("field_not_allowed", 403)
        description = descriptions[field]
        expected_kind = _VALUE_KIND_BY_FIELD_TYPE.get(description.get("type"))
        if expected_kind is None or description.get("readonly") is not False:
            raise OrmToolError("field_not_allowed", 403)
        for tagged in values_for_field(batch["items"], field):
            if tagged["kind"] != expected_kind:
                raise OrmToolError("write_schema_mismatch", 409)
            value = tagged["value"]
            if description.get("required") is True and (
                value is None or expected_kind == "text" and value == ""
            ):
                raise OrmToolError("invalid_action", 422)
            if expected_kind == "selection" and value is not None:
                options = description.get("selection") or []
                allowed = {
                    option[0]
                    for option in options
                    if isinstance(option, (list, tuple))
                    and len(option) == 2
                    and isinstance(option[0], str)
                }
                if value not in allowed:
                    raise OrmToolError("invalid_action", 422)
            if expected_kind == "many2one" and value is not None:
                relation = description.get("relation")
                if not isinstance(relation, str):
                    raise OrmToolError("field_not_allowed", 403)
                related = env[relation].browse([value])
                related.check_access("read")
                if len(related.exists()) != 1:
                    raise OrmToolError("access_denied", 403)


def _orm_values(assignments) -> dict[str, object]:
    return {
        assignment["field"]: _orm_write_value(assignment["value"])
        for assignment in assignments
    }


def _require_authority(batch: dict[str, object], claims: BatchAuthorityPayload) -> None:
    fingerprint = chunk_fingerprint(batch)
    if (
        claims.scopes != ("batch_commit",)
        or claims.operation != batch["operation"]
        or claims.model != batch["model"]
        or claims.schema_id != batch["schema_id"]
        or claims.fields != batch_fields(batch)
        or claims.failure_mode != batch["failure_mode"]
        or claims.row_count != len(batch["items"])
        or not hmac.compare_digest(claims.chunk_fingerprint, fingerprint)
    ):
        raise OrmToolError("scope_denied", 403)


@contextmanager
def _runtime_batch_environment(claims: BatchAuthorityPayload):
    registry = Registry(claims.database)
    with registry.cursor() as cursor:
        environment = api.Environment(
            cursor,
            claims.uid,
            {
                "allowed_company_ids": list(claims.allowed_company_ids),
                "company_id": claims.company_id,
            },
            su=False,
        )
        if environment.su or environment.cr.dbname != claims.database:
            raise OrmToolError("delegation_rejected", 403)
        yield environment
