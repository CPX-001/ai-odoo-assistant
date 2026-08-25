"""Contracts for the addon-local capability framework."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeAlias

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
CapabilityEventSink: TypeAlias = Callable[[str, str, Mapping[str, JsonValue]], None]
CapabilityHandler: TypeAlias = Callable[
    ["CapabilityContext", Mapping[str, JsonValue]], Any
]
CapabilityGuard: TypeAlias = Callable[["CapabilityContext"], bool]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_VERSION_RE = re.compile(r"^[1-9][0-9]*$")


class CapabilityError(RuntimeError):
    """Sanitized capability framework failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CapabilityRisk(str, Enum):
    """Host-declared risk; never inferred from model arguments."""

    METADATA = "metadata"
    READ = "read"
    WRITE_PREVIEW = "write-preview"
    WRITE = "write"
    ACTION_PREVIEW = "action-preview"
    ACTION = "action"
    HOST = "host"


class CapabilityEffect(str, Enum):
    """Effect class used by policy, approval, and audit layers."""

    READ_ONLY = "read-only"
    INTERNAL_REVERSIBLE = "internal-reversible"
    INTERNAL_IRREVERSIBLE = "internal-irreversible"
    EXTERNAL = "external"
    HOST = "host"


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Bounded transport-neutral result returned by a capability handler."""

    data: Mapping[str, JsonValue]
    evidence: tuple[object, ...] = ()
    changes_preconditions: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityContext:
    """Per-turn host context handed to capability handlers.

    ``env`` is the effective Odoo Environment for the originating user. It is an
    object-capability: handlers can only do what the host intentionally gives them.
    A deliberately privileged capability may use lower-level Odoo facilities (for
    example ``env.cr``), but that choice is explicit in that capability's metadata and
    policy rather than hidden in the framework.
    """

    env: Any
    turn_id: str
    conversation_id: str | None = None
    screen: Mapping[str, JsonValue] = field(default_factory=dict)
    event_sink: CapabilityEventSink | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def emit(
        self,
        event_type: str,
        title: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> None:
        if self.event_sink is not None:
            self.event_sink(event_type, title, payload or {})


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Single source of truth for one model-callable capability."""

    name: str
    description: str
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue]
    risk: CapabilityRisk
    effect: CapabilityEffect
    handler: CapabilityHandler = field(repr=False, compare=False)
    version: str = "1"
    tags: tuple[str, ...] = ()
    required_groups: tuple[str, ...] = ()
    default_enabled: bool = True
    approval_required: bool = False
    max_calls: int = 4
    max_input_bytes: int = 16 * 1024
    max_output_bytes: int = 96 * 1024
    guard: CapabilityGuard | None = field(default=None, repr=False, compare=False)
    source_module: str = ""
    source_qualname: str = ""

    def __post_init__(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise CapabilityError("capability_name_invalid")
        if not _VERSION_RE.fullmatch(self.version):
            raise CapabilityError("capability_version_invalid")
        if not self.description.strip() or len(self.description) > 4_000:
            raise CapabilityError("capability_description_invalid")
        if self.input_schema.get("type") != "object":
            raise CapabilityError("capability_input_schema_invalid")
        if self.output_schema.get("type") != "object":
            raise CapabilityError("capability_output_schema_invalid")
        if self.effect is CapabilityEffect.READ_ONLY and self.risk in {
            CapabilityRisk.WRITE,
            CapabilityRisk.ACTION,
            CapabilityRisk.HOST,
        }:
            raise CapabilityError("capability_effect_risk_mismatch")
        if self.risk in {CapabilityRisk.WRITE, CapabilityRisk.ACTION} and not self.approval_required:
            raise CapabilityError("capability_write_requires_approval")
        if not 1 <= self.max_calls <= 64:
            raise CapabilityError("capability_call_limit_invalid")
        if not 256 <= self.max_input_bytes <= 1024 * 1024:
            raise CapabilityError("capability_input_limit_invalid")
        if not 256 <= self.max_output_bytes <= 4 * 1024 * 1024:
            raise CapabilityError("capability_output_limit_invalid")
        if len(set(self.tags)) != len(self.tags):
            raise CapabilityError("capability_tag_duplicate")
        if len(set(self.required_groups)) != len(self.required_groups):
            raise CapabilityError("capability_group_duplicate")

    @property
    def executor_id(self) -> str:
        return f"{self.name}.v{self.version}"

    def available_for(self, context: CapabilityContext) -> bool:
        if not self.default_enabled:
            enabled = context.metadata.get("enabled_capabilities", [])
            if not isinstance(enabled, list) or self.name not in enabled:
                return False
        user = getattr(context.env, "user", None)
        if self.required_groups:
            if user is None or any(
                not user.has_group(group) for group in self.required_groups
            ):
                return False
        return self.guard(context) if self.guard is not None else True

    def wire_descriptor(self) -> dict[str, JsonValue]:
        """Return the stable MCP-shaped description consumed by adapters."""

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "meta": {
                "executor_id": self.executor_id,
                "risk": self.risk.value,
                "effect": self.effect.value,
                "approval_required": self.approval_required,
                "tags": list(self.tags),
            },
        }
