"""Authenticated transport for bounded temporary Knowledge attachments."""

from __future__ import annotations

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request


class AssistantKnowledgeController(http.Controller):
    @http.route(
        "/odoo_ai/v1/knowledge/attachment-upload",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def upload_attachment(self, filename=None, mimetype=None, data=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            attachment = request.env["odoo.ai.knowledge.attachment"].create_upload(
                filename=filename,
                mimetype=mimetype,
                data=data,
            )
        except AccessError:
            return _error("access_denied")
        except ValidationError as error:
            return _error(_safe_error_code(error))
        return {
            "ok": True,
            "attachment": {
                "token": attachment.token,
                "name": attachment.filename,
                "mimetype": attachment.mimetype,
                "size": attachment.file_size,
            },
        }

    @http.route(
        "/odoo_ai/v1/knowledge/attachment-discard",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def discard_attachment(self, token=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            attachment = request.env["odoo.ai.knowledge.attachment"].owned_by_tokens(
                [token]
            )
            if not attachment or attachment.turn_id:
                return _error("invalid_context")
            attachment.unlink()
        except AccessError:
            return _error("access_denied")
        except ValidationError:
            return _error("invalid_context")
        return {"ok": True}


def _safe_error_code(error) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code.startswith("knowledge_"):
        return code
    message = str(error)
    if isinstance(message, str) and message.startswith("knowledge_"):
        return message[:128]
    return "invalid_context"


def _error(code):
    return {"ok": False, "error": {"code": code}}


__all__ = ["AssistantKnowledgeController"]
