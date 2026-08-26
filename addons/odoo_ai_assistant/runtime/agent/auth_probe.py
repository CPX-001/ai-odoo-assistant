"""Product-turn authentication compatibility probe for the embedded Codex adapter."""

from __future__ import annotations

from .codex import CodexAgentSettings, _CodexClient


async def isolated_account_usable(settings: CodexAgentSettings) -> bool:
    """Check that persistent credentials also work through the isolated turn HOME.

    This deliberately reuses the product adapter's own HOME-copying behavior instead
    of duplicating assumptions about Codex credential files in the Odoo model layer.
    Codex is asked to refresh inside that temporary HOME so invalid/expired credentials
    fail without exposing or persisting token material through Odoo.
    """

    client = await _CodexClient.start(settings)
    async with client:
        result = await client.request(
            "account/read",
            {"refreshToken": True},
            timeout=settings.startup_timeout_seconds,
        )
    if not isinstance(result, dict) or type(result.get("requiresOpenaiAuth")) is not bool:
        return False
    account = result.get("account")
    return isinstance(account, dict) and account.get("type") in {
        "amazonBedrock",
        "apiKey",
        "chatgpt",
    }


__all__ = ["isolated_account_usable"]
