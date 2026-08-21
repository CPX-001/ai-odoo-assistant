import asyncio

from httpx import ASGITransport, AsyncClient, Response

from odoo_ai.api import create_app


async def _get_health() -> Response:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/health")


def test_health_returns_stable_liveness_payload() -> None:
    response = asyncio.run(_get_health())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_app_factory_returns_isolated_instances() -> None:
    assert create_app() is not create_app()
