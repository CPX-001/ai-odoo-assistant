import ast
import importlib.util
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from odoo_ai.application.action_policy import action_payload_fingerprint
from odoo_ai.contracts import (
    ActionAuthorityClaims,
    ActionFieldChange,
    ActionProposalPayload,
    ActionTarget,
    ActionValue,
    ActionValueKind,
)
from odoo_ai.security import ActionAuthorityCodec as ServiceActionAuthorityCodec

ADDON = Path(__file__).parents[2] / "addons/odoo_ai_assistant"
NOW = 1_787_337_600
OBSERVED_AT = datetime.fromtimestamp(NOW + 10, UTC)
SECRET = b"addon-only-delegation-secret-" + b"s" * 48
TURN_ID = UUID("12345678-1234-5678-1234-567812345678")
PROPOSAL_ID = UUID("11111111-1111-4111-8111-111111111111")


class FakeOdooError(Exception):
    pass


class FakeOrmToolError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_action_tools() -> tuple[ModuleType, ModuleType, ModuleType]:
    root_name = "odoo_ai_test_action_addon"
    for package_name, package_path in (
        (root_name, ADDON),
        (f"{root_name}.security", ADDON / "security"),
        (f"{root_name}.services", ADDON / "services"),
    ):
        package = ModuleType(package_name)
        package.__path__ = [str(package_path)]
        sys.modules[package_name] = package

    odoo = ModuleType("odoo")
    odoo.api = ModuleType("odoo.api")
    exceptions = ModuleType("odoo.exceptions")
    exceptions.AccessError = FakeOdooError
    exceptions.MissingError = FakeOdooError
    exceptions.ValidationError = FakeOdooError
    modules = ModuleType("odoo.modules")
    registry = ModuleType("odoo.modules.registry")
    registry.Registry = object
    sys.modules.update(
        {
            "odoo": odoo,
            "odoo.exceptions": exceptions,
            "odoo.modules": modules,
            "odoo.modules.registry": registry,
        }
    )

    delegation = _load_module(
        f"{root_name}.security.delegation", ADDON / "security/delegation.py"
    )
    action_authority = _load_module(
        f"{root_name}.security.action_authority",
        ADDON / "security/action_authority.py",
    )
    security = sys.modules[f"{root_name}.security"]
    security.ActionPreviewDelegationCodec = delegation.ActionPreviewDelegationCodec
    security.ActionPreviewDelegationPayload = delegation.ActionPreviewDelegationPayload
    security.ActionAuthorityCodec = action_authority.ActionAuthorityCodec
    security.ActionAuthorityPayload = action_authority.ActionAuthorityPayload
    security.DelegationTokenError = delegation.DelegationTokenError

    orm_tools = ModuleType(f"{root_name}.services.orm_tools")
    orm_tools.MAX_METADATA_FIELDS = 64
    orm_tools.OrmToolError = FakeOrmToolError
    orm_tools.check_response_size = lambda payload: None
    orm_tools.iso_datetime = lambda value: (
        value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    )

    def collect_model_metadata(
        env: object,
        *,
        model: str,
        max_fields: int,
        observed_at: datetime,
        allowed_fields: frozenset[str],
    ) -> dict[str, object]:
        del max_fields, observed_at
        model_set = env[model]
        return {
            "fields": {
                name: model_set.descriptions[name] for name in sorted(allowed_fields)
            }
        }

    orm_tools.collect_model_metadata = collect_model_metadata
    sys.modules[orm_tools.__name__] = orm_tools
    action_tools = _load_module(
        f"{root_name}.services.action_tools", ADDON / "services/action_tools.py"
    )
    return delegation, action_authority, action_tools


delegation, action_authority, action_tools = _load_action_tools()


class FakeRecords:
    def __init__(self, model: "FakeModel", ids: list[int]) -> None:
        self.model = model
        self.ids = ids

    def check_access(self, operation: str) -> None:
        self.model.access_checks.append(operation)
        if self.model.deny_write and operation == "write":
            raise FakeOdooError

    def read(self, fields: list[str], load: object = None) -> list[dict[str, object]]:
        assert load is None
        self.model.read_fields.append(tuple(fields))
        return [
            {"id": self.ids[0], **{name: self.model.state[name] for name in fields}}
        ]

    def exists(self) -> "FakeRecords":
        return self

    def write(self, values: dict[str, object]) -> bool:
        self.model.write_calls.append(values)
        self.model.state.update(values)
        return True

    def __len__(self) -> int:
        return len(self.ids)


class FakeModel:
    def __init__(
        self,
        env: "FakeEnv",
        *,
        state: dict[str, object],
        descriptions: dict[str, dict[str, object]],
        deny_write: bool = False,
    ) -> None:
        self.env = env
        self.state = state
        self.descriptions = descriptions
        self.deny_write = deny_write
        self.access_checks: list[str] = []
        self.field_access_checks: list[tuple[str, tuple[str, ...]]] = []
        self.read_fields: list[tuple[str, ...]] = []
        self.write_calls: list[dict[str, object]] = []

    def browse(self, ids: list[int] | None = None) -> FakeRecords:
        return FakeRecords(self, ids or [])

    def check_field_access_rights(self, operation: str, fields: list[str]) -> None:
        self.field_access_checks.append((operation, tuple(fields)))


