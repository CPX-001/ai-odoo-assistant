import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from odoo_ai.contracts import LogCapabilityState, LogCorrelation, LogSearchRequest
from odoo_ai.logs import (
    FileLogLimits,
    FileLogProvider,
    LogFileOrigin,
    LogFileSelection,
    LogProviderError,
    LogRedactor,
    ResolvedLogFile,
    log_file_override_from_env,
    resolve_log_file,
)


def _provider(path: Path, *, limits: FileLogLimits | None = None) -> FileLogProvider:
    return FileLogProvider(
        resolved=ResolvedLogFile(path.resolve(), LogFileOrigin.OVERRIDE),
        limits=limits or FileLogLimits(context_lines=3),
        redactor=LogRedactor(configured_secrets=("shared-secret-fixture-123",)),
    )


def _search(provider: FileLogProvider, request: LogSearchRequest):
    return asyncio.run(provider.search(request))


@pytest.fixture
def file_log(tmp_path: Path) -> Path:
    path = tmp_path / "customer logs" / "erp production.log"
    path.parent.mkdir()
    path.write_text(
        "2026-08-22 09:59:59,000 INFO odoo startup\n"
        "2026-08-22 10:00:00,100 ERROR sale action_confirm failed\n"
        "Traceback (most recent call last):\n"
        '  File "/srv/odoo/sale.py", line 42, in action_confirm\n'
        "ValueError: invalid order password=super-secret-value\n"
        "2026-08-22 10:00:01.200 INFO Bearer abcdefghijklmnop\n"
        "2026-08-22 10:05:00,000 INFO shared-secret-fixture-123\n",
        encoding="utf-8",
    )
    return path


def test_file_log_search_by_window_and_terms_is_redacted(file_log: Path) -> None:
    results = _search(
        _provider(file_log),
        LogSearchRequest(
            from_ts=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
            to_ts=datetime(2026, 8, 22, 10, 0, 2, tzinfo=UTC),
            terms=["action_confirm"],
            max_lines=20,
            max_bytes=4096,
        ),
    )

    assert len(results) == 1
    result = results[0]
    assert result.provider == "file"
    assert result.correlation is LogCorrelation.DIRECT
    assert result.timestamp_range.from_ts == datetime(2026, 8, 22, 9, 59, 59, tzinfo=UTC)
    assert "action_confirm" in result.excerpt
    assert "super-secret-value" not in result.excerpt
    assert "password=<redacted>" in result.excerpt
    assert result.pointer is not None
    assert str(file_log) not in result.model_dump_json()
    assert result.evidence is not None
    assert result.evidence.payload["trust"] == "untrusted_log"


def test_temporal_search_no_match_and_unparseable_timestamp(file_log: Path) -> None:
    provider = _provider(file_log)
    temporal = _search(
        provider,
        LogSearchRequest(
            from_ts=datetime(2026, 8, 22, 10, 5, tzinfo=UTC),
            to_ts=datetime(2026, 8, 22, 10, 6, tzinfo=UTC),
            max_lines=10,
            max_bytes=1024,
        ),
    )
    missing = _search(
        provider,
        LogSearchRequest(terms=["unknown-term"], max_lines=10, max_bytes=1024),
    )
    file_log.write_text(
        file_log.read_text(encoding="utf-8")
        + "2026-99-99 88:77:66 action_confirm token=token-secret-value\n",
        encoding="utf-8",
    )
    unparseable = _search(
        provider,
        LogSearchRequest(terms=["token-secret-value"], max_lines=5, max_bytes=1024),
    )

    assert temporal[0].correlation is LogCorrelation.TEMPORAL_INFERENCE
    assert missing == []
    assert unparseable[0].timestamp_parse_complete is False
    assert "token-secret-value" not in unparseable[0].excerpt


