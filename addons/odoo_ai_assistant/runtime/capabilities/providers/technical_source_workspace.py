"""Phase 12 Technical source-workspace and typed patch capabilities."""

from __future__ import annotations

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
from ...source_patch import (
    MAX_CHANGED_FILES,
    MAX_DIFF_BYTES,
    SourcePatchError,
    apply_installed_workspace_patch,
    inspect_installed_module_source,
    inspect_installed_patch_receipt,
    preview_installed_workspace_patch,
    read_installed_workspace_file,
)
from ...source_workspace import (
    SourceWorkspaceError,
    inspect_installed_module_workspace,
    prepare_installed_module_workspace,
)

_TECHNICAL_GROUPS = ("base.group_system",)
_WORKSPACE_ID = {"type": "string", "pattern": "^workspace:v1:[0-9a-f]{32}$"}
_FINGERPRINT = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_MODULE = {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,127}$"}
_PATH = {"type": "string", "minLength": 1, "maxLength": 512}
_EDIT = {
    "type": "object",
    "properties": {
        "old": {"type": "string", "minLength": 1, "maxLength": 65536},
        "new": {"type": "string", "maxLength": 524288},
    },
    "required": ["old", "new"],
    "additionalProperties": False,
}
_CHANGE = {
    "type": "object",
    "properties": {
        "path": _PATH,
        "action": {"type": "string", "enum": ["modify", "create", "delete"]},
        "edits": {"type": "array", "minItems": 1, "maxItems": 16, "items": _EDIT},
        "content": {"type": "string", "minLength": 1, "maxLength": 524288},
    },
    "required": ["path", "action"],
    "additionalProperties": False,
}
_CHANGES = {
    "type": "array",
    "minItems": 1,
    "maxItems": MAX_CHANGED_FILES,
    "items": _CHANGE,
}

