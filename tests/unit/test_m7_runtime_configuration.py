import json
from pathlib import Path

import pytest
from odoo_ai.contracts.configuration import (
    CONFIG_DESCRIPTOR_BY_KEY,
    AssistantAdminOverrides,
    ConfigReloadMode,
)
from odoo_ai.runtime.configuration import _host_facts, _post_action


def test_post_action_represents_restart_and_setup_without_executing_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "reasoning.model"
    descriptor = CONFIG_DESCRIPTOR_BY_KEY[key]
    previous = AssistantAdminOverrides()
    current = AssistantAdminOverrides(reasoning_model="gpt-5.6/codex")

    monkeypatch.setitem(
        CONFIG_DESCRIPTOR_BY_KEY,
        key,
        descriptor.model_copy(update={"reload_mode": ConfigReloadMode.RESTART_REQUIRED}),
    )
    assert _post_action(previous, current) == "restart_required"

    monkeypatch.setitem(
        CONFIG_DESCRIPTOR_BY_KEY,
        key,
        descriptor.model_copy(update={"reload_mode": ConfigReloadMode.SETUP_REQUIRED}),
    )
    assert _post_action(previous, current) == "setup_required"


def test_host_codex_timeout_contract_is_not_narrowed_by_settings(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    root.mkdir()
    facts = _host_facts(
        {
            "ODOO_AI_SOURCE_ROOTS": json.dumps([str(root)]),
            "ODOO_AI_CODEX_STARTUP_TIMEOUT_SECONDS": "60",
            "ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS": "1200",
        }
    )

    assert "reasoning.startup_timeout_seconds" not in facts.invalid_keys
    assert "reasoning.turn_timeout_seconds" not in facts.invalid_keys
