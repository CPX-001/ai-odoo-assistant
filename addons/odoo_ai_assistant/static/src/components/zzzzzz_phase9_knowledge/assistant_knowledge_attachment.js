/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const MAX_PENDING_ATTACHMENTS = 8;
const ATTACHMENT_MARKER_RE = /\n?\[\[odoo_ai_attachment:[0-9a-f]{32}\]\]/g;

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

function cleanLocalAttachmentMarkers(state) {
    state.messages = state.messages.map((message) => {
        if (message.role !== "user" || typeof message.content !== "string") {
            return message;
        }
        const content = message.content.replace(ATTACHMENT_MARKER_RE, "").trim();
        return content === message.content ? message : { ...message, content };
    });
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
            const code = error?.message;
            this.state.knowledgeUploadError =
                code === "knowledge_file_too_large"
                    ? _t("El archivo supera el límite de 8 MB.")
                    : code === "knowledge_unsupported_document"
                      ? _t("Formato no soportado todavía. Usa TXT, Markdown, RST, CSV, JSON o XML.")
                      : _t("No se pudo adjuntar el archivo.");
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
        const draft = this.state.draft;
        const question = draft.trim();
        if (
            !question ||
            this.state.loading ||
            this.state.decisionLoading ||
            this.recoveryPending
        ) {
            return false;
        }
        const uploads = pendingUploads(this.state);
        const markers = uploads.map((item) => `\n[[odoo_ai_attachment:${item.token}]]`).join("");
        const message = `${question}${markers}`;
        if (message.length > 4000) {
            this.state.knowledgeUploadError = _t(
                "El mensaje y las referencias de archivos superan el límite del turno."
            );
            return false;
        }

        this.panel.setDraft("");
        let sent = false;
        try {
            sent = await this.panel.submit(message);
        } catch {
            if (!this.state.errorCode) {
                this.state.errorCode = "service_unavailable";
            }
        }
        if (!sent) {
            this.panel.setDraft(draft);
            return false;
        }
        this.state.pendingKnowledgeUploads = [];
        this.state.knowledgeUploadError = null;
        cleanLocalAttachmentMarkers(this.state);
        return true;
    },
});
