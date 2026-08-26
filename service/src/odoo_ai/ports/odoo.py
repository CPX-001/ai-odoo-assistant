"""Safe residual boundary for machine-authenticated Odoo instance metadata."""

from typing import Protocol

from odoo_ai.contracts import InstanceInventory


class OdooGatewayError(RuntimeError):
    """Sanitized residual Odoo transport failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OdooInstanceGateway(Protocol):
    """Expose only non-business runtime inventory under machine authentication."""

    async def get_instance_inventory(self) -> InstanceInventory: ...
