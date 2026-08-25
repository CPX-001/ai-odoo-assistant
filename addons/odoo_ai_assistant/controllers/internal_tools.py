"""Internal machine-authenticated HTTP endpoints for delegated ORM reads."""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Final

from odoo import api, http
from odoo.http import request
from odoo.modules.registry import Registry

from ..security import (
    SHARED_SECRET_HEADER,
    ActionAuthorityCodec,
    ActionPreviewDelegationCodec,
    ActionPreviewDelegationPayload,
    AgentDelegationCodec,
    DelegationCodec,
    DelegationTokenError,
    MachineAuthenticationError,
    QueryDelegationCodec,
    QueryDelegationPayload,
    require_machine_secret,
)
from ..services import InstanceInventoryError, collect_instance_inventory
from ..services.action_tools import (
    ApprovedActionToolExecutor,
    DelegatedActionPreviewToolExecutor,
)
from ..services.orm_tools import DelegatedOrmToolExecutor, OrmToolError
from ..services.query_tools import DelegatedQueryToolExecutor
from ..services.turn_context import (
    ACTION_POLICY_REVISION,
    ACTION_PREVIEW_DELEGATION_TTL_SECONDS,
    AGENT_POLICY_REVISION,
    DELEGATION_SECRET_FILE_ENV,
    QUERY_DELEGATION_TTL_SECONDS,
    QUERY_POLICY_REVISION,
    TurnContextError,
    agent_model_is_eligible,
    search_agent_models,
    visible_action_preview_fields,
    visible_query_fields,
)

DELEGATION_HEADER: Final = "X-Odoo-AI-Delegation"
MAX_REQUEST_BYTES: Final = 32 * 1024
METADATA_ROUTE: Final = "/odoo_ai/internal/v1/model-metadata"
READ_ROUTE: Final = "/odoo_ai/internal/v1/read-records"
INVENTORY_ROUTE: Final = "/odoo_ai/internal/v1/instance-inventory"
NAVIGATION_ROUTE: Final = "/odoo_ai/internal/v1/navigation"
QUERY_SCHEMA_ROUTE: Final = "/odoo_ai/internal/v1/query-schema"
QUERY_RECORDS_ROUTE: Final = "/odoo_ai/internal/v1/query-records"
AGGREGATE_RECORDS_ROUTE: Final = "/odoo_ai/internal/v1/aggregate-records"
WRITE_SCHEMA_ROUTE: Final = "/odoo_ai/internal/v1/action-write-schema"
ACTION_PREVIEW_ROUTE: Final = "/odoo_ai/internal/v1/action-preview"
ACTION_COMMIT_ROUTE: Final = "/odoo_ai/internal/v1/action-commit"
ACTION_VERIFY_ROUTE: Final = "/odoo_ai/internal/v1/action-verify"
AGENT_MODEL_SEARCH_ROUTE: Final = "/odoo_ai/internal/v1/agent-model-search"

_logger = logging.getLogger(__name__)


