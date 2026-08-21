from pathlib import Path

import pytest
from installer.bootstrap.discovery import (
    DiscoveryError,
    discover_linux_host,
    parse_odoo_config,
    select_odoo_config,
    select_odoo_service,
)

FIXTURES = Path(__file__).with_name("fixtures")


def test_parse_odoo_config_reads_only_required_deployment_hints() -> None:
    deployment = parse_odoo_config(FIXTURES / "odoo.conf")

    assert deployment.addons_paths == (
        Path("/usr/lib/python3/dist-packages/odoo/addons"),
        Path("/odoo/custom/addons"),
    )
    assert deployment.database_host == "localhost"
    assert deployment.database_port == 5432
    assert deployment.database_user == "odoo"


def test_select_odoo_config_requires_explicit_choice_when_ambiguous(tmp_path: Path) -> None:
    first = tmp_path / "first.conf"
    second = tmp_path / "second.conf"
    first.touch()
    second.touch()

    with pytest.raises(DiscoveryError, match="Multiple Odoo configs"):
        select_odoo_config(None, candidates=(first, second))
    assert select_odoo_config(second, candidates=(first,)) == second


def test_linux_preflight_accepts_ubuntu_and_rejects_other_systems(tmp_path: Path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n', encoding="utf-8")

    assert discover_linux_host(os_release_path=os_release, system_name="Linux").version_id == (
        "24.04"
    )
    with pytest.raises(DiscoveryError, match="supported Linux"):
        discover_linux_host(os_release_path=os_release, system_name="Windows")


def test_service_detection_rejects_ambiguity_and_root() -> None:
    with pytest.raises(DiscoveryError, match="Multiple Odoo services"):
        select_odoo_service({"odoo.service": "odoo", "odoo18.service": "odoo18"})
    with pytest.raises(DiscoveryError, match="must not run as root"):
        select_odoo_service({"odoo.service": "root"})

    selected = select_odoo_service({"odoo-server.service": "odoo"})
    assert selected.unit == "odoo-server.service"
    assert selected.user == "odoo"
