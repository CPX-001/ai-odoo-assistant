import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from odoo_ai.adapters import (
    SOURCE_FIND_MODEL_EXTENSIONS,
    SOURCE_FIND_SYMBOL,
    SOURCE_READ_EXCERPT,
    CodexAppServerEngine,
    CodexEngineError,
    CodexRuntimeSettings,
    build_source_tool_registry,
    codex_dynamic_tool_name,
    source_tool_specs,
)
from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    FindModelExtensionsRequest,
    FindModelExtensionsResult,
    FindSymbolRequest,
    FindSymbolResult,
    InstanceProfileSummary,
    ModelExtensionGroup,
    ReadExcerptRequest,
    ScreenContext,
    SourceCandidate,
    SourceExcerpt,
    SourceExcerptLine,
    SourceMatchReason,
    SourceProvenance,
    SourceRef,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)
from odoo_ai.tools import (
    EvidenceLedger,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
)

SOURCE_FILE_ID = UUID("11111111-1111-1111-1111-111111111111")
SYMBOL_ID = UUID("22222222-2222-2222-2222-222222222222")
EVIDENCE_ID = UUID("33333333-3333-3333-3333-333333333333")
FINGERPRINT = "sha256:" + "a" * 64


class FakeSourceBackend:
    def __init__(self, *, stale: bool = False, unsafe_path: bool = False) -> None:
        self.calls: list[tuple[str, object]] = []
        self.stale = stale
        self.unsafe_path = unsafe_path
        self.ref = SourceRef(
            source_file_id=SOURCE_FILE_ID,
            fingerprint=FINGERPRINT,
            start_line=10,
            end_line=16,
        )
        self.candidate = SourceCandidate(
            symbol_id=SYMBOL_ID,
            module="sale_fixture",
            kind="method",
            model="sale.order",
            name="sale.order.action_confirm",
            logical_path="sale_fixture/models/sale_order.py",
            start_line=10,
            end_line=16,
            fingerprint=FINGERPRINT,
            provenance=SourceProvenance.MANUAL,
            ref=self.ref,
            score=100,
            match_reason=SourceMatchReason.EXACT,
            observed_at=datetime(2026, 8, 22, 10, 30, tzinfo=UTC),
        )

    async def find_model_extensions(
        self, request: FindModelExtensionsRequest
    ) -> FindModelExtensionsResult:
        self.calls.append((SOURCE_FIND_MODEL_EXTENSIONS, request))
        return FindModelExtensionsResult(
            model=request.model,
            groups=(
                ModelExtensionGroup(
                    module="sale_fixture",
                    logical_path="sale_fixture/models/sale_order.py",
                    provenance=SourceProvenance.MANUAL,
                    relationships=(self.candidate,),
                    runtime_order_checked=False,
                ),
            ),
        )

    async def find_symbol(self, request: FindSymbolRequest) -> FindSymbolResult:
        self.calls.append((SOURCE_FIND_SYMBOL, request))
        return FindSymbolResult(candidates=(self.candidate,))

    async def read_excerpt(self, request: ReadExcerptRequest) -> SourceExcerpt:
        self.calls.append((SOURCE_READ_EXCERPT, request))
        if self.stale:
            raise ToolExecutorError("stale_source")
        if request.ref != self.ref:
            raise ToolExecutorError("source_ref_invalid")
        logical_path = (
            "/srv/private/addons/sale_order.py"
            if self.unsafe_path
            else "sale_fixture/models/sale_order.py"
        )
        evidence = Evidence(
            evidence_id=EVIDENCE_ID,
            kind=EvidenceKind.SOURCE,
            status=EvidenceStatus.CHECKED,
            title="Source: sale_fixture/10",
            summary="Fingerprint-checked fixture excerpt.",
            payload={
                "module": "sale_fixture",
                "trust": "untrusted_source",
                "lines": [{"number": 12, "text": "def action_confirm(self):"}],
            },
            pointer={
                "source_file_id": str(SOURCE_FILE_ID),
                "logical_path": logical_path,
                "start_line": 10,
                "end_line": 16,
            },
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=FINGERPRINT,
        )
        return SourceExcerpt(
            ref=request.ref,
            module="sale_fixture",
            logical_path=logical_path,
            lines=(
                SourceExcerptLine(number=12, text="def action_confirm(self):"),
                SourceExcerptLine(number=13, text="    self.env['project.task'].create({})"),
            ),
            evidence=evidence,
        )


