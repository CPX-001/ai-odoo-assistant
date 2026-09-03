"""Bounded Odoo configuration operations for the local privilege broker."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from .outcome import BrokerOperationError, OperationOutcome
from .policy import BrokerPolicy, ConfigTarget

_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECEIPT_RE = re.compile(r"^receipt:v1:[0-9a-f]{32,64}$")
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[#;].*)?$")
_OPTION_RE = re.compile(r"^(\s*)([A-Za-z][A-Za-z0-9_.-]*)(\s*=\s*)(.*?)(\r?\n)?$")
_SECRET_KEY_RE = re.compile(
    r"(?:^|[_.-])(?:admin_passwd|db_password|password|passwd|secret|token|api_key|private_key)(?:$|[_.-])",
    re.IGNORECASE,
)
_MAX_VALUE = 1024


class ConfigOperations:
    def __init__(self, policy: BrokerPolicy, backups_dir: str | Path) -> None:
        self.policy = policy
        self.backups_dir = Path(backups_dir)
        self.backups_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.backups_dir, 0o700)

    def inspect(self, payload: dict[str, Any]) -> OperationOutcome:
        target, key = self._target(payload, allowed_shapes=({"target", "key"},))
        data, _ = _read_file(target)
        value = _read_option(_decode(data), key)
        fingerprint = _fingerprint(data)
        return OperationOutcome(
            summary={
                "target": target.target_id,
                "key": key,
                "value": value,
                "fingerprint": fingerprint,
            },
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
        )

    def preview_patch(self, payload: dict[str, Any]) -> OperationOutcome:
        target, key = self._target(payload, allowed_shapes=({"target", "key", "value"},))
        value = _value(payload)
        data, _ = _read_file(target)
        current = _read_option(_decode(data), key)
        fingerprint = _fingerprint(data)
        return OperationOutcome(
            summary={
                "target": target.target_id,
                "key": key,
                "current_value": current,
                "new_value": value,
                "changed": current != value,
            },
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
        )

    def execute_patch(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
        expected_precondition: str | None,
    ) -> OperationOutcome:
        target, key = self._target(payload, allowed_shapes=({"target", "key", "value"},))
        value = _value(payload)
        if not isinstance(expected_precondition, str) or _FINGERPRINT_RE.fullmatch(expected_precondition) is None:
            raise BrokerOperationError("broker_precondition_required")
        data, original = _read_file(target)
        before = _fingerprint(data)
        if before != expected_precondition:
            raise BrokerOperationError(
                "broker_precondition_changed",
                status="stale",
                precondition_fingerprint=before,
            )
        new_data = _patch_option(_decode(data), key, value).encode("utf-8")
        if len(new_data) > target.max_bytes:
            raise BrokerOperationError("broker_config_too_large")
        changed = new_data != data
        recovery_token = None
        if changed:
            recovery_token = self._backup(request_id, data)
            _atomic_replace(target.path, new_data, original)
        after_data, _ = _read_file(target)
        after = _fingerprint(after_data)
        if _read_option(_decode(after_data), key) != value:
            raise BrokerOperationError(
                "broker_config_verify_failed",
                status="uncertain",
                effect_state="unknown",
                precondition_fingerprint=before,
                postcondition_fingerprint=after,
                recovery_classification=("backup_available" if recovery_token else "none"),
                recovery_token=recovery_token,
            )
        return OperationOutcome(
            effect_state="applied" if changed else "none",
            summary={"target": target.target_id, "key": key, "changed": changed, "value": value},
            precondition_fingerprint=before,
            postcondition_fingerprint=after,
            recovery_classification=("backup_available" if recovery_token else "none"),
            recovery_token=recovery_token,
        )

    def verify_patch(self, payload: dict[str, Any]) -> OperationOutcome:
        target, key = self._target(
            payload,
            allowed_shapes=({"target", "key", "value", "receipt_id", "postcondition_fingerprint"},),
        )
        value = _value(payload)
        receipt_id = payload.get("receipt_id")
        expected = payload.get("postcondition_fingerprint")
        if (
            not isinstance(receipt_id, str)
            or _RECEIPT_RE.fullmatch(receipt_id) is None
            or not isinstance(expected, str)
            or _FINGERPRINT_RE.fullmatch(expected) is None
        ):
            raise BrokerOperationError("broker_payload_invalid")
        data, _ = _read_file(target)
        fingerprint = _fingerprint(data)
        if _read_option(_decode(data), key) != value or fingerprint != expected:
            raise BrokerOperationError(
                "broker_config_verify_failed",
                status="error",
                effect_state="unknown",
                postcondition_fingerprint=fingerprint,
                recovery_classification="external_or_unknown",
            )
        return OperationOutcome(
            summary={"target": target.target_id, "key": key, "verified": True, "receipt_id": receipt_id},
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
        )

    def _target(self, payload: dict[str, Any], *, allowed_shapes) -> tuple[ConfigTarget, str]:
        if set(payload) not in allowed_shapes:
            raise BrokerOperationError("broker_payload_invalid")
        target_id, key = payload.get("target"), payload.get("key")
        if (
            not isinstance(target_id, str)
            or _TARGET_RE.fullmatch(target_id) is None
            or not isinstance(key, str)
            or _KEY_RE.fullmatch(key) is None
        ):
            raise BrokerOperationError("broker_payload_invalid")
        target = self.policy.config_targets.get(target_id)
        if target is None or key not in target.allowed_keys or _SECRET_KEY_RE.search(key):
            raise BrokerOperationError("broker_target_denied")
        return target, key

    def _backup(self, request_id: str, data: bytes) -> str:
        suffix = hashlib.sha256(request_id.encode("ascii")).hexdigest()[:32]
        path = self.backups_dir / f"{suffix}.bak"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(fd)
        return f"backup:v1:{suffix}"


def _value(payload: dict[str, Any]) -> str:
    value = payload.get("value")
    if (
        not isinstance(value, str)
        or len(value.encode("utf-8")) > _MAX_VALUE
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise BrokerOperationError("broker_payload_invalid")
    return value


def _read_file(target: ConfigTarget) -> tuple[bytes, os.stat_result]:
    try:
        fd = os.open(target.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise BrokerOperationError("broker_config_unavailable") from error
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size < 0 or st.st_size > target.max_bytes:
            raise BrokerOperationError("broker_config_invalid")
        data = bytearray()
        while len(data) <= target.max_bytes:
            chunk = os.read(fd, min(64 * 1024, target.max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > target.max_bytes:
            raise BrokerOperationError("broker_config_too_large")
        return bytes(data), st
    finally:
        os.close(fd)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BrokerOperationError("broker_config_encoding_invalid") from error


def _fingerprint(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _bounds(lines: list[str]) -> tuple[int, int]:
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        match = _SECTION_RE.match(line.rstrip("\r\n"))
        if not match:
            continue
        if start is None and match.group(1).strip().casefold() == "options":
            start = index + 1
        elif start is not None:
            end = index
            break
    if start is None:
        raise BrokerOperationError("broker_config_options_missing")
    return start, end


def _read_option(text: str, key: str) -> str | None:
    lines = text.splitlines(keepends=True)
    start, end = _bounds(lines)
    found = [m.group(4).strip() for line in lines[start:end] if (m := _OPTION_RE.match(line)) and m.group(2) == key]
    if len(found) > 1:
        raise BrokerOperationError("broker_config_key_duplicate")
    return found[0] if found else None


def _patch_option(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    start, end = _bounds(lines)
    matches = [(i, m) for i in range(start, end) if (m := _OPTION_RE.match(lines[i])) and m.group(2) == key]
    if len(matches) > 1:
        raise BrokerOperationError("broker_config_key_duplicate")
    if matches:
        index, match = matches[0]
        newline = match.group(5) or ("\n" if text.endswith("\n") else "")
        lines[index] = f"{match.group(1)}{key}{match.group(3)}{value}{newline}"
        return "".join(lines)
    newline = "\r\n" if "\r\n" in text else "\n"
    insertion = f"{key} = {value}{newline}"
    if end == len(lines):
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        lines.append(insertion)
    else:
        lines.insert(end, insertion)
    return "".join(lines)


def _atomic_replace(path: str, data: bytes, original: os.stat_result) -> None:
    parent = os.path.dirname(path) or "/"
    fd, temporary = tempfile.mkstemp(prefix=".odoo-ai-host-broker-", dir=parent)
    try:
        os.fchmod(fd, stat.S_IMODE(original.st_mode))
        os.fchown(fd, original.st_uid, original.st_gid)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    finally:
        if fd >= 0:
            os.close(fd)


__all__ = ["ConfigOperations"]
