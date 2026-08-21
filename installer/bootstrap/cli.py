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
    SystemAccountManager,
)
from installer.bootstrap.discovery import (
    DiscoveryError,
    discover_linux_host,
    discover_odoo_services,
    parse_odoo_config,
    select_odoo_config,
    select_odoo_service,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the Odoo AI Assistant host")
    parser.add_argument("--odoo-conf", type=Path)
    parser.add_argument("--odoo-service")
    parser.add_argument("--odoo-user")
    parser.add_argument("--service-user", default="odoo-ai")
    parser.add_argument("--service-group", default="odoo-ai")
    parser.add_argument("--install-dir", type=Path, default=Path("/opt/odoo-ai-assistant"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/odoo-ai-assistant"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/odoo-ai-assistant"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("/run/odoo-ai-assistant"))
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
        deployment = parse_odoo_config(config_path)
        odoo_service = select_odoo_service(
            discover_odoo_services(),
            explicit_unit=options.odoo_service,
            explicit_user=options.odoo_user,
        )
        if options.preflight_only:
            print(
                json.dumps(
                    {
                        "host": f"{host.distribution_id}:{host.version_id}",
                        "odoo_config": str(deployment.config_path),
                        "addons_paths": [str(path) for path in deployment.addons_paths],
                        "odoo_service": odoo_service.unit,
                        "odoo_user": odoo_service.user,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if os.geteuid() != 0:
            raise BootstrapError("Bootstrap changes require one privileged execution as root")

        result = Bootstrapper(
            paths=BootstrapPaths(
                install_dir=options.install_dir,
                config_dir=options.config_dir,
                state_dir=options.state_dir,
                runtime_dir=options.runtime_dir,
            ),
            account_manager=SystemAccountManager(),
            service_user=options.service_user,
            service_group=options.service_group,
        ).run(host=host, deployment=deployment, odoo_service=odoo_service)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0
    except (BootstrapError, DiscoveryError) as error:
        print(f"bootstrap error: {error}", file=sys.stderr)
        return 2
