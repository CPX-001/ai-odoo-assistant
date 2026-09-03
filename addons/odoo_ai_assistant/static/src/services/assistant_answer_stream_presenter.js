/** @odoo-module **/

const MAX_ANSWER_CHARS = 16 * 1024;
const FRAME_DELAY_MS = 30;

function defaultNow() {
    return globalThis.performance?.now?.() ?? Date.now();
}

function defaultSchedule(callback) {
    return globalThis.setTimeout(callback, FRAME_DELAY_MS);
}

function defaultCancel(handle) {
    globalThis.clearTimeout(handle);
}

function reducedMotionRequested() {
    try {
        return Boolean(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
    } catch {
        return false;
    }
}

function targetSliceLength(backlog, catchingUp) {
    if (catchingUp) {
        return backlog <= 64 ? backlog : Math.max(48, Math.ceil(backlog / 5));
    }
    if (backlog > 2048) return 160;
    if (backlog > 1024) return 112;
    if (backlog > 512) return 72;
    if (backlog > 256) return 48;
    if (backlog > 96) return 32;
    return 20;
}

export function presentationSliceLength(text, maximum) {
    if (typeof text !== "string" || !text || !Number.isSafeInteger(maximum) || maximum < 1) {
        return 0;
    }
    let cut = Math.min(text.length, maximum);
    if (cut < text.length) {
        const minimum = Math.max(1, Math.floor(cut * 0.55));
        for (let index = cut - 1; index >= minimum; index -= 1) {
            if (/\s|[.,;:!?)]/.test(text[index])) {
                cut = index + 1;
                break;
            }
        }
    }
    if (cut < text.length && /[\uD800-\uDBFF]/.test(text[cut - 1])) {
        cut -= 1;
    }
    return Math.max(1, cut);
}

export function createAnswerStreamPresenter({
    writeText,
    schedule = defaultSchedule,
    cancel = defaultCancel,
    now = defaultNow,
    reduceMotion = reducedMotionRequested(),
    maxChars = MAX_ANSWER_CHARS,
} = {}) {
    if (typeof writeText !== "function") {
        throw new Error("invalid_stream_presenter");
    }
    let received = "";
    let displayed = "";
    let scheduled = null;
    let stopped = false;
    let catchingUp = false;
    let lastPresentedAt = null;
    let settleResolve = null;

    const resolveSettle = (value) => {
        if (settleResolve) {
            const resolve = settleResolve;
            settleResolve = null;
            resolve(value);
        }
    };

    const writeNextSlice = () => {
        const backlog = received.length - displayed.length;
        if (backlog <= 0) {
            resolveSettle(true);
            return;
        }
        const pending = received.slice(displayed.length);
        const cut = reduceMotion
            ? pending.length
            : presentationSliceLength(
                  pending,
                  targetSliceLength(backlog, catchingUp)
              );
        displayed += pending.slice(0, cut);
        writeText(displayed);
        lastPresentedAt = now();
    };

    const ensureScheduled = () => {
        if (stopped || scheduled !== null || displayed.length >= received.length) {
            if (displayed.length >= received.length) {
                resolveSettle(true);
            }
            return;
        }
        scheduled = schedule(() => {
            scheduled = null;
            if (stopped) {
                return;
            }
            writeNextSlice();
            ensureScheduled();
        });
    };

    return {
        push(text) {
            if (
                stopped ||
                typeof text !== "string" ||
                !text ||
                text.includes("\0") ||
                received.length + text.length > maxChars
            ) {
                throw new Error("invalid_stream");
            }
            received += text;
            if (
                displayed.length === 0 ||
                reduceMotion ||
                (lastPresentedAt !== null && now() - lastPresentedAt >= FRAME_DELAY_MS)
            ) {
                writeNextSlice();
            }
            ensureScheduled();
        },

        async reconcile(finalText) {
            if (stopped || typeof finalText !== "string" || finalText !== received || !received) {
                return false;
            }
            if (displayed === received) {
                return true;
            }
            catchingUp = true;
            if (scheduled !== null) {
                cancel(scheduled);
                scheduled = null;
            }
            const settled = new Promise((resolve) => {
                settleResolve = resolve;
            });
            ensureScheduled();
            return settled;
        },

        stop() {
            if (scheduled !== null) {
                cancel(scheduled);
                scheduled = null;
            }
            stopped = true;
            resolveSettle(false);
        },

        snapshot() {
            return { received, displayed };
        },
    };
}
