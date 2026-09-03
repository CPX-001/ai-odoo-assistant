/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import {
    createAnswerStreamPresenter,
    presentationSliceLength,
} from "@odoo_ai_assistant/services/assistant_answer_stream_presenter";

function manualScheduler() {
    const queue = [];
    return {
        schedule(callback) {
            const handle = { callback, cancelled: false };
            queue.push(handle);
            return handle;
        },
        cancel(handle) {
            handle.cancelled = true;
        },
        flush() {
            while (queue.length) {
                const handle = queue.shift();
                if (!handle.cancelled) {
                    handle.callback();
                }
            }
        },
    };
}

test("presentation slices prefer a readable boundary", () => {
    expect(presentationSliceLength("una respuesta con palabras", 14)).toBe(14);
    expect("una respuesta con palabras".slice(0, 14)).toBe("una respuesta ");
});

test("real bursty deltas are paced and reconciled without inventing final text", async () => {
    const scheduler = manualScheduler();
    const updates = [];
    const presenter = createAnswerStreamPresenter({
        writeText: (text) => updates.push(text),
        schedule: scheduler.schedule,
        cancel: scheduler.cancel,
        now: () => 0,
        reduceMotion: false,
    });
    const first = "**Resumen** " + "evidencia relevante ".repeat(30);
    const second = "conclusión y siguiente paso.";

    presenter.push(first);
    presenter.push(second);
    const beforeFlush = presenter.snapshot();
    expect(beforeFlush.received).toBe(first + second);
    expect(beforeFlush.displayed.length < beforeFlush.received.length).toBe(true);
    expect(beforeFlush.received.startsWith(beforeFlush.displayed)).toBe(true);

    const reconciliation = presenter.reconcile(first + second);
    scheduler.flush();
    expect(await reconciliation).toBe(true);
    expect(updates.at(-1)).toBe(first + second);
    presenter.stop();
});

test("terminal text is never simulated when it was not received as a delta", async () => {
    const updates = [];
    const presenter = createAnswerStreamPresenter({
        writeText: (text) => updates.push(text),
        reduceMotion: true,
    });
    presenter.push("Prefijo real");

    expect(await presenter.reconcile("Prefijo real más texto solo terminal")).toBe(false);
    expect(updates).toEqual(["Prefijo real"]);
    presenter.stop();
});