_WORKSPACE_PUBLIC_PROPERTIES = {
    "workspace_id": _WORKSPACE_ID,
    "module": {"type": "string"},
    "source_id": {"type": "string"},
    "source_fingerprint": _FINGERPRINT,
    "baseline_workspace_fingerprint": _FINGERPRINT,
    "current_workspace_fingerprint": _FINGERPRINT,
    "file_count": {"type": "integer"},
    "total_bytes": {"type": "integer"},
    "source_stale": {"type": ["boolean", "null"]},
    "workspace_changed": {"type": "boolean"},
    "binding_fingerprint": _FINGERPRINT,
    "current_file_count": {"type": "integer"},
    "current_total_bytes": {"type": "integer"},
}
_WORKSPACE_PUBLIC_REQUIRED = list(_WORKSPACE_PUBLIC_PROPERTIES)
_WORKSPACE_OUTPUT = {
    "type": "object",
    "properties": _WORKSPACE_PUBLIC_PROPERTIES,
    "required": _WORKSPACE_PUBLIC_REQUIRED,
    "additionalProperties": False,
}
_PREPARE_INPUT = {
    "type": "object",
    "properties": {"module": _MODULE},
    "required": ["module"],
    "additionalProperties": False,
}
_INSPECT_INPUT = {
    "type": "object",
    "properties": {"workspace_id": _WORKSPACE_ID},
    "required": ["workspace_id"],
    "additionalProperties": False,
}
_READ_INPUT = {
    "type": "object",
    "properties": {
        "workspace_id": _WORKSPACE_ID,
        "logical_path": _PATH,
        "start_line": {"type": "integer", "minimum": 1, "default": 1},
        "max_lines": {"type": "integer", "minimum": 1, "maximum": 240, "default": 120},
    },
    "required": ["workspace_id", "logical_path"],
    "additionalProperties": False,
}
_READ_OUTPUT = {
    "type": "object",
    "properties": {
        "workspace_id": _WORKSPACE_ID,
        "module": {"type": "string"},
        "logical_path": {"type": "string"},
        "workspace_fingerprint": _FINGERPRINT,
        "file_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "line_start": {"type": "integer"},
        "line_end": {"type": "integer"},
        "text": {"type": "string"},
        "truncated": {"type": "boolean"},
        "source_stale": {"type": ["boolean", "null"]},
    },
    "required": [
        "workspace_id",
        "module",
        "logical_path",
        "workspace_fingerprint",
        "file_sha256",
        "line_start",
        "line_end",
        "text",
        "truncated",
        "source_stale",
    ],
    "additionalProperties": False,
}
_PATCH_INPUT = {
    "type": "object",
    "properties": {
        "workspace_id": _WORKSPACE_ID,
        "expected_workspace_fingerprint": _FINGERPRINT,
        "changes": _CHANGES,
    },
    "required": ["workspace_id", "expected_workspace_fingerprint", "changes"],
    "additionalProperties": False,
}
_CHANGED_FILE = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "action": {"type": "string"},
        "before_sha256": {"type": ["string", "null"]},
        "after_sha256": {"type": ["string", "null"]},
        "additions": {"type": "integer"},
        "deletions": {"type": "integer"},
    },
    "required": [
        "path",
        "action",
        "before_sha256",
        "after_sha256",
        "additions",
        "deletions",
    ],
    "additionalProperties": False,
}
_PATCH_PREVIEW_OUTPUT = {
    "type": "object",
    "properties": {
        "workspace_id": _WORKSPACE_ID,
        "module": {"type": "string"},
        "source_id": {"type": "string"},
        "source_fingerprint": _FINGERPRINT,
        "before_workspace_fingerprint": _FINGERPRINT,
        "after_workspace_fingerprint": _FINGERPRINT,
        "diff_fingerprint": _FINGERPRINT,
        "approval_fingerprint": _FINGERPRINT,
        "changed_files": {
            "type": "array",
            "maxItems": MAX_CHANGED_FILES,
            "items": _CHANGED_FILE,
        },
        "change_count": {"type": "integer"},
        "diff": {"type": "string", "maxLength": MAX_DIFF_BYTES},
        "source_stale": {"type": ["boolean", "null"]},
    },
    "required": [
        "workspace_id",
        "module",
        "source_id",
        "source_fingerprint",
        "before_workspace_fingerprint",
        "after_workspace_fingerprint",
        "diff_fingerprint",
        "approval_fingerprint",
        "changed_files",
        "change_count",
        "diff",
        "source_stale",
    ],
    "additionalProperties": False,
}
_PATCH_RECEIPT_OUTPUT = {
    "type": "object",
    "properties": {
        "workspace_id": _WORKSPACE_ID,
        "parent_workspace_id": _WORKSPACE_ID,
        "module": {"type": "string"},
        "source_id": {"type": "string"},
        "source_fingerprint": _FINGERPRINT,
        "before_workspace_fingerprint": _FINGERPRINT,
        "after_workspace_fingerprint": _FINGERPRINT,
        "diff_fingerprint": _FINGERPRINT,
        "approval_fingerprint": _FINGERPRINT,
        "binding_fingerprint": _FINGERPRINT,
        "changed_paths": {
            "type": "array",
            "maxItems": MAX_CHANGED_FILES,
            "items": {"type": "string"},
        },
        "change_count": {"type": "integer"},
        "source_stale": {"type": ["boolean", "null"]},
    },
    "required": [
        "workspace_id",
        "parent_workspace_id",
        "module",
        "source_id",
        "source_fingerprint",
        "before_workspace_fingerprint",
        "after_workspace_fingerprint",
        "diff_fingerprint",
        "approval_fingerprint",
        "binding_fingerprint",
        "changed_paths",
        "change_count",
        "source_stale",
    ],
    "additionalProperties": False,
}


def _raise_capability(error):
    code = getattr(error, "code", "source_patch_rejected")
    raise CapabilityError(code) from None


def _prepare_preview(context: CapabilityContext, arguments):
    try:
        source = inspect_installed_module_source(context, arguments.get("module"))
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)
    return CapabilityPreview(
        summary={"operation": "source_workspace_prepare", **source},
        precondition_fingerprint=source["source_fingerprint"],
    )


