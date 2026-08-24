/** @odoo-module **/

import { onWillUnmount, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    DOCK_UNDOCK_DISTANCE_PX,
    clamp,
    detectDockTarget,
    dockGeometry,
    loadDockLayout,
    resizeDockSize,
    saveDockLayout,
    undockDistance,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_docking";

const PANEL_MARGIN = 12;
const PANEL_MIN_WIDTH = 320;
const PANEL_MIN_HEIGHT = 320;

function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
}

function viewportMetrics() {
    const width = Math.max(
        0,
        globalThis.innerWidth || globalThis.document?.documentElement?.clientWidth || 0
    );
    const height = Math.max(
        0,
        globalThis.innerHeight || globalThis.document?.documentElement?.clientHeight || 0
    );
    const navbar = globalThis.document?.querySelector?.(".o_main_navbar");
    const navbarBottom = navbar?.getBoundingClientRect?.().bottom;
    return {
        width,
        height,
        top: finiteNumber(navbarBottom) && navbarBottom >= 0 ? navbarBottom : 46,
    };
}

function geometryStyle(geometry, { minimized = false, docked = null } = {}) {
    if (!geometry) {
        return "";
    }
    if (minimized && docked === "bottom") {
        return `left:0px;right:auto;top:auto;bottom:0px;width:${Math.round(geometry.width)}px`;
    }
    const parts = [
        `left:${Math.round(geometry.x)}px`,
        "right:auto",
        `top:${Math.round(geometry.y)}px`,
        "bottom:auto",
        `width:${Math.round(geometry.width)}px`,
    ];
    if (!minimized) {
        parts.push(`height:${Math.round(geometry.height)}px`);
    }
    return parts.join(";");
}

function pointerDirection(value) {
    return ["n", "ne", "e", "se", "s", "sw", "w", "nw"].includes(value)
        ? value
        : null;
}

