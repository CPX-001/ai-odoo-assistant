"""Small extension of the local service client for persistent product chat."""

from __future__ import annotations

import http.client
import json
import logging
from collections.abc import Iterator
from time import monotonic
from urllib.parse import urlencode

from .assistant_client import (
    MAX_REQUEST_BYTES,
    SHARED_SECRET_HEADER,
    AssistantServiceClient,
    AssistantServiceError,
    _response_error_code,
)

CHAT_MAX_REQUEST_BYTES = max(MAX_REQUEST_BYTES, 64 * 1024)
CHAT_MAX_RESPONSE_BYTES = 512 * 1024
CHAT_MAX_STREAM_BYTES = 1024 * 1024
CHAT_MAX_STREAM_LINE_BYTES = 64 * 1024
LOGGER = logging.getLogger(__name__)


class AssistantChatServiceClient(AssistantServiceClient):
    def agent_turn(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/agent/turn", payload)

    def agent_turn_stream(
        self,
        payload: dict[str, object],
    ) -> Iterator[tuple[str, dict[str, object]]]:
        """Yield bounded, parsed SSE events from the Assistant Service."""

        secret = self._read_shared_secret()
        body = self._chat_body(payload, with_reasoning_model=True)
        connection = http.client.HTTPConnection(
            self._host,
            self._port,
            timeout=self._timeout,
        )
        started = monotonic()
        response = None
        try:
            connection.request(
                "POST",
                "/v1/agent/turn/stream",
                body=body,
                headers={
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                    SHARED_SECRET_HEADER: secret,
                },
            )
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
            if response.status != 200 or content_type != "text/event-stream":
                response_body = response.read(CHAT_MAX_RESPONSE_BYTES + 1)
                self._raise_chat_status(response.status, response_body)
                raise AssistantServiceError("invalid_response")
            yield from _read_sse_events(response)
        except AssistantServiceError:
            raise
        except (OSError, http.client.HTTPException) as error:
            raise AssistantServiceError("service_unavailable") from error
        finally:
            connection.close()
            LOGGER.info(
                "odoo_ai_timing phase=odoo_assistant_http_stream duration_ms=%d",
                max(0, round((monotonic() - started) * 1000)),
            )

    def agent_plan_decision(
        self,
        plan_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return self._chat_post(f"/v1/agent/plans/{plan_id}/decision", payload)

    def agent_plan_execute(
        self,
        plan_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return self._chat_post(f"/v1/agent/plans/{plan_id}/execute", payload)

    def agent_plan_status(
        self,
        plan_id: str,
        *,
        database: str,
        uid: int,
    ) -> dict[str, object]:
        secret = self._read_shared_secret()
        query = urlencode({"database": database, "uid": uid})
        return self._get_json(
            f"/v1/agent/plans/{plan_id}?{query}",
            headers={SHARED_SECRET_HEADER: secret},
        )

    def chat_history(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/chat/history", payload)

    def chat_delete(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/chat/delete", payload)

    def chat_append(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/chat/append", payload)

    def codex_models(self) -> dict[str, object]:
        secret = self._read_shared_secret()
        return self._get_json(
            "/v1/chat/models",
            headers={SHARED_SECRET_HEADER: secret},
        )

    def _chat_post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        secret = self._read_shared_secret()
        body = self._chat_body(
            payload,
            with_reasoning_model=path == "/v1/agent/turn",
        )
        return self._chat_request_json(
            path,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                SHARED_SECRET_HEADER: secret,
            },
        )

    def _chat_body(
        self,
        payload: dict[str, object],
        *,
        with_reasoning_model: bool,
    ) -> bytes:
        wire_payload = self._with_reasoning_model(payload) if with_reasoning_model else payload
        try:
            body = json.dumps(
                wire_payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise AssistantServiceError("invalid_request") from error
        if not body or len(body) > CHAT_MAX_REQUEST_BYTES:
            raise AssistantServiceError("invalid_request")
        return body

    def _chat_request_json(
        self,
        path: str,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, object]:
        connection = http.client.HTTPConnection(
            self._host,
            self._port,
            timeout=self._timeout,
        )
        started = monotonic()
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read(CHAT_MAX_RESPONSE_BYTES + 1)
        except OSError as error:
            raise AssistantServiceError("service_unavailable") from error
        finally:
            connection.close()
            if path == "/v1/agent/turn":
                LOGGER.info(
                    "odoo_ai_timing phase=odoo_assistant_http duration_ms=%d",
                    max(0, round((monotonic() - started) * 1000)),
                )

        self._raise_chat_status(response.status, response_body)
        content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
        if (
            response.status != 200
            or content_type != "application/json"
            or len(response_body) > CHAT_MAX_RESPONSE_BYTES
        ):
            raise AssistantServiceError("invalid_response")
        try:
            payload = json.loads(response_body)
        except (UnicodeError, ValueError) as error:
            raise AssistantServiceError("invalid_response") from error
        if not isinstance(payload, dict):
            raise AssistantServiceError("invalid_response")
        return payload

    @staticmethod
    def _raise_chat_status(status: int, response_body: bytes) -> None:
        code = _response_error_code(response_body)
        if status == 401:
            raise AssistantServiceError("authentication_rejected")
        if status == 403:
            raise AssistantServiceError("access_denied")
        if status == 404:
            raise AssistantServiceError(code or "conversation_not_found")
        if status == 410:
            if code == "agent_plan_expired":
                raise AssistantServiceError("approval_expired")
            raise AssistantServiceError("invalid_response")
        if status == 413:
            raise AssistantServiceError("invalid_request")
        if status == 422:
            raise AssistantServiceError(code or "invalid_context")
        if status in {502, 503, 504}:
            if code in {
                "agent_engine_timeout",
                "agent_engine_unavailable",
                "agent_execution_unavailable",
                "agent_plan_store_unavailable",
                "chat_store_unavailable",
                "engine_timeout",
                "engine_unavailable",
            }:
                raise AssistantServiceError(code)
            raise AssistantServiceError("service_unavailable")
        if status >= 500:
            raise AssistantServiceError("service_unavailable")


def _read_sse_events(response: http.client.HTTPResponse) -> Iterator[tuple[str, dict[str, object]]]:
    total = 0
    event_name = None
    data_line = None
    while True:
        line = response.readline(CHAT_MAX_STREAM_LINE_BYTES + 1)
        if not line:
            if event_name is not None or data_line is not None:
                raise AssistantServiceError("invalid_response")
            return
        total += len(line)
        if total > CHAT_MAX_STREAM_BYTES or len(line) > CHAT_MAX_STREAM_LINE_BYTES:
            raise AssistantServiceError("invalid_response")
        try:
            text = line.decode("utf-8")
        except UnicodeError as error:
            raise AssistantServiceError("invalid_response") from error
        if text in {"\n", "\r\n"}:
            if event_name not in {"delta", "final"} or data_line is None:
                raise AssistantServiceError("invalid_response")
            try:
                payload = json.loads(data_line)
            except (TypeError, ValueError) as error:
                raise AssistantServiceError("invalid_response") from error
            if not isinstance(payload, dict) or payload.get("type") != event_name:
                raise AssistantServiceError("invalid_response")
            yield event_name, payload
            if event_name == "final":
                return
            event_name = None
            data_line = None
            continue
        if text.startswith("event: ") and event_name is None:
            event_name = text[7:].strip()
            continue
        if text.startswith("data: ") and data_line is None:
            data_line = text[6:].rstrip("\r\n")
            continue
        raise AssistantServiceError("invalid_response")
