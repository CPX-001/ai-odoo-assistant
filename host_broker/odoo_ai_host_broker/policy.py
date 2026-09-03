"""Deployment-owned logical-target policy for the local host broker."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import BrokerProtocolError

_MAX_POLICY_BYTES = 256 * 1024
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_UNIT_RE = re.compile(r"^[A-Za-z0-9_.@:-]{1,120}\.service$")
_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_DATABASE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@dataclass(frozen=True, slots=True)
class ConfigTarget:
    target_id: str
    path: str
    allowed_keys: tuple[str, ...]
    max_bytes: int = 256 * 1024


@dataclass(frozen=True, slots=True)
class ServiceTarget:
    target_id: str
    unit: str
    timeout_seconds: int = 60


@dataclass(frozen=True, slots=True)
class ModuleTarget:
    target_id: str
    module: str
    database: str
    odoo_python: str
    odoo_bin: str
    config_path: str
    addons_path: tuple[str, ...]
    run_as_uid: int
    run_as_gid: int
    timeout_seconds: int = 540


@dataclass(frozen=True, slots=True)
class BrokerPolicy:
    allowed_peer_uids: tuple[int, ...]
    config_targets: dict[str, ConfigTarget]
    service_targets: dict[str, ServiceTarget]
    module_targets: dict[str, ModuleTarget]
    systemctl_path: str = "/usr/bin/systemctl"
    systemd_run_path: str = "/usr/bin/systemd-run"
    socket_gid: int | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> BrokerPolicy:
        if not isinstance(value, dict):
            raise BrokerProtocolError("broker_policy_invalid")
        allowed = {
            "protocol_version",
            "allowed_peer_uids",
            "systemctl_path",
            "systemd_run_path",
            "socket_gid",
            "config_targets",
            "service_targets",
            "module_targets",
        }
        if not set(value) <= allowed or value.get("protocol_version") != 1:
            raise BrokerProtocolError("broker_policy_invalid")

        raw_uids = value.get("allowed_peer_uids")
        if (
            not isinstance(raw_uids, list)
            or not raw_uids
            or any(type(uid) is not int or uid < 0 for uid in raw_uids)
            or len(set(raw_uids)) != len(raw_uids)
        ):
            raise BrokerProtocolError("broker_policy_invalid")

        systemctl_path = value.get("systemctl_path", "/usr/bin/systemctl")
        if (
            not isinstance(systemctl_path, str)
            or not systemctl_path.startswith("/")
            or "\x00" in systemctl_path
            or len(systemctl_path) > 512
        ):
            raise BrokerProtocolError("broker_policy_invalid")

        systemd_run_path = value.get("systemd_run_path", "/usr/bin/systemd-run")
        if (
            not isinstance(systemd_run_path, str)
            or not systemd_run_path.startswith("/")
            or "\x00" in systemd_run_path
            or len(systemd_run_path) > 512
        ):
            raise BrokerProtocolError("broker_policy_invalid")

        socket_gid = value.get("socket_gid")
        if socket_gid is not None and (type(socket_gid) is not int or socket_gid < 0):
            raise BrokerProtocolError("broker_policy_invalid")

        config_targets = _config_targets(value.get("config_targets", {}))
        service_targets = _service_targets(value.get("service_targets", {}))
        module_targets = _module_targets(value.get("module_targets", {}))
        return cls(
            allowed_peer_uids=tuple(sorted(raw_uids)),
            config_targets=config_targets,
            service_targets=service_targets,
            module_targets=module_targets,
            systemctl_path=systemctl_path,
            systemd_run_path=systemd_run_path,
            socket_gid=socket_gid,
        )


def _config_targets(value: Any) -> dict[str, ConfigTarget]:
    if not isinstance(value, dict) or len(value) > 64:
        raise BrokerProtocolError("broker_policy_invalid")
    result: dict[str, ConfigTarget] = {}
    for target_id, raw in value.items():
        if (
            not isinstance(target_id, str)
            or _TARGET_RE.fullmatch(target_id) is None
            or not isinstance(raw, dict)
            or not set(raw) <= {"path", "allowed_keys", "max_bytes"}
        ):
            raise BrokerProtocolError("broker_policy_invalid")
        path = raw.get("path")
        keys = raw.get("allowed_keys")
        maximum = raw.get("max_bytes", 256 * 1024)
        if (
            not isinstance(path, str)
            or not os.path.isabs(path)
            or "\x00" in path
            or len(path) > 1024
            or not isinstance(keys, list)
            or not keys
            or len(keys) > 128
            or any(not isinstance(key, str) or _KEY_RE.fullmatch(key) is None for key in keys)
            or len(set(keys)) != len(keys)
            or type(maximum) is not int
            or not 1024 <= maximum <= 4 * 1024 * 1024
        ):
            raise BrokerProtocolError("broker_policy_invalid")
        result[target_id] = ConfigTarget(
            target_id=target_id,
            path=path,
            allowed_keys=tuple(keys),
            max_bytes=maximum,
        )
    return result


def _service_targets(value: Any) -> dict[str, ServiceTarget]:
    if not isinstance(value, dict) or len(value) > 64:
        raise BrokerProtocolError("broker_policy_invalid")
    result: dict[str, ServiceTarget] = {}
    for target_id, raw in value.items():
        if (
            not isinstance(target_id, str)
            or _TARGET_RE.fullmatch(target_id) is None
            or not isinstance(raw, dict)
            or not set(raw) <= {"unit", "timeout_seconds"}
        ):
            raise BrokerProtocolError("broker_policy_invalid")
        unit = raw.get("unit")
        timeout = raw.get("timeout_seconds", 60)
        if (
            not isinstance(unit, str)
            or _UNIT_RE.fullmatch(unit) is None
            or type(timeout) is not int
            or not 1 <= timeout <= 300
        ):
            raise BrokerProtocolError("broker_policy_invalid")
        result[target_id] = ServiceTarget(
            target_id=target_id,
            unit=unit,
            timeout_seconds=timeout,
        )
    return result


def _module_targets(value: Any) -> dict[str, ModuleTarget]:
    if not isinstance(value, dict) or len(value) > 32:
        raise BrokerProtocolError("broker_policy_invalid")
    result: dict[str, ModuleTarget] = {}
    allowed = {
        "module",
        "database",
        "odoo_python",
        "odoo_bin",
        "config_path",
        "addons_path",
        "run_as_uid",
        "run_as_gid",
        "timeout_seconds",
    }
    for target_id, raw in value.items():
        if (
            not isinstance(target_id, str)
            or _TARGET_RE.fullmatch(target_id) is None
            or not isinstance(raw, dict)
            or set(raw) != allowed
        ):
            raise BrokerProtocolError("broker_policy_invalid")
        module = raw.get("module")
        database = raw.get("database")
        odoo_python = raw.get("odoo_python")
        odoo_bin = raw.get("odoo_bin")
        config_path = raw.get("config_path")
        addons_path = raw.get("addons_path")
        run_as_uid = raw.get("run_as_uid")
        run_as_gid = raw.get("run_as_gid")
        timeout = raw.get("timeout_seconds")
        paths = (odoo_python, odoo_bin, config_path)
        if (
            not isinstance(module, str)
            or _MODULE_RE.fullmatch(module) is None
            or not isinstance(database, str)
            or _DATABASE_RE.fullmatch(database) is None
            or any(
                not isinstance(path, str)
                or not os.path.isabs(path)
                or "\x00" in path
                or len(path) > 1024
                for path in paths
            )
            or not isinstance(addons_path, list)
            or not 1 <= len(addons_path) <= 16
            or any(
                not isinstance(path, str)
                or not os.path.isabs(path)
                or "\x00" in path
                or len(path) > 1024
                for path in addons_path
            )
            or type(run_as_uid) is not int
            or run_as_uid <= 0
            or type(run_as_gid) is not int
            or run_as_gid <= 0
            or type(timeout) is not int
            or not 60 <= timeout <= 540
        ):
            raise BrokerProtocolError("broker_policy_invalid")
        result[target_id] = ModuleTarget(
            target_id=target_id,
            module=module,
            database=database,
            odoo_python=odoo_python,
            odoo_bin=odoo_bin,
            config_path=config_path,
            addons_path=tuple(addons_path),
            run_as_uid=run_as_uid,
            run_as_gid=run_as_gid,
            timeout_seconds=timeout,
        )
    return result


def load_policy(path: str | os.PathLike[str]) -> BrokerPolicy:
    candidate = Path(path)
    try:
        st = candidate.stat()
    except OSError as error:
        raise BrokerProtocolError("broker_policy_unavailable") from error
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid != os.geteuid()
        or st.st_mode & 0o022
        or st.st_size <= 0
        or st.st_size > _MAX_POLICY_BYTES
    ):
        raise BrokerProtocolError("broker_policy_unsafe")
    try:
        raw = candidate.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrokerProtocolError("broker_policy_invalid") from error
    policy = BrokerPolicy.from_mapping(value)
    _validate_executable(policy.systemctl_path)
    _validate_executable(policy.systemd_run_path)
    for target in policy.module_targets.values():
        _validate_target_executable(target.odoo_python, target.run_as_uid)
        _validate_target_executable(target.odoo_bin, target.run_as_uid)
        _validate_target_file(target.config_path, target.run_as_uid)
        for addon_path in target.addons_path:
            _validate_target_directory(addon_path, target.run_as_uid)
    return policy


def _validate_executable(path: str) -> None:
    try:
        st = os.stat(path)
    except OSError as error:
        raise BrokerProtocolError("broker_policy_unsafe") from error
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid != os.geteuid()
        or st.st_mode & 0o022
        or not st.st_mode & 0o111
    ):
        raise BrokerProtocolError("broker_policy_unsafe")


def _validate_target_executable(path: str, run_as_uid: int) -> None:
    try:
        st = os.stat(path)
    except OSError as error:
        raise BrokerProtocolError("broker_policy_unsafe") from error
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid not in {0, run_as_uid}
        or st.st_mode & 0o022
        or not st.st_mode & 0o111
    ):
        raise BrokerProtocolError("broker_policy_unsafe")


def _validate_target_file(path: str, run_as_uid: int) -> None:
    try:
        st = os.stat(path)
    except OSError as error:
        raise BrokerProtocolError("broker_policy_unsafe") from error
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid not in {0, run_as_uid}
        or st.st_mode & 0o022
    ):
        raise BrokerProtocolError("broker_policy_unsafe")


def _validate_target_directory(path: str, run_as_uid: int) -> None:
    try:
        st = os.stat(path)
    except OSError as error:
        raise BrokerProtocolError("broker_policy_unsafe") from error
    if (
        not stat.S_ISDIR(st.st_mode)
        or st.st_uid not in {0, run_as_uid}
        or st.st_mode & 0o022
    ):
        raise BrokerProtocolError("broker_policy_unsafe")


__all__ = [
    "BrokerPolicy",
    "ConfigTarget",
    "ModuleTarget",
    "ServiceTarget",
    "load_policy",
]
