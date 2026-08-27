import ast
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def _load_terminal_failure_contract():
    repo = Path(__file__).resolve().parents[2]
    source_path = (
        repo / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "codex_decision.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    selected_names = {
        "CodexProviderFailure",
        "CodexDecisionError",
        "_safe_failure_token",
        "_upstream_error_payload",
        "_provider_failure_details",
        "_decision_terminal_error",
    }
    body = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.ClassDef)
            and node.name in selected_names
            or isinstance(node, ast.FunctionDef)
            and node.name in selected_names
        )
    ]
    module = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))

    class FakeCodexAgentError(RuntimeError):
        def __init__(self, code: str) -> None:
            super().__init__(code)
            self.code = code

    namespace = {
        "CodexAgentError": FakeCodexAgentError,
        "Mapping": Mapping,
        "dataclass": dataclass,
        "json": json,
        "_MAX_DECISION_CONTEXT_BYTES": 128 * 1024,
        "_MAX_PROVIDER_FAILURE_TOKEN": 64,
    }
    exec(compile(module, "codex_terminal_failure_contract", "exec"), namespace)
    return source, namespace


def test_terminal_failure_preserves_bounded_provider_facts_without_raw_message() -> None:
    source, namespace = _load_terminal_failure_contract()
    terminal_error = namespace["_decision_terminal_error"]
    failure_type = namespace["CodexProviderFailure"]

    upstream_message = json.dumps(
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "code": "invalid_json_schema",
                "message": "sensitive schema detail must not survive",
            },
            "status": 400,
        }
    )
    error = terminal_error(
        {
            "message": upstream_message,
            "codexErrorInfo": "other",
            "additionalDetails": {"private": "must-not-survive"},
        }
    )

    assert error.code == "codex_output_schema_invalid"
    assert error.provider_failure == failure_type(
        category="other",
        http_status_code=400,
        upstream_code="invalid_json_schema",
    )
    assert str(error) == "codex_output_schema_invalid"
    assert "sensitive schema detail" not in repr(error.provider_failure)
    assert "must-not-survive" not in repr(error.provider_failure)
    assert source.count("raise _decision_terminal_error(") >= 2


def test_structured_transport_category_and_status_survive_without_message_text() -> None:
    _, namespace = _load_terminal_failure_contract()
    terminal_error = namespace["_decision_terminal_error"]
    failure_type = namespace["CodexProviderFailure"]

    error = terminal_error(
        {
            "message": "provider transport detail must remain unpersisted",
            "codexErrorInfo": {
                "httpConnectionFailed": {
                    "httpStatusCode": 503,
                }
            },
            "additionalDetails": {"requestBody": "private"},
        }
    )

    assert error.code == "codex_turn_failed"
    assert error.provider_failure == failure_type(
        category="httpConnectionFailed",
        http_status_code=503,
        upstream_code=None,
    )
    assert str(error) == "codex_turn_failed"
    assert "transport detail" not in repr(error.provider_failure)
    assert "requestBody" not in repr(error.provider_failure)


def test_invalid_unbounded_provider_fields_are_discarded() -> None:
    _, namespace = _load_terminal_failure_contract()
    terminal_error = namespace["_decision_terminal_error"]

    error = terminal_error(
        {
            "message": json.dumps(
                {
                    "error": {"code": "not a safe token with spaces"},
                    "status": 999,
                }
            ),
            "codexErrorInfo": {
                "bad request\nsecret": {
                    "httpStatusCode": 999,
                }
            },
        }
    )

    assert error.code == "codex_turn_failed"
    assert error.provider_failure is None


def test_overload_fact_is_preserved_but_not_yet_classified_retryable() -> None:
    source, namespace = _load_terminal_failure_contract()
    terminal_error = namespace["_decision_terminal_error"]
    failure_type = namespace["CodexProviderFailure"]

    error = terminal_error(
        {
            "message": "overload detail",
            "codexErrorInfo": "serverOverloaded",
        }
    )

    assert error.code == "codex_turn_failed"
    assert error.provider_failure == failure_type(
        category="serverOverloaded",
        http_status_code=None,
        upstream_code=None,
    )
    assert "provider_retryable" not in source
    assert "codex_overloaded" not in source
    assert "codex_rate_limited" not in source


def test_current_conformance_binding_marks_terminal_failure_structured() -> None:
    import asyncio
    import importlib.util

    repo = Path(__file__).resolve().parents[2]
    adapter_module = (
        repo / "tests" / "contracts" / "current_codex_decision_conformance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "current_codex_decision_conformance_terminal",
        adapter_module,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    observation = asyncio.run(
        module.CurrentCodexDecisionConformanceAdapter(repo).observe(
            {"id": "terminal_failure"}
        )
    )
    assert observation == {
        "outcome": "rejected",
        "assertions": {"structured_error_preserved": True},
    }
