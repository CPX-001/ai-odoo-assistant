/** @odoo-module **/

export const DOCK_SIDES = Object.freeze(["left", "right", "top", "bottom"]);
export const DOCK_ACTIVATION_PX = 52;
export const DOCK_UNDOCK_DISTANCE_PX = 72;
export const DOCK_LAYOUT_VERSION = 1;

const DEFAULT_SIDE_SIZE = 420;
const DEFAULT_HORIZONTAL_SIZE = 340;
const MIN_SIDE_SIZE = 320;
const MIN_HORIZONTAL_SIZE = 240;

function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
}

export function clamp(value, minimum, maximum) {
    if (maximum <= minimum) {
        return maximum;
    }
    return Math.min(Math.max(value, minimum), maximum);
}

export function dockLayoutStorageKey() {
    const host = globalThis.location?.host || "odoo";
    const uid =
        globalThis.odoo?.session_info?.uid ??
        globalThis.odoo?.__session_info__?.uid;
    const userScope = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : "session";
    return `odoo_ai_assistant:panel_layout:${host}:${userScope}`;
}

export function defaultDockLayout() {
    return {
        version: DOCK_LAYOUT_VERSION,
        docked: null,
        floating: null,
        sizes: {
            left: DEFAULT_SIDE_SIZE,
            right: DEFAULT_SIDE_SIZE,
            top: DEFAULT_HORIZONTAL_SIZE,
            bottom: DEFAULT_HORIZONTAL_SIZE,
        },
    };
}

function validFloating(value) {
    return (
        value === null ||
        (value &&
            finiteNumber(value.x) &&
            finiteNumber(value.y) &&
            finiteNumber(value.width) &&
            finiteNumber(value.height) &&
            value.width > 0 &&
            value.height > 0)
    );
}

function validSizes(value) {
    return (
        value &&
        DOCK_SIDES.every((side) => finiteNumber(value[side]) && value[side] > 0)
    );
}

export function normalizeDockLayout(value) {
    if (
        !value ||
        value.version !== DOCK_LAYOUT_VERSION ||
        (value.docked !== null && !DOCK_SIDES.includes(value.docked)) ||
        !validFloating(value.floating) ||
        !validSizes(value.sizes)
    ) {
        return defaultDockLayout();
    }
    return {
        version: DOCK_LAYOUT_VERSION,
        docked: value.docked,
        floating: value.floating ? { ...value.floating } : null,
        sizes: {
            left: value.sizes.left,
            right: value.sizes.right,
            top: value.sizes.top,
            bottom: value.sizes.bottom,
        },
    };
}

export function loadDockLayout(storage) {
    try {
        const raw = storage?.getItem(dockLayoutStorageKey());
        return raw ? normalizeDockLayout(JSON.parse(raw)) : defaultDockLayout();
    } catch {
        return defaultDockLayout();
    }
}

export function saveDockLayout(storage, value) {
    try {
        const normalized = normalizeDockLayout(value);
        storage?.setItem(dockLayoutStorageKey(), JSON.stringify(normalized));
        return true;
    } catch {
        return false;
    }
}

export function detectDockTarget(
    clientX,
    clientY,
    { width, height, top = 0 },
    threshold = DOCK_ACTIVATION_PX
) {
    if (
        !finiteNumber(clientX) ||
        !finiteNumber(clientY) ||
        !finiteNumber(width) ||
        !finiteNumber(height) ||
        !finiteNumber(top) ||
        width <= 0 ||
        height <= top ||
        clientX < 0 ||
        clientX > width ||
        clientY < top ||
        clientY > height
    ) {
        return null;
    }
    const candidates = [];
    const left = clientX;
    const right = width - clientX;
    const upper = clientY - top;
    const bottom = height - clientY;
    if (left <= threshold) {
        candidates.push(["left", left]);
    }
    if (right <= threshold) {
        candidates.push(["right", right]);
    }
    if (upper <= threshold) {
        candidates.push(["top", upper]);
    }
    if (bottom <= threshold) {
        candidates.push(["bottom", bottom]);
    }
    if (!candidates.length) {
        return null;
    }
    candidates.sort((a, b) => a[1] - b[1]);
    return candidates[0][0];
}

export function dockGeometry(side, viewport, sizes) {
    const width = Math.max(0, viewport.width);
    const height = Math.max(0, viewport.height);
    const top = clamp(viewport.top || 0, 0, height);
    const availableHeight = Math.max(0, height - top);
    const maxSide = Math.max(0, Math.min(width, width * 0.66));
    const minSide = Math.min(MIN_SIDE_SIZE, maxSide);
    const maxHorizontal = Math.max(0, Math.min(availableHeight, availableHeight * 0.66));
    const minHorizontal = Math.min(MIN_HORIZONTAL_SIZE, maxHorizontal);

    if (side === "left" || side === "right") {
        const dockWidth = clamp(sizes[side], minSide, maxSide);
        return {
            x: side === "left" ? 0 : Math.max(0, width - dockWidth),
            y: top,
            width: dockWidth,
            height: availableHeight,
        };
    }
    if (side === "top" || side === "bottom") {
        const dockHeight = clamp(sizes[side], minHorizontal, maxHorizontal);
        return {
            x: 0,
            y: side === "top" ? top : Math.max(top, height - dockHeight),
            width,
            height: dockHeight,
        };
    }
    return null;
}

export function resizeDockSize(side, startSize, deltaX, deltaY, viewport) {
    let next = startSize;
    if (side === "left") {
        next += deltaX;
    } else if (side === "right") {
        next -= deltaX;
    } else if (side === "top") {
        next += deltaY;
    } else if (side === "bottom") {
        next -= deltaY;
    }
    const geometry = dockGeometry(
        side,
        viewport,
        { left: next, right: next, top: next, bottom: next }
    );
    return side === "left" || side === "right" ? geometry.width : geometry.height;
}

export function undockDistance(side, startX, startY, clientX, clientY) {
    if (side === "left") {
        return Math.max(0, clientX - startX);
    }
    if (side === "right") {
        return Math.max(0, startX - clientX);
    }
    if (side === "top") {
        return Math.max(0, clientY - startY);
    }
    if (side === "bottom") {
        return Math.max(0, startY - clientY);
    }
    return 0;
}
