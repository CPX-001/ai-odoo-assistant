from addons.odoo_ai_assistant.runtime.agent.turn_effect_boundary import (
    acquire_turn_effect_lock,
    turn_effect_lock_key,
)


class _Cursor:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((statement, params))


def test_turn_effect_lock_key_is_stable_signed_int64():
    turn_uuid = "00000000-0000-4000-8000-000000000111"
    first = turn_effect_lock_key(turn_uuid)
    second = turn_effect_lock_key(turn_uuid)
    other = turn_effect_lock_key("00000000-0000-4000-8000-000000000222")

    assert first == second
    assert first != other
    assert -(1 << 63) <= first < (1 << 63)


def test_acquire_turn_effect_lock_uses_transaction_scoped_postgres_lock():
    cursor = _Cursor()
    turn_uuid = "00000000-0000-4000-8000-000000000333"

    key = acquire_turn_effect_lock(cursor, turn_uuid)

    assert key == turn_effect_lock_key(turn_uuid)
    assert cursor.calls == [("SELECT pg_advisory_xact_lock(%s)", [key])]


def test_turn_effect_lock_rejects_invalid_binding():
    for value in (None, "", "x\x00y"):
        try:
            turn_effect_lock_key(value)
        except ValueError as error:
            assert str(error) == "turn_effect_lock_key_invalid"
        else:
            raise AssertionError("invalid lock binding was accepted")
