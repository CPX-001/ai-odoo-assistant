"""Temporary HTTP surface for Source/Scanner/Diagnostics responsibilities."""

import asyncio
from typing import Final, Literal

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.adapters import CachedCodexReasoningStatus, RuntimeDiagnosticsService
from odoo_ai.application import DiagnosticsError, DiagnosticsService
from odoo_ai.contracts import (
    EmptyDiagnosticsRequest,
    LogEvidence,
    LogSearchRequest,
    LogTestDiagnostics,
    SourceScanDiagnostics,
    SourceStatusDiagnostics,
    SourceTestDiagnostics,
    TracebackRequest,
)
from odoo_ai.runtime.status import (
    AdminStatus,
    ComponentState,
    ReasoningComponentStatus,
    inspect_admin_status,
)
from odoo_ai.security import require_shared_secret

MAX_REQUEST_BYTES: Final = 16 * 1024
_BOUNDED_POST_PATHS: Final = frozenset(
    {
        "/v1/admin/source/rescan",
        "/v1/admin/source/test",
        "/v1/admin/logs/test",
        "/v1/admin/logs/traceback",
    }
)


class HealthResponse(BaseModel):
    """Stable liveness response with no dependency on external systems."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class BoundedRequestLimitMiddleware:
    """Reject oversized residual admin requests before JSON parsing."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST"
            and scope.get("path") in _BOUNDED_POST_PATHS
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
            return {
                "type": "http.request",
                "body": bytes(body),
                "more_body": False,
            }

        await self._app(scope, replay_receive, send)


def create_app(*, diagnostics_service: DiagnosticsService | None = None) -> FastAPI:
    """Build the residual source/scanner/diagnostics service surface."""

    application = FastAPI(title="Odoo AI Assistant Residual Service")
    application.add_middleware(
        BoundedRequestLimitMiddleware,
        max_bytes=MAX_REQUEST_BYTES,
    )
    diagnostics = diagnostics_service
    reasoning_status_probe: CachedCodexReasoningStatus | None = None

    def get_diagnostics() -> DiagnosticsService:
        nonlocal diagnostics
        if diagnostics is None:
            try:
                diagnostics = RuntimeDiagnosticsService.from_env()
            except (OSError, ValueError):
                raise DiagnosticsError("diagnostics_unconfigured", 503) from None
        return diagnostics

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error) -> JSONResponse:
        return _error_response("invalid_request", 422)

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get(
        "/v1/admin/status",
        response_model=AdminStatus,
        dependencies=[Depends(require_shared_secret)],
    )
    async def admin_status() -> AdminStatus:
        nonlocal reasoning_status_probe
        try:
            if reasoning_status_probe is None:
                reasoning_status_probe = CachedCodexReasoningStatus.from_env()
            reasoning = await reasoning_status_probe.inspect()
        except (OSError, RuntimeError, ValueError):
            reasoning = ReasoningComponentStatus(
                state=ComponentState.PENDING,
                detail="error",
            )
        return await asyncio.to_thread(inspect_admin_status, reasoning=reasoning)

    @application.get(
        "/v1/admin/source/status",
        response_model=SourceStatusDiagnostics,
        dependencies=[Depends(require_shared_secret)],
    )
    async def source_status() -> SourceStatusDiagnostics | JSONResponse:
        try:
            return await get_diagnostics().source_status()
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/admin/source/rescan",
        response_model=SourceScanDiagnostics,
        dependencies=[Depends(require_shared_secret)],
    )
    async def source_rescan(
        payload: EmptyDiagnosticsRequest,
    ) -> SourceScanDiagnostics | JSONResponse:
        del payload
        try:
            return await get_diagnostics().rescan_source()
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/admin/source/test",
        response_model=SourceTestDiagnostics,
        dependencies=[Depends(require_shared_secret)],
    )
    async def source_test(
        payload: EmptyDiagnosticsRequest,
    ) -> SourceTestDiagnostics | JSONResponse:
        del payload
        try:
            return await get_diagnostics().test_source()
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/admin/logs/test",
        response_model=LogTestDiagnostics,
        dependencies=[Depends(require_shared_secret)],
    )
    async def logs_test(payload: LogSearchRequest) -> LogTestDiagnostics | JSONResponse:
        try:
            return await get_diagnostics().test_logs(payload)
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/admin/logs/traceback",
        response_model=LogEvidence,
        dependencies=[Depends(require_shared_secret)],
    )
    async def logs_traceback(payload: TracebackRequest) -> LogEvidence | JSONResponse:
        try:
            return await get_diagnostics().read_traceback(payload)
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

    return application


def _error_response(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "ok": False},
    )


app = create_app()
