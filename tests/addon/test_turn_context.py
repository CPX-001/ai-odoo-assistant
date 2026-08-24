import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from odoo_ai.contracts import ContextReadTurnRequest

NOW = 1_787_337_600
NOW_DATETIME = datetime.fromtimestamp(NOW, UTC)
SECRET = b"addon-only-delegation-secret-" + b"s" * 48
TURN_ID = UUID("12345678-1234-5678-1234-567812345678")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_addon_services() -> tuple[ModuleType, ModuleType, ModuleType]:
    addon = Path(__file__).parents[2] / "addons/odoo_ai_assistant"
    root_name = "odoo_ai_test_addon"
    for package_name, package_path in (
        (root_name, addon),
        (f"{root_name}.security", addon / "security"),
        (f"{root_name}.services", addon / "services"),
    ):
        package = ModuleType(package_name)
        package.__path__ = [str(package_path)]
        sys.modules[package_name] = package
    delegation = _load_module(
        f"{root_name}.security.delegation", addon / "security/delegation.py"
    )
    security_package = sys.modules[f"{root_name}.security"]
    security_package.DelegationCodec = delegation.DelegationCodec
    security_package.DelegationPayload = delegation.DelegationPayload
    security_package.DelegationTokenError = delegation.DelegationTokenError
    security_package.QueryDelegationCodec = delegation.QueryDelegationCodec
    security_package.QueryDelegationPayload = delegation.QueryDelegationPayload
    security_package.ActionPreviewDelegationCodec = delegation.ActionPreviewDelegationCodec
    security_package.ActionPreviewDelegationPayload = delegation.ActionPreviewDelegationPayload
    screen = _load_module(
        f"{root_name}.services.screen_context", addon / "services/screen_context.py"
    )
    turn = _load_module(
        f"{root_name}.services.turn_context", addon / "services/turn_context.py"
    )
    return delegation, screen, turn


delegation, screen_context, turn_context = _load_addon_services()


class FakeRecord:
    def __init__(self, record_id: int) -> None:
        self.id = record_id


class FakeRecords:
    def __init__(self, record_ids: list[int]) -> None:
        self.ids = record_ids


class FakeCursor:
    dbname = "customer-db"


class FakeEnv:
    uid = 17
    su = False
    company = FakeRecord(3)
    companies = FakeRecords([3, 5])
    lang = "es_ES"
    cr = FakeCursor()

    def __contains__(self, model: object) -> bool:
        return model == "sale.order"


class FakeModel:
    def browse(self):
        return self

    def check_access(self, operation: str) -> None:
        assert operation == "read"

    def fields_get(self, *, attributes: list[str]) -> dict[str, dict[str, object]]:
        assert attributes in (["type"], ["readonly", "type"])
        values = {
            "amount_total": {"type": "monetary"},
            "display_name": {"type": "char"},
            "id": {"type": "integer"},
            "message_ids": {"type": "one2many"},
        }
        if "readonly" in attributes:
            for description in values.values():
                description["readonly"] = False
        return values

    def check_field_access_rights(self, operation: str, fields: list[str]) -> None:
        assert operation == "write"
        assert len(fields) == 1


class QueryFakeEnv(FakeEnv):
    def __getitem__(self, model: str) -> FakeModel:
        assert model == "sale.order"
        return FakeModel()


def _screen(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "action_id": 42,
        "menu_id": 7,
        "view_type": "form",
        "model": "sale.order",
        "res_id": 4832,
        "selected_ids": [4832, 4833],
        "allowed_context_subset": {
            "active_id": 4832,
            "active_ids": [4832, 4833],
            "active_model": "sale.order",
        },
        "captured_at": NOW_DATETIME.isoformat(),
    }
    values.update(overrides)
    return values


def _codec():
    return delegation.DelegationCodec(SECRET, clock=lambda: NOW)


def _preparer():
    return turn_context.TurnContextPreparer(
        codec=_codec(),
        clock=lambda: NOW,
        turn_id_factory=lambda: TURN_ID,
        nonce_factory=lambda: "jti_0123456789abcdefghij",
    )


def _query_codec():
    return delegation.QueryDelegationCodec(SECRET, clock=lambda: NOW)


def _query_preparer():
    return turn_context.QueryTurnContextPreparer(
        codec=_query_codec(),
        clock=lambda: NOW,
        turn_id_factory=lambda: TURN_ID,
        nonce_factory=lambda: "jti_0123456789abcdefghij",
    )


def _how_to_preparer():
    return turn_context.HowToTurnContextPreparer(
        codec=_codec(),
        clock=lambda: NOW,
        turn_id_factory=lambda: TURN_ID,
        nonce_factory=lambda: "jti_0123456789abcdefghij",
    )


