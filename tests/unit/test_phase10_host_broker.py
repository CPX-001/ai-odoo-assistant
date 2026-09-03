from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host_broker"))

from odoo_ai_host_broker.ledger import ExecutionLedger
from odoo_ai_host_broker.operations import BrokerEngine
from odoo_ai_host_broker.policy import BrokerPolicy
from odoo_ai_host_broker.protocol import canonical_sha256, replay_sha256


def _fingerprint(char="a"):
    return "sha256:" + char * 64


def _request(operation, phase, payload, *, request_id=None, precondition=None):
    now = int(time.time())
    return {
        "protocol_version": 1,
        "request_id": request_id or ("req:v1:" + "1" * 32),
        "operation": operation,
        "phase": phase,
        "issued_at": now - 1,
        "expires_at": now + 60,
        "binding": {
            "turn_id": "turn-test-0001",
            "conversation_id": "conversation-test-0001",
            "odoo_uid": 7,
            "database_fingerprint": _fingerprint("d"),
            "capability": operation,
            "step_id": "step-1" if phase == "execute" else None,
            "args_sha256": canonical_sha256(payload),
            "binding_fingerprint": _fingerprint("b") if phase == "execute" else None,
            "precondition_fingerprint": precondition,
        },
        "payload": payload,
    }


class FakeSystemctl:
    def __init__(self):
        self.restart_calls = 0
        self.timestamp = 100

    def __call__(self, argv, *, timeout):
        if argv[1] == "show":
            stdout = (
                "ActiveState=active\n"
                "SubState=running\n"
                "UnitFileState=enabled\n"
                "ExecMainStatus=0\n"
                f"ActiveEnterTimestampMonotonic={self.timestamp}\n"
            )
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")
        if argv[1] == "restart":
            self.restart_calls += 1
            self.timestamp += 100
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(argv)


