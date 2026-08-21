"""FastAPI application factory for the Assistant Service."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict


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

    return application


app = create_app()
