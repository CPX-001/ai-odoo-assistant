from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = REPO_ROOT / "addons" / "odoo_ai_assistant"
AUTH_NONE_RE = re.compile(r"\bauth\s*=\s*['\"]none['\"]")


def test_supported_assistant_has_no_unauthenticated_http_or_machine_inventory_surface():
    controllers = ADDON_ROOT / "controllers"
    security = ADDON_ROOT / "security"
    services = ADDON_ROOT / "services"
    violations = []
    for root in (controllers, security, services):
        for path in sorted(root.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if AUTH_NONE_RE.search(text):
                violations.append(path.relative_to(REPO_ROOT).as_posix())

    assert violations == []
    assert not (controllers / "internal_tools.py").exists()
    assert not (security / "machine_auth.py").exists()
    assert not (services / "instance_inventory.py").exists()


def test_obsolete_github_actions_workflow_is_not_in_supported_tree():
    assert not (
        REPO_ROOT
        / ".github"
        / "workflows"
        / "embedded-runtime-verification.yml"
    ).exists()
