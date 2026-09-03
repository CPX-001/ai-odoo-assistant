/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const MAX_PENDING_ATTACHMENTS = 8;

async function fileToBase64(file) {
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunkSize = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
    }
    return globalThis.btoa(binary);
}

function pendingUploads(state) {
    return Array.isArray(state.pendingKnowledgeUploads) ? state.pendingKnowledgeUploads : [];
}

function uploadErrorMessage(code) {
    const messages = {
        knowledge_empty_document: _t(
            "No se pudo extraer texto. Los PDF escaneados necesitan OCR."
        ),
        knowledge_file_too_large: _t("El archivo supera el límite de 8 MB."),
        knowledge_invalid_pdf: _t("El PDF está dañado o no se puede leer."),
        knowledge_pdf_dependency_missing: _t(
            "Esta instalación de Odoo no tiene disponible la lectura de PDF."
        ),
        knowledge_pdf_encrypted: _t("No se pueden leer PDF protegidos con contraseña."),
        knowledge_unsupported_document: _t(
            "Formato no soportado. Usa PDF, TXT, Markdown, RST, CSV, JSON o XML."
        ),
    };
    return messages[code] || _t("No se pudo adjuntar el archivo.");
}

patch(AssistantPanel.prototype, {
    async onKnowledgeFileSelected(event) {
        const input = event?.target;
        const file = input?.files?.[0];
        if (!file) {
            return;
        }
        if (pendingUploads(this.state).length >= MAX_PENDING_ATTACHMENTS) {
            this.state.knowledgeUploadError = _t("Puedes adjuntar como máximo 8 archivos por turno.");
            input.value = "";
            return;
        }
        this.state.knowledgeUploadBusy = true;
        this.state.knowledgeUploadError = null;
        try {
            const response = await rpc("/odoo_ai/v1/knowledge/attachment-upload", {
                filename: file.name,
                mimetype: file.type || "application/octet-stream",
                data: await fileToBase64(file),
            });
            const attachment = response?.ok === true ? response.attachment : null;
            if (
                !attachment ||
                typeof attachment.token !== "string" ||
                typeof attachment.name !== "string"
            ) {
                throw new Error(response?.error?.code || "knowledge_upload_failed");
            }
            this.state.pendingKnowledgeUploads = [
                ...pendingUploads(this.state),
                attachment,
            ];
        } catch (error) {
            this.state.knowledgeUploadError = uploadErrorMessage(error?.message);
        } finally {
            this.state.knowledgeUploadBusy = false;
            input.value = "";
        }
    },

    async removeKnowledgeUpload(token) {
        const current = pendingUploads(this.state);
        const selected = current.find((item) => item.token === token);
        if (!selected) {
            return;
        }
        this.state.pendingKnowledgeUploads = current.filter((item) => item.token !== token);
        try {
            await rpc("/odoo_ai/v1/knowledge/attachment-discard", { token });
        } catch {
            // The temporary row expires automatically; UI removal stays local and fail-soft.
        }
    },

    async submit() {
        const uploads = pendingUploads(this.state);
        if (!uploads.length) {
            return super.submit(...arguments);
        }
        if (this.composerActionMode && this.composerActionMode !== "send") {
            this.state.knowledgeUploadError = _t(
                "Los archivos adjuntos sólo se pueden enviar al iniciar un turno nuevo."
            );
            return false;
        }

        const draft = this.state.draft;
        const question = draft.trim();
        if (!question) {
            return false;
        }
        const markers = uploads.map((item) => `\n[[odoo_ai_attachment:${item.token}]]`).join("");
        const markedDraft = `${question}${markers}`;
        if (markedDraft.length > 4000) {
            this.state.knowledgeUploadError = _t(
                "El mensaje y las referencias de archivos superan el límite del turno."
            );
            return false;
        }

        this.panel.setDraft("");
        let sent = false;
        try {
            sent = await this.panel.submit(markedDraft, {
                displayMessage: question,
                displayAttachments: uploads.map((item) => ({
                    name: item.name,
                    mimetype: item.mimetype,
                    size: item.size,
                })),
            });
        } catch {
            if (!this.state.errorCode) {
                this.state.errorCode = "service_unavailable";
            }
        }
        if (!sent) {
            // Restore only when the user did not type a newer message while the request ran.
            if (!this.state.draft) {
                this.panel.setDraft(draft);
            }
            return false;
        }
        this.state.pendingKnowledgeUploads = [];
        this.state.knowledgeUploadError = null;
        return true;
    },
});
