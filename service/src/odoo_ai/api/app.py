"""FastAPI application factory for the Assistant Service."""

import asyncio
from collections.abc import Callable
from typing import Final, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.adapters import (
    CachedCodexReasoningStatus,
    CodexAppServerEngine,
    CodexRuntimeSettings,
    KnowledgeToolExecutorFactory,
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
    QueryToolExecutorFactory,
    RuntimeDiagnosticsService,
    SourceToolExecutorFactory,
    knowledge_tool_specs,
    load_instance_summary,
    persist_trace_events,
    query_tool_specs,
    source_tool_specs,
)
from odoo_ai.application import (
    ActionApprovalError,
    ActionApprovalService,
    ActionExecutionError,
    ActionExecutionService,
    ContextReadError,
    ContextReadService,
    DiagnosticsError,
    DiagnosticsService,
    ExplainService,
    ExplainTurnError,
    HowToService,
    HowToTurnError,
    QueryService,
    QueryTurnError,
    TraceEventData,
)
from odoo_ai.contracts import (
    ActionDecisionReceipt,
    ActionDecisionRequest,
    ActionExecutionReceipt,
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    EmptyDiagnosticsRequest,
    ExecuteApprovedActionRequest,
    ExplainTurnRequest,
    ExplainTurnResponse,
    HowToTurnRequest,
    HowToTurnResponse,
    InstanceProfileSummary,
    LogEvidence,
    LogSearchRequest,
    LogTestDiagnostics,
    PersistActionPreviewRequest,
    PersistActionPreviewResponse,
    QueryTurnRequest,
    QueryTurnResponse,
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
from odoo_ai.security import ActionAuthorityCodec, ActionAuthorityError, require_shared_secret
from odoo_ai.storage import (
    DatabaseSettings,
    SqlActionApprovalStore,
    create_database_engine,
    create_session_factory,
)

MAX_CONTEXT_REQUEST_BYTES: Final = 16 * 1024
_BOUNDED_POST_PATHS: Final = frozenset(
    {
        "/v1/turns/context-read",
        "/v1/turns/explain",
        "/v1/turns/how-to",
        "/v1/turns/query",
        "/v1/admin/source/rescan",
        "/v1/admin/source/test",
        "/v1/admin/logs/test",
        "/v1/admin/logs/traceback",
        "/v1/actions/previews",
        "/v1/actions/decisions",
        "/v1/actions/commits",
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
    query_service: QueryService | None = None,
    how_to_service: HowToService | None = None,
    action_approval_service: ActionApprovalService | None = None,
    action_execution_service: ActionExecutionService | None = None,
) -> FastAPI:
    """Build an isolated application instance for runtime and API tests."""

    application = FastAPI(title="Odoo AI Assistant Service")
    application.add_middleware(
        BoundedRequestLimitMiddleware,
        max_bytes=MAX_CONTEXT_REQUEST_BYTES,
    )
    diagnostics = diagnostics_service
    approvals = action_approval_service
    executions = action_execution_service
    reasoning_status_probe: CachedCodexReasoningStatus | None = None

    def get_action_approval_service() -> ActionApprovalService:
        nonlocal approvals
        if approvals is None:
            try:
                engine = create_database_engine(DatabaseSettings.from_env())
                approvals = ActionApprovalService(
                    SqlActionApprovalStore(create_session_factory(engine))
                )
            except (OSError, ValueError):
                raise ActionApprovalError("approval_store_unavailable", 503) from None
        return approvals

    def get_action_execution_service() -> ActionExecutionService:
        nonlocal executions
        if executions is None:
            try:
                engine = create_database_engine(DatabaseSettings.from_env())
                store = SqlActionApprovalStore(create_session_factory(engine))
                executions = ActionExecutionService(
                    store=store,
                    authority_codec=ActionAuthorityCodec.from_env(),
                    gateway_factory=gateway_factory
                    or OdooGatewayFactory(OdooGatewaySettings.from_env()),
                )
            except (ActionAuthorityError, OdooGatewayError, OSError, ValueError):
                raise ActionExecutionError("action_execution_unavailable", 503) from None
        return executions

    def get_explain_service() -> ExplainService:
        if explain_service is not None:
            return explain_service
        effective_factory = gateway_factory or OdooGatewayFactory(
            OdooGatewaySettings.from_env()
        )
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
            trace_writer=(
                persist_trace_events if trace_writer is None else trace_writer
            ),
        )

    def get_diagnostics() -> DiagnosticsService:
        nonlocal diagnostics
        if diagnostics is None:
            try:
                diagnostics = RuntimeDiagnosticsService.from_env()
            except (OSError, ValueError):
                raise DiagnosticsError("diagnostics_unconfigured", 503) from None
        return diagnostics

    def get_query_service(payload: QueryTurnRequest) -> QueryService:
        if query_service is not None:
            return query_service
        effective_factory = gateway_factory or OdooGatewayFactory(OdooGatewaySettings.from_env())
        gateway = effective_factory.for_turn(
            turn_id=payload.turn_id,
            delegation_token=payload.delegation_token,
        )
        query_factory = QueryToolExecutorFactory(
            gateway=gateway,
            user_id=payload.user.uid,
            model=payload.screen.model or "",
        )
        engine = CodexAppServerEngine(
            CodexRuntimeSettings.from_env(),
            tool_executor_factory=query_factory,
        )
        return QueryService(
            reasoning_engine=engine,
            query_tools=query_tool_specs(),
            report_loader=query_factory.take_report,
            instance_loader=instance_loader,
            trace_writer=(persist_trace_events if trace_writer is None else trace_writer),
        )

    def get_how_to_service() -> HowToService:
        if how_to_service is not None:
            return how_to_service
        effective_factory = gateway_factory or OdooGatewayFactory(
            OdooGatewaySettings.from_env()
        )
        knowledge_factory = KnowledgeToolExecutorFactory.from_env()
        engine = CodexAppServerEngine(
            CodexRuntimeSettings.from_env(),
            tool_executor_factory=knowledge_factory,
        )
        return HowToService(
            gateway_factory=effective_factory,
            reasoning_engine=engine,
            knowledge_tools=knowledge_tool_specs(),
            report_loader=knowledge_factory.take_report,
            instance_loader=instance_loader,
            trace_writer=(persist_trace_events if trace_writer is None else trace_writer),
        )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        del request, error
        return _error_response("invalid_request", 422)

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.post(
        "/v1/actions/previews",
        response_model=PersistActionPreviewResponse,
        dependencies=[Depends(require_shared_secret)],
    )
    async def persist_action_preview(
        request: Request,
    ) -> PersistActionPreviewResponse | JSONResponse:
        try:
            payload = PersistActionPreviewRequest.model_validate_json(
                await request.body()
            )
            return await asyncio.to_thread(
                get_action_approval_service().persist_preview,
                payload,
            )
        except ValidationError:
            return _error_response("invalid_request", 422)
        except ActionApprovalError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/actions/decisions",
        response_model=ActionDecisionReceipt,
        dependencies=[Depends(require_shared_secret)],
    )
    async def decide_action(
        request: Request,
    ) -> ActionDecisionReceipt | JSONResponse:
        try:
            payload = ActionDecisionRequest.model_validate_json(await request.body())
            return await asyncio.to_thread(
                get_action_approval_service().decide,
                payload,
            )
        except ValidationError:
            return _error_response("invalid_request", 422)
        except ActionApprovalError as error:
            return _error_response(error.code, error.status_code)

    @application.post(
        "/v1/actions/commits",
        response_model=ActionExecutionReceipt,
        dependencies=[Depends(require_shared_secret)],
    )
    async def commit_action(request: Request) -> ActionExecutionReceipt | JSONResponse:
        try:
            payload = ExecuteApprovedActionRequest.model_validate_json(
                await request.body()
            )
            return await get_action_execution_service().execute(payload)
        except ValidationError:
            return _error_response("invalid_request", 422)
        except ActionExecutionError as error:
            return _error_response(error.code, error.status_code)

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

    @application.post(
        "/v1/turns/how-to",
        response_model=HowToTurnResponse,
        dependencies=[Depends(require_shared_secret)],
    )
    async def how_to_turn(
        payload: HowToTurnRequest,
    ) -> HowToTurnResponse | JSONResponse:
        try:
            return await get_how_to_service().run(payload)
        except HowToTurnError as error:
            return _error_response(error.code, error.status_code)
        except Exception:  # noqa: BLE001 - sanitize infrastructure details
            return _error_response("engine_unavailable", 503)

    @application.post(
        "/v1/turns/query",
        response_model=QueryTurnResponse,
        dependencies=[Depends(require_shared_secret)],
    )
    async def query_turn(
        payload: QueryTurnRequest,
    ) -> QueryTurnResponse | JSONResponse:
        try:
            return await get_query_service(payload).run(payload)
        except QueryTurnError as error:
            return _error_response(error.code, error.status_code)
        except Exception:  # noqa: BLE001 - sanitize infrastructure details
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