def test_line_byte_and_large_file_caps_are_explicit(tmp_path: Path) -> None:
    path = tmp_path / "large.log"
    path.write_text(
        ("2026-08-22 09:00:00,000 INFO filler\n" * 1000)
        + ("2026-08-22 10:00:00,000 ERROR target event\n" * 20),
        encoding="utf-8",
    )
    provider = _provider(
        path,
        limits=FileLogLimits(
            max_output_bytes=512,
            max_scan_bytes=2048,
            context_lines=1,
        ),
    )
    result = _search(
        provider,
        LogSearchRequest(terms=["target"], max_lines=3, max_bytes=120),
    )[0]

    assert result.truncated is True
    assert {"scan_byte_cap", "line_cap"} <= set(result.truncation_reasons)
    assert result.line_count <= 3
    assert result.byte_count <= 120
    assert len(result.excerpt.encode()) <= 120


def test_resolution_priority_nondefault_path_and_readiness_states(
    file_log: Path, tmp_path: Path
) -> None:
    config = tmp_path / "config.log"
    config.write_text("ignored", encoding="utf-8")
    resolved = resolve_log_file(
        LogFileSelection(override=(file_log,), config=(config,))
    )
    missing = resolve_log_file(
        LogFileSelection(override=(tmp_path / "missing.log",))
    )
    denied = resolve_log_file(
        LogFileSelection(override=(file_log,)),
        probe=lambda path: LogCapabilityState.NO_PERMISSION,
    )
    invalid = resolve_log_file(LogFileSelection(override=(file_log.parent,)))

    assert resolved.state is LogCapabilityState.OPERATIONAL
    assert resolved.resolved is not None
    assert resolved.resolved.path == file_log.resolve()
    assert resolved.resolved.origin is LogFileOrigin.OVERRIDE
    assert missing.state is LogCapabilityState.NOT_FOUND
    assert denied.state is LogCapabilityState.NO_PERMISSION
    assert invalid.state is LogCapabilityState.ERROR
    assert log_file_override_from_env({"ODOO_AI_LOG_FILE": str(file_log)}) == (
        str(file_log),
    )

    runtime = resolve_log_file(
        LogFileSelection(runtime=(file_log,), config=(config,))
    )
    assert runtime.resolved is not None
    assert runtime.resolved.origin is LogFileOrigin.RUNTIME


def test_request_and_provider_reject_unbounded_or_pathless_access(file_log: Path) -> None:
    provider = _provider(file_log, limits=FileLogLimits(max_output_bytes=1024))
    with pytest.raises(ValueError):
        LogSearchRequest(
            terms=["x" * 129], max_lines=10, max_bytes=512
        )
    with pytest.raises(LogProviderError, match="log_filter_required"):
        _search(provider, LogSearchRequest(max_lines=10, max_bytes=512))
    with pytest.raises(LogProviderError, match="log_byte_cap_exceeded"):
        _search(
            provider,
            LogSearchRequest(terms=["INFO"], max_lines=10, max_bytes=2048),
        )
    assert not hasattr(LogSearchRequest, "path")


def test_shared_secret_and_url_credentials_are_redacted(file_log: Path) -> None:
    file_log.write_text(
        file_log.read_text(encoding="utf-8")
        + "2026-08-22 10:06:00,000 ERROR "
        + "https://demo:password123@example.test shared-secret-fixture-123\n",
        encoding="utf-8",
    )
    result = _search(
        _provider(file_log),
        LogSearchRequest(terms=["example.test"], max_lines=5, max_bytes=2048),
    )[0]

    assert "password123" not in result.excerpt
    assert "shared-secret-fixture-123" not in result.excerpt
    assert "<redacted>" in result.excerpt


def test_file_traceback_fingerprint_can_be_read_only_after_search(file_log: Path) -> None:
    provider = _provider(file_log)
    result = _search(
        provider,
        LogSearchRequest(terms=["action_confirm"], max_lines=10, max_bytes=2048),
    )[0]

    assert result.traceback_fingerprint is not None
    reread = asyncio.run(
        provider.read_traceback(result.traceback_fingerprint, max_bytes=2048)
    )
    assert reread is not None
    assert "super-secret-value" not in reread.excerpt
    with pytest.raises(LogProviderError, match="traceback_reference_invalid"):
        asyncio.run(provider.read_traceback("not-a-fingerprint", max_bytes=2048))
