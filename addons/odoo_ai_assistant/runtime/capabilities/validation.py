"""Small dependency-free validator for capability JSON-schema contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .contracts import CapabilityError, JsonValue


def validate_payload(
    value: JsonValue,
    schema: Mapping[str, JsonValue],
    *,
    max_bytes: int,
    error_code: str,
) -> None:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CapabilityError(error_code) from None
    if len(encoded) > max_bytes:
        raise CapabilityError(f"{error_code}_too_large")
    _validate_node(value, schema, depth=0, error_code=error_code)


def _validate_node(
    value: JsonValue,
    schema: Mapping[str, JsonValue],
    *,
    depth: int,
    error_code: str,
) -> None:
    if depth > 16:
        raise CapabilityError(error_code)
    expected = schema.get("type")
    if isinstance(expected, str) and not _matches_type(value, expected):
        raise CapabilityError(error_code)
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise CapabilityError(error_code)

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise CapabilityError(error_code)
        if any(not isinstance(item, str) or item not in value for item in required):
            raise CapabilityError(error_code)
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            property_schema = properties.get(key)
            if property_schema is None:
                if additional is False:
                    raise CapabilityError(error_code)
                if isinstance(additional, dict):
                    _validate_node(
                        item,
                        additional,
                        depth=depth + 1,
                        error_code=error_code,
                    )
                continue
            if not isinstance(property_schema, dict):
                raise CapabilityError(error_code)
            _validate_node(
                item,
                property_schema,
                depth=depth + 1,
                error_code=error_code,
            )
        return

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise CapabilityError(error_code)
        if isinstance(maximum, int) and len(value) > maximum:
            raise CapabilityError(error_code)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for item in value:
                _validate_node(
                    item,
                    item_schema,
                    depth=depth + 1,
                    error_code=error_code,
                )
        return

    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            raise CapabilityError(error_code)
        if isinstance(maximum, int) and len(value) > maximum:
            raise CapabilityError(error_code)
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise CapabilityError(error_code)
        if isinstance(maximum, (int, float)) and value > maximum:
            raise CapabilityError(error_code)


def _matches_type(value: JsonValue, expected: str) -> bool:
    return {
        "null": value is None,
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in {int, float},
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(expected, False)
