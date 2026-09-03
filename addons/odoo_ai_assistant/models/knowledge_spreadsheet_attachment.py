"""Temporary spreadsheet artifacts for chat-driven imports.

The P9 attachment model was originally document-oriented and rejected binary
spreadsheets before P11 could inspect them.  This extension keeps Knowledge source
formats unchanged while allowing short-lived XLS/XLSX/ODS chat artifacts to reach the
bounded P11 import pipeline.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from odoo import api, fields, models

from .knowledge import (
    _ATTACHMENT_INTERNAL_FIELDS,
    _decode_binary,
    _filename,
)

_SPREADSHEET_MIMETYPES = {
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}
_SPREADSHEET_PLACEHOLDER = (
    "Spreadsheet artifact attached for structured import. "
    "Use the Assistant data-import capabilities to inspect its rows and columns."
)


class AssistantKnowledgeSpreadsheetAttachment(models.Model):
    _inherit = "odoo.ai.knowledge.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        """Allow spreadsheets only as temporary chat artifacts, not Knowledge sources."""

        result = self.browse()
        normal_rows = []
        for incoming in vals_list:
            filename = _filename(dict(incoming).get("filename"))
            extension = _extension(filename)
            if extension not in _SPREADSHEET_MIMETYPES:
                normal_rows.append(incoming)
                continue
            values = dict(incoming)
            if not self.env.su:
                for key in _ATTACHMENT_INTERNAL_FIELDS:
                    values.pop(key, None)
                values["user_id"] = self.env.uid
                values["company_id"] = self.env.company.id
            raw = _decode_binary(values.get("data"))
            values.update(
                {
                    "filename": filename,
                    "mimetype": _SPREADSHEET_MIMETYPES[extension],
                    "file_size": len(raw),
                    "fingerprint": hashlib.sha256(raw).hexdigest(),
                    "extracted_text": _SPREADSHEET_PLACEHOLDER,
                }
            )
            values.setdefault("expires_at", fields.Datetime.now() + timedelta(hours=24))
            # Intentionally bypass the document-only validation in the P9 attachment
            # create override.  We reproduce its ownership/fingerprint/TTL invariants and
            # call the generic ORM create path.  Persistent Knowledge ingestion still
            # passes through the original document validator and therefore remains
            # PDF/text-only.
            result |= models.Model.create(self, [values])
        if normal_rows:
            result |= super().create(normal_rows)
        return result


def _extension(filename: str) -> str:
    position = filename.rfind(".")
    return filename[position:].casefold() if position >= 0 else ""


__all__ = ["AssistantKnowledgeSpreadsheetAttachment"]
