"""Bounded technical inventory for the machine-authenticated source scanner."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from odoo import SUPERUSER_ID, release, tools

MAX_INSTALLED_MODULES: Final = 4096
MAX_ADDONS_ROOTS: Final = 128
MAX_TEXT_LENGTH: Final = 4096


class InstanceInventoryError(RuntimeError):
    """Sanitized inventory failure safe for the internal HTTP boundary."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def collect_instance_inventory(env) -> dict[str, object]:
    """Return only version/database/modules/roots; never business records."""

    try:
        database = _bounded_text(env.cr.dbname, maximum=128)
        server_version = _bounded_text(release.version, maximum=64)
        module_rows = (
            env["ir.module.module"]
            .with_user(SUPERUSER_ID)
            .search_read(
                [("state", "=", "installed")],
                ["name"],
                limit=MAX_INSTALLED_MODULES + 1,
                order="name",
            )
        )
        if len(module_rows) > MAX_INSTALLED_MODULES:
            raise InstanceInventoryError("inventory_limit_exceeded", 413)
        installed_modules = tuple(
            _bounded_text(row.get("name"), maximum=255) for row in module_rows
        )
        addons_roots = _addons_roots(tools.config.get("addons_path"))
    except InstanceInventoryError:
        raise
    except Exception:  # noqa: BLE001 - sanitize the Odoo runtime boundary
        raise InstanceInventoryError("inventory_unavailable", 503) from None

    return {
        "addons_roots": list(addons_roots),
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database": database,
        "installed_modules": list(installed_modules),
        "ok": True,
        "server_version": server_version,
    }


def _addons_roots(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = ()
    normalized: list[str] = []
    for item in raw_values:
        if not isinstance(item, (str, Path)):
            raise InstanceInventoryError("inventory_unavailable", 503)
        text = str(item).strip()
        if not text:
            continue
        normalized.append(_bounded_text(text, maximum=MAX_TEXT_LENGTH))
    unique = tuple(dict.fromkeys(normalized))
    if len(unique) > MAX_ADDONS_ROOTS:
        raise InstanceInventoryError("inventory_limit_exceeded", 413)
    return unique


def _bounded_text(value: object, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise InstanceInventoryError("inventory_unavailable", 503)
    return value
