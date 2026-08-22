"""Technology-neutral application boundary for M3 admin diagnostics."""

from typing import Protocol

from odoo_ai.contracts import (
    LogEvidence,
    LogSearchRequest,
    LogTestDiagnostics,
    SourceScanDiagnostics,
    SourceStatusDiagnostics,
    SourceTestDiagnostics,
    TracebackRequest,
)


class DiagnosticsError(RuntimeError):
    """Sanitized M3 failure suitable for the authenticated admin API."""

    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class DiagnosticsService(Protocol):
    async def source_status(self) -> SourceStatusDiagnostics: ...

    async def rescan_source(self) -> SourceScanDiagnostics: ...

    async def test_source(self) -> SourceTestDiagnostics: ...

    async def test_logs(self, request: LogSearchRequest) -> LogTestDiagnostics: ...

    async def read_traceback(self, request: TracebackRequest) -> LogEvidence: ...
