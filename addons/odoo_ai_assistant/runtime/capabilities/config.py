"""Generic declarative settings resolution for capabilities."""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import CapabilityDefinition, CapabilityError, CapabilitySettingType, JsonValue

_CONFIG_PREFIX = "odoo_ai_assistant.capability."


class CapabilityConfigResolver:
    """Resolve defaults → namespace → capability → turn overrides."""

    def __init__(self, parameter_getter=None) -> None:
        self._get = parameter_getter

    @classmethod
    def from_env(cls, env):
        return cls(env["ir.config_parameter"]._get_param)

    def resolve(
        self,
        definition: CapabilityDefinition,
        *,
        turn_overrides: Mapping[str, JsonValue] | None = None,
    ) -> dict[str, JsonValue]:
        values = {setting.key: setting.default for setting in definition.settings}
        if self._get is not None:
            for setting in definition.settings:
                for namespace in _namespace_chain(definition.namespace):
                    raw = self._get(f"{_CONFIG_PREFIX}{namespace}.*.{setting.key}")
                    if raw not in (None, False, ""):
                        values[setting.key] = _decode(setting.kind, raw, setting.choices)
                raw = self._get(f"{_CONFIG_PREFIX}{definition.name}.{setting.key}")
                if raw not in (None, False, ""):
                    values[setting.key] = _decode(setting.kind, raw, setting.choices)
        for key, value in (turn_overrides or {}).items():
            if key in values:
                values[key] = value
        _validate_resolved(definition, values)
        return values

    @staticmethod
    def parameter_key(capability_name: str, setting_key: str) -> str:
        return f"{_CONFIG_PREFIX}{capability_name}.{setting_key}"


def _namespace_chain(namespace: str) -> tuple[str, ...]:
    parts = namespace.split(".")
    return tuple(".".join(parts[:index]) for index in range(1, len(parts) + 1))


def _decode(kind: CapabilitySettingType, raw: object, choices: tuple[str, ...]) -> JsonValue:
    value = str(raw)
    if kind is CapabilitySettingType.BOOLEAN:
        if value.lower() in {"1", "true", "yes", "on"}:
            return True
        if value.lower() in {"0", "false", "no", "off"}:
            return False
        raise CapabilityError("capability_setting_value_invalid")
    if kind is CapabilitySettingType.INTEGER:
        try:
            return int(value)
        except ValueError:
            raise CapabilityError("capability_setting_value_invalid") from None
    if kind is CapabilitySettingType.CHOICE and value not in choices:
        raise CapabilityError("capability_setting_value_invalid")
    return value


def _validate_resolved(definition: CapabilityDefinition, values: Mapping[str, JsonValue]) -> None:
    for setting in definition.settings:
        value = values.get(setting.key)
        if setting.required and value in (None, ""):
            raise CapabilityError("capability_configuration_missing")
        if setting.kind is CapabilitySettingType.INTEGER and isinstance(value, int) and not isinstance(value, bool):
            if setting.minimum is not None and value < setting.minimum:
                raise CapabilityError("capability_setting_value_invalid")
            if setting.maximum is not None and value > setting.maximum:
                raise CapabilityError("capability_setting_value_invalid")
