"""Read-only discovery of the supported Linux and Odoo deployment."""

import configparser
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SUPPORTED_DISTRIBUTIONS: Final = frozenset({"ubuntu", "debian"})
DEFAULT_ODOO_CONFIG_CANDIDATES: Final = (
    Path("/etc/odoo-server.conf"),
    Path("/etc/odoo/odoo.conf"),
    Path("/etc/odoo.conf"),
)
ODOO_SERVICE_PATTERN = re.compile(r"^odoo[A-Za-z0-9_.@-]*\.service$")


class DiscoveryError(RuntimeError):
    """Raised when host discovery is unsupported or ambiguous."""


@dataclass(frozen=True, slots=True)
class LinuxHost:
    distribution_id: str
    version_id: str


@dataclass(frozen=True, slots=True)
class OdooDeployment:
    config_path: Path
    addons_paths: tuple[Path, ...]
    database_host: str | None
    database_port: int | None
    database_user: str | None


@dataclass(frozen=True, slots=True)
class OdooService:
    unit: str | None
    user: str


def _parse_os_release(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def discover_linux_host(
    *, os_release_path: Path = Path("/etc/os-release"), system_name: str | None = None
) -> LinuxHost:
    effective_system = platform.system() if system_name is None else system_name
    if effective_system != "Linux":
        raise DiscoveryError("Bootstrap requires a supported Linux host")

    try:
        values = _parse_os_release(os_release_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DiscoveryError(
            "Cannot read /etc/os-release; specify a supported Linux host"
        ) from error

    distribution_id = values.get("ID", "").casefold()
    version_id = values.get("VERSION_ID", "")
    if distribution_id not in SUPPORTED_DISTRIBUTIONS or not version_id:
        raise DiscoveryError("Unsupported Linux distribution; initial support is Ubuntu/Debian")
    return LinuxHost(distribution_id=distribution_id, version_id=version_id)


def select_odoo_config(
    explicit_path: Path | None,
    *,
    candidates: tuple[Path, ...] = DEFAULT_ODOO_CONFIG_CANDIDATES,
) -> Path:
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise DiscoveryError(f"Explicit Odoo config does not exist: {explicit_path}")
        return explicit_path

    matches = tuple(path for path in candidates if path.is_file())
    if not matches:
        raise DiscoveryError("Odoo config was not found; pass --odoo-conf explicitly")
    if len(matches) > 1:
        rendered = ", ".join(str(path) for path in matches)
        raise DiscoveryError(f"Multiple Odoo configs found ({rendered}); pass --odoo-conf")
    return matches[0]


def parse_odoo_config(path: Path) -> OdooDeployment:
    parser = configparser.RawConfigParser(interpolation=None, strict=True)
    try:
        with path.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (configparser.Error, OSError) as error:
        raise DiscoveryError(f"Cannot parse Odoo config: {path}") from error

    if not parser.has_section("options"):
        raise DiscoveryError("Odoo config must contain an [options] section")
    options = parser["options"]
    raw_addons = options.get("addons_path", "")
    addons_paths: list[Path] = []
    for item in raw_addons.split(","):
        value = item.strip()
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            raise DiscoveryError("Every addons_path entry must be absolute")
        addons_paths.append(candidate)
    if not addons_paths:
        raise DiscoveryError("Odoo config has no usable addons_path entries")

    raw_port = options.get("db_port", "").strip()
    try:
        database_port = int(raw_port) if raw_port else None
    except ValueError as error:
        raise DiscoveryError("Odoo db_port must be an integer") from error

    return OdooDeployment(
        config_path=path,
        addons_paths=tuple(addons_paths),
        database_host=options.get("db_host", "").strip() or None,
        database_port=database_port,
        database_user=options.get("db_user", "").strip() or None,
    )


def discover_odoo_services() -> dict[str, str]:
    listed = subprocess.run(
        ["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        return {}

    units = sorted(
        line.split(maxsplit=1)[0]
        for line in listed.stdout.splitlines()
        if line and ODOO_SERVICE_PATTERN.fullmatch(line.split(maxsplit=1)[0])
    )
    discovered: dict[str, str] = {}
    for unit in units:
        shown = subprocess.run(
            ["systemctl", "show", unit, "--property=User", "--value", "--no-pager"],
            check=False,
            capture_output=True,
            text=True,
        )
        if shown.returncode == 0:
            discovered[unit] = shown.stdout.strip()
    return discovered


def select_odoo_service(
    available: dict[str, str],
    *,
    explicit_unit: str | None = None,
    explicit_user: str | None = None,
) -> OdooService:
    if explicit_unit is not None:
        if explicit_unit not in available:
            raise DiscoveryError(
                f"Odoo service {explicit_unit} was not found; verify --odoo-service"
            )
        unit = explicit_unit
    elif len(available) == 1:
        unit = next(iter(available))
    elif len(available) > 1:
        raise DiscoveryError("Multiple Odoo services found; pass --odoo-service explicitly")
    else:
        unit = None

    detected_user = available.get(unit, "") if unit is not None else ""
    if explicit_user and detected_user and explicit_user != detected_user:
        raise DiscoveryError("Explicit Odoo user does not match the detected systemd service")
    user = explicit_user or detected_user
    if not user:
        raise DiscoveryError("Odoo service user is unknown; pass --odoo-user explicitly")
    if user == "root":
        raise DiscoveryError("Odoo must not run as root")
    return OdooService(unit=unit, user=user)
