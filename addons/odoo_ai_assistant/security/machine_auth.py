"""Machine authentication for Assistant Service to Odoo callbacks."""

import hmac
import os
import stat
from pathlib import Path
from typing import Final

SHARED_SECRET_FILE_ENV: Final = "ODOO_AI_SHARED_SECRET_FILE"
SHARED_SECRET_HEADER: Final = "X-Odoo-AI-Shared-Secret"
MIN_SECRET_LENGTH: Final = 43


class MachineAuthenticationError(RuntimeError):
    """Sanitized machine-auth failure with an HTTP-safe status."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def require_machine_secret(
    supplied: str | None,
    *,
    secret_file: str | None = None,
) -> None:
    """Verify the M1 peer secret without returning or retaining it."""

    resolved = (secret_file or os.environ.get(SHARED_SECRET_FILE_ENV, "")).strip()
    if not resolved:
        raise MachineAuthenticationError("machine_auth_unconfigured", 503)
    expected = _read_secret(Path(resolved))
    if supplied is None or not hmac.compare_digest(supplied, expected):
        raise MachineAuthenticationError("machine_auth_rejected", 401)


def _read_secret(path: Path) -> str:
    try:
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
            or metadata.st_mode & 0o007
        ):
            raise OSError
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise MachineAuthenticationError("machine_auth_unavailable", 503) from None
    if len(value) < MIN_SECRET_LENGTH:
        raise MachineAuthenticationError("machine_auth_unavailable", 503)
    return value