class InternalOdooToolsController(http.Controller):
    @http.route(
        AGENT_MODEL_SEARCH_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def agent_model_search(self):
        return self._dispatch("model_search")

    @http.route(
        ACTION_COMMIT_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def action_commit(self):
        return self._dispatch("action_commit")

    @http.route(
        ACTION_VERIFY_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def action_verify(self):
        return self._dispatch("action_verify")

    @http.route(
        ACTION_PREVIEW_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def action_preview(self):
        return self._dispatch("action_preview")

    @http.route(
        WRITE_SCHEMA_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def action_write_schema(self):
        return self._dispatch("action_write_schema")

    @http.route(
        METADATA_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def model_metadata(self):
        return self._dispatch("metadata")

    @http.route(
        READ_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def read_records(self):
        return self._dispatch("read")

    @http.route(
        NAVIGATION_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def navigation(self):
        return self._dispatch("navigation")

    @http.route(
        QUERY_SCHEMA_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def query_schema(self):
        return self._dispatch("query_schema")

    @http.route(
        QUERY_RECORDS_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def query_records(self):
        return self._dispatch("query_records")

    @http.route(
        AGGREGATE_RECORDS_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def aggregate_records(self):
        return self._dispatch("aggregate_records")

    @http.route(
        INVENTORY_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def instance_inventory(self):
        return self._dispatch("inventory")

    def _dispatch(self, operation: str):
        try:
            require_machine_secret(
                request.httprequest.headers.get(SHARED_SECRET_HEADER)
            )
            payload = _request_payload()
            if operation == "inventory":
                _require_keys(payload, set())
                result = collect_instance_inventory(request.env)
                return request.make_json_response(result, status=200)
            token = request.httprequest.headers.get(DELEGATION_HEADER)
            if not token or len(token) > 8192:
                raise OrmToolError("delegation_rejected", 403)
            if operation == "model_search":
                _require_keys(payload, {"limit", "query", "turn_id"})
                claims = _agent_catalog_claims(token, payload)
                with _agent_environment(claims) as env:
                    models = search_agent_models(
                        env,
                        payload["query"],
                        limit=payload["limit"],
                    )
                return request.make_json_response(
                    {
                        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "content_trust": "untrusted",
                        "models": models,
                        "ok": True,
                    },
                    status=200,
                )
            if operation in {"action_commit", "action_verify"}:
                _require_keys(payload, {"proposal"})
                action_executor = ApprovedActionToolExecutor(
                    codec=ActionAuthorityCodec.from_env()
                )
                proposal = payload["proposal"]
                if operation == "action_commit":
                    if (
                        isinstance(proposal, dict)
                        and proposal.get("action_kind") == "business_action"
                    ):
                        result = action_executor.commit_business_action(
                            authority_token=token, proposal=proposal
                        )
                    elif (
                        isinstance(proposal, dict)
                        and proposal.get("action_kind") == "record_create"
                    ):
                        result = action_executor.commit_record_create(
                            authority_token=token, proposal=proposal
                        )
                    else:
                        result = action_executor.commit_record_patch(
                            authority_token=token, proposal=proposal
                        )
                else:
                    if (
                        isinstance(proposal, dict)
                        and proposal.get("action_kind") == "business_action"
                    ):
                        result = action_executor.verify_business_action(
                            authority_token=token, proposal=proposal
                        )
                    elif (
                        isinstance(proposal, dict)
                        and proposal.get("action_kind") == "record_create"
                    ):
                        result = action_executor.verify_record_create(
                            authority_token=token, proposal=proposal
                        )
                    else:
                        result = action_executor.verify_record_patch(
                            authority_token=token, proposal=proposal
                        )
                return request.make_json_response(result, status=200)
            if operation == "action_write_schema":
                _require_keys(payload, {"model", "turn_id"})
                action_executor = DelegatedActionPreviewToolExecutor(
                    codec=_action_preview_codec_for(
                        token,
                        operation=operation,
                        payload=payload,
                        model=payload["model"],
                        record_id=1,
                    )
                )
                result = action_executor.get_write_model_metadata(
                    delegation_token=token,
                    turn_id=payload["turn_id"],
                    model=payload["model"],
                )
                return request.make_json_response(result, status=200)
            if operation == "action_preview":
                _require_keys(payload, {"payload_fingerprint", "proposal", "turn_id"})
                proposal = payload["proposal"]
                target = proposal.get("target") if isinstance(proposal, dict) else None
                model = target.get("model") if isinstance(target, dict) else None
                record_id = target.get("record_id") if isinstance(target, dict) else 1
                action_executor = DelegatedActionPreviewToolExecutor(
                    codec=_action_preview_codec_for(
                        token,
                        operation=operation,
                        payload=payload,
                        model=model,
                        record_id=record_id,
                    )
                )
                if (
                    isinstance(proposal, dict)
                    and proposal.get("action_kind") == "business_action"
                ):
                    result = action_executor.preview_business_action(
                        delegation_token=token,
                        turn_id=payload["turn_id"],
                        proposal=proposal,
                        payload_fingerprint=payload["payload_fingerprint"],
                    )
                elif (
                    isinstance(proposal, dict)
                    and proposal.get("action_kind") == "record_create"
                ):
                    result = action_executor.preview_record_create(
                        delegation_token=token,
                        turn_id=payload["turn_id"],
                        proposal=proposal,
                        payload_fingerprint=payload["payload_fingerprint"],
                    )
                else:
                    result = action_executor.preview_record_patch(
                        delegation_token=token,
                        turn_id=payload["turn_id"],
                        proposal=proposal,
                        payload_fingerprint=payload["payload_fingerprint"],
                    )
                return request.make_json_response(result, status=200)
            if operation in {"aggregate_records", "query_records", "query_schema"}:
                query_model = (
                    payload.get("model")
                    if operation == "query_schema"
                    else payload.get("query", {}).get("model")
                    if isinstance(payload.get("query"), dict)
                    else None
                )
                query_executor = DelegatedQueryToolExecutor(
                    codec=_query_codec_for(
                        token,
                        operation=operation,
                        payload=payload,
                        model=query_model,
                    )
                )
                if operation == "query_schema":
                    _require_keys(payload, {"model", "turn_id"})
                    result = query_executor.get_model_metadata(
                        delegation_token=token,
                        turn_id=payload["turn_id"],
                        model=payload["model"],
                    )
                else:
                    _require_keys(payload, {"query", "turn_id"})
                    if operation == "query_records":
                        result = query_executor.query_records(
                            delegation_token=token,
                            turn_id=payload["turn_id"],
                            payload=payload["query"],
                        )
                    else:
                        result = query_executor.aggregate_records(
                            delegation_token=token,
                            turn_id=payload["turn_id"],
                            payload=payload["query"],
                        )
                return request.make_json_response(result, status=200)
            codec = _delegation_codec()
            executor = DelegatedOrmToolExecutor(codec=codec)
            if operation == "metadata":
                _require_keys(payload, {"model", "turn_id"})
                result = executor.get_model_metadata(
                    delegation_token=token,
                    turn_id=payload["turn_id"],
                    model=payload["model"],
                )
            elif operation == "navigation":
                _require_keys(payload, {"turn_id"})
                result = executor.get_navigation(
                    delegation_token=token,
                    turn_id=payload["turn_id"],
                )
            elif operation == "read":
                _require_keys(payload, {"fields", "ids", "model", "turn_id"})
                result = executor.read_records(
                    delegation_token=token,
                    turn_id=payload["turn_id"],
                    model=payload["model"],
                    record_ids=payload["ids"],
                    fields=payload["fields"],
                )
            else:
                raise OrmToolError("operation_not_allowed", 404)
            return request.make_json_response(result, status=200)
        except MachineAuthenticationError as error:
            return _error_response(error.code, error.status)
        except OrmToolError as error:
            _logger.warning(
                "Odoo AI internal tool rejected operation=%s code=%s status=%s",
                operation,
                error.code,
                error.status,
            )
            return _error_response(error.code, error.status)
        except InstanceInventoryError as error:
            return _error_response(error.code, error.status)
        except DelegationTokenError:
            return _error_response("delegation_unavailable", 503)
        except Exception:  # noqa: BLE001 - sanitize the internal HTTP boundary
            return _error_response("internal_error", 500)


def _delegation_codec() -> DelegationCodec:
    path = os.environ.get(DELEGATION_SECRET_FILE_ENV, "").strip()
    if not path:
        raise OrmToolError("delegation_unconfigured", 503)
    try:
        return DelegationCodec.from_secret_file(path)
    except DelegationTokenError:
        raise OrmToolError("delegation_unavailable", 503) from None


def _query_delegation_codec() -> QueryDelegationCodec:
    path = os.environ.get(DELEGATION_SECRET_FILE_ENV, "").strip()
    if not path:
        raise OrmToolError("delegation_unconfigured", 503)
    try:
        return QueryDelegationCodec.from_secret_file(path)
    except DelegationTokenError:
        raise OrmToolError("delegation_unavailable", 503) from None


def _action_preview_delegation_codec() -> ActionPreviewDelegationCodec:
    path = os.environ.get(DELEGATION_SECRET_FILE_ENV, "").strip()
    if not path:
        raise OrmToolError("delegation_unconfigured", 503)
    try:
        return ActionPreviewDelegationCodec.from_secret_file(path)
    except DelegationTokenError:
        raise OrmToolError("delegation_unavailable", 503) from None


class _StaticQueryCodec:
    def __init__(self, claims: QueryDelegationPayload) -> None:
        self._claims = claims

    def decode(self, token: str) -> QueryDelegationPayload:
        del token
        return self._claims


class _StaticActionPreviewCodec:
    def __init__(self, claims: ActionPreviewDelegationPayload) -> None:
        self._claims = claims

    def decode(self, token: str) -> ActionPreviewDelegationPayload:
        del token
        return self._claims


def _query_codec_for(
    token: str,
    *,
    operation: str,
    payload: dict[str, object],
    model: object,
):
    if not token.startswith("ag1."):
        return _query_delegation_codec()
    claims = _agent_claims(token, operation=operation, payload=payload, model=model)
    try:
        issued_at, expires_at = _derived_validity(
            claims.expires_at,
            maximum_ttl=QUERY_DELEGATION_TTL_SECONDS,
        )
        with _agent_environment(claims) as env:
            fields = visible_query_fields(env, model)
        legacy = QueryDelegationPayload(
            format_version=1,
            jti=_derived_jti(claims.jti, operation, payload),
            turn_id=claims.turn_id,
            database=claims.database,
            uid=claims.uid,
            company_id=claims.company_id,
            allowed_company_ids=claims.allowed_company_ids,
            lang=claims.lang,
            model=model,
            allowed_fields=fields,
            scopes=("query_schema", "query_records", "aggregate_records"),
            issued_at=issued_at,
            expires_at=expires_at,
            max_records=claims.max_records,
            max_fields=min(claims.max_fields, len(fields)),
            max_conditions=claims.max_conditions,
            max_groups=claims.max_groups,
            max_aggregates=claims.max_aggregates,
            policy_revision=QUERY_POLICY_REVISION,
        )
    except (DelegationTokenError, TurnContextError, TypeError, ValueError):
        raise OrmToolError("delegation_rejected", 403) from None
    return _StaticQueryCodec(legacy)


def _action_preview_codec_for(
    token: str,
    *,
    operation: str,
    payload: dict[str, object],
    model: object,
    record_id: object,
):
    if not token.startswith("ag1."):
        return _action_preview_delegation_codec()
    claims = _agent_claims(token, operation=operation, payload=payload, model=model)
    try:
        issued_at, expires_at = _derived_validity(
            claims.expires_at,
            maximum_ttl=ACTION_PREVIEW_DELEGATION_TTL_SECONDS,
        )
        with _agent_environment(claims) as env:
            fields = visible_action_preview_fields(env, model)
        parsed_record_id = record_id if type(record_id) is int and record_id > 0 else 1
        legacy = ActionPreviewDelegationPayload(
            format_version=1,
            jti=_derived_jti(claims.jti, operation, payload),
            turn_id=claims.turn_id,
            database=claims.database,
            uid=claims.uid,
            company_id=claims.company_id,
            allowed_company_ids=claims.allowed_company_ids,
            lang=claims.lang,
            model=model,
            record_id=parsed_record_id,
            allowed_fields=fields,
            scopes=("action_preview", "action_write_schema"),
            issued_at=issued_at,
            expires_at=expires_at,
            max_fields=min(claims.max_fields, len(fields)),
            policy_revision=ACTION_POLICY_REVISION,
        )
    except (DelegationTokenError, TurnContextError, TypeError, ValueError):
        raise OrmToolError("delegation_rejected", 403) from None
    return _StaticActionPreviewCodec(legacy)


def _agent_claims(
    token: str,
    *,
    operation: str,
    payload: dict[str, object],
    model: object,
):
    path = os.environ.get(DELEGATION_SECRET_FILE_ENV, "").strip()
    if not path:
        raise OrmToolError("delegation_unconfigured", 503)
    try:
        claims = AgentDelegationCodec.from_secret_file(path).decode(token)
    except DelegationTokenError:
        raise OrmToolError("delegation_rejected", 403) from None
    turn_id = payload.get("turn_id")
    if (
        not isinstance(model, str)
        or operation not in claims.scopes
        or str(claims.turn_id) != turn_id
        or claims.policy_revision != AGENT_POLICY_REVISION
    ):
        raise OrmToolError("scope_denied", 403)
    if model not in claims.allowed_models and not claims.allow_runtime_models:
        raise OrmToolError("scope_denied", 403)
    with _agent_environment(claims) as env:
        if not agent_model_is_eligible(env, model):
            raise OrmToolError("scope_denied", 403)
    return claims


def _agent_catalog_claims(token: str, payload: dict[str, object]):
    claims = _agent_claims_from_token(token)
    if (
        "model_search" not in claims.scopes
        or not claims.allow_runtime_models
        or str(claims.turn_id) != payload.get("turn_id")
        or claims.policy_revision != AGENT_POLICY_REVISION
    ):
        raise OrmToolError("scope_denied", 403)
    return claims


def _agent_claims_from_token(token: str):
    path = os.environ.get(DELEGATION_SECRET_FILE_ENV, "").strip()
    if not path:
        raise OrmToolError("delegation_unconfigured", 503)
    try:
        return AgentDelegationCodec.from_secret_file(path).decode(token)
    except DelegationTokenError:
        raise OrmToolError("delegation_rejected", 403) from None


@contextmanager
def _agent_environment(claims):
    context = {
        "allowed_company_ids": [
            claims.company_id,
            *(item for item in claims.allowed_company_ids if item != claims.company_id),
        ]
    }
    if claims.lang is not None:
        context["lang"] = claims.lang
    try:
        registry = Registry(claims.database)
        with registry.cursor() as cursor:
            env = api.Environment(cursor, claims.uid, context, su=False)
            if (
                env.su
                or env.cr.dbname != claims.database
                or env.company.id != claims.company_id
                or tuple(sorted(env.companies.ids)) != claims.allowed_company_ids
            ):
                raise OrmToolError("delegation_rejected", 403)
            yield env
    except OrmToolError:
        raise
    except Exception:  # noqa: BLE001 - sanitize registry/user environment failures
        raise OrmToolError("delegation_rejected", 403) from None


def _derived_jti(
    root_jti: str,
    operation: str,
    payload: dict[str, object],
) -> str:
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(f"{root_jti}|{operation}|{canonical}".encode()).hexdigest()


def _derived_validity(parent_expires_at: int, *, maximum_ttl: int) -> tuple[int, int]:
    """Bound an in-process legacy capability by its valid ag1 parent."""

    issued_at = int(datetime.now(UTC).timestamp())
    expires_at = min(parent_expires_at, issued_at + maximum_ttl)
    if expires_at <= issued_at:
        raise DelegationTokenError("expired")
    return issued_at, expires_at


def _request_payload() -> dict[str, object]:
    if request.httprequest.mimetype != "application/json":
        raise OrmToolError("invalid_request", 400)
    raw_length = request.httprequest.headers.get("Content-Length")
    if raw_length:
        try:
            content_length = int(raw_length)
        except ValueError:
            raise OrmToolError("invalid_request", 400) from None
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            raise OrmToolError("request_too_large", 413)
    body = request.httprequest.get_data(cache=False)
    if not body or len(body) > MAX_REQUEST_BYTES:
        raise OrmToolError("request_too_large", 413)
    try:
        payload = json.loads(body, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError):
        raise OrmToolError("invalid_request", 400) from None
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise OrmToolError("invalid_request", 400)
    return payload


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _require_keys(payload: dict[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise OrmToolError("invalid_request", 400)


def _error_response(code: str, status: int):
    return request.make_json_response(
        {"error": {"code": code}, "ok": False}, status=status
    )
