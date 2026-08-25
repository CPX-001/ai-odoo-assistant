import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.contracts.admin_configuration import (
    AdminConfigurationActor,
    AdminConfigurationAuthorized,
    AdminConfigurationResponse,
)
from odoo_ai.contracts.configuration import (
    AssistantAdminOverrides,
    resolve_config_snapshot,
)
from odoo_ai.runtime.configuration import (
    RuntimeConfigurationError,
    RuntimeConfigurationService,
)

ADMIN_SECRET = "m7-admin-secret-" + "s" * 48


class StubConfigurationService(RuntimeConfigurationService):
    def __init__(self) -> None:
        self.revision = 0
        self.overrides = AssistantAdminOverrides()

    def snapshot(self) -> AdminConfigurationResponse:
        return self._response()

    def validate(self, overrides: AssistantAdminOverrides) -> AdminConfigurationResponse:
        return self._response(overrides=overrides)

    def apply(
        self,
        *,
        expected_revision: int,
        overrides: AssistantAdminOverrides,
        actor: AdminConfigurationActor,
    ) -> AdminConfigurationResponse:
        del actor
        if expected_revision != self.revision:
            raise RuntimeConfigurationError("configuration_revision_conflict", 409)
        if overrides != self.overrides:
            self.revision += 1
            self.overrides = overrides
        return self._response(overrides=self.overrides)

    def _response(
        self,
        *,
        overrides: AssistantAdminOverrides | None = None,
    ) -> AdminConfigurationResponse:
        effective = self.overrides if overrides is None else overrides
        snapshot = resolve_config_snapshot(())
        return AdminConfigurationResponse(
            revision=self.revision,
            fingerprint=snapshot.fingerprint,
            validation_state="valid",
            post_action="none",
            overrides=effective,
            authorized=AdminConfigurationAuthorized(),
            snapshot=snapshot,
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{ADMIN_SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


async def _request(
    method: str,
    path: str,
    *,
    service: RuntimeConfigurationService | None = None,
    json_payload: object | None = None,
    secret: str | None = ADMIN_SECRET,
    content: bytes | None = None,
) -> Response:
    transport = ASGITransport(app=create_app(configuration_service=service))
    headers = {"X-Odoo-AI-Shared-Secret": secret} if secret is not None else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(
            method,
            path,
            headers=headers,
            json=json_payload,
            content=content,
        )


def test_configuration_snapshot_requires_machine_auth_and_is_sanitized() -> None:
    service = StubConfigurationService()

    missing = asyncio.run(
        _request("GET", "/v1/admin/configuration", service=service, secret=None)
    )
    response = asyncio.run(_request("GET", "/v1/admin/configuration", service=service))

    assert missing.status_code == 401
    assert response.status_code == 200
    assert response.json()["revision"] == 0
    assert ADMIN_SECRET not in response.text


def test_configuration_validate_rejects_unknown_or_host_only_keys() -> None:
    service = StubConfigurationService()

    unknown = asyncio.run(
        _request(
            "POST",
            "/v1/admin/configuration/validate",
            service=service,
            json_payload={"overrides": {"arbitrary_key": "value"}},
        )
    )
    host_only = asyncio.run(
        _request(
            "POST",
            "/v1/admin/configuration/validate",
            service=service,
            json_payload={"overrides": {"database_url": "postgresql://forbidden"}},
        )
    )

    assert unknown.status_code == 422
    assert unknown.json() == {"error": {"code": "configuration_invalid"}, "ok": False}
    assert host_only.status_code == 422


def test_configuration_apply_is_revision_guarded() -> None:
    service = StubConfigurationService()
    payload = {
        "expected_revision": 0,
        "overrides": {"reasoning_model": "gpt-5.6/codex"},
        "actor": {"odoo_uid": 7, "odoo_database": "customer"},
    }

    applied = asyncio.run(
        _request(
            "POST",
            "/v1/admin/configuration/apply",
            service=service,
            json_payload=payload,
        )
    )
    stale = asyncio.run(
        _request(
            "POST",
            "/v1/admin/configuration/apply",
            service=service,
            json_payload=payload,
        )
    )

    assert applied.status_code == 200
    assert applied.json()["revision"] == 1
    assert stale.status_code == 409
    assert stale.json() == {
        "error": {"code": "configuration_revision_conflict"},
        "ok": False,
    }


def test_configuration_apply_rejects_oversized_body_before_json_parse() -> None:
    service = StubConfigurationService()
    body = b'{' + b'"padding":"' + b"x" * (17 * 1024) + b'"}'

    response = asyncio.run(
        _request(
            "POST",
            "/v1/admin/configuration/apply",
            service=service,
            content=body,
        )
    )

    assert response.status_code == 413
    assert response.json() == {"error": {"code": "request_too_large"}, "ok": False}
