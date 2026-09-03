"""Linux AF_UNIX server for the optional host broker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import stat
import struct
from pathlib import Path

from .ledger import ExecutionLedger
from .operations import BrokerEngine
from .policy import load_policy
from .protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    BrokerProtocolError,
    canonical_json,
)

_DEFAULT_SOCKET = "/run/odoo-ai-host-broker/broker.sock"
_DEFAULT_POLICY = "/etc/odoo-ai-host-broker/policy.json"
_DEFAULT_STATE = "/var/lib/odoo-ai-host-broker/execution.sqlite3"
_DEFAULT_BACKUPS = "/var/lib/odoo-ai-host-broker/backups"


class BrokerServer:
    def __init__(self, *, socket_path: str, engine: BrokerEngine) -> None:
        if not os.path.isabs(socket_path) or "\x00" in socket_path or len(socket_path) > 1024:
            raise BrokerProtocolError("broker_socket_path_invalid")
        self.socket_path = socket_path
        self.engine = engine
        self._stop = False
        self._listener: socket.socket | None = None

    def serve_forever(self) -> None:
        path = Path(self.socket_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            st = os.lstat(path)
            if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.geteuid():
                raise BrokerProtocolError("broker_socket_existing_unsafe")
            path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener = listener
        listener.bind(self.socket_path)
        os.chmod(self.socket_path, 0o660)
        if self.engine.policy.socket_gid is not None:
            os.chown(self.socket_path, os.geteuid(), self.engine.policy.socket_gid)
        listener.listen(16)
        listener.settimeout(1.0)

        try:
            while not self._stop:
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    try:
                        self._handle_connection(connection)
                    except (BrokerProtocolError, OSError):
                        # A managed service operation may terminate the calling Odoo worker
                        # before the broker can send its already-durable receipt. Keep the
                        # broker alive; a replay with the same request id will return the
                        # stored terminal receipt instead of repeating the effect.
                        continue
        finally:
            listener.close()
            self._listener = None
            try:
                st = os.lstat(self.socket_path)
                if stat.S_ISSOCK(st.st_mode) and st.st_uid == os.geteuid():
                    os.unlink(self.socket_path)
            except OSError:
                pass

    def stop(self, *_args) -> None:
        self._stop = True

    def _handle_connection(self, connection: socket.socket) -> None:
        peer_uid = _peer_uid(connection)
        raw = _recv_line(connection, MAX_REQUEST_BYTES)
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            request = {}
        receipt = self.engine.handle(peer_uid=peer_uid, request=request)
        encoded = canonical_json(receipt) + b"\n"
        if len(encoded) > MAX_RESPONSE_BYTES:
            raise BrokerProtocolError("broker_response_too_large")
        connection.sendall(encoded)


def _peer_uid(connection: socket.socket) -> int:
    if not hasattr(socket, "SO_PEERCRED"):
        raise BrokerProtocolError("broker_peer_credentials_unavailable")
    size = struct.calcsize("3i")
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
    _pid, uid, _gid = struct.unpack("3i", raw)
    if uid < 0:
        raise BrokerProtocolError("broker_peer_credentials_invalid")
    return uid


def _recv_line(connection: socket.socket, maximum: int) -> bytes:
    data = bytearray()
    while len(data) <= maximum:
        chunk = connection.recv(min(8192, maximum + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if len(data) > maximum:
        raise BrokerProtocolError("broker_request_too_large")
    if b"\n" in data:
        line, trailing = bytes(data).split(b"\n", 1)
        if trailing:
            raise BrokerProtocolError("broker_request_framing_invalid")
        return line
    return bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Odoo AI Assistant local host privilege broker")
    parser.add_argument("--socket", default=_DEFAULT_SOCKET)
    parser.add_argument("--policy", default=_DEFAULT_POLICY)
    parser.add_argument("--state-db", default=_DEFAULT_STATE)
    parser.add_argument("--backups-dir", default=_DEFAULT_BACKUPS)
    args = parser.parse_args(argv)

    os.umask(0o077)
    policy = load_policy(args.policy)
    state_path = Path(args.state_db)
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_path.parent, 0o700)
    ledger = ExecutionLedger(state_path)
    engine = BrokerEngine(
        policy=policy,
        ledger=ledger,
        backups_dir=args.backups_dir,
    )
    server = BrokerServer(socket_path=args.socket, engine=engine)
    signal.signal(signal.SIGTERM, server.stop)
    signal.signal(signal.SIGINT, server.stop)
    try:
        server.serve_forever()
    finally:
        ledger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