class Phase10BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = root / "odoo.conf"
        self.config.write_text(
            "[options]\nworkers = 2\nadmin_passwd = secret-value\n",
            encoding="utf-8",
        )
        self.runner = FakeSystemctl()
        self.policy = BrokerPolicy.from_mapping(
            {
                "protocol_version": 1,
                "allowed_peer_uids": [1000],
                "systemctl_path": "/usr/bin/systemctl",
                "config_targets": {
                    "odoo": {
                        "path": str(self.config),
                        "allowed_keys": ["workers"],
                        "max_bytes": 65536,
                    }
                },
                "service_targets": {
                    "demo": {"unit": "odoo-ai-demo.service", "timeout_seconds": 10}
                },
            }
        )
        self.ledger = ExecutionLedger(root / "ledger.sqlite3")
        self.engine = BrokerEngine(
            policy=self.policy,
            ledger=self.ledger,
            backups_dir=root / "backups",
            runner=self.runner,
        )

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def test_peer_uid_denied(self):
        receipt = self.engine.handle(
            peer_uid=2000,
            request=_request("broker.status", "preview", {}, request_id="req:v1:" + "2" * 32),
        )
        self.assertEqual(receipt["status"], "denied")
        self.assertEqual(receipt["error_code"], "broker_peer_denied")

    def test_config_patch_is_precondition_bound_and_replay_safe(self):
        preview = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.patch",
                "preview",
                {"target": "odoo", "key": "workers", "value": "4"},
                request_id="req:v1:" + "3" * 32,
            ),
        )
        self.assertEqual(preview["summary"]["current_value"], "2")
        precondition = preview["precondition_fingerprint"]
        execute_request = _request(
            "odoo.config.patch",
            "execute",
            {"target": "odoo", "key": "workers", "value": "4"},
            request_id="req:v1:" + "4" * 32,
            precondition=precondition,
        )
        first = self.engine.handle(peer_uid=1000, request=execute_request)
        second = self.engine.handle(peer_uid=1000, request=execute_request)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["recovery"]["classification"], "backup_available")
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("workers = 4", text)
        self.assertIn("admin_passwd = secret-value", text)
        self.assertEqual(len(list((Path(self.temp.name) / "backups").glob("*.bak"))), 1)

    def test_replay_accepts_refreshed_transport_lifetime(self):
        preview = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.patch",
                "preview",
                {"target": "odoo", "key": "workers", "value": "4"},
                request_id="req:v1:" + "2" * 32,
            ),
        )
        execute_request = _request(
            "odoo.config.patch",
            "execute",
            {"target": "odoo", "key": "workers", "value": "4"},
            request_id="req:v1:" + "3" * 32,
            precondition=preview["precondition_fingerprint"],
        )
        first = self.engine.handle(peer_uid=1000, request=execute_request)

        refreshed = {
            **execute_request,
            "issued_at": execute_request["issued_at"] + 1,
            "expires_at": execute_request["expires_at"] + 1,
        }
        second = self.engine.handle(peer_uid=1000, request=refreshed)

        self.assertEqual(first, second)
        self.assertEqual(len(list((Path(self.temp.name) / "backups").glob("*.bak"))), 1)

    def test_config_patch_rejects_stale_precondition(self):
        preview = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.patch",
                "preview",
                {"target": "odoo", "key": "workers", "value": "4"},
                request_id="req:v1:" + "5" * 32,
            ),
        )
        self.config.write_text(
            "[options]\nworkers = 9\nadmin_passwd = secret-value\n",
            encoding="utf-8",
        )
        receipt = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.patch",
                "execute",
                {"target": "odoo", "key": "workers", "value": "4"},
                request_id="req:v1:" + "6" * 32,
                precondition=preview["precondition_fingerprint"],
            ),
        )
        self.assertEqual(receipt["status"], "stale")
        self.assertEqual(receipt["error_code"], "broker_precondition_changed")
        self.assertIn("workers = 9", self.config.read_text(encoding="utf-8"))

    def test_config_target_and_key_are_not_model_paths(self):
        receipt = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.inspect",
                "preview",
                {"target": "/etc/shadow", "key": "workers"},
                request_id="req:v1:" + "7" * 32,
            ),
        )
        self.assertEqual(receipt["status"], "denied")
        receipt = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.inspect",
                "preview",
                {"target": "odoo", "key": "admin_passwd"},
                request_id="req:v1:" + "8" * 32,
            ),
        )
        self.assertEqual(receipt["status"], "denied")
        self.assertEqual(receipt["error_code"], "broker_target_denied")

    def test_secret_like_config_key_is_denied_even_if_policy_allowlists_it(self):
        secret_policy = BrokerPolicy.from_mapping(
            {
                "protocol_version": 1,
                "allowed_peer_uids": [1000],
                "config_targets": {
                    "odoo": {
                        "path": str(self.config),
                        "allowed_keys": ["admin_passwd"],
                        "max_bytes": 65536,
                    }
                },
                "service_targets": {},
            }
        )
        secret_engine = BrokerEngine(
            policy=secret_policy,
            ledger=ExecutionLedger(":memory:"),
            backups_dir=Path(self.temp.name) / "secret-backups",
            runner=self.runner,
        )
        try:
            receipt = secret_engine.handle(
                peer_uid=1000,
                request=_request(
                    "odoo.config.inspect",
                    "preview",
                    {"target": "odoo", "key": "admin_passwd"},
                    request_id="req:v1:" + "0" * 32,
                ),
            )
        finally:
            secret_engine.ledger.close()
        self.assertEqual(receipt["status"], "denied")
        self.assertEqual(receipt["error_code"], "broker_target_denied")

    def test_service_restart_uses_fixed_unit_and_replays_once(self):
        preview = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "host.service.restart",
                "preview",
                {"target": "demo"},
                request_id="req:v1:" + "9" * 32,
            ),
        )
        execute = _request(
            "host.service.restart",
            "execute",
            {"target": "demo"},
            request_id="req:v1:" + "a" * 32,
            precondition=preview["precondition_fingerprint"],
        )
        first = self.engine.handle(peer_uid=1000, request=execute)
        second = self.engine.handle(peer_uid=1000, request=execute)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(self.runner.restart_calls, 1)

        denied = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "host.service.status",
                "preview",
                {"target": "demo.service;rm-rf"},
                request_id="req:v1:" + "b" * 32,
            ),
        )
        self.assertEqual(denied["status"], "denied")

    def test_known_running_request_is_uncertain_and_not_replayed(self):
        preview = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "host.service.restart",
                "preview",
                {"target": "demo"},
                request_id="req:v1:" + "c" * 32,
            ),
        )
        request = _request(
            "host.service.restart",
            "execute",
            {"target": "demo"},
            request_id="req:v1:" + "d" * 32,
            precondition=preview["precondition_fingerprint"],
        )
        state, _ = self.ledger.begin(
            request_id=request["request_id"],
            request_hash=replay_sha256(request),
            operation=request["operation"],
            started_at=int(time.time()),
        )
        self.assertEqual(state, "new")
        receipt = self.engine.handle(peer_uid=1000, request=request)
        self.assertEqual(receipt["status"], "uncertain")
        self.assertEqual(receipt["effect_state"], "unknown")
        self.assertEqual(self.runner.restart_calls, 0)

    def test_reused_request_id_with_changed_payload_is_denied(self):
        preview = self.engine.handle(
            peer_uid=1000,
            request=_request(
                "odoo.config.patch",
                "preview",
                {"target": "odoo", "key": "workers", "value": "4"},
                request_id="req:v1:" + "e" * 32,
            ),
        )
        first_request = _request(
            "odoo.config.patch",
            "execute",
            {"target": "odoo", "key": "workers", "value": "4"},
            request_id="req:v1:" + "f" * 32,
            precondition=preview["precondition_fingerprint"],
        )
        first = self.engine.handle(peer_uid=1000, request=first_request)
        self.assertEqual(first["status"], "ok")

        changed = _request(
            "odoo.config.patch",
            "execute",
            {"target": "odoo", "key": "workers", "value": "6"},
            request_id="req:v1:" + "f" * 32,
            precondition=preview["precondition_fingerprint"],
        )
        conflict = self.engine.handle(peer_uid=1000, request=changed)
        self.assertEqual(conflict["status"], "denied")
        self.assertEqual(conflict["error_code"], "broker_request_replay_mismatch")

    def test_binding_hash_and_operation_must_match_payload(self):
        request = _request(
            "odoo.config.inspect",
            "preview",
            {"target": "odoo", "key": "workers"},
            request_id="req:v1:" + "9" * 32,
        )
        request["binding"]["args_sha256"] = _fingerprint("f")
        receipt = self.engine.handle(peer_uid=1000, request=request)
        self.assertEqual(receipt["status"], "denied")
        self.assertEqual(receipt["error_code"], "broker_binding_invalid")

        request = _request(
            "odoo.config.inspect",
            "preview",
            {"target": "odoo", "key": "workers"},
            request_id="req:v1:" + "8" * 32,
        )
        request["binding"]["capability"] = "host.service.status"
        receipt = self.engine.handle(peer_uid=1000, request=request)
        self.assertEqual(receipt["status"], "denied")
        self.assertEqual(receipt["error_code"], "broker_binding_invalid")

    def test_execute_requires_exact_effect_binding(self):
        request = _request(
            "host.service.restart",
            "execute",
            {"target": "odoo_test"},
            request_id="req:v1:" + "7" * 32,
            precondition=_fingerprint("c"),
        )
        request["binding"]["binding_fingerprint"] = None
        receipt = self.engine.handle(peer_uid=1000, request=request)
        self.assertEqual(receipt["status"], "denied")
        self.assertEqual(receipt["error_code"], "broker_binding_invalid")


if __name__ == "__main__":
    unittest.main()