def _action_preview_codec():
    return delegation.ActionPreviewDelegationCodec(SECRET, clock=lambda: NOW)


def _action_preview_preparer():
    return turn_context.ActionPreviewTurnContextPreparer(
        codec=_action_preview_codec(),
        clock=lambda: NOW,
        turn_id_factory=lambda: TURN_ID,
        nonce_factory=lambda: "jti_0123456789abcdefghij",
    )


def test_server_env_identity_and_current_record_are_signed() -> None:
    prepared = _preparer().prepare(
        env=FakeEnv(), screen_payload=_screen(), message="¿Qué estado tiene?"
    )
    claims = _codec().decode(prepared.delegation_token)

    assert claims.uid == FakeEnv.uid
    assert claims.company_id == 3
    assert claims.allowed_company_ids == (3, 5)
    assert claims.lang == "es_ES"
    assert claims.turn_id == TURN_ID
    assert claims.database == "customer-db"
    assert claims.model == "sale.order"
    assert claims.record_ids == (4832,)
    assert claims.scopes == ("fields_get", "read_records")
    assert claims.expires_at - claims.issued_at == 60
    assert prepared.screen.selected_ids == (4832, 4833)

    transport = ContextReadTurnRequest.model_validate_json(
        json.dumps(prepared.to_assistant_payload())
    )
    assert transport.turn_id == TURN_ID
    assert transport.user.uid == 17
    assert transport.delegation_token.get_secret_value() == prepared.delegation_token


def test_query_authority_is_runtime_field_bounded_and_separate_from_m2() -> None:
    prepared = _query_preparer().prepare(
        env=QueryFakeEnv(), screen_payload=_screen(), message="Total por cliente"
    )
    claims = _query_codec().decode(prepared.delegation_token)

    assert claims.uid == 17
    assert claims.model == "sale.order"
    assert claims.allowed_fields == ("id", "amount_total", "display_name")
    assert claims.scopes == (
        "query_schema",
        "query_records",
        "aggregate_records",
    )
    assert claims.policy_revision == "m5-query-read-v1"
    assert claims.max_records == 50
    assert claims.max_fields == 3
    assert claims.expires_at - claims.issued_at == 120
    with pytest.raises(delegation.DelegationTokenError):
        _codec().decode(prepared.delegation_token)


def test_query_authority_keeps_common_runtime_fields_within_the_existing_cap() -> None:
    class BroadModel(FakeModel):
        def fields_get(self, *, attributes: list[str]) -> dict[str, dict[str, object]]:
            assert attributes == ["type"]
            values = {
                f"custom_field_{index:03d}": {"type": "char"}
                for index in range(80)
            }
            values.update(
                {
                    "id": {"type": "integer"},
                    "invoice_date": {"type": "date"},
                    "invoice_date_due": {"type": "date"},
                    "partner_id": {"type": "many2one"},
                }
            )
            return values

    class BroadEnv(QueryFakeEnv):
        def __getitem__(self, model: str) -> BroadModel:
            assert model == "sale.order"
            return BroadModel()

    fields = turn_context._visible_query_fields(BroadEnv(), "sale.order")

    assert len(fields) == 64
    assert {"id", "partner_id", "invoice_date", "invoice_date_due"} <= set(fields)
    assert fields == tuple(sorted(fields, key=lambda item: (item != "id", item)))


def test_action_preview_authority_is_record_bound_and_non_writing() -> None:
    prepared = _action_preview_preparer().prepare(
        env=QueryFakeEnv(), screen_payload=_screen(), message="Change reference"
    )
    claims = _action_preview_codec().decode(prepared.delegation_token)

    assert claims.uid == 17
    assert claims.company_id == 3
    assert claims.allowed_company_ids == (3, 5)
    assert claims.model == "sale.order"
    assert claims.record_id == 4832
    assert claims.allowed_fields == ("amount_total", "display_name")
    assert claims.scopes == ("action_write_schema", "action_preview")
    assert claims.policy_revision == "m6-record-patch-v1"
    assert claims.max_fields == 2
    assert claims.expires_at - claims.issued_at == 120
    assert prepared.to_browser_payload() == {"turn_id": str(TURN_ID)}
    assert prepared.delegation_token not in repr(prepared)
    with pytest.raises(delegation.DelegationTokenError):
        _codec().decode(prepared.delegation_token)
    with pytest.raises(delegation.DelegationTokenError):
        _query_codec().decode(prepared.delegation_token)


def test_action_decision_actor_is_derived_only_from_authenticated_env() -> None:
    actor = turn_context.derive_action_decision_actor(QueryFakeEnv())

    assert actor == {
        "database": "customer-db",
        "uid": 17,
        "company_id": 3,
        "allowed_company_ids": [3, 5],
    }


