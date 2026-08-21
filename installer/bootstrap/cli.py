"""Command-line entrypoint for the one-time privileged bootstrap."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from installer.bootstrap.bootstrap import (
    BootstrapError,
    BootstrapPaths,
    Bootstrapper,
    ServiceSettings,
    SystemAccountManager,
)
from installer.bootstrap.discovery import (
    DiscoveryError,
    discover_linux_host,
    discover_odoo_services,
    resolve_odoo_deployment,
    select_odoo_config,
    select_odoo_service,
)
from installer.bootstrap.postgres import PostgresBootstrapper, PostgresSettings
from installer.bootstrap.systemd import SystemdInstaller, SystemdSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the Odoo AI Assistant host")
    parser.add_argument("--odoo-conf", type=Path)
    parser.add_argument("--odoo-service")
    parser.add_argument("--odoo-user")
    parser.add_argument(
        "--addons-path",
        action="append",
        type=Path,
        default=[],
        help="Override the effective Odoo addons roots; repeat for multiple paths",
    )
    parser.add_argument("--odoo-data-dir", type=Path)
    parser.add_argument("--odoo-log-file", type=Path)
    parser.add_argument(
        "--odoo-db-name",
        action="append",
        default=[],
        help="Odoo database to deny to the Assistant role; repeat when needed",
    )
    parser.add_argument("--service-user", default="odoo-ai")
    parser.add_argument("--service-group", default="odoo-ai")
    parser.add_argument("--install-dir", type=Path, default=Path("/opt/odoo-ai-assistant"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/odoo-ai-assistant"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/odoo-ai-assistant"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("/run/odoo-ai-assistant"))
    parser.add_argument("--assistant-host", default="127.0.0.1")
    parser.add_argument("--assistant-port", type=int, default=8000)
    parser.add_argument("--assistant-db-name", default="odoo_ai")
    parser.add_argument("--assistant-db-role", default="odoo_ai_service")
    parser.add_argument("--assistant-db-host", default="127.0.0.1")
    parser.add_argument("--assistant-db-port", type=int, default=5432)
    parser.add_argument("--postgres-admin-host", default="/var/run/postgresql")
    parser.add_argument(
        "--postgres-mode",
        choices=("managed-local", "external-existing"),
        default="managed-local",
    )
    parser.add_argument("--assistant-database-url-file", type=Path)
    parser.add_argument("--psql-path", type=Path, default=Path("/usr/bin/psql"))
    parser.add_argument("--postgres-os-user", default="postgres")
    parser.add_argument("--assistant-unit-name", default="odoo-ai-assistant.service")
    parser.add_argument("--systemd-unit-dir", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument("--systemd-template", type=Path)
    parser.add_argument("--service-executable", type=Path)
    parser.add_argument("--alembic-config", type=Path)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Detect the host without creating or changing resources",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(arguments)
    try:
        host = discover_linux_host()
        config_path = select_odoo_config(options.odoo_conf)
        deployment = resolve_odoo_deployment(
            config_path,
            addons_paths=tuple(options.addons_path),
            data_dir=options.odoo_data_dir,
            log_file=options.odoo_log_file,
            database_names=tuple(options.odoo_db_name),
        )
        odoo_service = select_odoo_service(
            discover_odoo_services(explicit_unit=options.odoo_service),
            explicit_unit=options.odoo_service,
            explicit_user=options.odoo_user,
        )
        if options.preflight_only:
            print(
                json.dumps(
                    {
                        "host": f"{host.distribution_id}:{host.version_id}",
                        "odoo_config": (
                            str(deployment.config_path) if deployment.config_path else None
                        ),
                        "addons_paths": [str(path) for path in deployment.addons_paths],
                        "odoo_data_dir": (
                            str(deployment.data_dir) if deployment.data_dir else None
                        ),
                        "odoo_log_file": (
                            str(deployment.log_file) if deployment.log_file else None
                        ),
                        "odoo_service": odoo_service.unit,
                        "odoo_user": odoo_service.user,
                        "odoo_database_names": list(deployment.database_names),
                        "postgres_mode": options.postgres_mode,
                        "assistant_unit_name": options.assistant_unit_name,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if os.geteuid() != 0:
            raise BootstrapError("Bootstrap changes require one privileged execution as root")

        paths = BootstrapPaths(
            install_dir=options.install_dir,
            config_dir=options.config_dir,
            state_dir=options.state_dir,
            runtime_dir=options.runtime_dir,
        )
        alembic_config = options.alembic_config or paths.install_dir / "alembic.ini"
        postgres_settings = PostgresSettings(
            mode=options.postgres_mode,
            database_name=options.assistant_db_name,
            role_name=options.assistant_db_role,
            host=options.assistant_db_host,
            port=options.assistant_db_port,
            admin_host=options.postgres_admin_host,
            odoo_database_names=deployment.database_names,
            odoo_os_user=odoo_service.user,
            alembic_config=alembic_config,
            external_url_file=options.assistant_database_url_file,
            psql_path=options.psql_path,
            postgres_os_user=options.postgres_os_user,
        )
        database_manager = None
        database_manager_factory = None
        if options.postgres_mode == "external-existing":
            database_manager = PostgresBootstrapper(settings=postgres_settings)
        else:
            def create_database_manager(password: str) -> PostgresBootstrapper:
                return PostgresBootstrapper(settings=postgres_settings, password=password)

            database_manager_factory = create_database_manager

        systemd_template = options.systemd_template or (
            Path(__file__).resolve().parents[1] / "systemd" / "odoo-ai-assistant.service.in"
        )
        service_executable = options.service_executable or (
            paths.install_dir / "venv" / "bin" / "odoo-ai-service"
        )
        systemd_manager = SystemdInstaller(
            settings=SystemdSettings(
                unit_name=options.assistant_unit_name,
                unit_dir=options.systemd_unit_dir,
                template_path=systemd_template,
                service_user=options.service_user,
                service_group=options.service_group,
                working_directory=paths.install_dir,
                environment_file=paths.service_config,
                executable=service_executable,
                host=options.assistant_host,
                port=options.assistant_port,
            )
        )

        result = Bootstrapper(
            paths=paths,
            account_manager=SystemAccountManager(),
            service_user=options.service_user,
            service_group=options.service_group,
            service_settings=ServiceSettings(
                host=options.assistant_host,
                port=options.assistant_port,
                database_name=options.assistant_db_name,
                alembic_config=alembic_config,
            ),
            database_manager=database_manager,
            database_manager_factory=database_manager_factory,
            systemd_manager=systemd_manager,
        ).run(host=host, deployment=deployment, odoo_service=odoo_service)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0
    except (BootstrapError, DiscoveryError) as error:
        print(f"bootstrap error: {error}", file=sys.stderr)
        return 2
