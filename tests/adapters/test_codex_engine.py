import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from odoo_ai.adapters import (
    ActionToolExecutorFactory,
    CodexAppServerEngine,
    CodexEngineError,
    CodexEngineLimits,
    CodexRuntimeSettings,
    action_tool_specs,
)
from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    InstanceProfileSummary,
    ProposedAction,
    ScreenContext,
    ToolRisk,
    ToolSpec,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)

EVIDENCE_ID = UUID("12345678-1234-5678-1234-567812345678")


def _fake_codex(tmp_path: Path, body: str) -> Path:
    executable = tmp_path / "fake-codex-engine"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import os\n"
        "import signal\n"
        "import sys\n"
        "import time\n"
        f"{body}\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _answer(**overrides: object) -> dict[str, object]:
    answer: dict[str, object] = {
        "answer_markdown": "The checked record supports this explanation.",
        "workflow": "EXPLAIN",
        "confidence": "high",
        "evidence_refs": [str(EVIDENCE_ID)],
        "limitations": [],
        "proposed_action": None,
    }
    answer.update(overrides)
    return answer


def _server_body(
    answer: object,
    *,
    observed_path: Path | None = None,
    completed_status: str = "completed",
    extra_item: dict[str, object] | None = None,
) -> str:
    observed = (
        ""
        if observed_path is None
        else f"open({str(observed_path)!r}, 'w', encoding='utf-8').write("
        "json.dumps({'thread': thread_request, 'turn': turn_request}))\n"
    )
    items: list[dict[str, object]] = [
        {
            "id": "agent-1",
            "type": "agentMessage",
            "text": answer if isinstance(answer, str) else json.dumps(answer),
        }
    ]
    if extra_item is not None:
        items.insert(0, extra_item)
    notification = {
        "method": "turn/completed",
        "params": {
            "threadId": "thread-1",
            "turn": {
                "id": "turn-1",
                "items": items,
                "status": completed_status,
            },
        },
    }
    return (
        "initialize = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': initialize['id'], 'result': {"
        "'platformFamily': 'unix', 'platformOs': 'linux', "
        "'userAgent': 'fake-codex/0.149.0'}}), flush=True)\n"
        "json.loads(sys.stdin.readline())\n"
        "thread_request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': thread_request['id'], 'result': {"
        "'model': 'fake-model', 'modelProvider': 'fake-provider', "
        "'runtimeWorkspaceRoots': [], "
        "'thread': {'id': 'thread-1', 'ephemeral': True}}}), flush=True)\n"
        "turn_request = json.loads(sys.stdin.readline())\n"
        f"{observed}"
        "print(json.dumps({'id': turn_request['id'], 'result': {"
        "'turn': {'id': 'turn-1', 'items': [], 'status': 'inProgress'}}}), flush=True)\n"
        f"print(json.dumps({notification!r}), flush=True)\n"
        "sys.stdin.read()"
    )


def _context(*, with_secrets: bool = False) -> ContextPack:
    screen = ScreenContext(
        model="sale.order",
        res_id=56,
        allowed_context_subset=(
            {"dsn": "postgresql://raw-dsn", "physical_path": "/srv/odoo/private"}
            if with_secrets
            else {}
        ),
        captured_at=datetime(2026, 8, 22, 10, 30, tzinfo=UTC),
    )
    evidence = Evidence(
        evidence_id=EVIDENCE_ID,
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="Quotation",
        summary="Record read under the effective user.",
        payload=(
            {
                "delegation_token": "raw-delegation-token",
                "password": "raw-password",
                "safe_state": "sale",
            }
            if with_secrets
            else {"safe_state": "sale"}
        ),
        pointer=(
            {
                "absolute_path": "/srv/odoo/private.py",
                "model": "sale.order",
            }
            if with_secrets
            else {"model": "sale.order"}
        ),
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint="record:56:v1",
    )
    return ContextPack(
        request=UserRequest(message="Explain why this quotation created a task."),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1, allowed_company_ids=[1]),
        workflow_hint=Workflow.EXPLAIN,
        instance=InstanceProfileSummary(
            instance_id="/srv/odoo/private-instance" if with_secrets else "odoo-test",
            profile_revision="rev-12",
            capabilities=["source", "records"],
        ),
        live_evidence=[evidence],
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=0, max_evidence_items=4),
    )


def _run(
    executable: Path,
    context: ContextPack | None = None,
    *,
    turn_timeout: float = 2,
) -> tuple[AnswerEnvelope, CodexAppServerEngine]:
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(
            executable=executable,
            turn_timeout_seconds=turn_timeout,
            shutdown_timeout_seconds=0.1,
            experimental_api=True,
        )
    )
    answer = asyncio.run(
        engine.run_turn(
            context or _context(),
            [],
            AnswerEnvelope.model_json_schema(),
        )
    )
    return answer, engine


