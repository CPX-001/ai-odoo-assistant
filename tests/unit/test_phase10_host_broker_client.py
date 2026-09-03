from __future__ import annotations

import importlib
import struct
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ADDON_ROOT = Path(__file__).resolve().parents[2] / "addons/odoo_ai_assistant"
for package_name, package_path in (
    ("addons.odoo_ai_assistant", ADDON_ROOT),
    ("addons.odoo_ai_assistant.runtime", ADDON_ROOT / "runtime"),
    (
        "addons.odoo_ai_assistant.runtime.capabilities",
        ADDON_ROOT / "runtime/capabilities",
    ),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules.setdefault(package_name, package)

contracts = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.contracts"
)
client_module = importlib.import_module("addons.odoo_ai_assistant.runtime.host_broker")

CapabilityContext = contracts.CapabilityContext
CapabilityError = contracts.CapabilityError
HostBrokerClient = client_module.HostBrokerClient


def _fingerprint(char: str) -> str:
    return "sha256:" + char * 64


def _context(*, effectful: bool) -> CapabilityContext:
    metadata = {}
    if effectful:
        metadata = {
            "capability_plan_step_id": "step-1",
            "capability_plan_binding_fingerprint": _fingerprint("b"),
            "capability_precondition_fingerprint": _fingerprint("c"),
        }
    return CapabilityContext(
        env=SimpleNamespace(
            uid=7,
            cr=SimpleNamespace(dbname="phase10_transport_test"),
        ),
        turn_id="turn-test-0001",
        conversation_id="conversation-test-0001",
        metadata=metadata,
    )


class _FakeConnection:
    def __init__(
        self,
        *,
        peer_uid: int = 0,
        send_error: BaseException | None = None,
        response: bytes = b"",
    ) -> None:
        self.peer_uid = peer_uid
        self.send_error = send_error
        self.response = response
        self.sent = False
        self.closed = False
        self._response_read = False

    def settimeout(self, _timeout) -> None:
        return None

    def connect(self, _path) -> None:
        return None

    def getsockopt(self, _level, _option, _size):
        return struct.pack("3i", 1234, self.peer_uid, 1234)

    def sendall(self, _payload) -> None:
        self.sent = True
        if self.send_error is not None:
            raise self.send_error

    def recv(self, _maximum) -> bytes:
        if self._response_read:
            return b""
        self._response_read = True
        return self.response

    def close(self) -> None:
        self.closed = True


class _InvalidReceiptClient(HostBrokerClient):
    def _exchange(self, raw_request: bytes, *, effectful: bool = False):
        del raw_request, effectful
        return {}


class Phase10HostBrokerClientTests(unittest.TestCase):
    def _call(self, client: HostBrokerClient, *, effectful: bool) -> None:
        client.call(
            _context(effectful=effectful),
            capability=(
                "host.service.restart" if effectful else "host.service.status"
            ),
            operation=(
                "host.service.restart" if effectful else "host.service.status"
            ),
            phase="execute" if effectful else "preview",
            payload={"target": "demo"},
            effectful=effectful,
        )

    def test_effectful_transport_loss_after_dispatch_is_uncertain(self):
        connection = _FakeConnection(send_error=OSError("connection lost"))
        client = HostBrokerClient(
            socket_path="/tmp/phase10-broker.sock",
            expected_uid=0,
        )

        with patch.object(client_module.socket, "socket", return_value=connection):
            with self.assertRaises(CapabilityError) as captured:
                self._call(client, effectful=True)

        self.assertTrue(connection.sent)
        self.assertTrue(connection.closed)
        self.assertEqual(captured.exception.code, "host_effect_uncertain")
        self.assertEqual(
            captured.exception.details["broker_code"],
            "broker_transport_uncertain",
        )

    def test_read_transport_loss_remains_unavailable(self):
        connection = _FakeConnection(send_error=OSError("connection lost"))
        client = HostBrokerClient(
            socket_path="/tmp/phase10-broker.sock",
            expected_uid=0,
        )

        with patch.object(client_module.socket, "socket", return_value=connection):
            with self.assertRaises(CapabilityError) as captured:
                self._call(client, effectful=False)

        self.assertEqual(captured.exception.code, "host_broker_unavailable")

    def test_peer_uid_rejection_happens_before_effect_dispatch(self):
        connection = _FakeConnection(peer_uid=1001)
        client = HostBrokerClient(
            socket_path="/tmp/phase10-broker.sock",
            expected_uid=0,
        )

        with patch.object(client_module.socket, "socket", return_value=connection):
            with self.assertRaises(CapabilityError) as captured:
                self._call(client, effectful=True)

        self.assertFalse(connection.sent)
        self.assertEqual(captured.exception.code, "host_broker_peer_unverified")

    def test_invalid_effect_receipt_is_uncertain_not_safe_to_retry(self):
        client = _InvalidReceiptClient(
            socket_path="/tmp/phase10-broker.sock",
            expected_uid=0,
        )

        with self.assertRaises(CapabilityError) as captured:
            self._call(client, effectful=True)

        self.assertEqual(captured.exception.code, "host_effect_uncertain")
        self.assertEqual(
            captured.exception.details["broker_code"],
            "host_broker_response_invalid",
        )


if __name__ == "__main__":
    unittest.main()
