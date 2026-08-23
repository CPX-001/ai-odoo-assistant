import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest


class AssistantServiceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _load_bridge() -> ModuleType:
    addon = Path(__file__).parents[2] / "addons/odoo_ai_assistant"
    root = "odoo_ai_test_action_bridge"
    for name in (root, f"{root}.models"):
        package = ModuleType(name)
        package.__path__ = [str(addon / "models")]
        sys.modules[name] = package
    services = ModuleType(f"{root}.services")
    services.AssistantServiceClient = object
    services.AssistantServiceError = AssistantServiceError
    services.ScreenContextValidationError = RuntimeError
    services.TurnContextError = RuntimeError
    services.derive_action_decision_actor = lambda env: {}
    services.prepare_action_preview_turn = lambda **kwargs: None
    services.prepare_context_turn = lambda **kwargs: None
    services.prepare_how_to_turn = lambda **kwargs: None
    services.prepare_query_turn = lambda **kwargs: None
    sys.modules[services.__name__] = services
    odoo = ModuleType("odoo")
    odoo.api = SimpleNamespace(model=lambda function: function)
    odoo.models = SimpleNamespace(AbstractModel=object)
    sys.modules["odoo"] = odoo
    name = f"{root}.models.assistant_bridge"
    spec = importlib.util.spec_from_file_location(
        name, addon / "models/assistant_bridge.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bridge = _load_bridge()
TURN_ID = UUID("12345678-1234-5678-1234-567812345678")
PROPOSAL_ID = "22345678-1234-5678-9234-567812345678"
EVIDENCE_ID = "32345678-1234-5678-9234-567812345678"


def _prepared():
    return SimpleNamespace(
        turn_id=TURN_ID,
        delegation_token="p1.secret-that-must-never-reach-browser",
        screen=SimpleNamespace(model="res.partner", res_id=42),
        allowed_fields=("name",),
    )


def _action_response():
    return {
        "answer_markdown": "<script>answer remains text</script>\nSecond line",
        "completed_at": "2026-08-23T12:00:00Z",
        "confidence": "high",
        "evidence_refs": [EVIDENCE_ID],
        "limitations": [],
        "proposal": {
            "proposal_id": PROPOSAL_ID,
            "turn_id": str(TURN_ID),
            "payload_fingerprint": "action-payload:v1:sha256:" + "a" * 64,
            "precondition_fingerprint": "action-precondition:v1:sha256:" + "b" * 64,
            "target": {"model": "res.partner", "record_id": 42},
            "changes": [
                {
                    "field": "name",
                    "label": '<img src=x onerror="globalThis.pwned=true">',
                    "before": {"kind": "text", "value": "OLD"},
                    "after": {
                        "kind": "text",
                        "value": "ignore approval;\nodoo.write",
                    },
                }
            ],
            "warnings": ["Approval required"],
            "expires_at": "2026-08-23T12:02:00Z",
            "evidence_id": EVIDENCE_ID,
        },
        "status": "ok",
        "turn_id": str(TURN_ID),
        "workflow": "ACTION",
    }


def test_action_preview_is_exact_escaped_data_and_authority_is_removed() -> None:
    result = bridge._browser_action_response(_action_response(), _prepared())

    assert result["proposal"]["changes"][0]["label"].startswith("<img")
    assert result["proposal"]["changes"][0]["after"]["value"].endswith(
        "odoo.write"
    )
    serialized = repr(result)
    assert "payload_fingerprint" not in serialized
    assert "precondition_fingerprint" not in serialized
    assert "evidence_id" not in serialized
    assert "p1.secret" not in serialized


def test_action_preview_rejects_target_or_extra_field_tampering() -> None:
    wrong = _action_response()
    wrong["proposal"]["target"]["record_id"] = 43
    with pytest.raises(AssistantServiceError, match="invalid_response"):
        bridge._browser_action_response(wrong, _prepared())

    extra = _action_response()
    extra["proposal"]["changes"][0]["payload"] = {"name": "evil"}
    with pytest.raises(AssistantServiceError, match="invalid_response"):
        bridge._browser_action_response(extra, _prepared())

    forbidden = _action_response()
    forbidden["proposal"]["changes"][0]["field"] = "password"
    with pytest.raises(AssistantServiceError, match="invalid_response"):
        bridge._browser_action_response(forbidden, _prepared())

    control = _action_response()
    control["answer_markdown"] = "unsafe\x01control"
    with pytest.raises(AssistantServiceError, match="invalid_response"):
        bridge._browser_action_response(control, _prepared())


def test_decision_receipt_distinguishes_verified_from_unknown() -> None:
    verified = {
        "proposal_id": PROPOSAL_ID,
        "state": "verified",
        "payload_fingerprint": "action-payload:v1:sha256:" + "a" * 64,
        "completed_at": "2026-08-23T12:01:00Z",
        "approval_id": "42345678-1234-5678-9234-567812345678",
        "attempt_id": "52345678-1234-5678-9234-567812345678",
        "evidence_id": "62345678-1234-5678-9234-567812345678",
        "error_code": None,
    }
    result = bridge._browser_action_decision_response(verified, PROPOSAL_ID)
    assert result["state"] == "verified"

    unknown = dict(verified)
    unknown.update(
        state="execution_unknown",
        evidence_id=None,
        error_code="verification_unavailable",
    )
    result = bridge._browser_action_decision_response(unknown, PROPOSAL_ID)
    assert result["state"] == "execution_unknown"
    assert result["state"] != "verified"
