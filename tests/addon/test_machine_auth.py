import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_machine_auth_module() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "addons/odoo_ai_assistant/security/machine_auth.py"
    )
    spec = importlib.util.spec_from_file_location("odoo_ai_test_machine_auth", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


machine_auth = _load_machine_auth_module()
MachineAuthenticationError = machine_auth.MachineAuthenticationError
require_machine_secret = machine_auth.require_machine_secret
SECRET = "machine-auth-secret-" + "s" * 48


def test_machine_auth_uses_the_m1_secret_file_policy(tmp_path: Path) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)

    require_machine_secret(SECRET, secret_file=str(secret_file))

    with pytest.raises(MachineAuthenticationError, match="machine_auth_rejected"):
        require_machine_secret("wrong-" + "x" * 48, secret_file=str(secret_file))


def test_machine_auth_errors_are_sanitized(tmp_path: Path) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o644)

    with pytest.raises(MachineAuthenticationError) as failure:
        require_machine_secret(SECRET, secret_file=str(secret_file))

    assert failure.value.code == "machine_auth_unavailable"
    assert SECRET not in str(failure.value)
    assert str(secret_file) not in str(failure.value)