def test_valid_structured_answer_uses_one_ephemeral_no_tool_thread(
    tmp_path: Path,
) -> None:
    observed = tmp_path / "observed.json"
    executable = _fake_codex(
        tmp_path,
        _server_body(_answer(), observed_path=observed),
    )

    answer, engine = _run(executable)

    assert answer.workflow is Workflow.EXPLAIN
    assert answer.evidence_refs == [EVIDENCE_ID]
    assert engine.last_metadata is not None
    assert engine.last_metadata.engine == "codex"
    assert engine.last_metadata.status == "ok"
    assert engine.last_metadata.model == "fake-model"
    captured = json.loads(observed.read_text(encoding="utf-8"))
    assert captured["thread"]["method"] == "thread/start"
    assert captured["thread"]["params"] == {
        "approvalPolicy": "never",
        "baseInstructions": captured["thread"]["params"]["baseInstructions"],
        "cwd": captured["thread"]["params"]["cwd"],
        "dynamicTools": [],
        "environments": [],
        "ephemeral": True,
        "runtimeWorkspaceRoots": [],
        "sandbox": "read-only",
    }
    assert "thread/resume" not in observed.read_text(encoding="utf-8")
    assert captured["turn"]["method"] == "turn/start"
    provider_schema = captured["turn"]["params"]["outputSchema"]
    assert set(provider_schema["required"]) == set(provider_schema["properties"])
    assert provider_schema["properties"]["proposed_action"] == {"type": "null"}
    assert "JsonValue" not in provider_schema["$defs"]
    assert "ProposedAction" not in provider_schema["$defs"]


def test_context_serialization_omits_authority_secrets_and_physical_paths(
    tmp_path: Path,
) -> None:
    observed = tmp_path / "observed.json"
    executable = _fake_codex(
        tmp_path,
        _server_body(_answer(), observed_path=observed),
    )

    _run(executable, _context(with_secrets=True))

    captured = observed.read_text(encoding="utf-8")
    assert "raw-delegation-token" not in captured
    assert "raw-password" not in captured
    assert "postgresql://raw-dsn" not in captured
    assert "/srv/odoo" not in captured
    assert '"uid"' not in captured
    turn_input = json.loads(json.loads(captured)["turn"]["params"]["input"][0]["text"])
    assert turn_input["host_contract"]["data_trust"] == "untrusted"
    assert turn_input["host_contract"]["tools_available"] is False
    assert turn_input["untrusted_data"]["evidence"][0]["payload"] == {
        "safe_state": "sale"
    }


@pytest.mark.parametrize(
    ("answer", "error_code"),
    [
        ("not-json", "codex_answer_schema_invalid"),
        (json.dumps(_answer()) + " trailing text", "codex_answer_schema_invalid"),
        (_answer(extra="forbidden"), "codex_answer_schema_invalid"),
        (_answer(workflow="DIAGNOSE"), "codex_workflow_mismatch"),
        (
            _answer(evidence_refs=["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]),
            "codex_evidence_ref_unknown",
        ),
    ],
)
def test_invalid_structured_output_fails_closed(
    tmp_path: Path, answer: object, error_code: str
) -> None:
    executable = _fake_codex(tmp_path, _server_body(answer))
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=True)
    )

    with pytest.raises(CodexEngineError, match=error_code):
        asyncio.run(engine.run_turn(_context(), [], AnswerEnvelope.model_json_schema()))

    assert engine.last_metadata is not None
    assert engine.last_metadata.error_code == error_code


def test_proposed_action_is_rejected(tmp_path: Path) -> None:
    proposed = ProposedAction(action_type="write", summary="Change the quotation")
    executable = _fake_codex(
        tmp_path,
        _server_body(_answer(proposed_action=proposed.model_dump(mode="json"))),
    )

    with pytest.raises(CodexEngineError, match="codex_proposed_action_not_allowed"):
        _run(executable)


