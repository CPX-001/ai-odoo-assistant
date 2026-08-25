"""Machine-authenticated unified agent plan endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Final, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.application.agent_events import bind_agent_delta_sink, reset_agent_delta_sink
from odoo_ai.application.agent_execution import AgentExecutionError, AgentPlanExecutionService
from odoo_ai.application.agent_failure import agent_failure_response
from odoo_ai.application.agent_plans import AgentPlanError, AgentPlanService
from odoo_ai.application.agent_turn import AgentTurnError, AgentTurnService
from odoo_ai.contracts import (
    AgentPlanDecisionRequest,
    AgentPlanDecisionResponse,
    AgentPlanExecutionRequest,
    AgentPlanStatusResponse,
    AgentTurnRequest,
    AgentTurnResponse,
)
from odoo_ai.contracts.agent_stream import AgentTurnDeltaEvent, AgentTurnFinalEvent
from odoo_ai.runtime.agent import RuntimeAgentFactory
from odoo_ai.security import require_shared_secret

MAX_AGENT_REQUEST_BYTES: Final = 64 * 1024
_STREAM_QUEUE_SIZE: Final = 32
LOGGER = logging.getLogger(__name__)


class AgentServiceFactory(Protocol):
    def turn_service(self, request: AgentTurnRequest) -> AgentTurnService: ...

    def plan_service(self) -> AgentPlanService: ...

    def execution_service(self) -> AgentPlanExecutionService: ...


class AgentRequestLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST"
            and str(scope.get("path", "")).startswith("/v1/agent/")
        ):
            await self._app(scope, receive, send)
            return
        raw_length = dict(scope.get("headers", [])).get(b"content-length")
        try:
            if raw_length is not None and int(raw_length) > self._max_bytes:
                await _error("request_too_large", 413)(scope, receive, send)
                return
        except ValueError:
            await _error("request_too_large", 413)(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self._max_bytes:
                await _error("request_too_large", 413)(scope, receive, send)
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


@router.post(
    "/v1/agent/turn",
    response_model=AgentTurnResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def agent_turn(
    payload: AgentTurnRequest,
    request: Request,
) -> AgentTurnResponse:
    try:
        return await _factory(request).turn_service(payload).run(payload)
    except AgentTurnError as error:
        LOGGER.warning("Unified agent turn failed: %s", error.code)
        return agent_failure_response(payload, error.code)
    except Exception:
        LOGGER.exception("Unified agent turn failed unexpectedly")
        return agent_failure_response(payload, "agent_unavailable")


@router.post(
    "/v1/agent/turn/stream",
    dependencies=[Depends(require_shared_secret)],
)
async def agent_turn_stream(
    payload: AgentTurnRequest,
    request: Request,
) -> StreamingResponse:
    """Stream provisional answer text and finish with one host-validated turn response."""

    service = _factory(request).turn_service(payload)
    return StreamingResponse(
        _stream_agent_turn(payload, service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/v1/agent/plans/{plan_id}/decision",
    response_model=AgentPlanDecisionResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def agent_plan_decision(
    plan_id: UUID,
    payload: AgentPlanDecisionRequest,
    request: Request,
) -> AgentPlanDecisionResponse | JSONResponse:
    if payload.plan_id != plan_id:
        return _error("agent_plan_binding_mismatch", 422)
    try:
        return await asyncio.to_thread(_factory(request).plan_service().decide, payload)
    except AgentPlanError as error:
        return _error(error.code, error.status_code)
    except Exception:
        return _error("agent_plan_store_unavailable", 503)


@router.post(
    "/v1/agent/plans/{plan_id}/execute",
    response_model=AgentPlanStatusResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def agent_plan_execute(
    plan_id: UUID,
    payload: AgentPlanExecutionRequest,
    request: Request,
) -> AgentPlanStatusResponse | JSONResponse:
    if payload.plan_id != plan_id:
        return _error("agent_plan_binding_mismatch", 422)
    try:
        return await _factory(request).execution_service().execute(payload)
    except AgentExecutionError as error:
        LOGGER.warning("Unified agent execution rejected: %s", error.code)
        return _error(error.code, error.status_code)
    except Exception:
        return _error("agent_execution_unavailable", 503)


@router.get(
    "/v1/agent/plans/{plan_id}",
    response_model=AgentPlanStatusResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def agent_plan_status(
    plan_id: UUID,
    request: Request,
    database: str = Query(min_length=1, max_length=128),
    uid: int = Query(gt=0),
) -> AgentPlanStatusResponse | JSONResponse:
    try:
        return await asyncio.to_thread(
            _factory(request).plan_service().get_status,
            plan_id,
            database,
            uid,
        )
    except AgentPlanError as error:
        return _error(error.code, error.status_code)
    except Exception:
        return _error("agent_plan_store_unavailable", 503)


async def _stream_agent_turn(
    payload: AgentTurnRequest,
    service: AgentTurnService,
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[AgentTurnDeltaEvent | AgentTurnFinalEvent | None] = asyncio.Queue(
        maxsize=_STREAM_QUEUE_SIZE
    )

    async def delta_sink(text: str) -> None:
        await queue.put(AgentTurnDeltaEvent(text=text))

    async def produce() -> None:
        token = bind_agent_delta_sink(delta_sink)
        try:
            try:
                response = await service.run(payload)
            except AgentTurnError as error:
                LOGGER.warning("Unified streaming agent turn failed: %s", error.code)
                response = agent_failure_response(payload, error.code)
            except Exception:
                LOGGER.exception("Unified streaming agent turn failed unexpectedly")
                response = agent_failure_response(payload, "agent_unavailable")
            await queue.put(AgentTurnFinalEvent(response=response))
        finally:
            reset_agent_delta_sink(token)
            await queue.put(None)

    producer = asyncio.create_task(produce())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse_event(event.type, event.model_dump(mode="json"))
    finally:
        if not producer.done():
            producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)


def _sse_event(event: str, payload: dict[str, object]) -> bytes:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"event: {event}\ndata: {encoded}\n\n".encode("utf-8")


def install_agent_routes(
    application: FastAPI,
    *,
    factory: AgentServiceFactory | None = None,
) -> FastAPI:
    if factory is not None:
        application.state.agent_service_factory = factory
    if getattr(application.state, "agent_routes_installed", False):
        return application
    application.state.agent_routes_installed = True
    application.add_middleware(
        AgentRequestLimitMiddleware,
        max_bytes=MAX_AGENT_REQUEST_BYTES,
    )
    application.include_router(router)
    return application


def _factory(request: Request) -> AgentServiceFactory:
    configured = getattr(request.app.state, "agent_service_factory", None)
    if configured is not None:
        return cast(AgentServiceFactory, configured)
    configured = RuntimeAgentFactory.from_env()
    request.app.state.agent_service_factory = configured
    return configured


def _error(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "ok": False},
    )
