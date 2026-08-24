"""Machine-authenticated endpoints for batch preflight and exact signed commit."""

from __future__ import annotations

import json
from typing import Final

from odoo import http
from odoo.http import request

from ..security import SHARED_SECRET_HEADER, MachineAuthenticationError, require_machine_secret
from ..security.batch_authority import BatchAuthorityCodec
from ..services.batch_commit import ApprovedBatchMutationExecutor
from ..services.batch_preflight import DelegatedBatchPreflightExecutor
from ..services.orm_tools import OrmToolError
from .internal_tools import _agent_claims, _agent_environment

DELEGATION_HEADER: Final = "X-Odoo-AI-Delegation"
BATCH_PREFLIGHT_ROUTE: Final = "/odoo_ai/internal/v1/batch-preflight"
BATCH_COMMIT_ROUTE: Final = "/odoo_ai/internal/v1/batch-commit"
MAX_BATCH_REQUEST_BYTES: Final = 512 * 1024


class InternalBatchToolsController(http.Controller):
    @http.route(
        BATCH_PREFLIGHT_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def batch_preflight(self):
        try:
            require_machine_secret(
                request.httprequest.headers.get(SHARED_SECRET_HEADER)
            )
            token = request.httprequest.headers.get(DELEGATION_HEADER)
            if not token or not token.startswith("ag1.") or len(token) > 8192:
                raise OrmToolError("delegation_rejected", 403)
            payload = _request_payload()
            if set(payload) != {"batch", "turn_id"}:
                raise OrmToolError("invalid_request", 422)
            batch = payload["batch"]
            model = batch.get("model") if isinstance(batch, dict) else None
            # Batch preflight is an effect-free write preview. Reuse the existing ag1
            # action_preview scope instead of introducing a second equivalent scope.
            claims = _agent_claims(
                token,
                operation="action_preview",
                payload=payload,
                model=model,
            )
            with _agent_environment(claims) as env:
                result = DelegatedBatchPreflightExecutor().preflight(
                    env=env,
                    batch=batch,
                    max_records=min(claims.max_records, 50),
                )
            return request.make_json_response({"ok": True, **result}, status=200)
        except MachineAuthenticationError:
            return request.make_json_response(
                {"ok": False, "error": {"code": "machine_auth_rejected"}},
                status=401,
            )
        except OrmToolError as error:
            return request.make_json_response(
                {"ok": False, "error": {"code": error.code}},
                status=error.status_code,
            )
        except Exception:  # noqa: BLE001 - never expose runtime/record details
            return request.make_json_response(
                {"ok": False, "error": {"code": "batch_preflight_unavailable"}},
                status=503,
            )

    @http.route(
        BATCH_COMMIT_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def batch_commit(self):
        try:
            require_machine_secret(
                request.httprequest.headers.get(SHARED_SECRET_HEADER)
            )
            token = request.httprequest.headers.get(DELEGATION_HEADER)
            if not token or len(token) > 8192:
                raise OrmToolError("delegation_rejected", 403)
            payload = _request_payload()
            if set(payload) != {"batch"}:
                raise OrmToolError("invalid_request", 422)
            result = ApprovedBatchMutationExecutor(
                codec=BatchAuthorityCodec.from_env()
            ).commit(
                authority_token=token,
                batch=payload["batch"],
            )
            return request.make_json_response(result, status=200)
        except MachineAuthenticationError:
            return request.make_json_response(
                {"ok": False, "error": {"code": "machine_auth_rejected"}},
                status=401,
            )
        except OrmToolError as error:
            return request.make_json_response(
                {"ok": False, "error": {"code": error.code}},
                status=error.status_code,
            )
        except Exception:  # noqa: BLE001 - never expose host/provider details
            return request.make_json_response(
                {"ok": False, "error": {"code": "batch_execution_unavailable"}},
                status=503,
            )


def _request_payload() -> dict[str, object]:
    content_type = request.httprequest.headers.get("Content-Type", "").partition(";")[0].strip()
    if content_type != "application/json":
        raise OrmToolError("invalid_request", 415)
    raw_length = request.httprequest.headers.get("Content-Length")
    if raw_length:
        try:
            content_length = int(raw_length)
        except ValueError:
            raise OrmToolError("invalid_request", 422) from None
        if content_length < 0 or content_length > MAX_BATCH_REQUEST_BYTES:
            raise OrmToolError("request_too_large", 413)
    body = request.httprequest.get_data(cache=False, as_text=False)
    if not body or len(body) > MAX_BATCH_REQUEST_BYTES:
        raise OrmToolError("request_too_large", 413)
    try:
        value = json.loads(body, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError):
        raise OrmToolError("invalid_request", 422) from None
    if not isinstance(value, dict):
        raise OrmToolError("invalid_request", 422)
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate json key")
        result[key] = value
    return result
