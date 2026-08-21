import json
import subprocess
from pathlib import Path

from installer.bootstrap import cli
from installer.bootstrap.discovery import LinuxHost


def test_parser_exposes_customer_deployment_overrides() -> None:
    options = cli.build_parser().parse_args(
        [
            "--odoo-conf",
            "/srv/acme/prod.conf",
            "--odoo-service",
            "acme-erp.service",
            "--odoo-user",
            "acme-odoo",
            "--addons-path",
            "/srv/acme/addons",
            "--addons-path",
            "/mnt/oca",
            "--odoo-data-dir",
            "/srv/acme/data",
            "--odoo-log-file",
            "/srv/acme/logs/prod.log",
            "--assistant-port",
            "8123",
            "--assistant-db-name",
            "acme_ai",
            "--assistant-db-role",
            "acme_ai_runtime",
            "--assistant-db-host",
            "db.internal",
            "--assistant-db-port",
            "5544",
            "--postgres-mode",
            "external-existing",
            "--assistant-database-url-file",
            "/run/secrets/acme-ai-db",
            "--odoo-db-name",
            "acme_odoo",
            "--assistant-unit-name",
            "acme-assistant.service",
            "--systemd-unit-dir",
            "/srv/acme/systemd",
            "--service-executable",
            "/srv/acme/runtime/bin/assistant",
            "--restart-service",
            "--assistant-backup-dir",
            "/srv/acme/backups/assistant",
            "--runtime-source",
            "/srv/acme/release-src",
            "--runtime-python",
            "/usr/local/bin/python3.12",
        ]
    )

    assert options.odoo_conf == Path("/srv/acme/prod.conf")
    assert options.odoo_service == "acme-erp.service"
    assert options.odoo_user == "acme-odoo"
    assert options.addons_path == [Path("/srv/acme/addons"), Path("/mnt/oca")]
    assert options.odoo_data_dir == Path("/srv/acme/data")
    assert options.odoo_log_file == Path("/srv/acme/logs/prod.log")
    assert options.assistant_port == 8123
    assert options.assistant_db_name == "acme_ai"
    assert options.assistant_db_role == "acme_ai_runtime"
    assert options.assistant_db_host == "db.internal"
    assert options.assistant_db_port == 5544
    assert options.postgres_mode == "external-existing"
    assert options.assistant_database_url_file == Path("/run/secrets/acme-ai-db")
    assert options.odoo_db_name == ["acme_odoo"]
    assert options.assistant_unit_name == "acme-assistant.service"
    assert options.systemd_unit_dir == Path("/srv/acme/systemd")
    assert options.service_executable == Path("/srv/acme/runtime/bin/assistant")
    assert options.restart_service
    assert options.assistant_backup_dir == Path("/srv/acme/backups/assistant")
    assert options.runtime_source == Path("/srv/acme/release-src")
    assert options.runtime_python == Path("/usr/local/bin/python3.12")


def test_preflight_can_use_explicit_user_without_config_or_systemd(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli, "discover_linux_host", lambda: LinuxHost(distribution_id="ubuntu", version_id="24.04")
    )
    monkeypatch.setattr(cli, "select_odoo_config", lambda explicit: None)
    monkeypatch.setattr(cli, "discover_odoo_services", lambda *, explicit_unit=None: {})

    result = cli.main(
        [
            "--preflight-only",
            "--odoo-user",
            "customer-odoo",
            "--addons-path",
            "/srv/customer/addons",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["odoo_config"] is None
    assert payload["odoo_service"] is None
    assert payload["odoo_user"] == "customer-odoo"
    assert payload["addons_paths"] == ["/srv/customer/addons"]


def test_runtime_rollback_requires_acknowledgement_and_restarts(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        cli.RuntimeInstaller,
        "activate_previous",
        lambda self, *, schema_compatible: (
            "/srv/releases/previous" if schema_compatible else ""
        ),
    )
    restarted: list[list[str]] = []

    def fake_run(arguments, **kwargs):
        restarted.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = cli.main(
        [
            "--rollback-runtime",
            "--acknowledge-schema-compatibility",
            "--install-dir",
            "/srv/assistant",
            "--assistant-unit-name",
            "acme-assistant.service",
        ]
    )

    assert result == 0
    assert restarted == [["/usr/bin/systemctl", "restart", "acme-assistant.service"]]
    assert json.loads(capsys.readouterr().out)["database_changed"] is False
