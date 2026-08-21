"""Read-only discovery of the supported Linux and Odoo deployment."""

import configparser
import platform
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

SUPPORTED_DISTRIBUTIONS: Final = frozenset({"ubuntu", "debian"})
DEFAULT_ODOO_CONFIG_CANDIDATES: Final = (
    Path("/etc/odoo-server.conf"),
    Path("/etc/odoo/odoo.conf"),
    Path("/etc/odoo.conf"),
)
# A heuristic only. Explicit service names may be arbitrary and are inspected directly.
ODOO_SERVICE_PATTERN = re.compile(
    r"^[A-Za-z0-9_.@-]*odoo[A-Za-z0-9_.@-]*\.service$", re.IGNORECASE
)


class DiscoveryError(RuntimeError):
    """Raised when host discovery is unsupported or ambiguous."""


@dataclass(frozen=True, slots=True)
class LinuxHost:
    distribution_id: str
    version_id: str


@dataclass(frozen=True, slots=True)
class OdooDeployment:
    config_path: Path | None
    addons_paths: tuple[Path, ...] = ()
    database_host: str | None = None
    database_port: int | None = None
    database_user: str | None = None
    data_dir: Path | None = None
    log_file: Path | None = None


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
) -> Path | None:
    """Resolve a config-file hint without making common paths a deployment contract."""
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise DiscoveryError(f"Explicit Odoo config does not exist: {explicit_path}")
        return explicit_path

    matches = tuple(path for path in candidates if path.is_file())
    if not matches:
        return None
    if len(matches) > 1:
        rendered = ", ".join(str(path) for path in matches)
        raise DiscoveryError(f"Multiple Odoo configs found ({rendered}); pass --odoo-conf")
    return matches[0]


def _optional_path(raw_value: str) -> Path | None:
    value = raw_value.strip()
    if not value or value.casefold() in {"false", "none", "null"}:
        return None
    return Path(value)


def parse_odoo_config(path: Path) -> OdooDeployment:
    """Read deployment hints from Odoo config; no individual option is mandatory."""
    parser = configparser.RawConfigParser(interpolation=None, strict=True)
    try:
        with path.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (configparser.Error, OSError) as error:
        raise DiscoveryError(f"Cannot parse Odoo config: {path}") from error

    if not parser.has_section("options"):
        raise DiscoveryError("Odoo config must contain an [options] section")
    options = parser["options"]

    addons_paths = tuple(
        Path(value)
        for item in options.get("addons_path", "").split(",")
        if (value := item.strip())
    )

    raw_port = options.get("db_port", "").strip()
    try:
        database_port = int(raw_port) if raw_port else None
    except ValueError as error:
        raise DiscoveryError("Odoo db_port must be an integer") from error

    return OdooDeployment(
        config_path=path,
        addons_paths=addons_paths,
        database_host=options.get("db_host", "").strip() or None,
        database_port=database_port,
        database_user=options.get("db_user", "").strip() or None,
        data_dir=_optional_path(options.get("data_dir", "")),
        log_file=_optional_path(options.get("logfile", "")),
    )


def resolve_odoo_deployment(
    config_path: Path | None,
    *,
    addons_paths: tuple[Path, ...] = (),
    data_dir: Path | None = None,
    log_file: Path | None = None,
) -> OdooDeployment:
    """Combine discovered config hints with explicit operator overrides.

    Explicit values win. Missing values remain unknown so later runtime probes or
    Odoo Settings can resolve them instead of forcing a guessed filesystem layout.
    """
    deployment = (
        parse_odoo_config(config_path)
        if config_path is not None
        else OdooDeployment(config_path=None)
    )
    return replace(
        deployment,
        addons_paths=addons_paths or deployment.addons_paths,
        data_dir=data_dir if data_dir is not None else deployment.data_dir,
        log_file=log_file if log_file is not None else deployment.log_file,
    )


def _systemd_service_user(unit: str) -> str | None:
    shown = subprocess.run(
        ["systemctl", "show", unit, "--property=User", "--value", "--no-pager"],
        check=False,
        capture_output=True,
        text=True,
    )
    if shown.returncode != 0:
        return None
    return shown.stdout.strip()


def discover_odoo_services(*, explicit_unit: str | None = None) -> dict[str, str]:
    """Discover likely Odoo units and optionally inspect an arbitrary explicit unit."""
    listed = subprocess.run(
        ["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
        check=False,
        capture_output=True,
        text=True,
    )
    units: set[str] = set()
    if listed.returncode == 0:
        units.update(
            line.split(maxsplit=1)[0]
            for line in listed.stdout.splitlines()
            if line and ODOO_SERVICE_PATTERN.fullmatch(line.split(maxsplit=1)[0])
        )
    if explicit_unit:
        units.add(explicit_unit)

    discovered: dict[str, str] = {}
    for unit in sorted(units):
        user = _systemd_service_user(unit)
        if user is not None:
            discovered[unit] = user
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
                f"Odoo service {explicit_unit} was not found or readable; verify --odoo-service"
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
        raise DiscoveryError(
            "Odoo service user is unknown; pass --odoo-user explicitly (systemd is not required)"
        )
    if user == "root":
        raise DiscoveryError("Odoo must not run as root")
    return OdooService(unit=unit, user=user)
