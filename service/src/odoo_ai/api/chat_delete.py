"""Machine-authenticated endpoint for deleting Assistant chat conversations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from odoo_ai.contracts.chat_delete import ChatDeleteRequest, ChatDeleteResponse
from odoo_ai.runtime.chat_delete import RuntimeChatDeleteError, RuntimeChatDeleteService
from odoo_ai.security import require_shared_secret

router = APIRouter()


@router.post(
    "/v1/chat/delete",
    response_model=ChatDeleteResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def chat_delete(
    payload: ChatDeleteRequest,
    request: Request,
) -> ChatDeleteResponse | JSONResponse:
    try:
        return await _delete_service(request).delete(payload)
    except RuntimeChatDeleteError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code}, "ok": False},
        )


def install_chat_delete_routes(
    application: FastAPI,
    *,
    service: RuntimeChatDeleteService | None = None,
) -> FastAPI:
    if service is not None:
        application.state.chat_delete_service = service
    if getattr(application.state, "chat_delete_routes_installed", False):
        return application
    application.state.chat_delete_routes_installed = True
    application.include_router(router)
    return application


def _delete_service(request: Request) -> RuntimeChatDeleteService:
    configured = getattr(request.app.state, "chat_delete_service", None)
    if isinstance(configured, RuntimeChatDeleteService):
        return configured
    try:
        configured = RuntimeChatDeleteService.from_env()
    except (OSError, ValueError):
        raise RuntimeChatDeleteError("chat_store_unavailable", 503) from None
    request.app.state.chat_delete_service = configured
    return configured
