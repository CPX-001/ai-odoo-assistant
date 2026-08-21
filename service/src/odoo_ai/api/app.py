"""FastAPI application factory for the Assistant Service."""

from collections.abc import Callable
from typing import Final, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.adapters import (
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
    load_instance_summary,
    persist_trace_events,
)
from odoo_ai.application import (
    ContextReadError,
    ContextReadService,
    TraceEventData,
)
from odoo_ai.contracts import (
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    InstanceProfileSummary,
)
from odoo_ai.runtime.status import AdminStatus, inspect_admin_status
from odoo_ai.security import require_shared_secret

MAX_CONTEXT_REQUEST_BYTES: Final = 16 * 1024


class HealthResponse(BaseModel):
    """Stable liveness response with no dependency on external systems."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class ContextRequestLimitMiddleware:
    """Reject oversized contextual turns before FastAPI parses their JSON body."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST"
            and scope.get("path") == "/v1/turns/context-read"
        ):
            await self._app(scope, receive, send)
            return

        raw_length = dict(scope.get("headers", [])).get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self._max_bytes:
                    await _error_response("request_too_large", 413)(
                        scope, receive, send
                    )
                    return
            except ValueError:
                await _error_response("request_too_large", 413)(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            body.extend(chunk)
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


def create_app(
    *,
    gateway_factory: OdooGatewayFactory | None = None,
    instance_loader: Callable[[], InstanceProfileSummary] = load_instance_summary,
    trace_writer: Callable[[UUID, tuple[TraceEventData, ...]], None] | None = None,
) -> FastAPI:
    """Build an isolated application instance for runtime and API tests."""

    application = FastAPI(title="Odoo AI Assistant Service")
    application.add_middleware(
        ContextRequestLimitMiddleware,
        max_bytes=MAX_CONTEXT_REQUEST_BYTES,
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request, error
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
        return inspect_admin_status()

    @application.post(
        "/v1/turns/context-read",
        response_model=ContextReadTurnResponse,
        dependencies=[Depends(require_shared_secret)],
    )
    async def context_read_turn(
        payload: ContextReadTurnRequest,
    ) -> ContextReadTurnResponse | JSONResponse:
        try:
            effective_factory = gateway_factory or OdooGatewayFactory(
                OdooGatewaySettings.from_env()
            )
            service = ContextReadService(
                gateway_factory=effective_factory,
                instance_loader=instance_loader,
                trace_writer=(
                    persist_trace_events
                    if trace_writer is None
                    else trace_writer
                ),
            )
            return await service.run(payload)
        except ContextReadError as error:
            return _error_response(error.code, error.status_code)
        except OdooGatewayError as error:
            code, status_code = _gateway_error(error.code)
            return _error_response(code, status_code)

    return application


def _gateway_error(code: str) -> tuple[str, int]:
    if code in {"access_denied", "delegation_rejected"}:
        return "access_denied", 403
    if code in {"invalid_request", "request_too_large"}:
        return code, 413 if code == "request_too_large" else 422
    if code in {"malformed_response", "response_too_large"}:
        return "invalid_gateway_response", 502
    return "service_unavailable", 503


def _error_response(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "ok": False},
    )


app = create_app()