def test_action_turn_allows_only_preview_presentation_schema(tmp_path: Path) -> None:
    observed = tmp_path / "observed-action.json"
    proposed = {
        "action_type": "record_patch",
        "summary": "Preview the bounded change",
        "details": {
            "proposal_id": "60000000-0000-4000-8000-000000000006",
            "payload_fingerprint": "action-payload:v1:sha256:" + "a" * 64,
        },
    }
    executable = _fake_codex(
        tmp_path,
        _server_body(
            _answer(
                workflow="ACTION",
                evidence_refs=[],
                proposed_action=proposed,
            ),
            observed_path=observed,
        ),
    )
    context = _context().model_copy(
        update={
            "workflow_hint": Workflow.ACTION,
            "limits": TurnLimits(max_tool_calls=2, max_evidence_items=4),
        }
    )

    class UnusedGateway:
        pass

    class UnusedApprovals:
        pass

    factory = ActionToolExecutorFactory(
        gateway=UnusedGateway(),  # type: ignore[arg-type]
        approval_service=UnusedApprovals(),  # type: ignore[arg-type]
        turn_id=UUID("50000000-0000-4000-8000-000000000005"),
        database="fixture-db",
        user_id=7,
        company_id=1,
        allowed_company_ids=(1,),
        model="sale.order",
        record_id=56,
    )
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=True),
        tool_executor_factory=factory,
    )

    answer = asyncio.run(
        engine.run_turn(
            context, list(action_tool_specs()), AnswerEnvelope.model_json_schema()
        )
    )

    assert answer.workflow is Workflow.ACTION
    assert answer.proposed_action is not None
    captured = json.loads(observed.read_text(encoding="utf-8"))
    instructions = captured["thread"]["params"]["baseInstructions"]
    dynamic_names = {
        item["name"] for item in captured["thread"]["params"]["dynamicTools"]
    }
    assert dynamic_names == {
        "odoo_get_effective_write_schema",
            "odoo_preview_record_create",
            "odoo_preview_business_action",
        "odoo_preview_record_patch",
    }
    assert "cannot\napprove, commit" in instructions
    proposed_schema = captured["turn"]["params"]["outputSchema"]["properties"][
        "proposed_action"
    ]
    assert proposed_schema != {"type": "null"}
    assert "approval_id" not in json.dumps(proposed_schema)


def test_nonempty_tools_require_executor_before_process_spawn(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    executable = _fake_codex(
        tmp_path,
        f"open({str(marker)!r}, 'w').write('spawned')",
    )
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=True)
    )
    tool = ToolSpec(
        name="source.read",
        description="Not available in M4-02.",
        input_schema={"type": "object"},
        risk=ToolRisk.READ,
        executor_id="source.read.v1",
    )

    with pytest.raises(CodexEngineError, match="codex_tool_executor_unavailable"):
        asyncio.run(
            engine.run_turn(_context(), [tool], AnswerEnvelope.model_json_schema())
        )

    assert not marker.exists()


def test_provider_tool_item_is_rejected(tmp_path: Path) -> None:
    executable = _fake_codex(
        tmp_path,
        _server_body(
            _answer(),
            extra_item={
                "id": "command-1",
                "type": "commandExecution",
                "command": "pwd",
            },
        ),
    )

    with pytest.raises(CodexEngineError, match="codex_tool_call_not_allowed"):
        _run(executable)


def test_timeout_interrupts_and_cleans_up_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    executable = _fake_codex(
        tmp_path,
        "initialize = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': initialize['id'], 'result': {"
        "'platformFamily': 'unix', 'platformOs': 'linux', "
        "'userAgent': 'fake-codex/0.149.0'}}), flush=True)\n"
        "json.loads(sys.stdin.readline())\n"
        "thread_request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': thread_request['id'], 'result': {"
        "'runtimeWorkspaceRoots': [], 'thread': {"
        "'id': 'thread-1', 'ephemeral': True}}}), flush=True)\n"
        "turn_request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': turn_request['id'], 'result': {"
        "'turn': {'id': 'turn-1', 'items': [], 'status': 'inProgress'}}}), flush=True)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "while True: time.sleep(1)",
    )
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(
            executable=executable,
            turn_timeout_seconds=0.1,
            shutdown_timeout_seconds=0.1,
            experimental_api=True,
        )
    )

    with pytest.raises(CodexEngineError, match="codex_read_timeout"):
        asyncio.run(engine.run_turn(_context(), [], AnswerEnvelope.model_json_schema()))

    pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_invalid_requested_schema_is_rejected_before_spawn(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    executable = _fake_codex(
        tmp_path,
        f"open({str(marker)!r}, 'w').write('spawned')",
    )
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=True)
    )

    with pytest.raises(CodexEngineError, match="codex_output_schema_invalid"):
        asyncio.run(engine.run_turn(_context(), [], {"type": "object"}))

    assert not marker.exists()


def test_context_caps_are_enforced_before_spawn(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    executable = _fake_codex(
        tmp_path,
        f"open({str(marker)!r}, 'w').write('spawned')",
    )
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=True),
        limits=CodexEngineLimits(max_string_chars=128),
    )
    context = _context().model_copy(update={"request": UserRequest(message="x" * 129)})

    with pytest.raises(CodexEngineError, match="codex_context_string_too_large"):
        asyncio.run(engine.run_turn(context, [], AnswerEnvelope.model_json_schema()))

    assert not marker.exists()
