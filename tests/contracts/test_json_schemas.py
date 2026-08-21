import json

from odoo_ai.contracts import export_public_json_schemas

REQUIRED_M0_SCHEMAS = {
    "AnswerEnvelope",
    "ContextPack",
    "Evidence",
    "RecordRef",
    "ScreenContext",
    "ToolSpec",
}


def test_public_m0_json_schemas_are_complete_and_serializable() -> None:
    schemas = export_public_json_schemas()
    serialized = json.dumps(schemas, sort_keys=True)
    round_tripped = json.loads(serialized)

    assert REQUIRED_M0_SCHEMAS <= schemas.keys()
    assert list(schemas) == sorted(schemas)
    assert round_tripped.keys() == schemas.keys()

    for name, schema in round_tripped.items():
        assert schema["type"] == "object", name
        assert schema["title"] == name


def test_public_m0_json_schema_export_is_deterministic() -> None:
    first = json.dumps(export_public_json_schemas(), sort_keys=True)
    second = json.dumps(export_public_json_schemas(), sort_keys=True)

    assert first == second
