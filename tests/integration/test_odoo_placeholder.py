import json
import os
import pwd
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from installer.bootstrap.systemd import SystemdInstaller, SystemdSettings


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _run_odoo(
    *, repo_root: Path, database: str, arguments: list[str], input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    addons_path = ",".join(
        (
            "/odoo/odoo-server/odoo/addons",
            "/odoo/odoo-server/addons",
            str(repo_root / "addons"),
        )
    )
    command = [
        "runuser",
        "--user",
        "odoo",
        "--",
        "/odoo/venv/bin/python3",
        "/odoo/odoo-server/odoo-bin",
    ]
    if arguments and arguments[0] == "shell":
        command.append("shell")
        arguments = arguments[1:]
    command.extend(
        [
            "--config=/etc/odoo-server.conf",
            f"--database={database}",
            f"--addons-path={addons_path}",
            "--no-http",
            *arguments,
        ]
    )
    return subprocess.run(
        command,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _diagnostics(
    *, repo_root: Path, database: str, service_url: str, secret_file: Path
) -> dict[str, object]:
    script = f"""
import json
params = env['ir.config_parameter']
params.set_param('odoo_ai_assistant.service_url', {service_url!r})
params.set_param('odoo_ai_assistant.shared_secret_file', {str(secret_file)!r})
values = env['odoo.ai.assistant.diagnostics']._diagnostic_values()
print('M1_08_DIAGNOSTICS=' + json.dumps(values, default=str, sort_keys=True))
env.cr.commit()
"""
    completed = _run_odoo(
        repo_root=repo_root,
        database=database,
        arguments=["shell"],
        input_text=script,
    )
    if completed.returncode != 0:
        detail = " | ".join(completed.stderr.strip().splitlines()[-8:])[-1200:]
        raise AssertionError(f"Odoo diagnostics shell failed: {detail}")
    match = re.search(r"M1_08_DIAGNOSTICS=(\{.*\})", completed.stdout)
    if match is None:
        raise AssertionError("Odoo diagnostics result was not emitted")
    return json.loads(match.group(1))


def _uninstall_addon(*, repo_root: Path, database: str) -> None:
    completed = _run_odoo(
        repo_root=repo_root,
        database=database,
        arguments=["shell"],
        input_text="""
module = env['ir.module.module'].search([('name', '=', 'odoo_ai_assistant')], limit=1)
module.button_immediate_uninstall()
env.cr.commit()
print('M1_09_UNINSTALL=done')
""",
    )
    assert completed.returncode == 0, "Odoo addon uninstall failed"
    assert "M1_09_UNINSTALL=done" in completed.stdout


@pytest.mark.skipif(
    os.environ.get("ODOO_AI_RUN_ODOO_PLACEHOLDER_TEST") != "1" or os.geteuid() != 0,
    reason="set ODOO_AI_RUN_ODOO_PLACEHOLDER_TEST=1 and run as root",
)
def test_odoo18_addon_install_upgrade_and_health_error_states() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    odoo_bin = Path("/odoo/odoo-server/odoo-bin")
    if not odoo_bin.is_file() or not Path("/run/systemd/system").exists():
        pytest.skip("Odoo 18 DEV or real systemd is unavailable")

    suffix = str(os.getpid())
    database = f"odoo_ai_m1_08_{suffix}"
    if not re.fullmatch(r"odoo_ai_m1_08_[0-9]+", database):
        raise AssertionError("unsafe disposable Odoo database name")
    unit_name = f"odoo-ai-assistant-m1-08-{suffix}.service"
    unit_path = Path("/etc/systemd/system") / unit_name
    runtime_dir = Path("/run") / f"odoo-ai-assistant-m1-08-{suffix}"
    environment = runtime_dir / "service.env"
    secret = runtime_dir / "shared-secret"
    runtime_dir.mkdir(mode=0o750)
    odoo_account = pwd.getpwnam("odoo")
    os.chown(runtime_dir, 0, odoo_account.pw_gid)
    port = _free_port()
    environment.write_text(
        f'ODOO_AI_HOST="127.0.0.1"\nODOO_AI_PORT="{port}"\n'
        'ODOO_AI_DATABASE_NAME="odoo_ai_m1_08"\n'
        f'ODOO_AI_SHARED_SECRET_FILE="{secret}"\n',
        encoding="utf-8",
    )
    secret.write_text("m1-08-secret-" + "s" * 52 + "\n", encoding="utf-8")
    for path in (environment, secret):
        path.chmod(0o640)
        os.chown(path, 0, odoo_account.pw_gid)

    installer = SystemdInstaller(
        settings=SystemdSettings(
            unit_name=unit_name,
            unit_dir=unit_path.parent,
            template_path=repo_root / "installer/systemd/odoo-ai-assistant.service.in",
            service_user="odoo",
            service_group="odoo",
            working_directory=repo_root,
            environment_file=environment,
            shared_secret_file=secret,
            executable=repo_root / ".venv/bin/odoo-ai-service",
            host="127.0.0.1",
            port=port,
        )
    )
    try:
        installer.ensure()
        install = _run_odoo(
            repo_root=repo_root,
            database=database,
            arguments=[
                "--init=odoo_ai_assistant",
                "--without-demo=all",
                "--test-enable",
                "--test-tags=/odoo_ai_assistant",
                "--stop-after-init",
            ],
        )
        assert install.returncode == 0, "Odoo addon installation/tests failed"

        healthy = _diagnostics(
            repo_root=repo_root,
            database=database,
            service_url=f"http://127.0.0.1:{port}",
            secret_file=secret,
        )
        assert healthy["service_state"] == "ok"
        assert healthy["endpoint_state"] == "Configured"

        subprocess.run(["systemctl", "stop", unit_name], check=True, capture_output=True)
        stopped = _diagnostics(
            repo_root=repo_root,
            database=database,
            service_url=f"http://127.0.0.1:{port}",
            secret_file=secret,
        )
        assert stopped["service_state"] == "error"
        assert "unavailable" in str(stopped["message"]).lower()
        assert "traceback" not in str(stopped["message"]).lower()

        upgrade = _run_odoo(
            repo_root=repo_root,
            database=database,
            arguments=["--update=odoo_ai_assistant", "--stop-after-init"],
        )
        assert upgrade.returncode == 0, "Odoo addon upgrade failed"

        assistant_database = f"assistant_uninstall_{suffix}"
        subprocess.run(
            ["runuser", "--user", "postgres", "--", "createdb", assistant_database],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            _uninstall_addon(repo_root=repo_root, database=database)
            database_exists = subprocess.run(
                [
                    "runuser",
                    "--user",
                    "postgres",
                    "--",
                    "psql",
                    "--dbname=postgres",
                    "--tuples-only",
                    "--no-align",
                    "--command",
                    f"SELECT 1 FROM pg_database WHERE datname = '{assistant_database}'",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert database_exists.stdout.strip() == "1"
        finally:
            subprocess.run(
                [
                    "runuser",
                    "--user",
                    "postgres",
                    "--",
                    "dropdb",
                    "--if-exists",
                    assistant_database,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
    finally:
        subprocess.run(
            ["systemctl", "disable", "--now", unit_name],
            check=False,
            capture_output=True,
        )
        unit_path.unlink(missing_ok=True)
        environment.unlink(missing_ok=True)
        secret.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)
        subprocess.run(["systemctl", "daemon-reload"], check=False, capture_output=True)
        subprocess.run(
            [
                "runuser",
                "--user",
                "postgres",
                "--",
                "dropdb",
                "--if-exists",
                database,
            ],
            check=False,
            capture_output=True,
        )
