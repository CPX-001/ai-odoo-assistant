"""Shared-secret authentication for privileged local endpoints."""

import hmac
import os
import stat
from pathlib import Path

from fastapi import Header, HTTPException, status

SHARED_SECRET_FILE_ENV = "ODOO_AI_SHARED_SECRET_FILE"
SHARED_SECRET_HEADER = "X-Odoo-AI-Shared-Secret"


def _load_shared_secret() -> str:
    raw_path = os.environ.get(SHARED_SECRET_FILE_ENV, "").strip()
    if not raw_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin authentication is not configured",
        )
    path = Path(raw_path)
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
            raise OSError
        secret = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin authentication is unavailable",
        ) from error
    if len(secret) < 43:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin authentication is unavailable",
        )
    return secret


def require_shared_secret(
    supplied: str | None = Header(default=None, alias=SHARED_SECRET_HEADER),
) -> None:
    """Authenticate a privileged request without logging or returning the secret."""

    expected = _load_shared_secret()
    if supplied is None or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid local service credentials",
        )
