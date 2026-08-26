"""Product-turn authentication compatibility probe for the embedded Codex adapter."""

from __future__ import annotations

from .codex import CodexAgentSettings, _CodexClient


async def isolated_account_usable(settings: CodexAgentSettings) -> bool:
    """Check that persistent credentials also work through the isolated turn HOME.

    This deliberately reuses the product adapter's own HOME-copying behavior instead
    of duplicating assumptions about Codex credential files in the Odoo model layer.
    The probe does not refresh credentials because the HOME is disposable: a rotating
    refresh token must only be refreshed in the persistent Codex-owned credential store.
    """

    client = await _CodexClient.start(settings)
    async with client:
        result = await client.request(
            "account/read",
            {"refreshToken": False},
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
