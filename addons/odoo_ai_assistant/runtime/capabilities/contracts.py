"""Transport-neutral contracts for the addon-local capability framework."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
type CapabilityEventSink = Callable[[str, str, Mapping[str, JsonValue]], None]
type CapabilityHandler = Callable[["CapabilityContext", Mapping[str, JsonValue]], Any]
type CapabilityGuard = Callable[["CapabilityContext"], bool]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_VERSION_RE = re.compile(r"^[1-9][0-9]*$")
_SETTING_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class CapabilityError(RuntimeError):
    """Sanitized capability framework failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CapabilityRisk(StrEnum):
    """Host-declared risk; never inferred from model arguments."""

    METADATA = "metadata"
    READ = "read"
    WRITE_PREVIEW = "write-preview"
    WRITE = "write"
    ACTION_PREVIEW = "action-preview"
    ACTION = "action"
    HOST = "host"


class CapabilityEffect(StrEnum):
    """Effect class used by policy, approval, and audit layers."""

    READ_ONLY = "read-only"
    INTERNAL_REVERSIBLE = "internal-reversible"
    INTERNAL_IRREVERSIBLE = "internal-irreversible"
    EXTERNAL = "external"
    HOST = "host"


class CapabilityExposure(StrEnum):
    """Discovery is not authority: exposure only describes who may learn the capability."""

    REASONING = "reasoning"
    PLAN = "plan"
    HOST = "host"


class CapabilityApproval(StrEnum):
    """Human-approval contract independent from model visibility."""

    NONE = "none"
    POLICY = "policy"
    ALWAYS = "always"


class CapabilitySettingType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    STRING = "string"
    CHOICE = "choice"
    SECRET = "secret"


