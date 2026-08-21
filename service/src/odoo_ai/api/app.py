"""FastAPI application factory for the Assistant Service."""

from typing import Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict

from odoo_ai.runtime.status import AdminStatus, inspect_admin_status
from odoo_ai.security import require_shared_secret


class HealthResponse(BaseModel):
    """Stable liveness response with no dependency on external systems."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    """Build an isolated application instance for runtime and API tests."""

    application = FastAPI(title="Odoo AI Assistant Service")

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

    return application


app = create_app()
