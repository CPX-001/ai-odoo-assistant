"""Small durable replay ledger for effectful broker operations."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .protocol import BrokerProtocolError, canonical_json, validate_receipt


class ExecutionLedger:
    """Persist execute request identity before crossing the privileged barrier."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self._path, timeout=5)
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self._path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS broker_execution (
                request_id TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                operation TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('running', 'terminal')),
                receipt_json TEXT,
                started_at INTEGER NOT NULL
            )
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def begin(
        self,
        *,
        request_id: str,
        request_hash: str,
        operation: str,
        started_at: int,
    ) -> tuple[str, dict[str, Any] | None]:
        """Return new|terminal|running|conflict without ever re-running a known id."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                """
                SELECT request_hash, state, receipt_json
                  FROM broker_execution
                 WHERE request_id = ?
                """,
                [request_id],
            ).fetchone()
            if row is None:
                self._connection.execute(
                    """
                    INSERT INTO broker_execution(
                        request_id, request_hash, operation, state, receipt_json, started_at
                    ) VALUES (?, ?, ?, 'running', NULL, ?)
                    """,
                    [request_id, request_hash, operation, started_at],
                )
                self._connection.commit()
                return "new", None
            self._connection.commit()
            existing_hash, state, receipt_json = row
            if existing_hash != request_hash:
                return "conflict", None
            if state == "running":
                return "running", None
            if state != "terminal" or not isinstance(receipt_json, str):
                raise BrokerProtocolError("broker_ledger_corrupt")
            try:
                receipt = json.loads(receipt_json)
                validate_receipt(receipt)
            except (json.JSONDecodeError, BrokerProtocolError) as error:
                raise BrokerProtocolError("broker_ledger_corrupt") from error
            return "terminal", receipt

    def finish(self, receipt: dict[str, Any]) -> None:
        validate_receipt(receipt)
        encoded = canonical_json(receipt).decode("utf-8")
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE broker_execution
                   SET state = 'terminal',
                       receipt_json = ?
                 WHERE request_id = ?
                   AND state = 'running'
                """,
                [encoded, receipt["request_id"]],
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise BrokerProtocolError("broker_ledger_state_invalid")
            self._connection.commit()


__all__ = ["ExecutionLedger"]