def _context() -> ContextPack:
    screen = ScreenContext(
        model="sale.order",
        res_id=56,
        captured_at=datetime(2026, 8, 22, 10, 30, tzinfo=UTC),
    )
    return ContextPack(
        request=UserRequest(message="Explain why confirming this order creates a task."),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1),
        workflow_hint=Workflow.EXPLAIN,
        instance=InstanceProfileSummary(
            instance_id="odoo-test",
            capabilities=["source"],
        ),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=8, max_evidence_items=8),
    )


def _executor_factory(backend: FakeSourceBackend):
    @asynccontextmanager
    async def factory(context: ContextPack, tools):
        limits = ToolExecutionLimits()
        ledger = EvidenceLedger(
            max_items=min(context.limits.max_evidence_items, limits.max_evidence_items),
            max_payload_bytes=limits.max_evidence_bytes,
            live=context.live_evidence,
            retrieved=context.retrieved_evidence,
        )
        yield ToolExecutor(
            registry=build_source_tool_registry(backend, tools),
            ledger=ledger,
            turn_limits=context.limits,
            limits=limits,
        )

    return factory


def _fake_codex(tmp_path: Path, body: str) -> Path:
    executable = tmp_path / "fake-codex-source-tools"
    executable.write_text(
        f"#!{sys.executable}\nimport json\nimport sys\n{body}\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _server_body(
    requests: list[dict[str, object]],
    *,
    answer: dict[str, object] | None,
    observed: Path,
    expect_abort: bool = False,
) -> str:
    answer_text = json.dumps(
        answer
        or {
            "answer_markdown": "The tool request was rejected.",
            "workflow": "EXPLAIN",
            "confidence": "low",
            "evidence_refs": [],
            "limitations": ["No current source evidence was available."],
            "proposed_action": None,
        }
    )
    dynamic_items = [
        {
            "id": request["callId"],
            "type": "dynamicToolCall",
            "tool": request["tool"],
            "arguments": request["arguments"],
            "status": "completed",
        }
        for request in requests
    ]
    completed = {
        "method": "turn/completed",
        "params": {
            "threadId": "thread-1",
            "turn": {
                "id": "turn-1",
                "items": [
                    *dynamic_items,
                    {"id": "agent-1", "type": "agentMessage", "text": answer_text},
                ],
                "status": "completed",
            },
        },
    }
    request_lines = ""
    for index, request in enumerate(requests, start=100):
        params = {
            **request,
            "threadId": "thread-1",
            "turnId": "turn-1",
        }
        request_lines += (
            f"print(json.dumps({{'id': {index}, 'method': 'item/tool/call', "
            f"'params': {params!r}}}), flush=True)\n"
            "tool_responses.append(json.loads(sys.stdin.readline()))\n"
        )
    tail = (
        "interrupt = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': interrupt['id'], 'result': {}}), flush=True)\n"
        if expect_abort
        else f"print(json.dumps({completed!r}), flush=True)\n"
    )
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
        "print(json.dumps({'id': turn_request['id'], 'result': {"
        "'turn': {'id': 'turn-1', 'items': [], 'status': 'inProgress'}}}), flush=True)\n"
        "tool_responses = []\n"
        f"{request_lines}"
        f"open({str(observed)!r}, 'w', encoding='utf-8').write(json.dumps({{"
        "'thread': thread_request, 'turn': turn_request, "
        "'tool_responses': tool_responses}))\n"
        f"{tail}"
        "sys.stdin.read()"
    )


def _run(
    executable: Path,
    backend: FakeSourceBackend,
    *,
    tools=None,
) -> AnswerEnvelope:
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=True),
        tool_executor_factory=_executor_factory(backend),
    )
    return asyncio.run(
        engine.run_turn(
            _context(),
            list(tools or source_tool_specs()),
            AnswerEnvelope.model_json_schema(),
        )
    )


def _read_request(ref: SourceRef, *, call_id: str = "call-read") -> dict[str, object]:
    return {
        "callId": call_id,
        "tool": codex_dynamic_tool_name(SOURCE_READ_EXCERPT),
        "arguments": {
            "ref": ref.model_dump(mode="json"),
            "context_before": 2,
            "context_after": 2,
            "max_lines": 40,
            "max_bytes": 16_384,
        },
    }


