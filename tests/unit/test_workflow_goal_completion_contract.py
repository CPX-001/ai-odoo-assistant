from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
AGENT = REPO / "addons" / "odoo_ai_assistant" / "runtime" / "agent"
WORKFLOW = (
    REPO
    / "addons"
    / "odoo_ai_assistant"
    / "runtime"
    / "capabilities"
    / "providers"
    / "odoo_workflows.py"
)


def test_reasoning_contract_infers_unnamed_mandatory_test_data_dependencies() -> None:
    for source in (AGENT / "codex.py", AGENT / "codex_decision.py"):
        contract = source.read_text(encoding="utf-8")
        normalized = " ".join(contract.split())
        assert "user" in normalized.lower() and "outcome" in normalized.lower()
        assert "minimum" in normalized.lower() and "relational prerequisites" in normalized.lower()
        assert "test/demo/synthetic" in normalized
        assert "user did not name" in normalized
        assert "unrelated real business records" in normalized


def test_workflow_catalog_exposes_schema_inferred_prerequisite_use_case() -> None:
    contract = WORKFLOW.read_text(encoding="utf-8")
    assert "mandatory synthetic prerequisites inferred from schema" in contract
    assert "even when " in contract and "the user did not name" in contract
