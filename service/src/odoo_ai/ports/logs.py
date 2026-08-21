"""Technology-neutral boundary for bounded log access."""

from typing import Protocol

from odoo_ai.contracts import LogEvidence, LogSearchRequest


class LogProvider(Protocol):
    """Search redacted log excerpts without exposing shell or filesystem access."""

    async def search(self, request: LogSearchRequest) -> list[LogEvidence]: ...

    async def read_traceback(
        self,
        fingerprint: str,
        *,
        max_bytes: int,
    ) -> LogEvidence | None: ...