def test_query_turn_accepts_model_only_list_context() -> None:
    prepared = _query_preparer().prepare(
        env=QueryFakeEnv(),
        screen_payload=_screen(
            res_id=None,
            selected_ids=[],
            allowed_context_subset={"active_model": "sale.order"},
        ),
        message="Count orders",
    )

    assert prepared.screen.model == "sale.order"
    assert prepared.screen.res_id is None


def test_how_to_authority_contains_navigation_and_optional_schema_but_no_records() -> None:
    prepared = _how_to_preparer().prepare(
        env=FakeEnv(),
        screen_payload=_screen(
            res_id=None,
            selected_ids=[],
            allowed_context_subset={"active_model": "sale.order"},
        ),
        message="¿Cómo creo un pedido?",
    )
    claims = _codec().decode(prepared.delegation_token)

    assert claims.model == "sale.order"
    assert claims.record_ids == ()
    assert claims.max_records == 0
    assert claims.scopes == ("navigation", "fields_get")
    assert "read_records" not in claims.scopes


def test_how_to_can_prepare_navigation_only_context_without_a_model() -> None:
    prepared = _how_to_preparer().prepare(
        env=FakeEnv(),
        screen_payload=_screen(
            model=None,
            res_id=None,
            selected_ids=[],
            allowed_context_subset={},
        ),
        message="¿Dónde se configura la empresa?",
    )
    claims = _codec().decode(prepared.delegation_token)

    assert claims.model is None
    assert claims.record_ids == ()
    assert claims.scopes == ("navigation",)


def test_browser_identity_is_rejected_and_never_changes_the_delegation() -> None:
    for key, value in (
        ("uid", 1),
        ("company_id", 99),
        ("allowed_company_ids", [99]),
        ("lang", "xx_XX"),
    ):
        with pytest.raises(
            screen_context.ScreenContextValidationError,
            match="identity_not_allowed",
        ):
            _preparer().prepare(
                env=FakeEnv(),
                screen_payload=_screen(**{key: value}),
                message="question",
            )

    clean = _preparer().prepare(
        env=FakeEnv(), screen_payload=_screen(), message="question"
    )
    assert _codec().decode(clean.delegation_token).uid == 17


class UnauthorizedCompanyEnv(FakeEnv):
    @property
    def companies(self):
        raise RuntimeError("browser requested company 99")


def test_unauthorized_company_context_is_sanitized() -> None:
    with pytest.raises(turn_context.TurnContextError) as failure:
        _preparer().prepare(
            env=UnauthorizedCompanyEnv(),
            screen_payload=_screen(),
            message="question",
        )

    assert failure.value.code == "identity_unavailable"
    assert "99" not in str(failure.value)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"model": "bad model"}, "invalid_model"),
        ({"res_id": 0}, "invalid_record_id"),
        ({"res_id": 2_147_483_648}, "invalid_record_id"),
        ({"selected_ids": list(range(1, 10))}, "invalid_selected_ids"),
        ({"allowed_context_subset": {"uid": 1}}, "context_key_not_allowed"),
        (
            {"captured_at": datetime.fromtimestamp(NOW - 301, UTC).isoformat()},
            "screen_expired",
        ),
    ],
)
def test_screen_context_limits_are_enforced(
    overrides: dict[str, object], code: str
) -> None:
    with pytest.raises(screen_context.ScreenContextValidationError) as failure:
        _preparer().prepare(
            env=FakeEnv(),
            screen_payload=_screen(**overrides),
            message="question",
        )

    assert failure.value.code == code


def test_token_is_server_only_and_redacted_from_repr_and_browser_payload() -> None:
    prepared = _preparer().prepare(
        env=FakeEnv(), screen_payload=_screen(), message="question"
    )
    token = prepared.delegation_token

    assert token in prepared.to_assistant_payload().values()
    assert prepared.to_browser_payload() == {"turn_id": str(TURN_ID)}
    assert token not in repr(prepared)
    assert token not in repr(prepared.to_browser_payload())
    assert "gateway" not in prepared.to_browser_payload()


def test_configured_entrypoint_loads_only_the_addon_secret_file(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / "delegation-secret"
    secret_file.write_bytes(SECRET + b"\n")
    secret_file.chmod(0o640)

    prepared = turn_context.prepare_context_turn(
        env=FakeEnv(),
        screen_payload=_screen(),
        message="question",
        secret_file=str(secret_file),
        clock=lambda: NOW,
    )

    assert _codec().decode(prepared.delegation_token).uid == 17
