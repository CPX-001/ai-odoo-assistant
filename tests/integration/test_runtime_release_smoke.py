import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from installer.bootstrap.runtime import RuntimeInstaller, RuntimeInstallSettings


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


@pytest.mark.skipif(
    os.environ.get("ODOO_AI_RUN_RUNTIME_INSTALL_TEST") != "1",
    reason="set ODOO_AI_RUN_RUNTIME_INSTALL_TEST=1 for the real runtime install smoke",
)
def test_runtime_release_install_upgrade_and_rollback(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source = tmp_path / "source"
    shutil.copytree(
        repo_root / "service",
        source / "service",
        ignore=shutil.ignore_patterns(".venv"),
    )
    shutil.copytree(repo_root / "migrations", source / "migrations")
    shutil.copy2(repo_root / "alembic.ini", source / "alembic.ini")

    installer = RuntimeInstaller(
        settings=RuntimeInstallSettings(
            source_root=source,
            install_dir=tmp_path / "runtime with spaces",
            python_executable=repo_root / ".venv/bin/python",
        )
    )
    first = installer.ensure()
    second = installer.ensure()

    executable = Path(first.release_dir) / ".venv/bin/python"
    installed_version = subprocess.run(
        [
            str(executable),
            "-c",
            "from importlib.metadata import version; print(version('odoo-ai-assistant-service'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert installed_version == first.version
    assert first.release_created and first.current_changed
    assert not second.release_created and not second.current_changed

    port = _free_port()
    environment = os.environ.copy()
    environment.update({"ODOO_AI_HOST": "127.0.0.1", "ODOO_AI_PORT": str(port)})
    process = subprocess.Popen(
        [str(Path(first.release_dir) / ".venv/bin/odoo-ai-service")],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=1
                ) as response:
                    assert response.status == 200
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
    finally:
        process.terminate()
        process.wait(timeout=5)

    source_file = source / "service/src/odoo_ai/__init__.py"
    source_file.write_text(
        source_file.read_text(encoding="utf-8") + "\n# upgrade smoke\n",
        encoding="utf-8",
    )
    upgraded = installer.ensure()
    assert upgraded.release_created and upgraded.current_changed
    assert upgraded.build_id != first.build_id
    assert Path(upgraded.previous_release or "") == Path(first.release_dir)

    restored = installer.activate_previous(schema_compatible=True)
    assert Path(restored) == Path(first.release_dir)
    assert (tmp_path / "runtime with spaces/current").resolve() == Path(first.release_dir)
