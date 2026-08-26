import shutil
import subprocess
from pathlib import Path

import pytest
from installer.bootstrap.bootstrap import BootstrapError
from installer.bootstrap.runtime import RuntimeInstaller, RuntimeInstallSettings


class FakeRuntimeRunner:
    def __init__(self, *, fail_install: bool = False) -> None:
        self.fail_install = fail_install
        self.commands: list[list[str]] = []

    def run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(arguments)
        if arguments[1:3] == ["-m", "venv"]:
            bin_dir = Path(arguments[3]) / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").write_text("python")
            (bin_dir / "odoo-ai-service").write_text("service")
        return subprocess.CompletedProcess(
            arguments,
            1 if self.fail_install and "pip" in arguments else 0,
            stdout="",
            stderr="",
        )


def _source_fixture(tmp_path: Path) -> Path:
    repo_root = Path(__file__).parents[2]
    source = tmp_path / "source"
    shutil.copytree(repo_root / "service", source / "service")
    shutil.copytree(repo_root / "migrations", source / "migrations")
    shutil.copy2(repo_root / "alembic.ini", source / "alembic.ini")
    return source


def test_runtime_release_first_second_upgrade_and_previous(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path)
    runner = FakeRuntimeRunner()
    installer = RuntimeInstaller(
        settings=RuntimeInstallSettings(
            source_root=source,
            install_dir=tmp_path / "install root",
            python_executable=Path("/custom/python"),
        ),
        runner=runner,
    )

    first = installer.ensure()
    second = installer.ensure()
    app_file = source / "service/src/odoo_ai/api/app.py"
    app_file.write_text(app_file.read_text() + "\n# new build\n")
    upgraded = installer.ensure()

    assert first.release_created and first.current_changed
    assert not second.release_created and not second.current_changed
    assert upgraded.release_created and upgraded.current_changed
    assert upgraded.build_id != first.build_id
    assert Path(upgraded.previous_release or "") == Path(first.release_dir)
    assert (tmp_path / "install root/current").resolve() == Path(upgraded.release_dir)
    assert (tmp_path / "install root/previous").resolve() == Path(first.release_dir)

    rolled_back = installer.activate_previous(schema_compatible=True)
    assert Path(rolled_back) == Path(first.release_dir)
    assert (tmp_path / "install root/current").resolve() == Path(first.release_dir)
    assert (tmp_path / "install root/previous").resolve() == Path(upgraded.release_dir)


def test_runtime_rollback_requires_explicit_schema_decision(tmp_path: Path) -> None:
    installer = RuntimeInstaller(
        settings=RuntimeInstallSettings(
            source_root=_source_fixture(tmp_path), install_dir=tmp_path / "install"
        ),
        runner=FakeRuntimeRunner(),
    )
    installer.ensure()

    with pytest.raises(BootstrapError, match="schema compatibility"):
        installer.activate_previous(schema_compatible=False)


def test_runtime_failed_install_keeps_activation_untouched(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path)
    install_dir = tmp_path / "install"
    installer = RuntimeInstaller(
        settings=RuntimeInstallSettings(source_root=source, install_dir=install_dir),
        runner=FakeRuntimeRunner(fail_install=True),
    )

    with pytest.raises(BootstrapError, match="install Assistant runtime package"):
        installer.ensure()

    assert not (install_dir / "current").exists()
    assert not tuple((install_dir / "releases").glob(".*.installing.*"))
