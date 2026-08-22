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
    CodexAppServerEngine,
    CodexRuntimeSettings,
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
    RuntimeDiagnosticsService,
    SourceToolExecutorFactory,
    load_instance_summary,
    persist_trace_events,
    source_tool_specs,
)
from odoo_ai.application import (
    ContextReadError,
    ContextReadService,
    DiagnosticsError,
    DiagnosticsService,
    ExplainService,
    ExplainTurnError,
    TraceEventData,
)
from odoo_ai.contracts import (
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    EmptyDiagnosticsRequest,
    ExplainTurnRequest,
    ExplainTurnResponse,
    InstanceProfileSummary,
    LogEvidence,
    LogSearchRequest,
    LogTestDiagnostics,
    SourceScanDiagnostics,
    SourceStatusDiagnostics,
    SourceTestDiagnostics,
    TracebackRequest,
)
from odoo_ai.runtime.status import AdminStatus, inspect_admin_status
from odoo_ai.security import require_shared_secret

MAX_CONTEXT_REQUEST_BYTES: Final = 16 * 1024
_BOUNDED_POST_PATHS: Final = frozenset(
    {
        "/v1/turns/context-read",
        "/v1/turns/explain",
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
    """Reject oversized turn/admin requests before FastAPI parses JSON."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST" and scope.get("path") in _BOUNDED_POST_PATHS
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
    diagnostics_service: DiagnosticsService | None = None,
    explain_service: ExplainService | None = None,
) -> FastAPI:
    """Build an isolated application instance for runtime and API tests."""

    application = FastAPI(title="Odoo AI Assistant Service")
    application.add_middleware(
        BoundedRequestLimitMiddleware,
        max_bytes=MAX_CONTEXT_REQUEST_BYTES,
    )
    diagnostics = diagnostics_service

    def get_explain_service() -> ExplainService:
        if explain_service is not None:
            return explain_service
        effective_factory = gateway_factory or OdooGatewayFactory(OdooGatewaySettings.from_env())
        source_factory = SourceToolExecutorFactory.from_env()
        engine = CodexAppServerEngine(
            CodexRuntimeSettings.from_env(),
            tool_executor_factory=source_factory,
        )
        return ExplainService(
            gateway_factory=effective_factory,
            reasoning_engine=engine,
            source_tools=source_tool_specs(),
            report_loader=source_factory.take_report,
            instance_loader=instance_loader,
            trace_writer=(persist_trace_events if trace_writer is None else trace_writer),
        )

    def get_diagnostics() -> DiagnosticsService:
        nonlocal diagnostics
        if diagnostics is None:
            try:
                diagnostics = RuntimeDiagnosticsService.from_env()
            except (OSError, ValueError):
                raise DiagnosticsError("diagnostics_unconfigured", 503) from None
        return diagnostics

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
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
    async def logs_test(
        payload: LogSearchRequest,
    ) -> LogTestDiagnostics | JSONResponse:
        try:
            return await get_diagnostics().test_logs(payload)
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/admin/logs/traceback",
        response_model=LogEvidence,
        dependencies=[Depends(require_shared_secret)],
    )
    async def logs_traceback(
        payload: TracebackRequest,
    ) -> LogEvidence | JSONResponse:
        try:
            return await get_diagnostics().read_traceback(payload)
        except DiagnosticsError as error:
            return _error_response(error.code, error.status_code)

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
                trace_writer=(persist_trace_events if trace_writer is None else trace_writer),
            )
            return await service.run(payload)
        except ContextReadError as error:
            return _error_response(error.code, error.status_code)
        except OdooGatewayError as error:
            code, status_code = _gateway_error(error.code)
            return _error_response(code, status_code)

    @application.post(
        "/v1/turns/explain",
        response_model=ExplainTurnResponse,
        dependencies=[Depends(require_shared_secret)],
    )
    async def explain_turn(
        payload: ExplainTurnRequest,
    ) -> ExplainTurnResponse | JSONResponse:
        try:
            return await get_explain_service().run(payload)
        except ExplainTurnError as error:
            return _error_response(error.code, error.status_code)
        # This is an authenticated infrastructure boundary; never expose
        # configuration/provider exception details to Odoo.
        except Exception:  # noqa: BLE001
            return _error_response("engine_unavailable", 503)

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
