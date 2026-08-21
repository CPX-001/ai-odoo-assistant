"""Authentication primitives shared by inbound and outbound transports."""

from odoo_ai.security.shared_secret import (
    SHARED_SECRET_HEADER,
    SharedSecretError,
    load_shared_secret,
    require_shared_secret,
)

__all__ = [
    "SHARED_SECRET_HEADER",
    "SharedSecretError",
    "load_shared_secret",
    "require_shared_secret",
]
