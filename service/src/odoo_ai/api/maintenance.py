"""Machine-authenticated API for the explicit M7 maintenance catalog."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from odoo_ai.contracts.maintenance import (
    MaintenanceJob,
    MaintenanceRequest,
    MaintenanceResult,
    MaintenanceStatus,
)
from odoo_ai.runtime.maintenance import RuntimeMaintenanceError, RuntimeMaintenanceService
from odoo_ai.security import require_shared_secret

MAX_MAINTENANCE_REQUEST_BYTES: Final = 8 * 1024
_MAINTENANCE_POST_PATHS: Final = frozenset(
    {
        "/v1/admin/maintenance/readiness/test",
        "/v1/admin/maintenance/source/rescan",
        "/v1/admin/maintenance/source/test",
        "/v1/admin/maintenance/logs/test",
        "/v1/admin/maintenance/knowledge/reindex",
        "/v1/admin/maintenance/reasoning/test",
        "/v1/admin/maintenance/configuration/revalidate",
    }
)


class MaintenanceRequestLimitMiddleware:
    """Reject oversized maintenance requests before JSON parsing."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("method") == "POST" and scope.get("path") in _MAINTENANCE_POST_PATHS
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
    "/v1/admin/maintenance/status",
    response_model=MaintenanceStatus,
    dependencies=[Depends(require_shared_secret)],
)
async def maintenance_status(request: Request) -> MaintenanceStatus | JSONResponse:
    try:
        return await _service(request).status()
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.get(
    "/v1/admin/maintenance/jobs/{job_id}",
    response_model=MaintenanceJob,
    dependencies=[Depends(require_shared_secret)],
)
async def maintenance_job(request: Request, job_id: UUID) -> MaintenanceJob | JSONResponse:
    try:
        return await _service(request).job(job_id)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/readiness/test",
    response_model=MaintenanceResult,
    dependencies=[Depends(require_shared_secret)],
)
async def readiness_test(request: Request) -> MaintenanceResult | JSONResponse:
    try:
        payload = await _payload(request)
        return await _service(request).readiness_test(payload.actor)
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/source/rescan",
    response_model=MaintenanceJob,
    dependencies=[Depends(require_shared_secret)],
)
async def source_rescan(
    request: Request,
    background_tasks: BackgroundTasks,
) -> MaintenanceJob | JSONResponse:
    try:
        payload = await _payload(request)
        service = _service(request)
        job = await service.enqueue_source_rescan(payload.actor)
        background_tasks.add_task(service.run_source_rescan_job, job.job_id)
        return job
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/source/test",
    response_model=MaintenanceResult,
    dependencies=[Depends(require_shared_secret)],
)
async def source_test(request: Request) -> MaintenanceResult | JSONResponse:
    try:
        payload = await _payload(request)
        return await _service(request).source_test(payload.actor)
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/logs/test",
    response_model=MaintenanceResult,
    dependencies=[Depends(require_shared_secret)],
)
async def logs_test(request: Request) -> MaintenanceResult | JSONResponse:
    try:
        payload = await _payload(request)
        return await _service(request).logs_test(payload.actor)
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/knowledge/reindex",
    response_model=MaintenanceJob,
    dependencies=[Depends(require_shared_secret)],
)
async def knowledge_reindex(
    request: Request,
    background_tasks: BackgroundTasks,
) -> MaintenanceJob | JSONResponse:
    try:
        payload = await _payload(request)
        service = _service(request)
        job = await service.enqueue_knowledge_reindex(payload.actor)
        background_tasks.add_task(service.run_knowledge_reindex_job, job.job_id)
        return job
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/reasoning/test",
    response_model=MaintenanceResult,
    dependencies=[Depends(require_shared_secret)],
)
async def reasoning_test(request: Request) -> MaintenanceResult | JSONResponse:
    try:
        payload = await _payload(request)
        return await _service(request).reasoning_test(payload.actor)
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


@router.post(
    "/v1/admin/maintenance/configuration/revalidate",
    response_model=MaintenanceResult,
    dependencies=[Depends(require_shared_secret)],
)
async def configuration_revalidate(request: Request) -> MaintenanceResult | JSONResponse:
    try:
        payload = await _payload(request)
        return await _service(request).configuration_revalidate(payload.actor)
    except ValidationError:
        return _error_response("maintenance_invalid", 422)
    except RuntimeMaintenanceError as error:
        return _error_response(error.code, error.status_code)


def install_maintenance_routes(
    application: FastAPI,
    *,
    service: RuntimeMaintenanceService | None = None,
) -> FastAPI:
    """Install only the fixed maintenance handlers; no generic dispatcher exists."""

    if getattr(application.state, "m7_maintenance_routes_installed", False):
        if service is not None:
            application.state.m7_maintenance_service = service
        return application
    application.state.m7_maintenance_routes_installed = True
    if service is not None:
        application.state.m7_maintenance_service = service
    application.add_middleware(
        MaintenanceRequestLimitMiddleware,
        max_bytes=MAX_MAINTENANCE_REQUEST_BYTES,
    )
    application.include_router(router)
    return application


async def _payload(request: Request) -> MaintenanceRequest:
    return MaintenanceRequest.model_validate_json(await request.body())


def _service(request: Request) -> RuntimeMaintenanceService:
    configured = getattr(request.app.state, "m7_maintenance_service", None)
    if isinstance(configured, RuntimeMaintenanceService):
        return configured
    try:
        configured = RuntimeMaintenanceService.from_env()
    except (OSError, ValueError):
        raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
    request.app.state.m7_maintenance_service = configured
    return configured


def _error_response(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "ok": False},
    )