class FakeEnv:
    def __init__(self, value: str = "PO-42", *, deny_write: bool = False) -> None:
        self.models: dict[str, FakeModel] = {}
        self.models["sale.order"] = FakeModel(
            self,
            state={"client_order_ref": value},
            descriptions={
                "client_order_ref": {
                    "readonly": False,
                    "required": False,
                    "string": "Customer Reference",
                    "type": "char",
                }
            },
            deny_write=deny_write,
        )

    def __getitem__(self, model: str) -> FakeModel:
        return self.models[model]


def _claims(**overrides: object):
    values = {
        "format_version": 1,
        "jti": "preview_0123456789abcdefg",
        "turn_id": TURN_ID,
        "database": "customer-db",
        "uid": 17,
        "company_id": 3,
        "allowed_company_ids": (3, 5),
        "lang": "es_ES",
        "model": "sale.order",
        "record_id": 4832,
        "allowed_fields": ("client_order_ref",),
        "scopes": ("action_write_schema", "action_preview"),
        "issued_at": NOW,
        "expires_at": NOW + 60,
        "max_fields": 1,
        "policy_revision": "m6-record-patch-v1",
    }
    values.update(overrides)
    return delegation.ActionPreviewDelegationPayload(**values)


def _proposal(*, value: str = "PO-43", companies: tuple[int, ...] = (3, 5)):
    return ActionProposalPayload(
        proposal_id=PROPOSAL_ID,
        turn_id=TURN_ID,
        instance_id="odoo-production",
        database="customer-db",
        uid=17,
        company_id=3,
        allowed_company_ids=companies,
        target=ActionTarget(model="sale.order", record_id=4832),
        changes=(
            ActionFieldChange(
                field="client_order_ref",
                value=ActionValue(kind=ActionValueKind.TEXT, value=value),
            ),
        ),
        policy_revision="m6-record-patch-v1",
        schema_revision="action-schema:v1:sha256:" + "a" * 64,
    )


def _execute(env: FakeEnv, proposal: ActionProposalPayload):
    codec = delegation.ActionPreviewDelegationCodec(SECRET, clock=lambda: NOW)

    @contextmanager
    def environment_provider(claims: object):
        del claims
        yield env

    executor = action_tools.DelegatedActionPreviewToolExecutor(
        codec=codec,
        environment_provider=environment_provider,
        replay_guard=lambda claims, scope: None,
        observed_at=lambda: OBSERVED_AT,
    )
    return executor.preview_record_patch(
        delegation_token=codec.encode(_claims()),
        turn_id=str(TURN_ID),
        proposal=proposal.model_dump(mode="json"),
        payload_fingerprint=action_payload_fingerprint(proposal),
    )


def test_real_user_preview_returns_exact_diff_and_never_has_a_write_call() -> None:
    env = FakeEnv()
    result = _execute(env, _proposal(value="'; __import__('os')"))

    preview = result["preview"]
    change = preview["summary"]["changes"][0]
    assert change["before"] == {"kind": "text", "value": "PO-42"}
    assert change["after"] == {"kind": "text", "value": "'; __import__('os')"}
    assert env.models["sale.order"].read_fields == [("client_order_ref",)]
    assert "read" in env.models["sale.order"].access_checks
    assert "write" in env.models["sale.order"].access_checks

    tree = ast.parse((ADDON / "services/action_tools.py").read_text(encoding="utf-8"))
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write"
    ]
    assert len(writes) == 1


def test_state_change_changes_precondition_without_changing_payload() -> None:
    proposal = _proposal()
    first = _execute(FakeEnv("PO-41"), proposal)
    second = _execute(FakeEnv("PO-42"), proposal)

    assert (
        first["preview"]["precondition_fingerprint"]
        != second["preview"]["precondition_fingerprint"]
    )
    assert (
        first["preview"]["payload_fingerprint"]
        == second["preview"]["payload_fingerprint"]
    )


def test_write_access_and_company_authority_fail_closed() -> None:
    with pytest.raises(FakeOrmToolError, match="access_denied"):
        _execute(FakeEnv(deny_write=True), _proposal())

    with pytest.raises(FakeOrmToolError, match="scope_denied"):
        _execute(FakeEnv(), _proposal(companies=(3,)))


def test_tampered_fingerprint_is_rejected_before_record_read() -> None:
    env = FakeEnv()
    proposal = _proposal()
    codec = delegation.ActionPreviewDelegationCodec(SECRET, clock=lambda: NOW)

    @contextmanager
    def environment_provider(claims: object):
        del claims
        yield env

    executor = action_tools.DelegatedActionPreviewToolExecutor(
        codec=codec,
        environment_provider=environment_provider,
        replay_guard=lambda claims, scope: None,
        observed_at=lambda: OBSERVED_AT,
    )
    with pytest.raises(FakeOrmToolError, match="payload_fingerprint_mismatch"):
        executor.preview_record_patch(
            delegation_token=codec.encode(_claims()),
            turn_id=str(TURN_ID),
            proposal=proposal.model_dump(mode="json"),
            payload_fingerprint="action-payload:v1:sha256:" + "0" * 64,
        )

    assert env.models["sale.order"].read_fields == []


