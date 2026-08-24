"""Efficient Odoo ORM chunk execution for already-validated batch mutations.

This helper deliberately owns execution mechanics only. Callers must resolve the
runtime schema, typed values and delegated user environment before invoking it.
No method uses sudo, direct SQL or caller-provided arbitrary method names.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Final

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

CONTINUE_ON_ERROR: Final = "continue_on_error"
ATOMIC_CHUNK: Final = "atomic_chunk"
_FAILURE_MODES: Final = frozenset({CONTINUE_ON_ERROR, ATOMIC_CHUNK})


class BatchOrmError(ValueError):
    """Sanitized validation error at the internal batch execution boundary."""



def execute_create_chunk(env, *, model: str, rows: Iterable[tuple[str, dict]], failure_mode: str):
    normalized = _rows(rows)
    _failure_mode(failure_mode)
    model_set = env[model]

    def bulk():
        model_set.browse().check_access("create")
        created = model_set.create([dict(values) for _, values in normalized])
        if len(created) != len(normalized):
            raise BatchOrmError("invalid_batch_result")
        return tuple(
            _applied(source_ref, record.id)
            for (source_ref, _), record in zip(normalized, created, strict=True)
        )

    return _bulk_or_rows(
        env,
        normalized,
        bulk=bulk,
        failure_mode=failure_mode,
        one=lambda row: _create_one(model_set, row),
    )


def execute_uniform_patch_chunk(
    env,
    *,
    model: str,
    rows: Iterable[tuple[str, int]],
    values: dict,
    failure_mode: str,
):
    normalized = _target_rows(rows)
    _failure_mode(failure_mode)
    if not isinstance(values, dict) or not values:
        raise BatchOrmError("invalid_batch_values")
    model_set = env[model]

    def bulk():
        record_ids = [record_id for _, record_id in normalized]
        records = model_set.browse(record_ids)
        records.check_access("write")
        _require_all_exist(records, record_ids)
        records.write(dict(values))
        return tuple(_applied(source_ref, record_id) for source_ref, record_id in normalized)

    return _bulk_or_rows(
        env,
        normalized,
        bulk=bulk,
        failure_mode=failure_mode,
        one=lambda row: _patch_one(model_set, row, values),
    )


def execute_delete_chunk(env, *, model: str, rows: Iterable[tuple[str, int]], failure_mode: str):
    normalized = _target_rows(rows)
    _failure_mode(failure_mode)
    model_set = env[model]

    def bulk():
        record_ids = [record_id for _, record_id in normalized]
        records = model_set.browse(record_ids)
        records.check_access("unlink")
        _require_all_exist(records, record_ids)
        records.unlink()
        return tuple(_applied(source_ref, record_id) for source_ref, record_id in normalized)

    return _bulk_or_rows(
        env,
        normalized,
        bulk=bulk,
        failure_mode=failure_mode,
        one=lambda row: _delete_one(model_set, row),
    )


def _bulk_or_rows(env, rows, *, bulk: Callable, failure_mode: str, one: Callable):
    try:
        with env.cr.savepoint():
            return bulk()
    except Exception as error:  # noqa: BLE001 - sanitized below
        code = _error_code(error)
        if failure_mode == ATOMIC_CHUNK:
            return tuple(_failed(row[0], code) for row in rows)

    results = []
    for row in rows:
        try:
            with env.cr.savepoint():
                results.append(one(row))
        except Exception as error:  # noqa: BLE001 - row errors must not stop the chunk
            results.append(_failed(row[0], _error_code(error)))
    return tuple(results)


def _create_one(model_set, row):
    source_ref, values = row
    model_set.browse().check_access("create")
    created = model_set.create(dict(values))
    if len(created) != 1 or type(created.id) is not int or created.id <= 0:
        raise BatchOrmError("invalid_batch_result")
    return _applied(source_ref, created.id)


def _patch_one(model_set, row, values):
    source_ref, record_id = row
    record = model_set.browse([record_id])
    record.check_access("write")
    _require_all_exist(record, [record_id])
    record.write(dict(values))
    return _applied(source_ref, record_id)


def _delete_one(model_set, row):
    source_ref, record_id = row
    record = model_set.browse([record_id])
    record.check_access("unlink")
    _require_all_exist(record, [record_id])
    record.unlink()
    return _applied(source_ref, record_id)


def _require_all_exist(records, record_ids):
    existing = records.exists()
    existing_ids = tuple(existing.ids)
    if tuple(record_ids) != existing_ids:
        raise MissingError("batch target missing")


def _rows(rows):
    normalized = tuple(rows)
    if not normalized:
        raise BatchOrmError("empty_batch_chunk")
    refs = []
    for source_ref, values in normalized:
        if not _source_ref(source_ref) or not isinstance(values, dict) or not values:
            raise BatchOrmError("invalid_batch_row")
        refs.append(source_ref)
    if len(refs) != len(set(refs)):
        raise BatchOrmError("duplicate_batch_source_ref")
    return normalized


def _target_rows(rows):
    normalized = tuple(rows)
    if not normalized:
        raise BatchOrmError("empty_batch_chunk")
    refs = []
    ids = []
    for source_ref, record_id in normalized:
        if not _source_ref(source_ref) or type(record_id) is not int or record_id <= 0:
            raise BatchOrmError("invalid_batch_row")
        refs.append(source_ref)
        ids.append(record_id)
    if len(refs) != len(set(refs)) or len(ids) != len(set(ids)):
        raise BatchOrmError("duplicate_batch_target")
    return normalized


def _source_ref(value):
    return isinstance(value, str) and 1 <= len(value) <= 128 and value == value.strip()


def _failure_mode(value):
    if value not in _FAILURE_MODES:
        raise BatchOrmError("invalid_batch_failure_mode")


def _error_code(error: Exception) -> str:
    if isinstance(error, (AccessError, MissingError)):
        return "access_denied"
    if isinstance(error, (UserError, ValidationError)):
        return "business_rule_rejected"
    if isinstance(error, BatchOrmError):
        return str(error)
    if isinstance(error, ValueError):
        return "invalid_action"
    return "operation_failed"


def _applied(source_ref: str, record_id: int):
    return {
        "source_ref": source_ref,
        "state": "applied",
        "record_id": record_id,
        "error_code": None,
    }


def _failed(source_ref: str, code: str):
    return {
        "source_ref": source_ref,
        "state": "failed",
        "record_id": None,
        "error_code": code,
    }
