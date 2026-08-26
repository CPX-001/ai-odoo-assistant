"""Security primitives owned by the current Odoo addon trust boundary."""

from .machine_auth import (
    SHARED_SECRET_FILE_ENV,
    SHARED_SECRET_HEADER,
    MachineAuthenticationError,
    require_machine_secret,
)

__all__ = [
    "SHARED_SECRET_FILE_ENV",
    "SHARED_SECRET_HEADER",
    "MachineAuthenticationError",
    "require_machine_secret",
]