def _authority_token(
    proposal: ActionProposalPayload,
    precondition: str,
    *,
    scope: str,
    fingerprint: str | None = None,
) -> str:
    codec = ServiceActionAuthorityCodec(SECRET, clock=lambda: NOW)
    claims = ActionAuthorityClaims(
        jti=("commit_0123456789abcdefg" if scope == "action_commit" else "verify_0123456789abcdefg"),
        proposal_id=proposal.proposal_id,
        approval_id=UUID("44444444-4444-4444-8444-444444444444"),
        attempt_id=UUID("55555555-5555-4555-8555-555555555555"),
        instance_id=proposal.instance_id,
        database=proposal.database,
        uid=proposal.uid,
        company_id=proposal.company_id,
        allowed_company_ids=proposal.allowed_company_ids,
        model=proposal.target.model,
        record_id=proposal.target.record_id,
        fields=("client_order_ref",),
        payload_fingerprint=fingerprint or action_payload_fingerprint(proposal),
        precondition_fingerprint=precondition,
        policy_revision=proposal.policy_revision,
        schema_revision=proposal.schema_revision,
        scopes=(scope,),
        issued_at=NOW,
        expires_at=NOW + 60,
    )
    return codec.encode(claims)


def _approved_executor(env: FakeEnv):
    @contextmanager
    def environment_provider(claims: object):
        del claims
        yield env

    return action_tools.ApprovedActionToolExecutor(
        codec=action_authority.ActionAuthorityCodec(SECRET, clock=lambda: NOW),
        environment_provider=environment_provider,
        replay_guard=lambda claims, scope: None,
        observed_at=lambda: OBSERVED_AT,
    )


def test_a1_commit_performs_exactly_one_write_then_verify_rereads() -> None:
    env = FakeEnv()
    proposal = _proposal()
    preview = _execute(env, proposal)["preview"]
    executor = _approved_executor(env)

    committed = executor.commit_record_patch(
        authority_token=_authority_token(
            proposal, preview["precondition_fingerprint"], scope="action_commit"
        ),
        proposal=proposal.model_dump(mode="json"),
    )
    verified = executor.verify_record_patch(
        authority_token=_authority_token(
            proposal, preview["precondition_fingerprint"], scope="action_verify"
        ),
        proposal=proposal.model_dump(mode="json"),
    )

    assert committed["ok"] is True
    assert env.models["sale.order"].write_calls == [{"client_order_ref": "PO-43"}]
    assert verified["matches"] is True
    assert verified["after"] == {
        "client_order_ref": {"kind": "text", "value": "PO-43"}
    }


def test_a1_stale_or_wrong_token_family_never_writes() -> None:
    env = FakeEnv("PO-changed")
    proposal = _proposal()
    executor = _approved_executor(env)
    stale_precondition = "action-precondition:v1:sha256:" + "0" * 64

    with pytest.raises(FakeOrmToolError, match="stale_precondition"):
        executor.commit_record_patch(
            authority_token=_authority_token(
                proposal, stale_precondition, scope="action_commit"
            ),
            proposal=proposal.model_dump(mode="json"),
        )

    p1 = delegation.ActionPreviewDelegationCodec(SECRET, clock=lambda: NOW).encode(
        _claims()
    )
    with pytest.raises(FakeOrmToolError, match="delegation_rejected"):
        executor.commit_record_patch(
            authority_token=p1,
            proposal=proposal.model_dump(mode="json"),
        )

    assert env.models["sale.order"].write_calls == []


def test_a1_runtime_environment_does_not_require_preview_language(monkeypatch) -> None:
    proposal = _proposal()
    token = _authority_token(
        proposal,
        "action-precondition:v1:sha256:" + "0" * 64,
        scope="action_commit",
    )
    claims = action_authority.ActionAuthorityCodec(
        SECRET, clock=lambda: NOW
    ).decode(token)
    captured: dict[str, object] = {}

    class Cursor:
        dbname = proposal.database

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class RuntimeEnvironment:
        su = False

        def __init__(
            self,
            cursor: Cursor,
            uid: int,
            context: dict[str, object],
            *,
            su: bool,
        ) -> None:
            assert su is False
            self.cr = cursor
            self.company = type("Company", (), {"id": proposal.company_id})()
            self.companies = type(
                "Companies", (), {"ids": list(proposal.allowed_company_ids)}
            )()
            captured.update({"context": context, "uid": uid})

    class RuntimeRegistry:
        def cursor(self) -> Cursor:
            return Cursor()

    monkeypatch.setattr(action_tools, "Registry", lambda database: RuntimeRegistry())
    monkeypatch.setattr(action_tools.api, "Environment", RuntimeEnvironment, raising=False)

    with action_tools._runtime_action_environment(claims):
        pass

    assert captured == {
        "context": {"allowed_company_ids": list(proposal.allowed_company_ids)},
        "uid": proposal.uid,
    }
