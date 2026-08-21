"""Shared-secret authentication for privileged local endpoints."""

import hmac
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from fastapi import Header, HTTPException, status

SHARED_SECRET_FILE_ENV = "ODOO_AI_SHARED_SECRET_FILE"
SHARED_SECRET_HEADER = "X-Odoo-AI-Shared-Secret"


class SharedSecretError(RuntimeError):
    """Sanitized failure raised by the transport-neutral secret loader."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_shared_secret(environ: Mapping[str, str] | None = None) -> str:
    """Load the M1 peer secret for HTTP clients and FastAPI dependencies."""

    source = os.environ if environ is None else environ
    raw_path = source.get(SHARED_SECRET_FILE_ENV, "").strip()
    if not raw_path:
        raise SharedSecretError("shared_secret_unconfigured")
    path = Path(raw_path)
    try:
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
            or metadata.st_mode & 0o007
        ):
            raise OSError
        secret = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise SharedSecretError("shared_secret_unavailable") from None
    if len(secret) < 43:
        raise SharedSecretError("shared_secret_unavailable")
    return secret


def require_shared_secret(
    supplied: str | None = Header(default=None, alias=SHARED_SECRET_HEADER),
) -> None:
    """Authenticate a privileged request without logging or returning the secret."""

    try:
        expected = load_shared_secret()
    except SharedSecretError as error:
        detail = (
            "admin authentication is not configured"
            if error.code == "shared_secret_unconfigured"
            else "admin authentication is unavailable"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from None
    if supplied is None or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid local service credentials",
        )
