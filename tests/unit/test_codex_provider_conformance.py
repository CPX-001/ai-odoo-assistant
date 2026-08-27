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
CURRENT_ADAPTER_MODULE = (
    Path(__file__).resolve().parents[1] / "contracts" / "current_codex_decision_conformance.py"
)
CURRENT_ADAPTER_SPEC = importlib.util.spec_from_file_location(
    "current_codex_decision_conformance", CURRENT_ADAPTER_MODULE
)
assert CURRENT_ADAPTER_SPEC is not None and CURRENT_ADAPTER_SPEC.loader is not None
current_adapter = importlib.util.module_from_spec(CURRENT_ADAPTER_SPEC)
CURRENT_ADAPTER_SPEC.loader.exec_module(current_adapter)


def test_contract_contains_exact_required_phase1_cases() -> None:
    cases = contract.load_contract(FIXTURE)
    assert {case["id"] for case in cases} == contract.REQUIRED_CASE_IDS
    assert len(cases) == 14
    assert {"reasoning_decision_mapping", "plan_decision_mapping", "final_answer_mapping"} <= contract.REQUIRED_CASE_IDS
    assert {"dynamic_tool_mapping", "capability_success", "capability_failure"}.isdisjoint(contract.REQUIRED_CASE_IDS)


def test_evaluator_fails_on_missing_safety_assertion() -> None:
    case = {
        "id": "plan_decision_mapping",
        "expected_outcome": "accepted",
        "required_assertions": ("plan_proposal_decoded", "stage_only", "host_action_lifecycle_preserved"),
    }
    result = contract.evaluate(
        case,
        {"outcome": "accepted", "assertions": {"plan_proposal_decoded": True, "stage_only": True}},
    )
    assert result["passed"] is False
    assert result["missing_assertions"] == ["host_action_lifecycle_preserved"]


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
    assert report["format_version"] == 2


def test_v1_or_incomplete_contract_is_rejected(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["format_version"] = 1
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        contract.load_contract(path)
    except ValueError as error:
        assert str(error) == "conformance_contract_invalid"
    else:
        raise AssertionError("stale v1 contract was accepted")

    data["format_version"] = 2
    data["cases"] = data["cases"][:-1]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        contract.load_contract(path)
    except ValueError as error:
        assert str(error) == "conformance_contract_incomplete"
    else:
        raise AssertionError("incomplete contract was accepted")


def test_reasoning_provider_port_matches_current_codex_decision_engine_signature() -> None:
    import ast

    repo = Path(__file__).resolve().parents[2]
    provider_source = repo / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "provider.py"
    codex_source = repo / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "codex_decision.py"

    def keyword_only_args(path: Path, class_name: str) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "next_decision":
                        return [arg.arg for arg in item.args.kwonlyargs]
        raise AssertionError(f"next_decision missing from {class_name}")

    expected = [
        "message",
        "conversation_summary",
        "context",
        "reasoning_capabilities",
        "planning_capabilities",
        "working_items",
        "remaining_budgets",
    ]
    assert keyword_only_args(provider_source, "ReasoningProvider") == expected
    assert keyword_only_args(codex_source, "CodexDecisionEngine") == expected


def test_unknown_notification_policy_tolerates_only_bounded_inert_additions() -> None:
    import ast

    repo = Path(__file__).resolve().parents[2]
    source = (
        repo / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "codex_decision.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_decision_notification"
    )
    module = ast.fix_missing_locations(ast.Module(body=[helper], type_ignores=[]))

    class FakeCodexAgentError(RuntimeError):
        def __init__(self, code: str) -> None:
            super().__init__(code)
            self.code = code

    def shared_validator(method, params, *, thread_id, turn_id):
        del params, thread_id, turn_id
        if method == "known-critical":
            raise FakeCodexAgentError("codex_item_event_mismatch")
        raise FakeCodexAgentError("codex_event_not_allowed")

    namespace = {
        "CodexAgentError": FakeCodexAgentError,
        "_validate_notification": shared_validator,
    }
    exec(compile(module, "codex_decision_notification_helper", "exec"), namespace)
    validate = namespace["_validate_decision_notification"]

    validate("future/telemetry", {"value": 1}, thread_id="thread-1", turn_id="turn-1")
    validate(
        "future/scoped",
        {"threadId": "thread-1", "turnId": "turn-1"},
        thread_id="thread-1",
        turn_id="turn-1",
    )

    for method, params, code in (
        ("", {}, "codex_event_invalid"),
        ("future/bad-thread", {"threadId": "thread-2"}, "codex_event_identity_mismatch"),
        ("future/bad-turn", {"turnId": "turn-2"}, "codex_event_identity_mismatch"),
        ("future/call", {"callId": "call-1"}, "codex_event_identity_unverified"),
        ("known-critical", {}, "codex_item_event_mismatch"),
    ):
        try:
            validate(method, params, thread_id="thread-1", turn_id="turn-1")
        except FakeCodexAgentError as error:
            assert error.code == code
        else:
            raise AssertionError(f"notification {method!r} was not rejected")


def test_current_codex_decision_engine_matrix_after_unknown_notification_repair() -> None:
    repo = Path(__file__).resolve().parents[2]
    cases = contract.load_contract(FIXTURE)
    adapter = current_adapter.CurrentCodexDecisionConformanceAdapter(repo)
    report = asyncio.run(contract.run_suite(adapter, cases))

    assert report["case_count"] == 14
    assert report["passed"] is False
    failed = {row["case_id"] for row in report["results"] if not row["passed"]}
    assert failed == {"terminal_failure", "overload_backpressure"}
    assert sum(1 for row in report["results"] if row["passed"]) == 12
