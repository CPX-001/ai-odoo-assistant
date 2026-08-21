from pathlib import Path
from types import SimpleNamespace

import pytest
from installer.bootstrap.discovery import (
    DiscoveryError,
    discover_linux_host,
    discover_odoo_services,
    parse_odoo_config,
    resolve_odoo_deployment,
    select_odoo_config,
    select_odoo_service,
)

FIXTURES = Path(__file__).with_name("fixtures")


def test_parse_odoo_config_reads_available_deployment_hints() -> None:
    deployment = parse_odoo_config(FIXTURES / "odoo.conf")

    assert deployment.addons_paths == (
        Path("/usr/lib/python3/dist-packages/odoo/addons"),
        Path("/odoo/custom/addons"),
    )
    assert deployment.database_host == "localhost"
    assert deployment.database_port == 5432
    assert deployment.database_user == "odoo"
    assert deployment.data_dir == Path("/srv/odoo data")
    assert deployment.log_file == Path("/srv/log/odoo production.log")


def test_parse_odoo_config_allows_missing_optional_paths(tmp_path: Path) -> None:
    config = tmp_path / "customer.ini"
    config.write_text("[options]\ndb_user = custom_odoo\n", encoding="utf-8")

    deployment = parse_odoo_config(config)

    assert deployment.config_path == config
    assert deployment.addons_paths == ()
    assert deployment.data_dir is None
    assert deployment.log_file is None


def test_resolve_odoo_deployment_explicit_overrides_win(tmp_path: Path) -> None:
    config = tmp_path / "customer.ini"
    config.write_text(
        "[options]\naddons_path = relative/addons\nlogfile = /old/odoo.log\n",
        encoding="utf-8",
    )

    deployment = resolve_odoo_deployment(
        config,
        addons_paths=(Path("/srv/customer/addons"), Path("/mnt/oca")),
        data_dir=Path("/data/odoo"),
        log_file=Path("/logs/customer.log"),
    )

    assert deployment.addons_paths == (Path("/srv/customer/addons"), Path("/mnt/oca"))
    assert deployment.data_dir == Path("/data/odoo")
    assert deployment.log_file == Path("/logs/customer.log")


def test_select_odoo_config_uses_common_paths_as_hints_only(tmp_path: Path) -> None:
    first = tmp_path / "first.conf"
    second = tmp_path / "second.conf"
    assert select_odoo_config(None, candidates=(first, second)) is None

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


def test_explicit_systemd_unit_name_is_not_required_to_match_odoo_pattern(monkeypatch) -> None:
    def fake_run(arguments, **kwargs):
        if arguments[1] == "list-unit-files":
            return SimpleNamespace(returncode=0, stdout="odoo.service enabled\n")
        unit = arguments[2]
        users = {"odoo.service": "odoo\n", "acme-erp.service": "erpuser\n"}
        return SimpleNamespace(returncode=0, stdout=users[unit])

    monkeypatch.setattr("installer.bootstrap.discovery.subprocess.run", fake_run)
    available = discover_odoo_services(explicit_unit="acme-erp.service")

    selected = select_odoo_service(
        available, explicit_unit="acme-erp.service", explicit_user="erpuser"
    )
    assert selected.unit == "acme-erp.service"
    assert selected.user == "erpuser"


def test_service_detection_rejects_ambiguity_and_root() -> None:
    with pytest.raises(DiscoveryError, match="Multiple Odoo services"):
        select_odoo_service({"odoo.service": "odoo", "odoo18.service": "odoo18"})
    with pytest.raises(DiscoveryError, match="must not run as root"):
        select_odoo_service({"odoo.service": "root"})

    selected = select_odoo_service({"odoo-server.service": "odoo"})
    assert selected.unit == "odoo-server.service"
    assert selected.user == "odoo"


def test_systemd_is_not_required_when_odoo_user_is_explicit() -> None:
    selected = select_odoo_service({}, explicit_user="customer-odoo")
    assert selected.unit is None
    assert selected.user == "customer-odoo"
