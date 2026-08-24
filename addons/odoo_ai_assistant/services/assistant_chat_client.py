"""Small extension of the local service client for persistent product chat."""

from __future__ import annotations

import http.client
import json

from .assistant_client import (
    MAX_REQUEST_BYTES,
    SHARED_SECRET_HEADER,
    AssistantServiceClient,
    AssistantServiceError,
    _response_error_code,
)

CHAT_MAX_REQUEST_BYTES = max(MAX_REQUEST_BYTES, 32 * 1024)
CHAT_MAX_RESPONSE_BYTES = 512 * 1024


class AssistantChatServiceClient(AssistantServiceClient):
    def route_chat(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/chat/route", payload)

    def general_chat(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/turns/general", payload)

    def chat_history(self, payload: dict[str, object]) -> dict[str, object]:
        return self._chat_post("/v1/chat/history", payload)

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
        wire_payload = (
            self._with_reasoning_model(payload)
            if path == "/v1/turns/general"
            else payload
        )
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
        return self._chat_request_json(
            path,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                SHARED_SECRET_HEADER: secret,
            },
        )

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
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read(CHAT_MAX_RESPONSE_BYTES + 1)
        except OSError as error:
            raise AssistantServiceError("service_unavailable") from error
        finally:
            connection.close()

        code = _response_error_code(response_body)
        if response.status == 401:
            raise AssistantServiceError("authentication_rejected")
        if response.status == 403:
            raise AssistantServiceError("access_denied")
        if response.status == 404:
            raise AssistantServiceError(code or "conversation_not_found")
        if response.status == 413:
            raise AssistantServiceError("invalid_request")
        if response.status == 422:
            raise AssistantServiceError("invalid_context")
        if response.status in {502, 503, 504}:
            if code in {"chat_store_unavailable", "engine_timeout", "engine_unavailable"}:
                raise AssistantServiceError(code)
            raise AssistantServiceError("service_unavailable")
        if response.status >= 500:
            raise AssistantServiceError("service_unavailable")
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
