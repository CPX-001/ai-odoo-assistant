"""Machine-authenticated M7 structured diagnostics endpoint."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from odoo_ai.contracts.admin_diagnostics import AdminDiagnosticsMatrix
from odoo_ai.runtime.admin_diagnostics import RuntimeAdminDiagnosticsService
from odoo_ai.security import require_shared_secret

_DIAGNOSTICS_PATH = "/v1/admin/diagnostics"


def install_admin_diagnostics_routes(
    application: FastAPI,
    *,
    service: RuntimeAdminDiagnosticsService | None = None,
) -> FastAPI:
    """Install the isolated M7 diagnostics matrix route exactly once."""

    if any(getattr(route, "path", None) == _DIAGNOSTICS_PATH for route in application.routes):
        return application

    active_service = service

    def get_service() -> RuntimeAdminDiagnosticsService:
        nonlocal active_service
        if active_service is None:
            active_service = RuntimeAdminDiagnosticsService.from_env()
        return active_service

    @application.get(
        _DIAGNOSTICS_PATH,
        response_model=AdminDiagnosticsMatrix,
        dependencies=[Depends(require_shared_secret)],
    )
    async def admin_diagnostics() -> AdminDiagnosticsMatrix:
        return await get_service().inspect()

    return application
