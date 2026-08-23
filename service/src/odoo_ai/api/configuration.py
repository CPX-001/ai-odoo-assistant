"""Machine-authenticated M7 administrative configuration API."""

from __future__ import annotations

import asyncio
from typing import Final

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.contracts.admin_configuration import (
    AdminConfigurationApplyRequest,
    AdminConfigurationResponse,
    AdminConfigurationValidateRequest,
)
from odoo_ai.runtime.configuration import (
    RuntimeConfigurationError,
    RuntimeConfigurationService,
)
from odoo_ai.security import require_shared_secret

MAX_CONFIGURATION_REQUEST_BYTES: Final = 16 * 1024
_CONFIGURATION_POST_PATHS: Final = frozenset(
    {
        "/v1/admin/configuration/validate",
        "/v1/admin/configuration/apply",
    }
)


class ConfigurationRequestLimitMiddleware:
    """Bound config writes before JSON parsing, including chunked requests."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST" and scope.get("path") in _CONFIGURATION_POST_PATHS
        ):
            await self._app(scope, receive, send)
            return

        raw_length = dict(scope.get("headers", [])).get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self._max_bytes:
                    await _error_response("request_too_large", 413)(scope, receive, send)
                    return
            except ValueError:
                await _error_response("request_too_large", 413)(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self._max_bytes:
                await _error_response("request_too_large", 413)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self._app(scope, replay_receive, send)


router = APIRouter()


@router.get(
    "/v1/admin/configuration",
    response_model=AdminConfigurationResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def configuration_snapshot(
    request: Request,
) -> AdminConfigurationResponse | JSONResponse:
    try:
        return await asyncio.to_thread(_service(request).snapshot)
    except RuntimeConfigurationError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/configuration/validate",
    response_model=AdminConfigurationResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def configuration_validate(
    request: Request,
) -> AdminConfigurationResponse | JSONResponse:
    try:
        payload = AdminConfigurationValidateRequest.model_validate_json(await request.body())
        return await asyncio.to_thread(_service(request).validate, payload.overrides)
    except ValidationError:
        return _error_response("configuration_invalid", 422)
    except RuntimeConfigurationError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/configuration/apply",
    response_model=AdminConfigurationResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def configuration_apply(
    request: Request,
) -> AdminConfigurationResponse | JSONResponse:
    try:
        payload = AdminConfigurationApplyRequest.model_validate_json(await request.body())
        service = _service(request)
        return await asyncio.to_thread(
            service.apply,
            expected_revision=payload.expected_revision,
            overrides=payload.overrides,
            actor=payload.actor,
        )
    except ValidationError:
        return _error_response("configuration_invalid", 422)
    except RuntimeConfigurationError as error:
        return _error_response(error.code, error.status_code)


def install_configuration_routes(
    application: FastAPI,
    *,
    service: RuntimeConfigurationService | None = None,
) -> FastAPI:
    """Install M7 routes once without changing the core turn/API authority model."""

    if getattr(application.state, "m7_configuration_routes_installed", False):
        if service is not None:
            application.state.m7_configuration_service = service
        return application
    application.state.m7_configuration_routes_installed = True
    if service is not None:
        application.state.m7_configuration_service = service
    application.add_middleware(
        ConfigurationRequestLimitMiddleware,
        max_bytes=MAX_CONFIGURATION_REQUEST_BYTES,
    )
    application.include_router(router)
    return application


def _service(request: Request) -> RuntimeConfigurationService:
    configured = getattr(request.app.state, "m7_configuration_service", None)
    if isinstance(configured, RuntimeConfigurationService):
        return configured
    try:
        configured = RuntimeConfigurationService.from_env()
    except (OSError, ValueError):
        raise RuntimeConfigurationError("configuration_unavailable", 503) from None
    request.app.state.m7_configuration_service = configured
    return configured


def _error_response(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "ok": False},
    )