def _prepare_verify(context: CapabilityContext, arguments):
    del arguments
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    try:
        receipt = inspect_installed_module_workspace(context, result.get("workspace_id"))
    except (SourcePatchError, SourceWorkspaceError):
        return CapabilityVerification(verified=False, summary={})
    public = receipt.public_metadata()
    verified = bool(
        public["module"] == result.get("module")
        and public["source_fingerprint"] == result.get("source_fingerprint")
        and public["current_workspace_fingerprint"]
        == result.get("current_workspace_fingerprint")
        and public["source_stale"] is False
    )
    return CapabilityVerification(
        verified=verified,
        summary={
            "workspace_id": public["workspace_id"],
            "module": public["module"],
            "workspace_fingerprint": public["current_workspace_fingerprint"],
        },
    )


@tool(
    name="assistant.source_workspace.prepare",
    title="Prepare a private source workspace",
    description=(
        "Create a bounded private staging snapshot of one installed Odoo addon for Technical "
        "source work. The host resolves the installed module root; no filesystem path is accepted "
        "from the model. This does not edit installed source or deploy code."
    ),
    input_schema=_PREPARE_INPUT,
    output_schema=_WORKSPACE_OUTPUT,
    risk=CapabilityRisk.ACTION_PREVIEW,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.NONE,
    required_groups=_TECHNICAL_GROUPS,
    preview=_prepare_preview,
    verify=_prepare_verify,
    tags=("assistant", "technical", "source", "workspace", "staging"),
    audit_metadata={
        "recovery_mode": "segmented",
        "journal_classification": "reconstructable",
    },
    max_calls=4,
    timeout_seconds=30,
    max_input_bytes=4 * 1024,
    max_output_bytes=16 * 1024,
)
def prepare_workspace(context: CapabilityContext, arguments):
    try:
        return prepare_installed_module_workspace(
            context, arguments.get("module")
        ).public_metadata()
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)


@tool(
    name="assistant.source_workspace.inspect",
    title="Inspect a private source workspace",
    description=(
        "Inspect path-free source/workspace fingerprints and freshness for a workspace bound to "
        "the current Technical user/company/database/turn."
    ),
    input_schema=_INSPECT_INPUT,
    output_schema=_WORKSPACE_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    tags=("assistant", "technical", "source", "workspace", "inspect"),
    max_calls=12,
    timeout_seconds=15,
)
def inspect_workspace(context: CapabilityContext, arguments):
    try:
        return inspect_installed_module_workspace(
            context, arguments.get("workspace_id")
        ).public_metadata()
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)


@tool(
    name="assistant.source_workspace.read_file",
    title="Read a staged source file",
    description=(
        "Read a bounded UTF-8 excerpt from one logical path inside the bound private source "
        "workspace. Physical paths, binary files, secret-like names and path escape are denied."
    ),
    input_schema=_READ_INPUT,
    output_schema=_READ_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    tags=("assistant", "technical", "source", "workspace", "read"),
    max_calls=20,
    timeout_seconds=10,
    max_output_bytes=48 * 1024,
)
def read_workspace_file(context: CapabilityContext, arguments):
    try:
        return read_installed_workspace_file(
            context,
            workspace_id=arguments.get("workspace_id"),
            logical_path=arguments.get("logical_path"),
            start_line=arguments.get("start_line", 1),
            max_lines=arguments.get("max_lines", 120),
        )
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)


@tool(
    name="assistant.source_workspace.preview_patch",
    title="Preview a typed staged source patch",
    description=(
        "Validate bounded create/delete/exact-text-replacement edits against an exact workspace "
        "fingerprint and return the complete bounded unified diff plus before/after/diff "
        "fingerprints. This is preview-only and never mutates the workspace."
    ),
    input_schema=_PATCH_INPUT,
    output_schema=_PATCH_PREVIEW_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    tags=("assistant", "technical", "source", "workspace", "patch", "preview"),
    max_calls=12,
    timeout_seconds=20,
    max_input_bytes=512 * 1024,
    max_output_bytes=96 * 1024,
)
def preview_patch(context: CapabilityContext, arguments):
    try:
        return preview_installed_workspace_patch(
            context,
            workspace_id=arguments.get("workspace_id"),
            expected_workspace_fingerprint=arguments.get(
                "expected_workspace_fingerprint"
            ),
            changes=arguments.get("changes"),
        ).public_metadata()
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)