patch(AssistantPanel.prototype, {
    setup() {
        super.setup(...arguments);
        const persisted = loadDockLayout(this.storage);
        this.dock = useState({
            docked: persisted.docked,
            previewTarget: null,
            interaction: null,
            floating: persisted.floating,
            sizes: { ...persisted.sizes },
        });
        this._dockFrame = null;
        this._resize = null;
        onWillUnmount(() => {
            if (this._dockFrame !== null) {
                globalThis.cancelAnimationFrame?.(this._dockFrame);
                this._dockFrame = null;
            }
        });
    },

    get panelClass() {
        const classes = [super.panelClass];
        if (this.dock?.docked) {
            classes.push("o_ai_assistant_panel_docked", `o_ai_assistant_panel_docked_${this.dock.docked}`);
        } else {
            classes.push("o_ai_assistant_panel_floating");
        }
        if (this.dock?.interaction) {
            classes.push(`o_ai_assistant_panel_${this.dock.interaction}`);
        }
        return classes.join(" ");
    },

    get panelStyle() {
        if (this.dock?.docked) {
            return geometryStyle(
                dockGeometry(this.dock.docked, viewportMetrics(), this.dock.sizes),
                { minimized: this.ui.isMinimized, docked: this.dock.docked }
            );
        }
        const base = super.panelStyle;
        if (!this._drag || this._drag.fromDocked) {
            return base;
        }
        const x = finiteNumber(this._drag.deltaX) ? this._drag.deltaX : 0;
        const y = finiteNumber(this._drag.deltaY) ? this._drag.deltaY : 0;
        return `${base};transform:translate3d(${Math.round(x)}px,${Math.round(y)}px,0)`;
    },

    get dockPreviewStyle() {
        return geometryStyle(
            dockGeometry(this.dock?.previewTarget, viewportMetrics(), this.dock?.sizes || {})
        );
    },

    get dockResizeDirection() {
        return {
            left: "e",
            right: "w",
            top: "s",
            bottom: "n",
        }[this.dock?.docked] || "";
    },

    initializePanelGeometry(panel) {
        super.initializePanelGeometry(panel);
        const stored = this.dock?.floating;
        if (stored) {
            this.layout.x = stored.x;
            this.layout.y = stored.y;
            this.layout.width = stored.width;
            this.layout.height = stored.height;
        }
        if (!this.dock?.docked) {
            super.constrainPanelToViewport();
            this.captureFloatingLayout();
        }
        this.persistDockLayout();
    },

    constrainPanelToViewport() {
        if (!this.dock) {
            super.constrainPanelToViewport();
            return;
        }
        if (this.dock.docked) {
            const geometry = dockGeometry(this.dock.docked, viewportMetrics(), this.dock.sizes);
            if (geometry) {
                this.dock.sizes[this.dock.docked] = ["left", "right"].includes(this.dock.docked)
                    ? geometry.width
                    : geometry.height;
            }
            this.persistDockLayout();
            return;
        }
        super.constrainPanelToViewport();
        this.captureFloatingLayout();
        this.persistDockLayout();
    },

    observePanelResize(panel) {
        if (this.dock?.docked) {
            this.disconnectResizeObserver();
            return;
        }
        super.observePanelResize(panel);
    },

    captureFloatingLayout() {
        if (
            !this.layout.initialized ||
            !finiteNumber(this.layout.x) ||
            !finiteNumber(this.layout.y) ||
            !finiteNumber(this.layout.width) ||
            !finiteNumber(this.layout.height)
        ) {
            return;
        }
        this.dock.floating = {
            x: this.layout.x,
            y: this.layout.y,
            width: this.layout.width,
            height: this.layout.height,
        };
    },

    persistDockLayout() {
        if (!this.dock) {
            return;
        }
        saveDockLayout(this.storage, {
            version: 1,
            docked: this.dock.docked,
            floating: this.dock.floating,
            sizes: { ...this.dock.sizes },
        });
    },

    startDrag(event) {
        if (
            event.button !== 0 ||
            event.target.closest("button, select, input, textarea, a, .o_ai_assistant_resize_handle")
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
            captureTarget: event.currentTarget,
            fromDocked: Boolean(this.dock.docked),
            dockedSide: this.dock.docked,
            startClientX: event.clientX,
            startClientY: event.clientY,
            offsetX: event.clientX - rect.left,
            offsetY: event.clientY - rect.top,
            startX: this.layout.x,
            startY: this.layout.y,
            deltaX: 0,
            deltaY: 0,
            clientX: event.clientX,
            clientY: event.clientY,
        };
        this.dock.interaction = "dragging";
        event.currentTarget.setPointerCapture?.(event.pointerId);
        event.preventDefault();
    },

    dragPanel(event) {
        if (!this._drag || this._drag.pointerId !== event.pointerId) {
            return;
        }
        this._drag.clientX = event.clientX;
        this._drag.clientY = event.clientY;
        if (this._dockFrame !== null) {
            return;
        }
        this._dockFrame = globalThis.requestAnimationFrame?.(() => {
            this._dockFrame = null;
            this.applyDragFrame();
        }) ?? null;
        if (this._dockFrame === null) {
            this.applyDragFrame();
        }
    },

    applyDragFrame() {
        const drag = this._drag;
        const panel = this.panelRef.el;
        if (!drag || !panel) {
            return;
        }
        if (drag.fromDocked) {
            const distance = undockDistance(
                drag.dockedSide,
                drag.startClientX,
                drag.startClientY,
                drag.clientX,
                drag.clientY
            );
            if (distance < DOCK_UNDOCK_DISTANCE_PX) {
                return;
            }
            this.undockAtPointer(drag.clientX, drag.clientY);
            drag.fromDocked = false;
            drag.dockedSide = null;
            drag.startClientX = drag.clientX;
            drag.startClientY = drag.clientY;
            drag.startX = this.layout.x;
            drag.startY = this.layout.y;
            drag.deltaX = 0;
            drag.deltaY = 0;
        }

        const viewport = viewportMetrics();
        const width = this.layout.width;
        const height = this.layout.height;
        const maxX = Math.max(PANEL_MARGIN, viewport.width - width - PANEL_MARGIN);
        const maxY = Math.max(viewport.top + PANEL_MARGIN, viewport.height - height - PANEL_MARGIN);
        const nextX = clamp(
            drag.startX + drag.clientX - drag.startClientX,
            PANEL_MARGIN,
            maxX
        );
        const nextY = clamp(
            drag.startY + drag.clientY - drag.startClientY,
            viewport.top + PANEL_MARGIN,
            maxY
        );
        drag.deltaX = nextX - drag.startX;
        drag.deltaY = nextY - drag.startY;
        panel.style.transform = `translate3d(${Math.round(drag.deltaX)}px,${Math.round(drag.deltaY)}px,0)`;

        const previewTarget = detectDockTarget(drag.clientX, drag.clientY, viewport);
        if (previewTarget !== this.dock.previewTarget) {
            this.dock.previewTarget = previewTarget;
        }
    },

    endDrag(event) {
        const drag = this._drag;
        if (!drag || drag.pointerId !== event.pointerId) {
            return;
        }
        if (this._dockFrame !== null) {
            globalThis.cancelAnimationFrame?.(this._dockFrame);
            this._dockFrame = null;
            this.applyDragFrame();
        }
        drag.captureTarget?.releasePointerCapture?.(event.pointerId);
        const panel = this.panelRef.el;
        if (panel) {
            panel.style.transform = "";
        }
        const target = this.dock.previewTarget;
        if (!drag.fromDocked && target) {
            this.dockPanel(target);
        } else if (!drag.fromDocked) {
            this.layout.x = drag.startX + drag.deltaX;
            this.layout.y = drag.startY + drag.deltaY;
            this.captureFloatingLayout();
            this.persistDockLayout();
        }
        this.dock.previewTarget = null;
        this.dock.interaction = null;
        this._drag = null;
    },

    dockPanel(side) {
        if (!["left", "right", "top", "bottom"].includes(side)) {
            return;
        }
        this.captureFloatingLayout();
        this.dock.docked = side;
        const geometry = dockGeometry(side, viewportMetrics(), this.dock.sizes);
        if (geometry) {
            this.dock.sizes[side] = ["left", "right"].includes(side)
                ? geometry.width
                : geometry.height;
        }
        this.disconnectResizeObserver();
        this.persistDockLayout();
    },

    undockPanel() {
        if (!this.dock.docked) {
            return;
        }
        this.dock.docked = null;
        this.restoreFloatingLayout();
        this.persistDockLayout();
    },

    undockAtPointer(clientX, clientY) {
        this.dock.docked = null;
        this.restoreFloatingLayout(clientX, clientY);
        this.persistDockLayout();
    },

    restoreFloatingLayout(clientX = null, clientY = null) {
        const viewport = viewportMetrics();
        const stored = this.dock.floating || {
            x: PANEL_MARGIN,
            y: viewport.top + PANEL_MARGIN,
            width: this.layout.width,
            height: this.layout.height,
        };
        const maxWidth = Math.max(0, viewport.width - PANEL_MARGIN * 2);
        const maxHeight = Math.max(0, viewport.height - viewport.top - PANEL_MARGIN * 2);
        const minWidth = Math.min(PANEL_MIN_WIDTH, maxWidth);
        const minHeight = Math.min(PANEL_MIN_HEIGHT, maxHeight);
        const width = clamp(stored.width, minWidth, maxWidth);
        const height = clamp(stored.height, minHeight, maxHeight);
        const maxX = Math.max(PANEL_MARGIN, viewport.width - width - PANEL_MARGIN);
        const maxY = Math.max(viewport.top + PANEL_MARGIN, viewport.height - height - PANEL_MARGIN);
        const x = finiteNumber(clientX)
            ? clamp(clientX - Math.min(width / 2, 180), PANEL_MARGIN, maxX)
            : clamp(stored.x, PANEL_MARGIN, maxX);
        const y = finiteNumber(clientY)
            ? clamp(clientY - 24, viewport.top + PANEL_MARGIN, maxY)
            : clamp(stored.y, viewport.top + PANEL_MARGIN, maxY);
        this.layout.x = x;
        this.layout.y = y;
        this.layout.width = width;
        this.layout.height = height;
        this.layout.initialized = true;
        this.captureFloatingLayout();
    },

    startResize(event) {
        if (event.button !== 0 || this.ui.isMinimized) {
            return;
        }
        const direction = pointerDirection(event.currentTarget.dataset.direction);
        if (!direction) {
            return;
        }
        const docked = this.dock.docked;
        if (docked && direction !== this.dockResizeDirection) {
            return;
        }
        this._resize = {
            pointerId: event.pointerId,
            captureTarget: event.currentTarget,
            direction,
            docked,
            startClientX: event.clientX,
            startClientY: event.clientY,
            startX: this.layout.x,
            startY: this.layout.y,
            startWidth: this.layout.width,
            startHeight: this.layout.height,
            startDockSize: docked ? this.dock.sizes[docked] : null,
            clientX: event.clientX,
            clientY: event.clientY,
        };
        this.dock.interaction = "resizing";
        event.currentTarget.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        event.stopPropagation();
    },

    resizePanel(event) {
        if (!this._resize || this._resize.pointerId !== event.pointerId) {
            return;
        }
        this._resize.clientX = event.clientX;
        this._resize.clientY = event.clientY;
        if (this._dockFrame !== null) {
            return;
        }
        this._dockFrame = globalThis.requestAnimationFrame?.(() => {
            this._dockFrame = null;
            this.applyResizeFrame();
        }) ?? null;
        if (this._dockFrame === null) {
            this.applyResizeFrame();
        }
    },

    applyResizeFrame() {
        const resize = this._resize;
        if (!resize) {
            return;
        }
        const dx = resize.clientX - resize.startClientX;
        const dy = resize.clientY - resize.startClientY;
        const viewport = viewportMetrics();
        if (resize.docked) {
            this.dock.sizes[resize.docked] = resizeDockSize(
                resize.docked,
                resize.startDockSize,
                dx,
                dy,
                viewport
            );
            return;
        }

        const direction = resize.direction;
        const right = resize.startX + resize.startWidth;
        const bottom = resize.startY + resize.startHeight;
        let x = resize.startX;
        let y = resize.startY;
        let width = resize.startWidth;
        let height = resize.startHeight;

        if (direction.includes("e")) {
            const maxWidth = Math.max(0, viewport.width - resize.startX - PANEL_MARGIN);
            width = clamp(resize.startWidth + dx, Math.min(PANEL_MIN_WIDTH, maxWidth), maxWidth);
        }
        if (direction.includes("w")) {
            const maxWidth = Math.max(0, right - PANEL_MARGIN);
            width = clamp(resize.startWidth - dx, Math.min(PANEL_MIN_WIDTH, maxWidth), maxWidth);
            x = right - width;
        }
        if (direction.includes("s")) {
            const maxHeight = Math.max(0, viewport.height - resize.startY - PANEL_MARGIN);
            height = clamp(resize.startHeight + dy, Math.min(PANEL_MIN_HEIGHT, maxHeight), maxHeight);
        }
        if (direction.includes("n")) {
            const maxHeight = Math.max(0, bottom - viewport.top - PANEL_MARGIN);
            height = clamp(resize.startHeight - dy, Math.min(PANEL_MIN_HEIGHT, maxHeight), maxHeight);
            y = bottom - height;
        }
        this.layout.x = x;
        this.layout.y = y;
        this.layout.width = width;
        this.layout.height = height;
    },

    endResize(event) {
        const resize = this._resize;
        if (!resize || resize.pointerId !== event.pointerId) {
            return;
        }
        if (this._dockFrame !== null) {
            globalThis.cancelAnimationFrame?.(this._dockFrame);
            this._dockFrame = null;
            this.applyResizeFrame();
        }
        resize.captureTarget?.releasePointerCapture?.(event.pointerId);
        if (!resize.docked) {
            this.captureFloatingLayout();
        }
        this.persistDockLayout();
        this.dock.interaction = null;
        this._resize = null;
    },
});
