"""Security primitives owned by the Odoo addon trust boundary."""

from .delegation import (
    DelegationCodec,
    DelegationPayload,
    DelegationTokenError,
    QueryDelegationCodec,
    QueryDelegationPayload,
)
from .machine_auth import (
    SHARED_SECRET_FILE_ENV,
    SHARED_SECRET_HEADER,
    MachineAuthenticationError,
    require_machine_secret,
)

__all__ = [
    "SHARED_SECRET_FILE_ENV",
    "SHARED_SECRET_HEADER",
    "DelegationCodec",
    "DelegationPayload",
    "DelegationTokenError",
    "MachineAuthenticationError",
    "QueryDelegationCodec",
    "QueryDelegationPayload",
    "require_machine_secret",
]