def _patch_preview(context: CapabilityContext, arguments):
    try:
        preview = preview_installed_workspace_patch(
            context,
            workspace_id=arguments.get("workspace_id"),
            expected_workspace_fingerprint=arguments.get(
                "expected_workspace_fingerprint"
            ),
            changes=arguments.get("changes"),
        )
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)
    return CapabilityPreview(
        summary={"operation": "source_workspace_apply_patch", **preview.public_metadata()},
        precondition_fingerprint=preview.approval_fingerprint,
    )


def _patch_verify(context: CapabilityContext, arguments):
    del arguments
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    try:
        receipt = inspect_installed_patch_receipt(
            context, result.get("workspace_id")
        )
    except (SourcePatchError, SourceWorkspaceError):
        return CapabilityVerification(verified=False, summary={})
    public = receipt.public_metadata()
    verified = bool(
        public["parent_workspace_id"] == result.get("parent_workspace_id")
        and public["before_workspace_fingerprint"]
        == result.get("before_workspace_fingerprint")
        and public["after_workspace_fingerprint"]
        == result.get("after_workspace_fingerprint")
        and public["diff_fingerprint"] == result.get("diff_fingerprint")
        and public["approval_fingerprint"] == result.get("approval_fingerprint")
        and public["source_stale"] is False
    )
    return CapabilityVerification(
        verified=verified,
        summary={
            "workspace_id": public["workspace_id"],
            "parent_workspace_id": public["parent_workspace_id"],
            "diff_fingerprint": public["diff_fingerprint"],
            "workspace_fingerprint": public["after_workspace_fingerprint"],
        },
    )


@tool(
    name="assistant.source_workspace.apply_patch",
    title="Apply an approved patch to a staged source workspace",
    description=(
        "Apply only the exact typed patch previewed for a bound private workspace. The host "
        "revalidates source freshness and the expected workspace fingerprint, then creates a new "
        "derived workspace and durable patch receipt while preserving the parent workspace as "
        "the rollback boundary. Installed/production source is never changed by this capability."
    ),
    input_schema=_PATCH_INPUT,
    output_schema=_PATCH_RECEIPT_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    required_groups=_TECHNICAL_GROUPS,
    preview=_patch_preview,
    verify=_patch_verify,
    tags=("assistant", "technical", "source", "workspace", "patch", "action"),
    audit_metadata={
        "recovery_mode": "segmented",
        "journal_classification": "reconstructable",
    },
    max_calls=4,
    timeout_seconds=30,
    max_input_bytes=512 * 1024,
    max_output_bytes=24 * 1024,
)
def apply_patch(context: CapabilityContext, arguments):
    try:
        return apply_installed_workspace_patch(
            context,
            workspace_id=arguments.get("workspace_id"),
            expected_workspace_fingerprint=arguments.get(
                "expected_workspace_fingerprint"
            ),
            changes=arguments.get("changes"),
        ).public_metadata()
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)


@tool(
    name="assistant.source_workspace.inspect_patch",
    title="Inspect a staged patch receipt",
    description=(
        "Inspect the durable path-free receipt for a derived source workspace, including parent, "
        "before/after workspace fingerprints and the approved diff fingerprint."
    ),
    input_schema=_INSPECT_INPUT,
    output_schema=_PATCH_RECEIPT_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    tags=("assistant", "technical", "source", "workspace", "patch", "receipt"),
    max_calls=12,
    timeout_seconds=10,
)
def inspect_patch(context: CapabilityContext, arguments):
    try:
        return inspect_installed_patch_receipt(
            context, arguments.get("workspace_id")
        ).public_metadata()
    except (SourcePatchError, SourceWorkspaceError) as error:
        _raise_capability(error)


__all__ = [
    "apply_patch",
    "inspect_patch",
    "inspect_workspace",
    "prepare_workspace",
    "preview_patch",
    "read_workspace_file",
]
