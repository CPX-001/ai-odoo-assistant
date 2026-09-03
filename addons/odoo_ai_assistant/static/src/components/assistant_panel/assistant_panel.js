/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";

const PANEL_MARGIN = 12;
const PANEL_MIN_WIDTH = 320;
const PANEL_MIN_HEIGHT = 320;
const PANEL_STORAGE_VERSION = 1;
const BATCH_PREVIEW_LIMIT = 5;

export function batchPreviewRows(step, expanded = false) {
    const preview = step?.preview;
    const regular = Array.isArray(preview?.rows)
        ? preview.rows
        : Array.isArray(preview?.records)
          ? preview.records
          : [];
    const protectedRows = Array.isArray(preview?.protected_records)
        ? preview.protected_records.map((row) => ({ ...row, excluded: true }))
        : [];
    const rows = [...regular, ...protectedRows];
    const visible = expanded ? rows : rows.slice(0, BATCH_PREVIEW_LIMIT);
    return visible.map((row, index) => ({
        key: `${step?.step_id || "preview"}:${index}`,
        label: batchPreviewRowLabel(row, index),
        excluded: row?.excluded === true,
    }));
}

export function batchPreviewRemaining(step, expanded = false) {
    const rows = batchPreviewRows(step, true);
    return expanded ? 0 : Math.max(0, rows.length - BATCH_PREVIEW_LIMIT);
}

export function batchPreviewOmitted(step) {
    const preview = step?.preview;
    const omittedEligible = Number.isSafeInteger(preview?.omitted_count)
        ? Math.max(0, preview.omitted_count)
        : 0;
    const sampledProtected = Array.isArray(preview?.protected_records)
        ? preview.protected_records.length
        : 0;
    const omittedProtected = Number.isSafeInteger(preview?.excluded_count)
        ? Math.max(0, preview.excluded_count - sampledProtected)
        : 0;
    return omittedEligible + omittedProtected;
}

function batchPreviewRowLabel(row, index) {
    if (typeof row === "string" && row.trim()) {
        return row.trim();
    }
    if (row && typeof row === "object") {
        const values = row.values && typeof row.values === "object" ? row.values : row;
        for (const key of ["display_name", "name"]) {
            if (typeof values[key] === "string" && values[key].trim()) {
                return values[key].trim();
            }
        }
    }
    return `${_t("Fila")} ${index + 1}`;
}

function browserStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

function panelGeometryStorageKey() {
    const host = globalThis.location?.host || "odoo";
    const uid =
        globalThis.odoo?.session_info?.uid ??
        globalThis.odoo?.__session_info__?.uid;
    const userScope = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : "session";
    return `odoo_ai_assistant:panel_geometry:${host}:${userScope}`;
}

function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
}

