from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/odoo18/odoo_ai_phase2_faults/models/fault_runtime.py"
FIXTURE_MANIFEST = ROOT / "tests/fixtures/odoo18/odoo_ai_phase2_faults/__manifest__.py"
PRODUCT_MANIFEST = ROOT / "addons/odoo_ai_assistant/__manifest__.py"
BROWSER = ROOT / "tests/e2e/phase2_real_failure_browser.mjs"
SETUP = ROOT / "tests/e2e/phase2_real_fixture.py"

MARKERS = {
    "__P2_REAL_AUTH__",
    "__P2_REAL_ACL__",
    "__P2_REAL_TIMEOUT__",
    "__P2_REAL_TOOLFAIL__",
    "__P2_REAL_RECOVERY__",
}


def test_fault_fixture_is_test_only_and_double_guarded():
    source = FIXTURE.read_text(encoding="utf-8")
    assert "ODOO_AI_PHASE2_FAULT_FIXTURE" in source
    assert 'env.cr.dbname.startswith(_DISPOSABLE_DB_PREFIX)' in source
    assert '_DISPOSABLE_DB_PREFIX = "odoo_ai_"' in source
    assert '_inherit = "odoo.ai.embedded.runtime"' in source
    assert "if self.env.su:" in source
    assert "turn.user_id.id != self.env.uid" in source
    assert MARKERS <= {
        line.strip().split(" = ", 1)[1].strip('"')
        for line in source.splitlines()
        if line.startswith("FAULT_") and ' = "__P2_REAL_' in line
    }


def test_fault_fixture_is_not_a_product_dependency():
    product = PRODUCT_MANIFEST.read_text(encoding="utf-8")
    fixture_manifest = FIXTURE_MANIFEST.read_text(encoding="utf-8")
    assert "odoo_ai_phase2_faults" not in product
    assert '"depends": ["odoo_ai_assistant"]' in fixture_manifest
    assert '"auto_install": False' in fixture_manifest


def test_real_browser_runner_covers_all_five_phase2_gates():
    source = BROWSER.read_text(encoding="utf-8")
    for gate in (
        "P2-REAL-AUTH",
        "P2-REAL-ACL",
        "P2-REAL-TIMEOUT",
        "P2-REAL-TOOLFAIL",
        "P2-REAL-RECOVERY",
    ):
        assert gate in source
    for marker in MARKERS:
        assert marker in source
    assert 'new URL(response.url()).pathname === "/odoo_ai/v1/turn"' in source
    assert 'jsonRpc(page, "/odoo_ai/v1/turn/status"' in source
    assert 'name: "Reintentar petición"' in source
    assert 'result: "OBSERVED_OK_NOT_AUTOMATIC_PASS"' in source


def test_fixture_setup_requires_disposable_database_and_separate_users():
    source = SETUP.read_text(encoding="utf-8")
    assert 'env.cr.dbname.startswith(_DB_PREFIX)' in source
    assert 'module.state != "installed"' in source
    assert 'required("ODOO_AI_P2_LOGIN")' in source
    assert 'required("ODOO_AI_P2_LIMITED_LOGIN")' in source
    assert "if login == limited_login:" in source
    assert 'Command.set([group_user.id])' in source
