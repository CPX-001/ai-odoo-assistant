import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from installer.bootstrap.bootstrap import BootstrapError
from installer.bootstrap.systemd import SystemdInstaller, SystemdSettings


class FakeSystemctlRunner:
    def __init__(self) -> None:
        self.enabled = False
        self.active = False
        self.commands: list[list[str]] = []

    def run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(arguments)
        action = arguments[1] if len(arguments) > 1 else ""
        if action == "is-enabled":
            return self._completed(arguments, 0 if self.enabled else 1)
        if action == "is-active":
            return self._completed(arguments, 0 if self.active else 3)
        if action == "enable":
            self.enabled = True
        elif action in {"start", "restart"}:
            self.active = True
        elif action == "show":
            return self._completed(arguments, stdout="assistant-user\n")
        if arguments[0].endswith("ss"):
            return self._completed(
                arguments, stdout="LISTEN 0 2048 127.0.0.1:8123 0.0.0.0:*\n"
            )
        return self._completed(arguments)

    @staticmethod
    def _completed(
        arguments: list[str], returncode: int = 0, stdout: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, returncode, stdout=stdout, stderr="")


class UnitTestSystemdInstaller(SystemdInstaller):
    def _verify_http_endpoints(self) -> tuple[bool, bool]:
        return True, True


def _settings(tmp_path: Path) -> SystemdSettings:
    source_template = Path(__file__).parents[2] / "installer/systemd/odoo-ai-assistant.service.in"
    template = tmp_path / "assistant.service.in"
    template.write_text(source_template.read_text())
    environment = tmp_path / "custom config" / "service.env"
    environment.parent.mkdir()
    environment.write_text('ODOO_AI_HOST="127.0.0.1"\nSECRET="not-in-unit"\n')
    secret = tmp_path / "custom config" / "shared-secret"
    secret.write_text("s" * 64 + "\n")
    executable = tmp_path / "runtime with spaces" / "bin" / "assistant"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    return SystemdSettings(
        unit_name="customer-assistant.service",
        unit_dir=tmp_path / "units",
        template_path=template,
        service_user="assistant-user",
        service_group="assistant-group",
        working_directory=tmp_path / "runtime with spaces",
        environment_file=environment,
        shared_secret_file=secret,
        executable=executable,
        host="127.0.0.1",
        port=8123,
        privileged_uid=os.getuid(),
        privileged_gid=os.getgid(),
        systemctl_path=Path("/custom/systemctl"),
        ss_path=Path("/custom/ss"),
    )


def test_systemd_first_second_run_and_changed_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runner = FakeSystemctlRunner()
    installer = UnitTestSystemdInstaller(settings=settings, runner=runner)

    first = installer.ensure()
    second = installer.ensure()
    config_changed = installer.ensure(config_changed=True)
    settings.template_path.write_text(settings.template_path.read_text() + "\n")
    third = installer.ensure()

    assert first.unit_changed and first.unit_enabled and not first.service_restarted
    assert not second.unit_changed and not second.service_restarted
    assert config_changed.service_restarted
    assert third.unit_changed and third.service_restarted
    actions = [command[1] for command in runner.commands if command[0].endswith("systemctl")]
    assert actions.count("daemon-reload") == 2
    assert actions.count("enable") == 1
    assert actions.count("start") == 1
    assert actions.count("restart") == 2
    unit = (settings.unit_dir / settings.unit_name).read_text()
    assert "WorkingDirectory=" in unit and "runtime with spaces" in unit
    assert 'ExecStart="' in unit
    assert "EnvironmentFile=" in unit
    assert "not-in-unit" not in unit
    assert "User=assistant-user" in unit


def test_systemd_rejects_root_and_public_bind(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(BootstrapError, match="non-root"):
        UnitTestSystemdInstaller(
            settings=replace(settings, service_user="root"),
            runner=FakeSystemctlRunner(),
        ).ensure()

    with pytest.raises(BootstrapError, match="loopback"):
        UnitTestSystemdInstaller(
            settings=replace(settings, host="0.0.0.0"),
            runner=FakeSystemctlRunner(),
        ).ensure()