function loadPanelGeometry(storage) {
    try {
        const raw = storage?.getItem(panelGeometryStorageKey());
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        if (
            parsed?.version !== PANEL_STORAGE_VERSION ||
            !finiteNumber(parsed.x) ||
            !finiteNumber(parsed.y) ||
            !finiteNumber(parsed.width) ||
            !finiteNumber(parsed.height)
        ) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

function savePanelGeometry(storage, layout) {
    if (
        !layout.initialized ||
        !finiteNumber(layout.x) ||
        !finiteNumber(layout.y) ||
        !finiteNumber(layout.width) ||
        !finiteNumber(layout.height)
    ) {
        return;
    }
    try {
        storage?.setItem(
            panelGeometryStorageKey(),
            JSON.stringify({
                version: PANEL_STORAGE_VERSION,
                x: Math.round(layout.x),
                y: Math.round(layout.y),
                width: Math.round(layout.width),
                height: Math.round(layout.height),
            })
        );
    } catch {
        // Browser storage is an optional UX enhancement.
    }
}

function clamp(value, minimum, maximum) {
    if (maximum <= minimum) {
        return maximum;
    }
    return Math.min(Math.max(value, minimum), maximum);
}

function viewportSize() {
    return {
        width: Math.max(
            0,
            globalThis.innerWidth || globalThis.document?.documentElement?.clientWidth || 0
        ),
        height: Math.max(
            0,
            globalThis.innerHeight || globalThis.document?.documentElement?.clientHeight || 0
        ),
    };
}

function navbarBottom() {
    const navbar = globalThis.document?.querySelector?.(".o_main_navbar");
    const bottom = navbar?.getBoundingClientRect?.().bottom;
    return finiteNumber(bottom) && bottom >= 0 ? bottom : 46;
}

export class AssistantSystray extends Component {
    static template = "odoo_ai_assistant.AssistantSystray";
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.actionService = useService("action");
        this.state = useState(this.panel.state);
    }

    togglePanel() {
        this.panel.toggle();
    }
}

export class AssistantPanel extends Component {
    static template = "odoo_ai_assistant.AssistantPanel";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.actionService = useService("action");
        this.state = useState(this.panel.state);
        this.panelRef = useRef("panel");
        this.ui = useState({ isMinimized: false });
        this.previewExpansion = useState({});
        this.layout = useState({
            initialized: false,
            x: 0,
            y: 0,
            width: 0,
            height: 0,
        });
        this.storage = browserStorage();
        this._drag = null;
        this._resizeObserver = null;
        this._observedPanel = null;
        this._wasOpen = false;
        this._onViewportResize = () => this.constrainPanelToViewport();

        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => {
            if (this.state.isOpen) {
                this.panel.refreshContext();
            }
        });

        onMounted(() => {
            globalThis.addEventListener?.("resize", this._onViewportResize);
            this.syncPanelElement();
        });
        onPatched(() => this.syncPanelElement());
        onWillUnmount(() => {
            globalThis.removeEventListener?.("resize", this._onViewportResize);
            this.disconnectResizeObserver();
        });
    }

    get panelClass() {
        const classes = [
            "o_ai_assistant_panel",
            "position-fixed",
            "shadow",
            "d-flex",
            "flex-column",
        ];
        if (this.layout.initialized) {
            classes.push("o_ai_assistant_panel_positioned");
        }
        if (this.ui.isMinimized) {
            classes.push("o_ai_assistant_panel_minimized");
        }
        return classes.join(" ");
    }

    get panelStyle() {
        if (!this.layout.initialized) {
            return "";
        }
        return [
            `left:${Math.round(this.layout.x)}px`,
            `top:${Math.round(this.layout.y)}px`,
            `width:${Math.round(this.layout.width)}px`,
            `height:${Math.round(this.layout.height)}px`,
        ].join(";");
    }

    get contextLabel() {
        const context = this.state.context;
        if (!context?.model) {
            return _t("Contexto general de Odoo");
        }
        if (!context.res_id) {
            return context.model;
        }
        return `${context.model} #${context.res_id}`;
    }

    get errorMessage() {
        const messages = {
            access_denied: _t("No tienes permisos para acceder a los datos necesarios."),
            agent_budget_exceeded: _t(
                "El agente alcanzó el límite seguro de herramientas. Inténtalo con una petición más concreta."
            ),
            action_budget_exceeded: _t("La acción superó los límites seguros del turno."),
            action_rejected: _t("La acción solicitada no está permitida."),
            approval_binding_mismatch: _t("La propuesta pertenece a otro contexto de usuario."),
            approval_expired: _t("La preview ha caducado. Pide de nuevo el cambio."),
            approval_not_found: _t("No se encontró una aprobación ejecutable."),
            authentication_failed: _t("La autenticación interna del Assistant ha fallado."),
            chat_store_unavailable: _t("El historial no está disponible temporalmente."),
            codex_not_connected: _t("Conecta una cuenta de ChatGPT para usar el Assistant."),
            codex_unavailable: _t("Codex no está instalado o no está disponible para Odoo."),
            engine_timeout: _t("Codex agotó el tiempo disponible. Inténtalo de nuevo."),
            engine_unavailable: _t("Codex no está disponible en este momento."),
            evidence_unavailable: _t("No está disponible la evidencia necesaria."),
            invalid_context: _t("No se pudo interpretar la petición o el contexto actual."),
            invalid_response: _t("El Assistant devolvió una respuesta no válida."),
            query_budget_exceeded: _t("La consulta superó los límites seguros del turno."),
            query_rejected: _t("La consulta no está permitida por el esquema efectivo."),
            proposal_already_decided: _t("Esta propuesta ya fue decidida."),
            proposal_not_found: _t("No se encontró la propuesta."),
            record_context_required: _t("Esta acción necesita un registro abierto."),
            service_unavailable: _t("El Assistant Service no está disponible."),
        };
        return messages[this.state.errorCode] || _t("No se pudo completar la petición.");
    }

    get confidenceLabel() {
        const labels = {
            high: _t("Confianza alta"),
            medium: _t("Confianza media"),
            low: _t("Confianza baja"),
        };
        return labels[this.state.result?.confidence] || "";
    }

    get runtimeSetupMessage() {
        const messages = {
            authentication_error: _t(
                "No se pudo comprobar la conexión con ChatGPT. Revisa la configuración de Codex."
            ),
            codex_unavailable: _t(
                "Codex no está disponible para el proceso Odoo. Un administrador debe configurarlo."
            ),
            login_pending: _t(
                "La sesión principal de Codex se está autenticando fuera de Odoo; el Assistant detectará el cambio automáticamente."
            ),
            not_authenticated: _t(
                "La sesión principal de Codex no está autenticada. Un administrador del host debe configurarla."
            ),
        };
        return messages[this.state.runtimeState] || _t("Comprobando la conexión con ChatGPT…");
    }

    openAssistantSettings() {
        return this.actionService.doAction("base_setup.action_general_configuration", {
            additionalContext: { module: "odoo_ai_assistant" },
        });
    }

    get recoveryPending() {
        return this.state.result?.plan?.state === "authorized";
    }

    get finalPresentation() {
        return this.panel.finalUxPresentation?.() || {};
    }

    batchPreviewRows(step) {
        return batchPreviewRows(step, this.previewExpansion[step.step_id] === true);
    }

    batchPreviewRemaining(step) {
        return batchPreviewRemaining(step, this.previewExpansion[step.step_id] === true);
    }

    batchPreviewOmitted(step) {
        return batchPreviewOmitted(step);
    }

    toggleBatchPreview(step) {
        this.previewExpansion[step.step_id] = !this.previewExpansion[step.step_id];
    }

    get actionDecisionMessage() {
        const messages = {
            authorized: _t(
                "El resultado del lote quedó pendiente de recuperar. Se conserva el mismo intento y no se crea una nueva autorización."
            ),
            completed: _t("Operación completada y verificada en Odoo."),
            rejected: _t("Operación cancelada. No se realizó ningún cambio."),
            partial: _t("La operación terminó parcialmente; revisa el resultado antes de continuar."),
            failed: _t("La operación falló y no se presenta como completada."),
        };
        return messages[this.state.actionReceipt?.state] || "";
    }

    openPlanRecord(ev) {
        const stepIndex = Number(ev.currentTarget?.dataset?.stepIndex);
        const receipt = this.state.result?.plan?.steps?.[stepIndex]?.receipt;
        if (!receipt?.record_model || !Number.isSafeInteger(receipt.record_id)) {
            return;
        }
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: receipt.record_model,
            res_id: receipt.record_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onConfirmationModeChange(ev) {
        void this.panel.setAgentPolicy(
            ev.target.value,
            this.state.agentPolicy.max_auto_risk
        );
    }

    onMaxAutoRiskChange(ev) {
        void this.panel.setAgentPolicy(
            this.state.agentPolicy.confirmation_mode,
            ev.target.value
        );
    }

    get actionDecisionClass() {
        const value = this.state.actionReceipt?.state;
        if (value === "completed") {
            return "alert-success";
        }
        if (value === "rejected") {
            return "alert-secondary";
        }
        if (value === "authorized" || value === "partial") {
            return "alert-warning";
        }
        return "alert-danger";
    }

    syncPanelElement() {
        const panel = this.panelRef.el;
        if (!panel) {
            if (this._wasOpen) {
                this.ui.isMinimized = false;
            }
            this._wasOpen = false;
            this.disconnectResizeObserver();
            return;
        }
        this._wasOpen = true;
        if (!this.layout.initialized) {
            this.initializePanelGeometry(panel);
        }
        this.observePanelResize(panel);
        this.constrainPanelToViewport();
    }

    initializePanelGeometry(panel) {
        const rect = panel.getBoundingClientRect();
        const stored = loadPanelGeometry(this.storage);
        const { width: viewportWidth, height: viewportHeight } = viewportSize();
        const topMinimum = navbarBottom() + PANEL_MARGIN;
        const maxWidth = Math.max(0, viewportWidth - PANEL_MARGIN * 2);
        const maxHeight = Math.max(0, viewportHeight - topMinimum - PANEL_MARGIN);
        const minWidth = Math.min(PANEL_MIN_WIDTH, maxWidth);
        const minHeight = Math.min(PANEL_MIN_HEIGHT, maxHeight);
        const width = clamp(stored?.width ?? rect.width, minWidth, maxWidth);
        const height = clamp(stored?.height ?? rect.height, minHeight, maxHeight);
        const maxX = Math.max(PANEL_MARGIN, viewportWidth - width - PANEL_MARGIN);
        const maxY = Math.max(topMinimum, viewportHeight - height - PANEL_MARGIN);
        const defaultX = maxX;
        const defaultY = maxY;

        this.layout.x = clamp(stored?.x ?? defaultX, PANEL_MARGIN, maxX);
        this.layout.y = clamp(stored?.y ?? defaultY, topMinimum, maxY);
        this.layout.width = width;
        this.layout.height = height;
        this.layout.initialized = true;
        savePanelGeometry(this.storage, this.layout);
    }

    constrainPanelToViewport() {
        const panel = this.panelRef.el;
        if (!panel || !this.layout.initialized) {
            return;
        }
        const { width: viewportWidth, height: viewportHeight } = viewportSize();
        if (!viewportWidth || !viewportHeight) {
            return;
        }

        const topMinimum = navbarBottom() + PANEL_MARGIN;
        const maxWidth = Math.max(0, viewportWidth - PANEL_MARGIN * 2);
        const maxHeight = Math.max(0, viewportHeight - topMinimum - PANEL_MARGIN);
        const minWidth = Math.min(PANEL_MIN_WIDTH, maxWidth);
        const minHeight = Math.min(PANEL_MIN_HEIGHT, maxHeight);

        if (!this.ui.isMinimized) {
            this.layout.width = clamp(this.layout.width, minWidth, maxWidth);
            this.layout.height = clamp(this.layout.height, minHeight, maxHeight);
        }

        const rect = panel.getBoundingClientRect();
        const panelWidth = this.ui.isMinimized ? rect.width : this.layout.width;
        const panelHeight = this.ui.isMinimized ? rect.height : this.layout.height;
        const maxX = Math.max(PANEL_MARGIN, viewportWidth - panelWidth - PANEL_MARGIN);
        const maxY = Math.max(topMinimum, viewportHeight - panelHeight - PANEL_MARGIN);
        this.layout.x = clamp(this.layout.x, PANEL_MARGIN, maxX);
        this.layout.y = clamp(this.layout.y, topMinimum, maxY);
        savePanelGeometry(this.storage, this.layout);
    }

    observePanelResize(panel) {
        if (this._observedPanel === panel || typeof globalThis.ResizeObserver !== "function") {
            return;
        }
        this.disconnectResizeObserver();
        this._observedPanel = panel;
        this._resizeObserver = new globalThis.ResizeObserver(() => {
            if (this.ui.isMinimized || !this.layout.initialized) {
                return;
            }
            const rect = panel.getBoundingClientRect();
            const { width: viewportWidth, height: viewportHeight } = viewportSize();
            const maxWidth = Math.max(0, viewportWidth - this.layout.x - PANEL_MARGIN);
            const maxHeight = Math.max(0, viewportHeight - this.layout.y - PANEL_MARGIN);
            const minWidth = Math.min(PANEL_MIN_WIDTH, maxWidth);
            const minHeight = Math.min(PANEL_MIN_HEIGHT, maxHeight);
            const width = clamp(rect.width, minWidth, maxWidth);
            const height = clamp(rect.height, minHeight, maxHeight);
            if (Math.abs(width - this.layout.width) >= 1) {
                this.layout.width = width;
            }
            if (Math.abs(height - this.layout.height) >= 1) {
                this.layout.height = height;
            }
            savePanelGeometry(this.storage, this.layout);
        });
        this._resizeObserver.observe(panel);
    }

    disconnectResizeObserver() {
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        this._observedPanel = null;
    }

    startDrag(event) {
        if (
            event.button !== 0 ||
            event.target.closest("button, select, input, textarea, a")
        ) {
            return;
        }
        const panel = this.panelRef.el;
        if (!panel || !this.layout.initialized) {
            return;
        }
        const rect = panel.getBoundingClientRect();
        this._drag = {
            pointerId: event.pointerId,
            offsetX: event.clientX - rect.left,
            offsetY: event.clientY - rect.top,
        };
        event.currentTarget.setPointerCapture?.(event.pointerId);
        event.preventDefault();
    }

    dragPanel(event) {
        if (!this._drag || this._drag.pointerId !== event.pointerId) {
            return;
        }
        const panel = this.panelRef.el;
        if (!panel) {
            return;
        }
        const rect = panel.getBoundingClientRect();
        const { width: viewportWidth, height: viewportHeight } = viewportSize();
        const topMinimum = navbarBottom() + PANEL_MARGIN;
        const maxX = Math.max(PANEL_MARGIN, viewportWidth - rect.width - PANEL_MARGIN);
        const maxY = Math.max(topMinimum, viewportHeight - rect.height - PANEL_MARGIN);
        this.layout.x = clamp(
            event.clientX - this._drag.offsetX,
            PANEL_MARGIN,
            maxX
        );
        this.layout.y = clamp(
            event.clientY - this._drag.offsetY,
            topMinimum,
            maxY
        );
    }

    endDrag(event) {
        if (!this._drag || this._drag.pointerId !== event.pointerId) {
            return;
        }
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        this._drag = null;
        savePanelGeometry(this.storage, this.layout);
    }

    toggleMinimized() {
        this.ui.isMinimized = !this.ui.isMinimized;
    }

    closePanel() {
        this.ui.isMinimized = false;
        this.panel.close();
    }

    newConversation() {
        this.panel.newConversation();
    }

    async selectConversation(event) {
        const value = event.target.value;
        if (value) {
            await this.panel.selectConversation(value);
        } else {
            this.panel.newConversation();
        }
    }

    onDraftInput(event) {
        this.panel.setDraft(event.target.value);
    }

    formatActionValue(value) {
        if (!value || value.value === null) {
            return _t("Vacío");
        }
        if (value.kind === "boolean") {
            return value.value ? _t("Sí") : _t("No");
        }
        if (value.kind === "many2one") {
            return `#${value.value}`;
        }
        return String(value.value);
    }

    async approveAction() {
        await this.panel.decide("approve");
    }

    async rejectAction() {
        await this.panel.decide("reject");
    }

    async retryAction() {
        await this.panel.retry();
    }

    async submit() {
        const question = this.state.draft.trim();
        if (
            !question ||
            this.state.loading ||
            this.state.decisionLoading ||
            this.recoveryPending
        ) {
            return;
        }
        await this.panel.submit(question);
    }
}

registry.category("systray").add(
    "odoo_ai_assistant.systray",
    { Component: AssistantSystray },
    { sequence: 35 }
);
registry.category("main_components").add("odoo_ai_assistant.panel", {
    Component: AssistantPanel,
});
