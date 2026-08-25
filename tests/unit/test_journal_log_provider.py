import asyncio
import subprocess
from datetime import UTC, datetime

import pytest
from odoo_ai.contracts import LogCorrelation, LogSearchRequest
from odoo_ai.logs import (
    JournalCommandResult,
    JournalLogLimits,
    JournalLogProvider,
    JournalUnitOrigin,
    JournalUnitSelection,
    LogProviderError,
    LogRedactor,
    ResolvedJournalUnit,
    SubprocessJournalRunner,
    journal_unit_override_from_env,
    resolve_journal_unit,
)
from odoo_ai.logs.tracebacks import extract_tracebacks


class FakeRunner:
    def __init__(self, result: JournalCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], float, int]] = []

    def run(self, argv: tuple[str, ...], *, timeout: float, max_bytes: int) -> JournalCommandResult:
        self.calls.append((argv, timeout, max_bytes))
        return self.result


def _provider(runner: FakeRunner) -> JournalLogProvider:
    return JournalLogProvider(
        resolved=ResolvedJournalUnit("customer-odoo.service", JournalUnitOrigin.OVERRIDE),
        runner=runner,
        limits=JournalLogLimits(max_seconds=1.5, context_lines=2),
        redactor=LogRedactor(configured_secrets=("configured-secret-value",)),
        now=lambda: datetime(2026, 8, 22, 10, 15, tzinfo=UTC),
    )


def _search(provider: JournalLogProvider, request: LogSearchRequest):
    return asyncio.run(provider.search(request))


def test_exact_fixed_argv_and_python_side_literal_filtering() -> None:
    runner = FakeRunner(
        JournalCommandResult(
            0,
            b"2026-08-22T10:00:00.000000+0000 host odoo[1]: ERROR target event\n",
            b"",
        )
    )
    provider = _provider(runner)
    request = LogSearchRequest(
        from_ts=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
        to_ts=datetime(2026, 8, 22, 10, 1, tzinfo=UTC),
        terms=["target event"],
        max_lines=10,
        max_bytes=1024,
    )

    result = _search(provider, request)[0]

    assert runner.calls == [
        (
            (
                "/usr/bin/journalctl",
                "--no-pager",
                "--quiet",
                "--output=short-iso-precise",
                "--unit",
                "customer-odoo.service",
                "--since",
                "2026-08-22T10:00:00.000000+00:00",
                "--until",
                "2026-08-22T10:01:00.000000+00:00",
                "--lines",
                "1000",
            ),
            1.5,
            2 * 1024 * 1024,
        )
    ]
    assert "target event" not in runner.calls[0][0]
    assert result.provider == "journal"
    assert result.correlation is LogCorrelation.DIRECT


@pytest.mark.parametrize(
    "unit",
    ["--since=yesterday.service", "odoo.service;rm", "odoo.service\n--all", "odoo"],
)
def test_malicious_or_invalid_units_are_rejected(unit: str) -> None:
    with pytest.raises(LogProviderError, match="journal_unit_invalid_or_ambiguous"):
        resolve_journal_unit(JournalUnitSelection(override=(unit,)))


def test_resolution_priority_environment_and_ambiguity() -> None:
    resolved = resolve_journal_unit(
        JournalUnitSelection(
            override=("override.service",),
            runtime=("runtime.service",),
            config=("config.service",),
        )
    )

    assert resolved == ResolvedJournalUnit("override.service", JournalUnitOrigin.OVERRIDE)
    assert journal_unit_override_from_env({"ODOO_AI_JOURNAL_UNIT": "customer.service"}) == (
        "customer.service",
    )
    with pytest.raises(LogProviderError, match="journal_unit_invalid_or_ambiguous"):
        resolve_journal_unit(JournalUnitSelection(runtime=("one.service", "two.service")))


def test_no_permission_is_sanitized() -> None:
    provider = _provider(
        FakeRunner(JournalCommandResult(1, b"", b"Failed: Permission denied for journal"))
    )

    with pytest.raises(LogProviderError, match="journal_no_permission"):
        _search(
            provider,
            LogSearchRequest(terms=["ERROR"], max_lines=10, max_bytes=1024),
        )


