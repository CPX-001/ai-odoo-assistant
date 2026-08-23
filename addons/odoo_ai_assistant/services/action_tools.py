"""Odoo-side p1 ACTION schema and preview capabilities; never commit."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol
from uuid import UUID, uuid4

from odoo import api
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.modules.registry import Registry

from ..security import (
    ActionAuthorityCodec,
    ActionAuthorityPayload,
    ActionPreviewDelegationCodec,
    ActionPreviewDelegationPayload,
    DelegationTokenError,
)
from .orm_tools import (
    MAX_METADATA_FIELDS,
    OrmToolError,
    check_response_size,
    collect_model_metadata,
    iso_datetime,
)

ACTION_POLICY_REVISION = "m6-record-patch-v1"
MAX_ACTION_FIELDS: Final = 4
MAX_ACTION_PAYLOAD_BYTES: Final = 8 * 1024
MAX_ACTION_VALUE_TEXT: Final = 4_000
_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,6})?$")
_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATETIME_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_VALUE_KIND_BY_FIELD_TYPE: Final = {
    "boolean": "boolean",
    "char": "text",
    "date": "date",
    "datetime": "datetime",
    "float": "decimal",
    "integer": "integer",
    "many2one": "many2one",
    "monetary": "decimal",
    "selection": "selection",
    "text": "text",
}
_BLOCKED_MODELS: Final = frozenset(
    {
        "base.automation",
        "ir.config_parameter",
        "ir.cron",
        "ir.model",
        "ir.model.access",
        "ir.model.fields",
        "ir.rule",
        "res.groups",
        "res.users",
    }
)
_BLOCKED_MODEL_PREFIXES: Final = ("auth.", "ir.actions.", "ir.ui.")
_BLOCKED_FIELDS: Final = frozenset(
    {
        "__last_update",
        "company_id",
        "company_ids",
        "create_date",
        "create_uid",
        "groups_id",
        "id",
        "password",
        "password_crypt",
        "share",
        "write_date",
        "write_uid",
    }
)
_SENSITIVE_FIELD_PARTS: Final = ("api_key", "credential", "password", "secret", "token")
_PREVIEW_WARNING: Final = (
    "Preview only: onchange and secondary write side effects are not simulated."
)

JsonValue = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


class ActionEnvironmentProvider(Protocol):
    def __call__(
        self, claims: ActionPreviewDelegationPayload
    ) -> AbstractContextManager[object]: ...


class ActionReplayGuard(Protocol):
    def __call__(self, claims: ActionPreviewDelegationPayload, scope: str) -> None: ...


class DelegatedActionPreviewToolExecutor:
    """Validate p1 and expose runtime write metadata without mutation."""

    def __init__(
        self,
        *,
        codec: ActionPreviewDelegationCodec,
        environment_provider: ActionEnvironmentProvider | None = None,
        replay_guard: ActionReplayGuard | None = None,
        observed_at: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._environment_provider = environment_provider or _runtime_action_environment
        self._replay_guard = replay_guard or _runtime_action_replay_guard
        self._observed_at = observed_at or _utc_now

    def get_write_model_metadata(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        model: object,
    ) -> dict[str, JsonValue]:
        parsed_turn = _turn_id(turn_id)
        parsed_model = _model_name(model)
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="action_write_schema",
            model=parsed_model,
        )
        self._replay_guard(claims, "action_write_schema")
        try:
            with self._environment_provider(claims) as env:
                model_set = env[parsed_model]
                result = collect_model_metadata(
                    env,
                    model=parsed_model,
                    max_fields=min(len(claims.allowed_fields), MAX_METADATA_FIELDS),
                    observed_at=self._observed_at(),
                    allowed_fields=frozenset(claims.allowed_fields),
                )
                try:
                    model_set.browse().check_access("write")
                except (AccessError, MissingError, ValidationError):
                    result["write_access"] = False
                    return result
                fields = result.get("fields")
                if not isinstance(fields, dict):
                    raise OrmToolError("invalid_metadata", 500)
                write_fields: dict[str, JsonValue] = {}
                for name, description in fields.items():
                    try:
                        model_set.check_field_access_rights("write", [name])
                    except AccessError:
                        continue
                    write_fields[name] = description
                result["fields"] = write_fields
                result["write_access"] = True
                return result
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None

    def preview_record_patch(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        proposal: object,
        payload_fingerprint: object,
    ) -> dict[str, JsonValue]:
        """Read the exact target and return a bounded diff without mutation."""

        parsed_turn = _turn_id(turn_id)
        parsed_proposal = _proposal(proposal)
        fingerprint = _fingerprint(payload_fingerprint, prefix="action-payload")
        expected_fingerprint = _action_payload_fingerprint(parsed_proposal)
        if not hmac.compare_digest(fingerprint, expected_fingerprint):
            raise OrmToolError("payload_fingerprint_mismatch", 403)
        target = parsed_proposal["target"]
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="action_preview",
            model=target["model"],
        )
        _check_proposal_authority(parsed_proposal, claims)
        self._replay_guard(claims, "action_preview")
        observed_at = self._observed_at()
        try:
            with self._environment_provider(claims) as env:
                model_set = env[target["model"]]
                changes = parsed_proposal["changes"]
                field_names = tuple(change["field"] for change in changes)
                metadata = _preview_metadata(
                    model_set, field_names, claims, observed_at=observed_at
                )
                records = model_set.browse([target["record_id"]])
                records.check_access("read")
                records.check_access("write")
                rows = records.read(list(field_names), load=None)
                if len(rows) != 1 or rows[0].get("id") != target["record_id"]:
                    raise OrmToolError("access_denied", 403)
                preview_changes = _preview_changes(
                    env,
                    changes=changes,
                    metadata=metadata,
                    row=rows[0],
                )
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None
        except ValueError:
            raise OrmToolError("invalid_action", 400) from None

        before = {change["field"]: change["before"] for change in preview_changes}
        precondition_fingerprint = _precondition_fingerprint(
            model=target["model"], record_id=target["record_id"], before=before
        )
        result: dict[str, JsonValue] = {
            "ok": True,
            "preview": {
                "expires_at": iso_datetime(datetime.fromtimestamp(claims.expires_at, UTC)),
                "observed_at": iso_datetime(observed_at),
                "payload_fingerprint": fingerprint,
                "policy_revision": parsed_proposal["policy_revision"],
                "precondition_fingerprint": precondition_fingerprint,
                "preview_id": str(uuid4()),
                "schema_revision": parsed_proposal["schema_revision"],
                "summary": {
                    "changes": preview_changes,
                    "proposal_id": parsed_proposal["proposal_id"],
                    "target": target,
                    "warnings": [_PREVIEW_WARNING],
                },
            },
        }
        check_response_size(result)
        return result

    def _authorize(
        self,
        token: str,
        *,
        turn_id: UUID,
        scope: str,
        model: str,
    ) -> ActionPreviewDelegationPayload:
        try:
            claims = self._codec.decode(token)
        except DelegationTokenError:
            raise OrmToolError("delegation_rejected", 403) from None
        if (
            claims.turn_id != turn_id
            or claims.model != model
            or scope not in claims.scopes
            or claims.policy_revision != ACTION_POLICY_REVISION
        ):
            raise OrmToolError("scope_denied", 403)
        return claims


class ApprovedActionToolExecutor:
    """Execute or verify exactly one a1-bound persisted record patch."""

    def __init__(
        self,
        *,
        codec: ActionAuthorityCodec,
        environment_provider: Callable[[ActionAuthorityPayload], AbstractContextManager[object]] | None = None,
        replay_guard: Callable[[ActionAuthorityPayload, str], None] | None = None,
        observed_at: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._environment_provider = environment_provider or _runtime_action_environment
        self._replay_guard = replay_guard or _runtime_action_replay_guard
        self._observed_at = observed_at or _utc_now

    def commit_record_patch(
        self, *, authority_token: str, proposal: object
    ) -> dict[str, JsonValue]:
        parsed = _proposal(proposal)
        claims = self._authorize(authority_token, parsed, "action_commit")
        self._replay_guard(claims, "action_commit")
        target = parsed["target"]
        changes = parsed["changes"]
        fields = tuple(change["field"] for change in changes)
        try:
            with self._environment_provider(claims) as env:
                model_set = env[target["model"]]
                metadata = _action_metadata(model_set, fields, claims, self._observed_at())
                records = model_set.browse([target["record_id"]])
                records.check_access("read")
                records.check_access("write")
                rows = records.read(list(fields), load=None)
                if len(rows) != 1 or rows[0].get("id") != target["record_id"]:
                    raise OrmToolError("access_denied", 403)
                preview_changes = _preview_changes(
                    env, changes=changes, metadata=metadata, row=rows[0]
                )
                before = {change["field"]: change["before"] for change in preview_changes}
                current = _precondition_fingerprint(
                    model=target["model"], record_id=target["record_id"], before=before
                )
                if not hmac.compare_digest(current, claims.precondition_fingerprint):
                    raise OrmToolError("stale_precondition", 409)
                values = {
                    change["field"]: _orm_write_value(change["value"])
                    for change in changes
                }
                records.write(values)
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None
        except ValueError:
            raise OrmToolError("invalid_action", 400) from None
        committed_at = self._observed_at()
        return {
            "attempt_id": str(claims.attempt_id),
            "committed_at": iso_datetime(committed_at),
            "ok": True,
            "payload_fingerprint": claims.payload_fingerprint,
            "precondition_fingerprint": claims.precondition_fingerprint,
            "proposal_id": str(claims.proposal_id),
        }

    def verify_record_patch(
        self, *, authority_token: str, proposal: object
    ) -> dict[str, JsonValue]:
        parsed = _proposal(proposal)
        claims = self._authorize(authority_token, parsed, "action_verify")
        self._replay_guard(claims, "action_verify")
        target = parsed["target"]
        changes = parsed["changes"]
        fields = tuple(change["field"] for change in changes)
        try:
            with self._environment_provider(claims) as env:
                model_set = env[target["model"]]
                metadata = _action_metadata(model_set, fields, claims, self._observed_at())
                records = model_set.browse([target["record_id"]])
                records.check_access("read")
                rows = records.read(list(fields), load=None)
                if len(rows) != 1 or rows[0].get("id") != target["record_id"]:
                    raise OrmToolError("access_denied", 403)
                observed = _preview_changes(
                    env, changes=changes, metadata=metadata, row=rows[0]
                )
                after = {change["field"]: change["before"] for change in observed}
                expected = {change["field"]: change["value"] for change in changes}
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None
        verified_at = self._observed_at()
        return {
            "after": after,
            "attempt_id": str(claims.attempt_id),
            "matches": after == expected,
            "ok": True,
            "proposal_id": str(claims.proposal_id),
            "verified_at": iso_datetime(verified_at),
        }

    def _authorize(
        self, token: str, proposal: dict[str, object], scope: str
    ) -> ActionAuthorityPayload:
        try:
            claims = self._codec.decode(token)
        except DelegationTokenError:
            raise OrmToolError("delegation_rejected", 403) from None
        target = proposal["target"]
        fields = tuple(sorted(change["field"] for change in proposal["changes"]))
        fingerprint = _action_payload_fingerprint(proposal)
        if (
            claims.scopes != (scope,)
            or str(claims.proposal_id) != proposal["proposal_id"]
            or claims.instance_id != proposal["instance_id"]
            or claims.database != proposal["database"]
            or claims.uid != proposal["uid"]
            or claims.company_id != proposal["company_id"]
            or claims.allowed_company_ids != tuple(proposal["allowed_company_ids"])
            or claims.model != target["model"]
            or claims.record_id != target["record_id"]
            or claims.fields != fields
            or claims.policy_revision != ACTION_POLICY_REVISION
            or claims.policy_revision != proposal["policy_revision"]
            or claims.schema_revision != proposal["schema_revision"]
            or not hmac.compare_digest(claims.payload_fingerprint, fingerprint)
        ):
            raise OrmToolError("scope_denied", 403)
        return claims


@contextmanager
def _runtime_action_environment(
    claims: ActionPreviewDelegationPayload,
) -> Iterator[object]:
    runtime_company_ids = [
        claims.company_id,
        *(item for item in claims.allowed_company_ids if item != claims.company_id),
    ]
    context: dict[str, object] = {"allowed_company_ids": runtime_company_ids}
    if claims.lang is not None:
        context["lang"] = claims.lang
    try:
        database_registry = Registry(claims.database)
        with database_registry.cursor() as cursor:
            env = api.Environment(cursor, claims.uid, context, su=False)
            if env.su or env.cr.dbname != claims.database:
                raise OrmToolError("delegation_rejected", 403)
            if (
                env.company.id != claims.company_id
                or tuple(sorted(env.companies.ids)) != claims.allowed_company_ids
            ):
                raise OrmToolError("delegation_rejected", 403)
            yield env
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("delegation_rejected", 403) from None
    except Exception:  # noqa: BLE001 - sanitize the registry boundary
        raise OrmToolError("service_unavailable", 503) from None


def _runtime_action_replay_guard(claims: ActionPreviewDelegationPayload, scope: str) -> None:
    try:
        with _runtime_action_environment(claims) as env:
            consumed = env["odoo.ai.delegation.use"]._consume(
                jti=claims.jti,
                scope=scope,
                expires_at=claims.expires_at,
            )
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("delegation_rejected", 403) from None
    except Exception:  # noqa: BLE001 - sanitize the replay ledger boundary
        raise OrmToolError("service_unavailable", 503) from None
    if consumed is not True:
        raise OrmToolError("delegation_replayed", 403)


def _turn_id(value: object) -> UUID:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise OrmToolError("invalid_request", 400) from None
    if str(parsed) != str(value):
        raise OrmToolError("invalid_request", 400)
    return parsed


def _model_name(value: object) -> str:
    if not isinstance(value, str) or _MODEL_PATTERN.fullmatch(value) is None:
        raise OrmToolError("invalid_request", 400)
    return value


def _proposal(value: object) -> dict[str, object]:
    raw = _exact_dict(
        value,
        {
            "action_kind",
            "allowed_company_ids",
            "changes",
            "company_id",
            "database",
            "format_version",
            "instance_id",
            "policy_revision",
            "proposal_id",
            "schema_revision",
            "target",
            "turn_id",
            "uid",
        },
    )
    if raw["format_version"] != 1 or raw["action_kind"] != "record_patch":
        raise OrmToolError("invalid_action", 400)
    proposal_id = _canonical_uuid(raw["proposal_id"])
    proposal_turn_id = _canonical_uuid(raw["turn_id"])
    database = _bounded_text(raw["database"], maximum=128)
    instance_id = _bounded_text(raw["instance_id"], maximum=255)
    uid = _positive_int(raw["uid"])
    company_id = _positive_int(raw["company_id"])
    allowed_company_ids = _positive_id_list(raw["allowed_company_ids"], maximum=16)
    if company_id not in allowed_company_ids or allowed_company_ids != sorted(allowed_company_ids):
        raise OrmToolError("invalid_action", 400)
    target_raw = _exact_dict(raw["target"], {"model", "record_id"})
    target = {
        "model": _model_name(target_raw["model"]),
        "record_id": _positive_int(target_raw["record_id"]),
    }
    policy_revision = _bounded_text(raw["policy_revision"], maximum=128)
    schema_revision = _bounded_text(raw["schema_revision"], maximum=128)
    changes = _changes(raw["changes"])
    parsed: dict[str, object] = {
        "action_kind": "record_patch",
        "allowed_company_ids": allowed_company_ids,
        "changes": changes,
        "company_id": company_id,
        "database": database,
        "format_version": 1,
        "instance_id": instance_id,
        "policy_revision": policy_revision,
        "proposal_id": proposal_id,
        "schema_revision": schema_revision,
        "target": target,
        "turn_id": proposal_turn_id,
        "uid": uid,
    }
    if not _model_permitted(target["model"]):
        raise OrmToolError("model_denied", 403)
    if len(_canonical_bytes(parsed)) > MAX_ACTION_PAYLOAD_BYTES:
        raise OrmToolError("payload_too_large", 413)
    return parsed


def _changes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ACTION_FIELDS:
        raise OrmToolError("limit_exceeded", 413)
    changes: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        raw = _exact_dict(item, {"field", "value"})
        field = _field_name(raw["field"])
        if field in seen or not _field_permitted(field):
            raise OrmToolError("field_denied", 403)
        seen.add(field)
        changes.append({"field": field, "value": _action_value(raw["value"])})
    return changes


def _action_value(value: object) -> dict[str, object]:
    raw = _exact_dict(value, {"kind", "value"})
    kind = raw["kind"]
    item = raw["value"]
    if kind not in frozenset(_VALUE_KIND_BY_FIELD_TYPE.values()):
        raise OrmToolError("invalid_action", 400)
    if item is None:
        return {"kind": kind, "value": None}
    if kind == "boolean" and type(item) is bool:
        return {"kind": kind, "value": item}
    if kind in {"integer", "many2one"}:
        if type(item) is not int or (kind == "many2one" and item <= 0):
            raise OrmToolError("invalid_action", 400)
        return {"kind": kind, "value": item}
    if not isinstance(item, str) or len(item) > MAX_ACTION_VALUE_TEXT:
        raise OrmToolError("invalid_action", 400)
    if kind == "decimal":
        if _DECIMAL_PATTERN.fullmatch(item) is None:
            raise OrmToolError("invalid_action", 400)
        try:
            decimal = Decimal(item)
        except InvalidOperation:
            raise OrmToolError("invalid_action", 400) from None
        normalized = format(decimal, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if normalized in {"", "-0"}:
            normalized = "0"
        if item != normalized:
            raise OrmToolError("invalid_action", 400)
    if kind == "date":
        if _DATE_PATTERN.fullmatch(item) is None:
            raise OrmToolError("invalid_action", 400)
        try:
            date.fromisoformat(item)
        except ValueError:
            raise OrmToolError("invalid_action", 400) from None
    if kind == "datetime":
        if _DATETIME_PATTERN.fullmatch(item) is None:
            raise OrmToolError("invalid_action", 400)
        try:
            datetime.fromisoformat(item.replace("Z", "+00:00"))
        except ValueError:
            raise OrmToolError("invalid_action", 400) from None
    if kind == "selection" and (not item or len(item) > 256):
        raise OrmToolError("invalid_action", 400)
    return {"kind": kind, "value": item}


def _check_proposal_authority(
    proposal: dict[str, object], claims: ActionPreviewDelegationPayload
) -> None:
    target = proposal["target"]
    changes = proposal["changes"]
    fields = {change["field"] for change in changes}
    if (
        proposal["turn_id"] != str(claims.turn_id)
        or proposal["database"] != claims.database
        or proposal["uid"] != claims.uid
        or proposal["company_id"] != claims.company_id
        or tuple(proposal["allowed_company_ids"]) != claims.allowed_company_ids
        or target["record_id"] != claims.record_id
        or proposal["policy_revision"] != claims.policy_revision
        or len(changes) > claims.max_fields
        or not fields.issubset(claims.allowed_fields)
    ):
        raise OrmToolError("scope_denied", 403)


def _preview_metadata(
    model_set: object,
    fields: tuple[str, ...],
    claims: ActionPreviewDelegationPayload,
    *,
    observed_at: datetime,
) -> dict[str, dict[str, JsonValue]]:
    if len(fields) > claims.max_fields or not set(fields).issubset(claims.allowed_fields):
        raise OrmToolError("scope_denied", 403)
    model_set.browse().check_access("read")
    model_set.browse().check_access("write")
    model_set.check_field_access_rights("read", list(fields))
    model_set.check_field_access_rights("write", list(fields))
    metadata = collect_model_metadata(
        model_set.env,
        model=claims.model,
        max_fields=len(fields),
        observed_at=observed_at,
        allowed_fields=frozenset(fields),
    )
    descriptions = metadata.get("fields")
    if not isinstance(descriptions, dict) or set(descriptions) != set(fields):
        raise OrmToolError("field_not_allowed", 403)
    return descriptions


def _action_metadata(
    model_set: object,
    fields: tuple[str, ...],
    claims: ActionAuthorityPayload,
    observed_at: datetime,
) -> dict[str, dict[str, JsonValue]]:
    if tuple(sorted(fields)) != claims.fields:
        raise OrmToolError("scope_denied", 403)
    model_set.browse().check_access("read")
    model_set.browse().check_access("write")
    model_set.check_field_access_rights("read", list(fields))
    model_set.check_field_access_rights("write", list(fields))
    metadata = collect_model_metadata(
        model_set.env,
        model=claims.model,
        max_fields=len(fields),
        observed_at=observed_at,
        allowed_fields=frozenset(fields),
    )
    descriptions = metadata.get("fields")
    if not isinstance(descriptions, dict) or set(descriptions) != set(fields):
        raise OrmToolError("field_not_allowed", 403)
    return descriptions


def _preview_changes(
    env: object,
    *,
    changes: list[dict[str, object]],
    metadata: dict[str, dict[str, JsonValue]],
    row: dict[str, object],
) -> list[JsonValue]:
    result: list[JsonValue] = []
    for change in changes:
        field = change["field"]
        value = change["value"]
        description = metadata[field]
        field_type = description.get("type")
        expected_kind = _VALUE_KIND_BY_FIELD_TYPE.get(field_type)
        if (
            expected_kind is None
            or description.get("readonly") is not False
            or description.get("required") not in {True, False}
            or value["kind"] != expected_kind
            or (
                description["required"] is True
                and (value["value"] is None or (expected_kind == "text" and value["value"] == ""))
            )
        ):
            raise OrmToolError("field_not_allowed", 403)
        if expected_kind == "selection":
            options = description.get("selection")
            allowed_options = (
                {
                    option[0]
                    for option in options
                    if isinstance(option, list) and len(option) == 2 and isinstance(option[0], str)
                }
                if isinstance(options, list)
                else set()
            )
            if value["value"] is not None and value["value"] not in allowed_options:
                raise OrmToolError("invalid_action", 400)
        if expected_kind == "many2one" and value["value"] is not None:
            relation = description.get("relation")
            if not isinstance(relation, str) or not _MODEL_PATTERN.fullmatch(relation):
                raise OrmToolError("field_not_allowed", 403)
            related = env[relation].browse([value["value"]])
            related.check_access("read")
            if len(related.exists()) != 1:
                raise OrmToolError("access_denied", 403)
        label = description.get("string")
        if label is not None and (not isinstance(label, str) or not 1 <= len(label) <= 256):
            raise OrmToolError("invalid_metadata", 500)
        result.append(
            {
                "after": value,
                "before": _observed_action_value(expected_kind, row.get(field)),
                "field": field,
                "label": label,
            }
        )
    return result


def _observed_action_value(kind: str, value: object) -> dict[str, object]:
    if kind == "boolean":
        if type(value) is not bool:
            raise OrmToolError("unsupported_value", 400)
        normalized: object = value
    elif value is False or value is None:
        normalized = None
    elif kind == "integer":
        if type(value) is not int:
            raise OrmToolError("unsupported_value", 400)
        normalized = value
    elif kind == "many2one":
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 2
            or type(value[0]) is not int
            or value[0] <= 0
        ):
            raise OrmToolError("unsupported_value", 400)
        normalized = value[0]
    elif kind == "decimal":
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise OrmToolError("unsupported_value", 400) from None
        normalized = format(decimal, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if normalized in {"", "-0"}:
            normalized = "0"
        if _DECIMAL_PATTERN.fullmatch(normalized) is None:
            raise OrmToolError("unsupported_value", 400)
    elif kind == "date":
        normalized = value.isoformat() if isinstance(value, date) else str(value)
        if _DATE_PATTERN.fullmatch(normalized) is None:
            raise OrmToolError("unsupported_value", 400)
    elif kind == "datetime":
        if isinstance(value, datetime):
            normalized = iso_datetime(value.replace(tzinfo=value.tzinfo or UTC))
        elif isinstance(value, str):
            normalized = value.replace(" ", "T") + ("" if value.endswith("Z") else "Z")
        else:
            raise OrmToolError("unsupported_value", 400)
        if _DATETIME_PATTERN.fullmatch(normalized) is None:
            raise OrmToolError("unsupported_value", 400)
    else:
        if not isinstance(value, str) or len(value) > MAX_ACTION_VALUE_TEXT:
            raise OrmToolError("unsupported_value", 400)
        normalized = value
    return {"kind": kind, "value": normalized}


def _orm_write_value(value: dict[str, object]) -> object:
    kind = value["kind"]
    item = value["value"]
    if item is None:
        return False
    if kind == "decimal":
        return float(item)
    if kind == "datetime":
        return str(item).replace("T", " ").removesuffix("Z")
    return item


def _action_payload_fingerprint(proposal: dict[str, object]) -> str:
    body = dict(proposal)
    body["allowed_company_ids"] = sorted(body["allowed_company_ids"])
    body["changes"] = sorted(body["changes"], key=lambda change: change["field"])
    digest = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    return f"action-payload:v1:sha256:{digest}"


def _precondition_fingerprint(*, model: str, record_id: int, before: dict[str, object]) -> str:
    digest = hashlib.sha256(
        _canonical_bytes(
            {
                "before": before,
                "format_version": 1,
                "model": model,
                "record_id": record_id,
            }
        )
    ).hexdigest()
    return f"action-precondition:v1:sha256:{digest}"


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise OrmToolError("invalid_action", 400) from None


def _exact_dict(value: object, keys: set[str]) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or not all(isinstance(key, str) for key in value)
    ):
        raise OrmToolError("invalid_action", 400)
    return value


def _canonical_uuid(value: object) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise OrmToolError("invalid_action", 400) from None
    if str(parsed) != value:
        raise OrmToolError("invalid_action", 400)
    return str(parsed)


def _bounded_text(value: object, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise OrmToolError("invalid_action", 400)
    return value


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise OrmToolError("invalid_action", 400)
    return value


def _positive_id_list(value: object, *, maximum: int) -> list[int]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= maximum
        or any(type(item) is not int or item <= 0 for item in value)
        or len(value) != len(set(value))
    ):
        raise OrmToolError("invalid_action", 400)
    return value


def _field_name(value: object) -> str:
    if not isinstance(value, str) or _FIELD_PATTERN.fullmatch(value) is None:
        raise OrmToolError("invalid_action", 400)
    return value


def _fingerprint(value: object, *, prefix: str) -> str:
    pattern = rf"^{re.escape(prefix)}:v1:sha256:[0-9a-f]{{64}}$"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise OrmToolError("invalid_action", 400)
    return value


def _model_permitted(model: str) -> bool:
    return model not in _BLOCKED_MODELS and not model.startswith(_BLOCKED_MODEL_PREFIXES)


def _field_permitted(field: str) -> bool:
    normalized = field.casefold()
    return field not in _BLOCKED_FIELDS and not any(
        part in normalized for part in _SENSITIVE_FIELD_PARTS
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
