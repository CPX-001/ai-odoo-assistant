import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from odoo_ai.api import create_app
from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    LogCorrelation,
    LogEvidence,
    LogPointer,
    LogSearchRequest,
    LogTestDiagnostics,
    SourceCandidate,
    SourceCapabilityState,
    SourceExcerpt,
    SourceExcerptLine,
    SourceMatchReason,
    SourceProvenance,
    SourceRef,
    SourceScanDiagnostics,
    SourceScanMetricsView,
    SourceStatusDiagnostics,
    SourceTestDiagnostics,
    TimestampRange,
    TracebackRequest,
)

ADMIN_SECRET = "m3-api-secret-" + "s" * 48
FINGERPRINT = "sha256:" + "a" * 64
TRACEBACK_FINGERPRINT = "sha256:" + "b" * 64
SOURCE_ID = UUID("12345678-1234-5678-1234-567812345678")


class FakeDiagnosticsService:
    def __init__(self) -> None:
        self.log_request: LogSearchRequest | None = None
        self.traceback_request: TracebackRequest | None = None

    async def source_status(self) -> SourceStatusDiagnostics:
        return SourceStatusDiagnostics(
            state=SourceCapabilityState.DETECTED,
            scan_status="succeeded",
            scan_id=SOURCE_ID,
            fingerprint=FINGERPRINT,
            completed_at=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
        )

    async def rescan_source(self) -> SourceScanDiagnostics:
        return SourceScanDiagnostics(
            state=SourceCapabilityState.DETECTED,
            scan_id=SOURCE_ID,
            fingerprint=FINGERPRINT,
            metrics=SourceScanMetricsView(
                modules=1,
                files_seen=2,
                files_extracted=2,
                files_unchanged=0,
                bytes_hashed=512,
                stale_files=0,
            ),
        )

    async def test_source(self) -> SourceTestDiagnostics:
        ref = SourceRef(
            source_file_id=SOURCE_ID,
            fingerprint=FINGERPRINT,
            start_line=10,
            end_line=12,
        )
        candidate = SourceCandidate(
            symbol_id=SOURCE_ID,
            module="odoo_ai_m3_sale_project",
            kind="method",
            model="sale.order",
            name="action_confirm",
            logical_path="odoo_ai_m3_sale_project/models/sale_order.py",
            start_line=10,
            end_line=12,
            fingerprint=FINGERPRINT,
            provenance=SourceProvenance.UNKNOWN,
            ref=ref,
            score=100,
            match_reason=SourceMatchReason.EXACT,
            observed_at=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
        )
        evidence = Evidence(
            evidence_id=SOURCE_ID,
            kind=EvidenceKind.SOURCE,
            status=EvidenceStatus.CHECKED,
            title="Fixture source",
            summary="Bounded fixture excerpt.",
            payload={"trust": "untrusted_source"},
            pointer={"logical_path": candidate.logical_path},
            observed_at=candidate.observed_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=FINGERPRINT,
        )
        return SourceTestDiagnostics(
            candidate=candidate,
            excerpt=SourceExcerpt(
                ref=ref,
                module=candidate.module,
                logical_path=candidate.logical_path,
                lines=(SourceExcerptLine(number=10, text="def action_confirm(self):"),),
                evidence=evidence,
            ),
        )

    async def test_logs(self, request: LogSearchRequest) -> LogTestDiagnostics:
        self.log_request = request
        return LogTestDiagnostics(provider="file", results=(self._log(),))

    async def read_traceback(self, request: TracebackRequest) -> LogEvidence:
        self.traceback_request = request
        return self._log()

    @staticmethod
    def _log() -> LogEvidence:
        return LogEvidence(
            provider="file",
            timestamp_range=TimestampRange(
                from_ts=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
                to_ts=datetime(2026, 8, 22, 10, 1, tzinfo=UTC),
            ),
            excerpt="Traceback (most recent call last):\nValueError: controlled",
            traceback_fingerprint=TRACEBACK_FINGERPRINT,
            correlation=LogCorrelation.DIRECT,
            pointer=LogPointer(provider="file", reference=TRACEBACK_FINGERPRINT),
            line_count=2,
            byte_count=64,
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "shared-secret"
    secret.write_text(ADMIN_SECRET, encoding="utf-8")
    secret.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret))


async def _request(method: str, path: str, *, json=None, secret=ADMIN_SECRET):
    diagnostics = FakeDiagnosticsService()
    transport = ASGITransport(app=create_app(diagnostics_service=diagnostics))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method,
            path,
            json=json,
            headers={"X-Odoo-AI-Shared-Secret": secret} if secret else {},
        )
    return response, diagnostics


def test_admin_diagnostics_routes_are_authenticated_and_bounded() -> None:
    routes = (
        ("GET", "/v1/admin/source/status", None),
        ("POST", "/v1/admin/source/rescan", {}),
        ("POST", "/v1/admin/source/test", {}),
        (
            "POST",
            "/v1/admin/logs/test",
            {"terms": ["Traceback"], "max_lines": 20, "max_bytes": 4096},
        ),
        (
            "POST",
            "/v1/admin/logs/traceback",
            {"fingerprint": TRACEBACK_FINGERPRINT, "max_bytes": 4096},
        ),
    )

    for method, path, payload in routes:
        rejected, _ = asyncio.run(_request(method, path, json=payload, secret=None))
        accepted, _ = asyncio.run(_request(method, path, json=payload))
        assert rejected.status_code == 401
        assert accepted.status_code == 200
        assert ADMIN_SECRET not in accepted.text


def test_source_actions_reject_arbitrary_paths_and_log_actions_reject_units() -> None:
    source, _ = asyncio.run(_request("POST", "/v1/admin/source/test", json={"path": "/etc/passwd"}))
    logs, _ = asyncio.run(
        _request(
            "POST",
            "/v1/admin/logs/test",
            json={
                "terms": ["Traceback"],
                "max_lines": 20,
                "max_bytes": 4096,
                "unit": "--all.service",
            },
        )
    )

    assert source.status_code == 422
    assert logs.status_code == 422
    assert "/etc/passwd" not in source.text


def test_log_requests_reach_only_the_bounded_provider_contract() -> None:
    response, search_diagnostics = asyncio.run(
        _request(
            "POST",
            "/v1/admin/logs/test",
            json={
                "from_ts": "2026-08-22T10:00:00Z",
                "to_ts": "2026-08-22T10:02:00Z",
                "terms": ["M3_DIAGNOSTIC_TRACEBACK"],
                "max_lines": 20,
                "max_bytes": 4096,
            },
        )
    )
    traceback, traceback_diagnostics = asyncio.run(
        _request(
            "POST",
            "/v1/admin/logs/traceback",
            json={"fingerprint": TRACEBACK_FINGERPRINT, "max_bytes": 1024},
        )
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "file"
    assert search_diagnostics.log_request == LogSearchRequest(
        from_ts=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
        to_ts=datetime(2026, 8, 22, 10, 2, tzinfo=UTC),
        terms=["M3_DIAGNOSTIC_TRACEBACK"],
        max_lines=20,
        max_bytes=4096,
    )
    assert traceback.status_code == 200
    assert traceback_diagnostics.traceback_request == TracebackRequest(
        fingerprint=TRACEBACK_FINGERPRINT, max_bytes=1024
    )


def test_admin_request_size_is_rejected_before_json_parsing() -> None:
    response, _ = asyncio.run(
        _request(
            "POST",
            "/v1/admin/logs/test",
            json={
                "terms": ["x" * 20_000],
                "max_lines": 20,
                "max_bytes": 4096,
            },
        )
    )

    assert response.status_code == 413