def test_subprocess_timeout_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="journalctl", timeout=1)

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(LogProviderError, match="journal_timeout"):
        SubprocessJournalRunner().run(
            ("/usr/bin/journalctl", "--no-pager"), timeout=1, max_bytes=1024
        )


def test_repeated_tracebacks_are_grouped_redacted_and_read_by_fingerprint() -> None:
    output = (
        b"2026-08-22T10:00:00.000000+0000 host odoo[1]: ERROR record 42 failed\n"
        b"2026-08-22T10:00:00.000001+0000 host odoo[1]: "
        b"Traceback (most recent call last):\n"
        b'2026-08-22T10:00:00.000002+0000 host odoo[1]:   File "/srv/odoo/sale.py", '
        b"line 42, in action_confirm\n"
        b"2026-08-22T10:00:00.000003+0000 host odoo[1]: "
        b"ValueError: record 42 token=top-secret-token-value\n"
        b"2026-08-22T10:00:01.000000+0000 host odoo[1]: ERROR record 84 failed\n"
        b"2026-08-22T10:00:01.000001+0000 host odoo[1]: "
        b"Traceback (most recent call last):\n"
        b'2026-08-22T10:00:01.000002+0000 host odoo[1]:   File "/opt/customer/sale.py", '
        b"line 99, in action_confirm\n"
        b"2026-08-22T10:00:01.000003+0000 host odoo[1]: "
        b"ValueError: record 84 token=another-secret-token\n"
    )
    provider = _provider(FakeRunner(JournalCommandResult(0, output, b"")))

    results = _search(
        provider,
        LogSearchRequest(terms=["record"], max_lines=20, max_bytes=4096),
    )

    assert len(results) == 1
    grouped = results[0]
    assert grouped.occurrence_count == 2
    assert grouped.traceback_fingerprint is not None
    assert grouped.pointer is not None
    assert grouped.pointer.reference == grouped.traceback_fingerprint
    assert "top-secret-token-value" not in grouped.excerpt
    reread = asyncio.run(provider.read_traceback(grouped.traceback_fingerprint, max_bytes=4096))
    assert reread is not None
    assert reread.traceback_fingerprint == grouped.traceback_fingerprint
    with pytest.raises(LogProviderError, match="traceback_reference_invalid"):
        asyncio.run(provider.read_traceback("sha256:../../etc/passwd", max_bytes=4096))
    with pytest.raises(LogProviderError, match="traceback_reference_unknown"):
        asyncio.run(provider.read_traceback("sha256:" + "0" * 64, max_bytes=4096))


def test_fingerprint_ignores_volatile_ids_addresses_paths_and_line_numbers() -> None:
    first = extract_tracebacks(
        "Traceback (most recent call last):\n"
        '  File "/srv/odoo/sale.py", line 42, in confirm\n'
        "ValueError: record 913 at 0x7f123456"
    )[0]
    second = extract_tracebacks(
        "Traceback (most recent call last):\n"
        '  File "/opt/customer/sale.py", line 999, in confirm\n'
        "ValueError: record 27 at 0xabc999"
    )[0]

    assert first.fingerprint == second.fingerprint


def test_journal_output_byte_cap_is_reported() -> None:
    output = b"2026-08-22T10:00:00.000000+0000 host odoo[1]: ERROR target\n" + b"x" * 256
    runner = FakeRunner(JournalCommandResult(0, output, b""))
    provider = JournalLogProvider(
        resolved=ResolvedJournalUnit("customer-odoo.service", JournalUnitOrigin.OVERRIDE),
        runner=runner,
        limits=JournalLogLimits(max_output_bytes=128, max_fetch_bytes=160),
        now=lambda: datetime(2026, 8, 22, 10, 15, tzinfo=UTC),
    )

    result = _search(
        provider,
        LogSearchRequest(terms=["target"], max_lines=10, max_bytes=128),
    )[0]

    assert result.truncated is True
    assert "scan_byte_cap" in result.truncation_reasons
    assert result.byte_count <= 128