def test_source_tool_specs_are_generated_from_real_path_free_input_schemas() -> None:
    specs = {spec.name: spec for spec in source_tool_specs()}

    assert set(specs) == {
        SOURCE_FIND_MODEL_EXTENSIONS,
        SOURCE_FIND_SYMBOL,
        SOURCE_READ_EXCERPT,
    }
    assert specs[SOURCE_FIND_SYMBOL].input_schema == FindSymbolRequest.model_json_schema()
    assert specs[SOURCE_FIND_MODEL_EXTENSIONS].input_schema == (
        FindModelExtensionsRequest.model_json_schema()
    )
    assert specs[SOURCE_READ_EXCERPT].input_schema == ReadExcerptRequest.model_json_schema()
    for spec in specs.values():
        assert "path" not in spec.input_schema.get("properties", {})


def test_fake_codex_completes_three_source_tool_roundtrips(tmp_path: Path) -> None:
    backend = FakeSourceBackend()
    observed = tmp_path / "roundtrip.json"
    requests = [
        {
            "callId": "call-extensions",
            "tool": codex_dynamic_tool_name(SOURCE_FIND_MODEL_EXTENSIONS),
            "arguments": {"model": "sale.order", "max_results": 10},
        },
        {
            "callId": "call-symbol",
            "tool": codex_dynamic_tool_name(SOURCE_FIND_SYMBOL),
            "arguments": {
                "query": "action_confirm",
                "model": "sale.order",
                "max_results": 5,
            },
        },
        _read_request(backend.ref),
    ]
    answer = {
        "answer_markdown": "The checked customization creates a project task.",
        "workflow": "EXPLAIN",
        "confidence": "high",
        "evidence_refs": [str(EVIDENCE_ID)],
        "limitations": [],
        "proposed_action": None,
    }
    executable = _fake_codex(
        tmp_path,
        _server_body(requests, answer=answer, observed=observed),
    )

    result = _run(executable, backend)

    assert result.evidence_refs == [EVIDENCE_ID]
    assert [name for name, _ in backend.calls] == [
        SOURCE_FIND_MODEL_EXTENSIONS,
        SOURCE_FIND_SYMBOL,
        SOURCE_READ_EXCERPT,
    ]
    captured = json.loads(observed.read_text(encoding="utf-8"))
    assert [tool["name"] for tool in captured["thread"]["params"]["dynamicTools"]] == [
        codex_dynamic_tool_name(spec.name) for spec in source_tool_specs()
    ]
    responses = captured["tool_responses"]
    assert all(response["result"]["success"] for response in responses)
    excerpt_result = json.loads(responses[-1]["result"]["contentItems"][0]["text"])
    assert excerpt_result["evidence"][0]["evidence_id"] == str(EVIDENCE_ID)
    assert excerpt_result["data"]["logical_path"] == ("sale_fixture/models/sale_order.py")
    assert str(tmp_path.resolve()) not in observed.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("tool_request", "error_code"),
    [
        (
            {"callId": "call-unknown", "tool": "source.read_file", "arguments": {}},
            "tool_not_registered",
        ),
        (
            {
                "callId": "call-path",
                "tool": codex_dynamic_tool_name(SOURCE_READ_EXCERPT),
                "arguments": {"path": "/srv/private/addons/secret.py"},
            },
            "tool_input_invalid",
        ),
    ],
)
def test_invented_tool_or_free_path_input_fails_closed(
    tmp_path: Path,
    tool_request: dict[str, object],
    error_code: str,
) -> None:
    backend = FakeSourceBackend()
    observed = tmp_path / f"{error_code}.json"
    executable = _fake_codex(
        tmp_path,
        _server_body([tool_request], answer=None, observed=observed, expect_abort=True),
    )

    with pytest.raises(CodexEngineError, match=error_code):
        _run(executable, backend)

    captured = json.loads(observed.read_text(encoding="utf-8"))
    response = captured["tool_responses"][0]["result"]
    assert response["success"] is False
    error = json.loads(response["contentItems"][0]["text"])["error"]
    assert error["code"] == error_code
    assert backend.calls == []


