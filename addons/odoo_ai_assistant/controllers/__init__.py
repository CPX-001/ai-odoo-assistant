"""Supported Odoo HTTP controllers.

All Assistant routes authenticate through Odoo. The retired machine-secret
sidecar callback is intentionally not imported.
"""

from . import activity_preferences
from . import chat_bridge
from . import chat_history_actions
from . import public_references
from . import turn_control
from . import turn_live
from . import turn_runtime

__all__ = [
    "activity_preferences",
    "chat_bridge",
    "chat_history_actions",
    "public_references",
    "turn_control",
    "turn_live",
    "turn_runtime",
]
