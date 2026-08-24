"""Authentication primitives shared by inbound and outbound transports."""

from odoo_ai.security.action_authority import (
    ACTION_AUTHORITY_SECRET_FILE_ENV,
    ActionAuthorityCodec,
    ActionAuthorityError,
)
from odoo_ai.security.batch_authority import BatchAuthorityCodec, BatchAuthorityError
from odoo_ai.security.shared_secret import (
    SHARED_SECRET_HEADER,
    SharedSecretError,
    load_shared_secret,
    require_shared_secret,
)

__all__ = [
    "ACTION_AUTHORITY_SECRET_FILE_ENV",
    "ActionAuthorityCodec",
    "ActionAuthorityError",
    "BatchAuthorityCodec",
    "BatchAuthorityError",
    "SHARED_SECRET_HEADER",
    "SharedSecretError",
    "load_shared_secret",
    "require_shared_secret",
]
