import os
import pwd
import shutil
import socket
import stat
import subprocess
from pathlib import Path

import pytest
from installer.bootstrap.systemd import SystemdInstaller, SystemdSettings


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


@pytest.mark.skipif(
    os.environ.get("ODOO_AI_RUN_SYSTEMD_BOOTSTRAP_TEST") != "1" or os.geteuid() != 0,
    reason="set ODOO_AI_RUN_SYSTEMD_BOOTSTRAP_TEST=1 and run as root",
)
def test_real_systemd_runtime_is_idempotent_non_root_and_loopback() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    executable = repo_root / ".venv/bin/odoo-ai-service"
    if not Path("/run/systemd/system").exists() or not executable.is_file():
        pytest.skip("real systemd or the repository service executable is unavailable")

    suffix = str(os.getpid())
    unit_name = f"odoo-ai-assistant-m1-07-{suffix}.service"
    unit_path = Path("/etc/systemd/system") / unit_name
    runtime_dir = Path("/run") / f"odoo-ai-assistant-m1-07-{suffix}"
    environment = runtime_dir / "service.env"
    secret = runtime_dir / "shared-secret"
    runtime_dir.mkdir(mode=0o750)
    nobody = pwd.getpwnam("nobody")
    os.chown(runtime_dir, 0, nobody.pw_gid)
    environment.write_text(
        'ODOO_AI_HOST="127.0.0.1"\n'
        f'ODOO_AI_PORT="{_free_port()}"\n'
        'ODOO_AI_DATABASE_NAME="systemd_smoke"\n'
        f'ODOO_AI_SHARED_SECRET_FILE="{secret}"\n',
        encoding="utf-8",
    )
    secret.write_text("s" * 64 + "\n", encoding="utf-8")
    environment.chmod(0o640)
    secret.chmod(0o640)
    os.chown(environment, 0, nobody.pw_gid)
    os.chown(secret, 0, nobody.pw_gid)
    port = int(
        next(
            line.split('"')[1]
            for line in environment.read_text().splitlines()
            if line.startswith("ODOO_AI_PORT")
        )
    )
    settings = SystemdSettings(
        unit_name=unit_name,
        unit_dir=unit_path.parent,
        template_path=repo_root / "installer/systemd/odoo-ai-assistant.service.in",
        service_user="nobody",
        service_group="nogroup",
        working_directory=repo_root,
        environment_file=environment,
        executable=executable,
        host="127.0.0.1",
        port=port,
    )
    installer = SystemdInstaller(settings=settings)
    try:
        first = installer.ensure()
        second = installer.ensure()

        assert first.unit_changed and first.service_active
        assert first.loopback_verified and first.health_verified
        assert first.admin_status_verified
        assert not second.unit_changed and not second.service_restarted
        subprocess.run(
            ["systemctl", "restart", unit_name],
            check=True,
            capture_output=True,
            text=True,
        )
        after_restart = installer.ensure()
        assert after_restart.service_active and after_restart.health_verified
        assert after_restart.admin_status_verified
        main_pid = int(
            subprocess.run(
                [
                    "systemctl",
                    "show",
                    unit_name,
                    "--property=MainPID",
                    "--value",
                    "--no-pager",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        assert Path(f"/proc/{main_pid}").stat().st_uid == nobody.pw_uid
        assert stat.S_IMODE(unit_path.stat().st_mode) == 0o644
        unit_content = unit_path.read_text(encoding="utf-8")
        assert "shared-secret" not in unit_content
        assert "StandardOutput=journal" in unit_content
    finally:
        subprocess.run(
            ["systemctl", "disable", "--now", unit_name],
            check=False,
            capture_output=True,
            text=True,
        )
        unit_path.unlink(missing_ok=True)
        environment.unlink(missing_ok=True)
        secret.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)
        subprocess.run(
            ["systemctl", "daemon-reload"],
            check=False,
            capture_output=True,
            text=True,
        )