@pytest.mark.parametrize("failure", ["stale", "manipulated_ref"])
def test_stale_or_manipulated_source_ref_never_adds_checked_evidence(
    tmp_path: Path, failure: str
) -> None:
    backend = FakeSourceBackend(stale=failure == "stale")
    ref = backend.ref
    if failure == "manipulated_ref":
        ref = ref.model_copy(update={"fingerprint": "sha256:" + "b" * 64})
    observed = tmp_path / f"{failure}.json"
    executable = _fake_codex(
        tmp_path,
        _server_body([_read_request(ref)], answer=None, observed=observed),
    )

    answer = _run(executable, backend)

    assert answer.evidence_refs == []
    captured = json.loads(observed.read_text(encoding="utf-8"))
    response = captured["tool_responses"][0]["result"]
    assert response["success"] is False
    assert json.loads(response["contentItems"][0]["text"])["error"]["code"] in {
        "source_ref_invalid",
        "stale_source",
    }


def test_duplicate_dynamic_call_does_not_execute_handler_twice(tmp_path: Path) -> None:
    backend = FakeSourceBackend()
    observed = tmp_path / "duplicate.json"
    request = {
        "callId": "call-symbol",
        "tool": codex_dynamic_tool_name(SOURCE_FIND_SYMBOL),
        "arguments": {"query": "action_confirm", "max_results": 5},
    }
    executable = _fake_codex(
        tmp_path,
        _server_body(
            [request, request],
            answer=None,
            observed=observed,
            expect_abort=True,
        ),
    )

    with pytest.raises(CodexEngineError, match="tool_call_duplicate"):
        _run(executable, backend)

    assert [name for name, _ in backend.calls] == [SOURCE_FIND_SYMBOL]
    captured = json.loads(observed.read_text(encoding="utf-8"))
    assert captured["tool_responses"][0]["result"]["success"] is True
    assert captured["tool_responses"][1]["result"]["success"] is False


def test_dynamic_tools_require_experimental_capability_before_spawn(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "spawned"
    executable = _fake_codex(
        tmp_path,
        f"open({str(marker)!r}, 'w').write('spawned')",
    )
    backend = FakeSourceBackend()
    engine = CodexAppServerEngine(
        CodexRuntimeSettings(executable=executable, experimental_api=False),
        tool_executor_factory=_executor_factory(backend),
    )

    with pytest.raises(CodexEngineError, match="codex_experimental_api_required"):
        asyncio.run(
            engine.run_turn(
                _context(),
                list(source_tool_specs()),
                AnswerEnvelope.model_json_schema(),
            )
        )
    assert not marker.exists()


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            SOURCE_FIND_SYMBOL,
            {"query": "action_confirm", "max_results": 21},
        ),
        (
            SOURCE_FIND_MODEL_EXTENSIONS,
            {"model": "sale.order", "max_results": 51},
        ),
        (
            SOURCE_READ_EXCERPT,
            {
                "ref": FakeSourceBackend().ref.model_dump(mode="json"),
                "max_lines": 81,
                "max_bytes": 32_768,
            },
        ),
    ],
)
def test_source_input_caps_are_preserved_before_backend_call(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    backend = FakeSourceBackend()
    specs = source_tool_specs()
    limits = ToolExecutionLimits()
    executor = ToolExecutor(
        registry=build_source_tool_registry(backend, specs),
        ledger=EvidenceLedger(
            max_items=8,
            max_payload_bytes=limits.max_evidence_bytes,
        ),
        turn_limits=TurnLimits(max_tool_calls=8, max_evidence_items=8),
        limits=limits,
    )

    with pytest.raises(ToolExecutorError, match="tool_input_invalid"):
        asyncio.run(
            executor.execute(
                ToolCall(
                    call_id="call-over-cap",
                    tool_name=tool_name,
                    arguments=arguments,
                )
            )
        )
    assert backend.calls == []


def test_physical_path_from_backend_is_rejected_before_tool_result() -> None:
    backend = FakeSourceBackend(unsafe_path=True)
    limits = ToolExecutionLimits()
    ledger = EvidenceLedger(max_items=8, max_payload_bytes=limits.max_evidence_bytes)
    executor = ToolExecutor(
        registry=build_source_tool_registry(backend, source_tool_specs()),
        ledger=ledger,
        turn_limits=TurnLimits(max_tool_calls=8, max_evidence_items=8),
        limits=limits,
    )

    with pytest.raises(ToolExecutorError, match="tool_output_invalid"):
        asyncio.run(
            executor.execute(
                ToolCall(
                    call_id="call-unsafe-path",
                    tool_name=SOURCE_READ_EXCERPT,
                    arguments=_read_request(backend.ref)["arguments"],
                )
            )
        )

    assert ledger.evidence_ids == frozenset()
