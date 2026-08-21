"""Security primitives owned by the Odoo addon trust boundary."""

from .delegation import (
    DelegationCodec,
    DelegationPayload,
    DelegationTokenError,
)

__all__ = ["DelegationCodec", "DelegationPayload", "DelegationTokenError"]