@dataclass(frozen=True, slots=True)
class CapabilityDependency:
    """Small dependency contract; versions are monotonically increasing integers."""

    name: str
    minimum_version: str = "1"

    def __post_init__(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise CapabilityError("capability_dependency_name_invalid")
        if not _VERSION_RE.fullmatch(self.minimum_version):
            raise CapabilityError("capability_dependency_version_invalid")


@dataclass(frozen=True, slots=True)
class CapabilitySetting:
    """Declarative setting rendered/stored by generic configuration adapters."""

    key: str
    title: str
    kind: CapabilitySettingType
    default: JsonValue = None
    help: str = ""
    required: bool = False
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self) -> None:
        if not _SETTING_KEY_RE.fullmatch(self.key) or not self.title.strip():
            raise CapabilityError("capability_setting_invalid")
        if self.kind is CapabilitySettingType.CHOICE and not self.choices:
            raise CapabilityError("capability_setting_choices_missing")
        if self.kind is not CapabilitySettingType.CHOICE and self.choices:
            raise CapabilityError("capability_setting_choices_invalid")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise CapabilityError("capability_setting_range_invalid")


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Bounded transport-neutral result returned by a capability handler."""

    data: Mapping[str, JsonValue]
    evidence: tuple[object, ...] = ()
    changes_preconditions: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityPreview:
    """Host-owned preview persisted before a plan capability may execute."""

    summary: Mapping[str, JsonValue]
    precondition_fingerprint: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.precondition_fingerprint, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.precondition_fingerprint) is None
        ):
            raise CapabilityError("capability_preview_fingerprint_invalid")


@dataclass(frozen=True, slots=True)
class CapabilityVerification:
    """Post-effect verification result produced by the capability provider."""

    verified: bool
    summary: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityContext:
    """Narrow per-turn host services handed to capability handlers.

    ``env`` is the effective non-sudo Odoo Environment. ``settings`` contains only the
    resolved settings for this capability/turn; providers do not need to know where
    configuration is persisted. ``metadata`` is bounded host-owned turn metadata.
    """

    env: Any
    turn_id: str
    conversation_id: str | None = None
    screen: Mapping[str, JsonValue] = field(default_factory=dict)
    settings: Mapping[str, JsonValue] = field(default_factory=dict)
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
    """Stable source of truth for one executable capability."""

    name: str
    description: str
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue]
    risk: CapabilityRisk
    effect: CapabilityEffect
    handler: CapabilityHandler = field(repr=False, compare=False)
    title: str = ""
    version: str = "1"
    exposure: CapabilityExposure = CapabilityExposure.REASONING
    approval: CapabilityApproval = CapabilityApproval.NONE
    tags: tuple[str, ...] = ()
    dependencies: tuple[CapabilityDependency, ...] = ()
    settings: tuple[CapabilitySetting, ...] = ()
    required_groups: tuple[str, ...] = ()
    default_enabled: bool = True
    timeout_seconds: int | None = None
    max_calls: int = 4
    max_input_bytes: int = 16 * 1024
    max_output_bytes: int = 96 * 1024
    help_text: str = ""
    audit_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    developer_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    preview_handler: CapabilityHandler | None = field(default=None, repr=False, compare=False)
    verify_handler: CapabilityHandler | None = field(default=None, repr=False, compare=False)
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
        if self.title and len(self.title) > 160:
            raise CapabilityError("capability_title_invalid")
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
        if self.risk in {CapabilityRisk.WRITE, CapabilityRisk.ACTION} and self.approval is CapabilityApproval.NONE:
            raise CapabilityError("capability_write_approval_invalid")
        if self.exposure is CapabilityExposure.REASONING and self.risk in {
            CapabilityRisk.WRITE,
            CapabilityRisk.ACTION,
            CapabilityRisk.HOST,
        }:
            raise CapabilityError("capability_reasoning_authority_invalid")
        if self.exposure is CapabilityExposure.HOST and self.approval is CapabilityApproval.ALWAYS:
            raise CapabilityError("capability_host_approval_invalid")
        if (
            self.exposure is CapabilityExposure.PLAN
            and self.effect is not CapabilityEffect.READ_ONLY
            and (self.preview_handler is None or self.verify_handler is None)
        ):
            raise CapabilityError("capability_plan_lifecycle_incomplete")
        if self.exposure is not CapabilityExposure.PLAN and (
            self.preview_handler is not None or self.verify_handler is not None
        ):
            raise CapabilityError("capability_plan_lifecycle_invalid")
        if self.timeout_seconds is not None and not 1 <= self.timeout_seconds <= 600:
            raise CapabilityError("capability_timeout_invalid")
        if not 1 <= self.max_calls <= 64:
            raise CapabilityError("capability_call_limit_invalid")
        if not 256 <= self.max_input_bytes <= 1024 * 1024:
            raise CapabilityError("capability_input_limit_invalid")
        if not 256 <= self.max_output_bytes <= 4 * 1024 * 1024:
            raise CapabilityError("capability_output_limit_invalid")
        if len(set(self.tags)) != len(self.tags):
            raise CapabilityError("capability_tag_duplicate")
        if len({item.name for item in self.dependencies}) != len(self.dependencies):
            raise CapabilityError("capability_dependency_duplicate")
        if len({item.key for item in self.settings}) != len(self.settings):
            raise CapabilityError("capability_setting_duplicate")
        if len(set(self.required_groups)) != len(self.required_groups):
            raise CapabilityError("capability_group_duplicate")

    @property
    def namespace(self) -> str:
        return self.name.rsplit(".", 1)[0]

    @property
    def executor_id(self) -> str:
        return f"{self.name}.v{self.version}"

    def available_for(self, context: CapabilityContext) -> bool:
        user = getattr(context.env, "user", None)
        if self.required_groups and (
            user is None or any(not user.has_group(group) for group in self.required_groups)
        ):
            return False
        return self.guard(context) if self.guard is not None else True

    def wire_descriptor(self) -> dict[str, JsonValue]:
        """Transport-neutral, MCP-shaped descriptor; adapters may further translate it."""

        return {
            "name": self.name,
            "title": self.title or self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "meta": {
                "namespace": self.namespace,
                "version": self.version,
                "executor_id": self.executor_id,
                "risk": self.risk.value,
                "effect": self.effect.value,
                "exposure": self.exposure.value,
                "approval": self.approval.value,
                "tags": list(self.tags),
            },
        }
