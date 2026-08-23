"""Security primitives owned by the Odoo addon trust boundary."""

from .action_authority import (
    ACTION_AUTHORITY_SECRET_FILE_ENV,
    ActionAuthorityCodec,
    ActionAuthorityPayload,
)
from .delegation import (
    ActionPreviewDelegationCodec,
    ActionPreviewDelegationPayload,
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
    "ACTION_AUTHORITY_SECRET_FILE_ENV",
    "SHARED_SECRET_FILE_ENV",
    "SHARED_SECRET_HEADER",
    "ActionAuthorityCodec",
    "ActionAuthorityPayload",
    "ActionPreviewDelegationCodec",
    "ActionPreviewDelegationPayload",
    "DelegationCodec",
    "DelegationPayload",
    "DelegationTokenError",
    "MachineAuthenticationError",
    "QueryDelegationCodec",
    "QueryDelegationPayload",
    "require_machine_secret",
]
