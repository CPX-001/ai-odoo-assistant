import { expect, test } from "@odoo/hoot";
import {
    detectDockTarget,
    dockGeometry,
    loadDockLayout,
    normalizeDockLayout,
    resizeDockSize,
    saveDockLayout,
    undockDistance,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_docking";

function memoryStorage() {
    const values = new Map();
    return {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
        removeItem: (key) => values.delete(key),
    };
}

const VIEWPORT = { width: 1200, height: 800, top: 46 };
const SIZES = { left: 420, right: 430, top: 340, bottom: 350 };

test("dock target selects the nearest active viewport edge", () => {
    expect(detectDockTarget(20, 400, VIEWPORT)).toBe("left");
    expect(detectDockTarget(1180, 400, VIEWPORT)).toBe("right");
    expect(detectDockTarget(600, 60, VIEWPORT)).toBe("top");
    expect(detectDockTarget(600, 785, VIEWPORT)).toBe("bottom");
    expect(detectDockTarget(600, 400, VIEWPORT)).toBe(null);
});

test("docked sidebars stay below the Odoo navbar", () => {
    const left = dockGeometry("left", VIEWPORT, SIZES);
    const bottom = dockGeometry("bottom", VIEWPORT, SIZES);

    expect(left).toEqual({ x: 0, y: 46, width: 420, height: 754 });
    expect(bottom.x).toBe(0);
    expect(bottom.width).toBe(1200);
    expect(bottom.y).toBe(450);
    expect(bottom.height).toBe(350);
});

test("dock resize grows only from the panel interior edge", () => {
    expect(resizeDockSize("left", 420, 40, 0, VIEWPORT)).toBe(460);
    expect(resizeDockSize("right", 420, -40, 0, VIEWPORT)).toBe(460);
    expect(resizeDockSize("top", 340, 0, 30, VIEWPORT)).toBe(370);
    expect(resizeDockSize("bottom", 340, 0, -30, VIEWPORT)).toBe(370);
});

test("undock threshold measures movement toward the viewport center", () => {
    expect(undockDistance("left", 120, 100, 200, 100)).toBe(80);
    expect(undockDistance("right", 1080, 100, 1000, 100)).toBe(80);
    expect(undockDistance("top", 500, 70, 500, 150)).toBe(80);
    expect(undockDistance("bottom", 500, 760, 500, 680)).toBe(80);
});

test("dock state persistence rejects malformed layouts", () => {
    const storage = memoryStorage();
    const valid = {
        version: 1,
        docked: "right",
        floating: { x: 500, y: 100, width: 520, height: 640 },
        sizes: { ...SIZES },
    };

    expect(saveDockLayout(storage, valid)).toBe(true);
    expect(loadDockLayout(storage)).toEqual(valid);
    expect(normalizeDockLayout({ ...valid, docked: "diagonal" }).docked).toBe(null);
});
