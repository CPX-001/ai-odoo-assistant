"""Phase 10 typed broker-backed Technical host capabilities."""

from __future__ import annotations

from ...host_broker import HostBrokerClient
from ..contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityRisk,
    CapabilityVerification,
)
from ..decorators import tool

_TECHNICAL_GROUPS = ("base.group_system",)
_TARGET_SCHEMA = {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{0,63}$"}
_KEY_SCHEMA = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"}

_CONFIG_INSPECT_INPUT = {
    "type": "object",
    "properties": {"target": _TARGET_SCHEMA, "key": _KEY_SCHEMA},
    "required": ["target", "key"],
    "additionalProperties": False,
}
_CONFIG_INSPECT_OUTPUT = {
    "type": "object",
    "properties": {
        "target": {"type": "string"},
        "key": {"type": "string"},
        "value": {"type": ["string", "null"]},
        "fingerprint": {"type": "string"},
    },
    "required": ["target", "key", "value", "fingerprint"],
    "additionalProperties": False,
}
_CONFIG_PATCH_INPUT = {
    "type": "object",
    "properties": {
        "target": _TARGET_SCHEMA,
        "key": _KEY_SCHEMA,
        "value": {"type": "string", "maxLength": 1024},
    },
    "required": ["target", "key", "value"],
    "additionalProperties": False,
}
_CONFIG_PATCH_OUTPUT = {
    "type": "object",
    "properties": {
        "receipt_id": {"type": "string"},
        "target": {"type": "string"},
        "key": {"type": "string"},
        "changed": {"type": "boolean"},
        "value": {"type": "string"},
        "postcondition_fingerprint": {"type": "string"},
        "recovery_classification": {"type": "string"},
        "recovery_token": {"type": ["string", "null"]},
    },
    "required": [
        "receipt_id",
        "target",
        "key",
        "changed",
        "value",
        "postcondition_fingerprint",
        "recovery_classification",
        "recovery_token",
    ],
    "additionalProperties": False,
}
_SERVICE_INPUT = {
    "type": "object",
    "properties": {"target": _TARGET_SCHEMA},
    "required": ["target"],
    "additionalProperties": False,
}
_SERVICE_STATUS_OUTPUT = {
    "type": "object",
    "properties": {
        "target": {"type": "string"},
        "active_state": {"type": "string"},
        "sub_state": {"type": "string"},
        "unit_file_state": {"type": "string"},
        "exec_main_status": {"type": "string"},
        "active_enter_timestamp_monotonic": {"type": "string"},
        "fingerprint": {"type": "string"},
    },
    "required": [
        "target",
        "active_state",
        "sub_state",
        "unit_file_state",
        "exec_main_status",
        "active_enter_timestamp_monotonic",
        "fingerprint",
    ],
    "additionalProperties": False,
}
_SERVICE_RESTART_OUTPUT = {
    "type": "object",
    "properties": {
        "receipt_id": {"type": "string"},
        "target": {"type": "string"},
        "active_state": {"type": "string"},
        "sub_state": {"type": "string"},
        "postcondition_fingerprint": {"type": "string"},
        "recovery_classification": {"type": "string"},
    },
    "required": [
        "receipt_id",
        "target",
        "active_state",
        "sub_state",
        "postcondition_fingerprint",
        "recovery_classification",
    ],
    "additionalProperties": False,
}


def _broker_guard(_context: CapabilityContext) -> bool:
    try:
        return HostBrokerClient().available()
    except CapabilityError:
        return False


def _broker(timeout_seconds=5.0):
    return HostBrokerClient(timeout_seconds=timeout_seconds)


def _summary(receipt):
    summary = receipt.get("summary")
    if not isinstance(summary, dict):
        raise CapabilityError("host_broker_response_invalid")
    return summary


def _required_string(mapping, key, *, maximum=1024):
    value = mapping.get(key)
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > maximum:
        raise CapabilityError("host_broker_response_invalid")
    return value


def _optional_string(mapping, key, *, maximum=160):
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or "\x00" in value or len(value) > maximum:
        raise CapabilityError("host_broker_response_invalid")
    return value


def _required_bool(mapping, key):
    value = mapping.get(key)
    if type(value) is not bool:
        raise CapabilityError("host_broker_response_invalid")
    return value


def _required_receipt_id(receipt):
    return _required_string(receipt, "receipt_id", maximum=96)


def _recovery(receipt):
    recovery = receipt.get("recovery")
    if not isinstance(recovery, dict):
        raise CapabilityError("host_broker_response_invalid")
    classification = _required_string(recovery, "classification", maximum=64)
    if classification not in {"none", "backup_available", "external_or_unknown"}:
        raise CapabilityError("host_broker_response_invalid")
    token = _optional_string(recovery, "token", maximum=160)
    return classification, token


@tool(
    name="odoo.config.inspect",
    title="Inspect a managed Odoo configuration value",
    description=(
        "Read one deployment-approved Odoo configuration key through the local host broker. "
        "Input uses logical target/key identifiers only; arbitrary filesystem paths are not "
        "accepted. Technical users only."
    ),
    input_schema=_CONFIG_INSPECT_INPUT,
    output_schema=_CONFIG_INSPECT_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    guard=_broker_guard,
    tags=("odoo", "technical", "config", "host"),
    max_calls=8,
    timeout_seconds=8,
)
def config_inspect(context: CapabilityContext, arguments):
    receipt = _broker().call(
        context,
        capability="odoo.config.inspect",
        operation="odoo.config.inspect",
        phase="preview",
        payload=arguments,
    )
    return dict(_summary(receipt))


def _config_patch_preview(context: CapabilityContext, arguments):
    receipt = _broker().call(
        context,
        capability="odoo.config.patch",
        operation="odoo.config.patch",
        phase="preview",
        payload=arguments,
    )
    fingerprint = receipt.get("precondition_fingerprint")
    if not isinstance(fingerprint, str):
        raise CapabilityError("host_broker_response_invalid")
    return CapabilityPreview(
        summary={
            "operation": "config_patch",
            **dict(_summary(receipt)),
            "recovery": "backup_available_when_changed",
        },
        precondition_fingerprint=fingerprint,
    )


def _config_patch_verify(context: CapabilityContext, arguments):
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    receipt_id = result.get("receipt_id")
    postcondition = result.get("postcondition_fingerprint")
    receipt = _broker().call(
        context,
        capability="odoo.config.patch",
        operation="odoo.config.patch",
        phase="verify",
        payload={
            "target": arguments["target"],
            "key": arguments["key"],
            "value": arguments["value"],
            "receipt_id": receipt_id,
            "postcondition_fingerprint": postcondition,
        },
    )
    return CapabilityVerification(
        verified=_required_bool(_summary(receipt), "verified"),
        summary=dict(_summary(receipt)),
    )


@tool(
    name="odoo.config.patch",
    title="Patch a managed Odoo configuration value",
    description=(
        "Change one deployment-approved Odoo configuration key through the local broker. "
        "Technical users only. The broker resolves the path from root-owned policy, requires "
        "the exact preview fingerprint, writes atomically, keeps a private backup and verifies "
        "the result. Never use this for an arbitrary path or secret retrieval."
    ),
    input_schema=_CONFIG_PATCH_INPUT,
    output_schema=_CONFIG_PATCH_OUTPUT,
    risk=CapabilityRisk.HOST,
    effect=CapabilityEffect.HOST,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    required_groups=_TECHNICAL_GROUPS,
    guard=_broker_guard,
    preview=_config_patch_preview,
    verify=_config_patch_verify,
    tags=("odoo", "technical", "config", "host", "write"),
    audit_metadata={
        "recovery_mode": "external",
        "journal_classification": "external_or_unknown",
    },
    max_calls=2,
    timeout_seconds=15,
)
def config_patch(context: CapabilityContext, arguments):
    receipt = _broker(timeout_seconds=12).call(
        context,
        capability="odoo.config.patch",
        operation="odoo.config.patch",
        phase="execute",
        payload=arguments,
        effectful=True,
    )
    summary = _summary(receipt)
    postcondition = receipt.get("postcondition_fingerprint")
    if not isinstance(postcondition, str):
        raise CapabilityError("host_broker_response_invalid")
    recovery_classification, recovery_token = _recovery(receipt)
    return {
        "receipt_id": _required_receipt_id(receipt),
        "target": _required_string(summary, "target", maximum=64),
        "key": _required_string(summary, "key", maximum=64),
        "changed": _required_bool(summary, "changed"),
        "value": _required_string(summary, "value", maximum=1024),
        "postcondition_fingerprint": postcondition,
        "recovery_classification": recovery_classification,
        "recovery_token": recovery_token,
    }


@tool(
    name="host.service.status",
    title="Inspect a managed host service",
    description=(
        "Inspect one deployment-approved systemd service target through the local broker. "
        "Technical users only. The logical target is resolved by broker policy; arbitrary unit "
        "names or commands are not accepted."
    ),
    input_schema=_SERVICE_INPUT,
    output_schema=_SERVICE_STATUS_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    guard=_broker_guard,
    tags=("host", "technical", "service", "status"),
    max_calls=8,
    timeout_seconds=8,
)
def service_status(context: CapabilityContext, arguments):
    receipt = _broker().call(
        context,
        capability="host.service.status",
        operation="host.service.status",
        phase="preview",
        payload=arguments,
    )
    return dict(_summary(receipt))


def _service_restart_preview(context: CapabilityContext, arguments):
    receipt = _broker().call(
        context,
        capability="host.service.restart",
        operation="host.service.restart",
        phase="preview",
        payload=arguments,
    )
    fingerprint = receipt.get("precondition_fingerprint")
    if not isinstance(fingerprint, str):
        raise CapabilityError("host_broker_response_invalid")
    return CapabilityPreview(
        summary={
            "operation": "service_restart",
            **dict(_summary(receipt)),
            "verification": "post_restart_active_state",
        },
        precondition_fingerprint=fingerprint,
    )


def _service_restart_verify(context: CapabilityContext, arguments):
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    receipt = _broker().call(
        context,
        capability="host.service.restart",
        operation="host.service.restart",
        phase="verify",
        payload={
            "target": arguments["target"],
            "receipt_id": result.get("receipt_id"),
        },
    )
    return CapabilityVerification(
        verified=_required_bool(_summary(receipt), "verified"),
        summary=dict(_summary(receipt)),
    )


@tool(
    name="host.service.restart",
    title="Restart a managed host service",
    description=(
        "Restart exactly one deployment-approved systemd service target through the local "
        "privilege broker. Technical users only. Uses preview/precondition binding, fixed argv, "
        "policy-driven approval and post-restart health verification. It cannot run commands or "
        "restart arbitrary unit names."
    ),
    input_schema=_SERVICE_INPUT,
    output_schema=_SERVICE_RESTART_OUTPUT,
    risk=CapabilityRisk.HOST,
    effect=CapabilityEffect.HOST,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    required_groups=_TECHNICAL_GROUPS,
    guard=_broker_guard,
    preview=_service_restart_preview,
    verify=_service_restart_verify,
    tags=("host", "technical", "service", "restart"),
    audit_metadata={
        "recovery_mode": "external",
        "journal_classification": "external_or_unknown",
    },
    max_calls=2,
    timeout_seconds=90,
)
def service_restart(context: CapabilityContext, arguments):
    receipt = _broker(timeout_seconds=30).call(
        context,
        capability="host.service.restart",
        operation="host.service.restart",
        phase="execute",
        payload=arguments,
        effectful=True,
    )
    summary = _summary(receipt)
    postcondition = receipt.get("postcondition_fingerprint")
    if not isinstance(postcondition, str):
        raise CapabilityError("host_broker_response_invalid")
    return {
        "receipt_id": _required_receipt_id(receipt),
        "target": _required_string(summary, "target", maximum=64),
        "active_state": _required_string(summary, "active_state", maximum=64),
        "sub_state": _required_string(summary, "sub_state", maximum=64),
        "postcondition_fingerprint": postcondition,
        "recovery_classification": _recovery(receipt)[0],
    }


__all__ = ["config_inspect", "config_patch", "service_restart", "service_status"]
