"""Internal machine-authenticated HTTP endpoints for delegated ORM reads."""

import json
import os
from typing import Final

from odoo import http
from odoo.http import request

from ..security import (
    SHARED_SECRET_HEADER,
    DelegationCodec,
    DelegationTokenError,
    MachineAuthenticationError,
    require_machine_secret,
)
from ..services import InstanceInventoryError, collect_instance_inventory
from ..services.orm_tools import DelegatedOrmToolExecutor, OrmToolError
from ..services.turn_context import DELEGATION_SECRET_FILE_ENV

DELEGATION_HEADER: Final = "X-Odoo-AI-Delegation"
MAX_REQUEST_BYTES: Final = 32 * 1024
METADATA_ROUTE: Final = "/odoo_ai/internal/v1/model-metadata"
READ_ROUTE: Final = "/odoo_ai/internal/v1/read-records"
INVENTORY_ROUTE: Final = "/odoo_ai/internal/v1/instance-inventory"
NAVIGATION_ROUTE: Final = "/odoo_ai/internal/v1/navigation"


class InternalOdooToolsController(http.Controller):
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
            if not token or len(token) > 4096:
                raise OrmToolError("delegation_rejected", 403)
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
        payload = json.loads(body)
    except (UnicodeError, json.JSONDecodeError):
        raise OrmToolError("invalid_request", 400) from None
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise OrmToolError("invalid_request", 400)
    return payload


def _require_keys(payload: dict[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise OrmToolError("invalid_request", 400)


def _error_response(code: str, status: int):
    return request.make_json_response(
        {"error": {"code": code}, "ok": False}, status=status
    )
