"""Machine-authenticated callback retained for Source inventory discovery."""

from __future__ import annotations

import json
from typing import Final

from odoo import http
from odoo.http import request

from ..security import (
    SHARED_SECRET_HEADER,
    MachineAuthenticationError,
    require_machine_secret,
)
from ..services import InstanceInventoryError, collect_instance_inventory

INVENTORY_ROUTE: Final = "/odoo_ai/internal/v1/instance-inventory"
MAX_REQUEST_BYTES: Final = 4 * 1024


class InternalOdooToolsController(http.Controller):
    """Expose only bounded technical inventory needed by the residual Source scanner."""

    @http.route(
        INVENTORY_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def instance_inventory(self):
        try:
            require_machine_secret(
                request.httprequest.headers.get(SHARED_SECRET_HEADER)
            )
            payload = _request_payload()
            if payload:
                return _error_response("invalid_request", 400)
            return request.make_json_response(
                collect_instance_inventory(request.env),
                status=200,
            )
        except MachineAuthenticationError as error:
            return _error_response(error.code, error.status)
        except InstanceInventoryError as error:
            return _error_response(error.code, error.status)
        except Exception:  # noqa: BLE001 - sanitize machine-authenticated boundary
            return _error_response("internal_error", 500)


def _request_payload() -> dict[str, object]:
    if request.httprequest.mimetype != "application/json":
        raise InstanceInventoryError("invalid_request", 400)
    raw_length = request.httprequest.headers.get("Content-Length")
    if raw_length:
        try:
            content_length = int(raw_length)
        except ValueError:
            raise InstanceInventoryError("invalid_request", 400) from None
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            raise InstanceInventoryError("request_too_large", 413)

    body = request.httprequest.get_data(cache=False)
    if not body or len(body) > MAX_REQUEST_BYTES:
        raise InstanceInventoryError("request_too_large", 413)
    try:
        payload = json.loads(body, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError):
        raise InstanceInventoryError("invalid_request", 400) from None
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise InstanceInventoryError("invalid_request", 400)
    return payload


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _error_response(code: str, status: int):
    return request.make_json_response(
        {"error": {"code": code}, "ok": False},
        status=status,
    )
