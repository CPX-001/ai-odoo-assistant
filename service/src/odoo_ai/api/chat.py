"""Machine-authenticated persistent chat and general read endpoints."""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.application.general_chat import GeneralChatError, GeneralChatService
from odoo_ai.contracts.chat import (
    ChatAppendRequest,
    ChatAppendResponse,
    ChatHistoryRequest,
    ChatHistoryResponse,
    GeneralTurnRequest,
    GeneralTurnResponse,
)
from odoo_ai.runtime.chat import RuntimeChatError, RuntimeChatHistoryService
from odoo_ai.security import require_shared_secret

MAX_CHAT_REQUEST_BYTES: Final = 32 * 1024
_CHAT_POST_PATHS: Final = frozenset(
    {"/v1/chat/history", "/v1/chat/append", "/v1/turns/general"}
)


class ChatRequestLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST" and scope.get("path") in _CHAT_POST_PATHS
        ):
            await self._app(scope, receive, send)
            return
        raw_length = dict(scope.get("headers", [])).get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self._max_bytes:
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
    "/v1/chat/history",
    response_model=ChatHistoryResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def chat_history(
    payload: ChatHistoryRequest,
    request: Request,
) -> ChatHistoryResponse | JSONResponse:
    try:
        return await _history_service(request).history(payload)
    except RuntimeChatError as error:
        return _error(error.code, error.status_code)


@router.post(
    "/v1/chat/append",
    response_model=ChatAppendResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def chat_append(
    payload: ChatAppendRequest,
    request: Request,
) -> ChatAppendResponse | JSONResponse:
    try:
        return await _history_service(request).append(payload)
    except RuntimeChatError as error:
        return _error(error.code, error.status_code)


@router.post(
    "/v1/turns/general",
    response_model=GeneralTurnResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def general_turn(
    payload: GeneralTurnRequest,
    request: Request,
) -> GeneralTurnResponse | JSONResponse:
    try:
        return await _general_service(request).run(payload)
    except GeneralChatError as error:
        return _error(error.code, error.status_code)


def install_chat_routes(
    application: FastAPI,
    *,
    history_service: RuntimeChatHistoryService | None = None,
    general_service: GeneralChatService | None = None,
) -> FastAPI:
    if history_service is not None:
        application.state.chat_history_service = history_service
    if general_service is not None:
        application.state.general_chat_service = general_service
    if getattr(application.state, "chat_routes_installed", False):
        return application
    application.state.chat_routes_installed = True
    application.add_middleware(ChatRequestLimitMiddleware, max_bytes=MAX_CHAT_REQUEST_BYTES)
    application.include_router(router)
    return application


def _history_service(request: Request) -> RuntimeChatHistoryService:
    configured = getattr(request.app.state, "chat_history_service", None)
    if isinstance(configured, RuntimeChatHistoryService):
        return configured
    try:
        configured = RuntimeChatHistoryService.from_env()
    except (OSError, ValueError):
        raise RuntimeChatError("chat_store_unavailable", 503) from None
    request.app.state.chat_history_service = configured
    return configured


def _general_service(request: Request) -> GeneralChatService:
    configured = getattr(request.app.state, "general_chat_service", None)
    if isinstance(configured, GeneralChatService):
        return configured
    try:
        configured = GeneralChatService.from_env()
    except (OSError, ValueError):
        raise GeneralChatError("engine_unavailable", 503) from None
    request.app.state.general_chat_service = configured
    return configured


def _error(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "ok": False},
    )
