import asyncio
import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "contracts" / "codex_provider_conformance.py"
SPEC = importlib.util.spec_from_file_location("codex_provider_conformance", MODULE)
assert SPEC is not None and SPEC.loader is not None
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "codex_provider_conformance_cases.json"


def test_contract_contains_exact_required_phase1_cases() -> None:
    cases = contract.load_contract(FIXTURE)
    assert {case["id"] for case in cases} == contract.REQUIRED_CASE_IDS
    assert len(cases) == 14


def test_evaluator_fails_on_missing_safety_assertion() -> None:
    case = {
        "id": "thread_isolation",
        "expected_outcome": "accepted",
        "required_assertions": ("approval_never", "sandbox_read_only", "ephemeral_thread"),
    }
    result = contract.evaluate(
        case,
        {"outcome": "accepted", "assertions": {"approval_never": True, "sandbox_read_only": True}},
    )
    assert result["passed"] is False
    assert result["missing_assertions"] == ["ephemeral_thread"]


def test_same_harness_runs_adapter_without_product_runtime_imports() -> None:
    cases = contract.load_contract(FIXTURE)

    class FakeAdapter:
        async def observe(self, case):
            return {
                "outcome": case["expected_outcome"],
                "assertions": {name: True for name in case["required_assertions"]},
            }

    report = asyncio.run(contract.run_suite(FakeAdapter(), cases))
    assert report["passed"] is True
    assert report["case_count"] == 14


def test_incomplete_contract_is_rejected(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["cases"] = data["cases"][:-1]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        contract.load_contract(path)
    except ValueError as error:
        assert str(error) == "conformance_contract_incomplete"
    else:
        raise AssertionError("incomplete contract was accepted")
