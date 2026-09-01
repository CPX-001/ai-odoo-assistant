/** @odoo-module **/

import { useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    normalizeHostNavigationReferences,
    openPublicReference,
    referenceDisclosure,
    resourceModelReference,
    resourceReferences,
} from "@odoo_ai_assistant/services/assistant_public_reference_service";
import { semanticActivityPresentation } from "@odoo_ai_assistant/services/assistant_semantic_activity";

function durationLabel(milliseconds) {
    const ms = Number.isFinite(milliseconds) ? Math.max(0, milliseconds) : 0;
    if (ms < 1000) {
        return _t("<1 s");
    }
    const seconds = Math.max(1, Math.round(ms / 1000));
    if (seconds < 60) {
        return _t("%s s", seconds);
    }
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return remainder ? _t("%s min %s s", minutes, remainder) : _t("%s min", minutes);
}

function semanticLabel(item) {
    if (!item) {
        return _t("Working in Odoo");
    }
    switch (item.semantic_code) {
        case "request.analysis":
            return _t("Analyzing the request");
        case "answer.compose":
            return _t("Drafting the answer");
        case "evidence.search":
            return _t("Searching for information");
        case "capability.prepare":
            return _t("Preparing changes");
        case "approval.wait":
            return _t("Waiting for approval");
        case "capability.execute":
            return _t("Applying changes");
        case "capability.verify":
            return _t("Verifying results");
        case "capability.use":
            return _t("Consulting Odoo");
        case "activity.prepare.model":
            return item.headline_args?.model_label
                ? _t("Preparing %s", item.headline_args.model_label)
                : _t("Preparing the requested operation");
        case "activity.inspect.model":
            return item.headline_args?.model_label
                ? _t("Reviewing available data for %s", item.headline_args.model_label)
                : _t("Reviewing available Odoo data");
        case "activity.query.records":
            return item.headline_args?.model_label
                ? _t("Consulting %s", item.headline_args.model_label)
                : _t("Consulting Odoo records");
        case "activity.search.odoo":
            return _t("Finding the relevant Odoo data");
        case "activity.navigation.resolve":
            return _t("Finding where to open it in Odoo");
        case "activity.inspect.odoo":
            return _t("Reviewing the current Odoo context");
        case "activity.query.odoo":
            return _t("Consulting Odoo");
        case "activity.prepare.create":
            return mutationLabel(item, "prepare", "create");
        case "activity.prepare.patch":
            return mutationLabel(item, "prepare", "update");
        case "activity.prepare.archive":
            return mutationLabel(item, "prepare", "archive");
        case "activity.prepare.unarchive":
            return mutationLabel(item, "prepare", "restore");
        case "activity.prepare.delete":
            return mutationLabel(item, "prepare", "delete");
        case "activity.prepare.confirm":
            return mutationLabel(item, "prepare", "confirm");
        case "activity.prepare.changes":
            return mutationLabel(item, "prepare", "change");
        case "activity.execute.create":
            return mutationLabel(item, "execute", "create");
        case "activity.execute.patch":
            return mutationLabel(item, "execute", "update");
        case "activity.execute.archive":
            return mutationLabel(item, "execute", "archive");
        case "activity.execute.unarchive":
            return mutationLabel(item, "execute", "restore");
        case "activity.execute.delete":
            return mutationLabel(item, "execute", "delete");
        case "activity.execute.confirm":
            return mutationLabel(item, "execute", "confirm");
        case "activity.execute.changes":
            return mutationLabel(item, "execute", "change");
        case "activity.verify.results":
            return _t("Verifying results");
        case "activity.failed":
            return _t("The operation failed");
        case "activity.blocked":
            return _t("The operation is blocked");
        case "activity.cancelled":
            return _t("The operation was cancelled");
        case "queue.wait":
            return _t("Waiting for a worker");
        case "turn.finalize":
            return _t("Finishing");
        default:
            return _t("Working in Odoo");
    }
}

function mutationLabel(item, stage, operation) {
    const model = item.headline_args?.model_label;
    const count = item.headline_args?.count;
    const target = model || _t("Odoo records");
    if (stage === "prepare") {
        if (Number.isSafeInteger(count)) {
            return _t("Preparing %s %s", count, target);
        }
        return _t("Preparing changes to %s", target);
    }
    if (Number.isSafeInteger(count)) {
        const counted = {
            create: () => _t("Creating %s %s", count, target),
            update: () => _t("Updating %s %s", count, target),
            archive: () => _t("Archiving %s %s", count, target),
            restore: () => _t("Restoring %s %s", count, target),
            delete: () => _t("Deleting %s %s", count, target),
            confirm: () => _t("Confirming %s %s", count, target),
            change: () => _t("Applying changes to %s %s", count, target),
        };
        return counted[operation]();
    }
    const singular = {
        create: () => _t("Creating %s", target),
        update: () => _t("Updating %s", target),
        archive: () => _t("Archiving %s", target),
        restore: () => _t("Restoring %s", target),
        delete: () => _t("Deleting %s", target),
        confirm: () => _t("Confirming %s", target),
        change: () => _t("Applying changes to %s", target),
    };
    return singular[operation]();
}

function resultSummaryLabel(item) {
    const summary = item?.result_summary;
    if (!summary) {
        return "";
    }
    const count = summary.args?.count;
    const model = summary.args?.model_label || _t("records");
    if (!Number.isSafeInteger(count)) {
        return "";
    }
    if (summary.code === "activity.result.records_found") {
        return _t("%s %s found", count, model);
    }
    if (summary.code === "activity.result.verified") {
        return _t("Verified result: %s %s", count, model);
    }
    return _t("Completed result: %s %s", count, model);
}

function technicalSuffix(item, preferences) {
    if (
        (!preferences?.show_technical_names && preferences?.detail_level !== "diagnostic") ||
        !item
    ) {
        return "";
    }
    const technical = [];
    if (item.capability) {
        technical.push(item.capability);
    }
    if (item.resource?.model && !technical.includes(item.resource.model)) {
        technical.push(item.resource.model);
    }
    if (!technical.length && item.label) {
        technical.push(item.label);
    }
    return technical.length ? ` · ${technical.join(" · ")}` : "";
}

function activeReasoningScope(state) {
    const scoped = state.turnScopes?.[state.activeTurnScopeKey];
    if (scoped) {
        const scopedReady =
            scoped.turnId &&
            scoped.reasoningSummaryTurnId === scoped.turnId &&
            Array.isArray(scoped.reasoningSummaryParts) &&
            scoped.reasoningSummaryParts.length > 0;
        const prebindReady =
            scoped.turnId &&
            state.reasoningSummaryTurnId === scoped.turnId &&
            Array.isArray(state.reasoningSummaryParts) &&
            state.reasoningSummaryParts.length > 0;
        if (!scopedReady && prebindReady) {
            return {
                ...scoped,
                reasoningSummaryTurnId: state.reasoningSummaryTurnId,
                reasoningSummaryParts: state.reasoningSummaryParts,
            };
        }
        return scoped;
    }
    return {
        turnId: state.turnId || null,
        reasoningSummaryTurnId: state.reasoningSummaryTurnId || null,
        reasoningSummaryParts: state.reasoningSummaryParts || [],
    };
}

function visibleReasoningParts(state, preferences) {
    if (preferences?.reasoning_summary === "off") {
        return [];
    }
    const scope = activeReasoningScope(state);
    if (
        !scope?.turnId ||
        scope.reasoningSummaryTurnId !== scope.turnId ||
        !Array.isArray(scope.reasoningSummaryParts)
    ) {
        return [];
    }
    const serverLimit = Number.isSafeInteger(preferences?.limits?.max_reasoning_summary_chars)
        ? preferences.limits.max_reasoning_summary_chars
        : 2000;
    const maximum =
        preferences.reasoning_summary === "concise" ? Math.min(serverLimit, 600) : serverLimit;
    return boundedReasoningParts(scope.reasoningSummaryParts, preferences, maximum);
}

function boundedReasoningParts(parts, preferences, explicitMaximum = null) {
    if (preferences?.reasoning_summary === "off" || !Array.isArray(parts)) {
        return [];
    }
    const serverLimit = Number.isSafeInteger(preferences?.limits?.max_reasoning_summary_chars)
        ? preferences.limits.max_reasoning_summary_chars
        : 2000;
    const maximum = Number.isSafeInteger(explicitMaximum)
        ? explicitMaximum
        : preferences.reasoning_summary === "concise"
          ? Math.min(serverLimit, 600)
          : serverLimit;
    const result = [];
    let remaining = Math.max(0, maximum);
    for (const part of parts) {
        if (!remaining || typeof part?.text !== "string" || !part.text) {
            continue;
        }
        const text = plainReasoningText(part.text).slice(0, remaining);
        if (text) {
            result.push({ key: part.key, text });
            remaining -= text.length;
        }
    }
    return result;
}

function plainReasoningText(value) {
    const source = String(value || "");
    // Codex can emit terse internal headings as isolated bold Markdown fragments.  They are
    // presentation scaffolding, not useful user-facing reasoning, so the UI keeps the host-owned
    // semantic activity rows and suppresses these raw fragments entirely.
    const nonEmptyLines = source.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (
        nonEmptyLines.length &&
        nonEmptyLines.every((line) => /^\*\*[^*]+\*\*$/.test(line))
    ) {
        return "";
    }
    return source
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/^\s{0,3}#{1,6}\s+/gm, "")
        .trim();
}

function activitySummaryLabel(activity, running) {
    if (running) {
        return semanticLabel(activity.headline);
    }
    return activity.step_count ? _t("Worked for %s", durationLabel(activity.duration_ms)) : "";
}

patch(AssistantPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.semanticReferenceUi = useState({ visibleByKey: {} });
        if (typeof this.state.publicReferenceNotice !== "string") {
            this.state.publicReferenceNotice = "";
        }
    },

    get semanticActivity() {
        return semanticActivityPresentation(this.state.activityEvents, {
            running: Boolean(this.state.loading),
            preferences: this.state.activityPresentation,
        });
    },

    get activityItems() {
        return this.presentActivityItems(this.semanticActivity);
    },

    presentActivityItems(activity) {
        return activity.items.map((item) => {
            const navigationReferences =
                normalizeHostNavigationReferences(item.references || [], 12) || [];
            const references = [...navigationReferences, ...resourceReferences(item.resource)];
            const disclosure = referenceDisclosure(references, {
                pageSize: activity.preferences.batch_page_size,
                visibleCount: this.semanticReferenceUi.visibleByKey[item.key] || null,
                maximumRows: activity.preferences.limits.max_rendered_batch_rows,
            });
            return {
                ...item,
                display_label: `${semanticLabel(item)}${technicalSuffix(item, activity.preferences)}`,
                duration_label:
                    activity.preferences.show_step_durations && item.duration_ms !== null
                        ? durationLabel(item.duration_ms)
                        : "",
                progress_label: item.progress_detail
                    ? _t("%s / %s", item.progress_detail.current, item.progress_detail.total)
                    : "",
                result_summary_label: resultSummaryLabel(item),
                references: disclosure.visible,
                model_reference: resourceModelReference(item.resource),
                reference_remaining_count: disclosure.remaining_count,
                reference_next_count: disclosure.next_count,
                can_show_more_references: disclosure.can_show_more,
                can_show_remaining_references: disclosure.can_show_remaining,
                references_over_limit: disclosure.remaining_blocked,
            };
        });
    },

    get activityReasoningSummaryParts() {
        return visibleReasoningParts(this.state, this.semanticActivity.preferences);
    },

    get activityReasoningSummaryTitle() {
        return _t("Reasoning summary");
    },

    get activitySummaryLabel() {
        return activitySummaryLabel(this.semanticActivity, Boolean(this.state.loading));
    },

    get activityDisclosureKey() {
        const scope = activeReasoningScope(this.state);
        if (scope?.turnId) {
            return `live:${scope.turnId}:${this.state.loading ? "running" : "settled"}`;
        }
        const messages = Array.isArray(this.state.messages) ? this.state.messages : [];
        return `pending:${messages.at(-1)?.message_id || "idle"}`;
    },

    messageActivity(message) {
        const stored = message?.activity;
        if (!stored || !Array.isArray(stored.events)) {
            return null;
        }
        const activity = semanticActivityPresentation(stored.events, {
            running: false,
            preferences: this.state.activityPresentation,
        });
        return {
            key: `history:${message.message_id}:${stored.turn_id}`,
            summary_label: activitySummaryLabel(activity, false),
            items: this.presentActivityItems(activity),
            reasoning_parts: boundedReasoningParts(
                stored.reasoning_summary_parts,
                activity.preferences
            ),
            truncated: activity.truncated,
        };
    },

    get settledActivityAnswer() {
        if (!this.activityItems.length || typeof this.state.result?.answer !== "string") {
            return "";
        }
        const messages = Array.isArray(this.state.messages) ? this.state.messages : [];
        const last = messages.at(-1);
        return last?.role === "assistant" && last.content === this.state.result.answer
            ? this.state.result.answer
            : "";
    },

    get activityOrderedMessages() {
        const messages = Array.isArray(this.state.messages) ? this.state.messages : [];
        return this.settledActivityAnswer ? messages.slice(0, -1) : messages;
    },

    get activityDetailLevel() {
        return this.semanticActivity.preferences.detail_level;
    },

    get activityReasoningSummaryLevel() {
        return this.semanticActivity.preferences.reasoning_summary;
    },

    get activityExpandedLineCount() {
        return this.semanticActivity.preferences.expanded_line_count;
    },

    get activityDetailsStyle() {
        return `--o-ai-assistant-activity-visible-lines: ${this.activityExpandedLineCount}`;
    },

    activityShowMoreLabel(item) {
        if (!item?.reference_next_count) {
            return "";
        }
        return _t("Show %s more", item.reference_next_count);
    },

    activityShowRemainingLabel(item) {
        if (!item?.reference_remaining_count) {
            return "";
        }
        return _t("Show the remaining %s", item.reference_remaining_count);
    },

    showMoreActivityReferences(item) {
        if (!item?.key || !item.reference_next_count) {
            return;
        }
        const current =
            this.semanticReferenceUi.visibleByKey[item.key] ||
            this.semanticActivity.preferences.batch_page_size;
        const maximum = this.semanticActivity.preferences.limits.max_rendered_batch_rows;
        this.semanticReferenceUi.visibleByKey[item.key] = Math.min(
            maximum,
            current + item.reference_next_count
        );
    },

    showRemainingActivityReferences(item) {
        if (!item?.key || !item.can_show_remaining_references) {
            return;
        }
        const maximum = this.semanticActivity.preferences.limits.max_rendered_batch_rows;
        const desired = item.references.length + item.reference_remaining_count;
        this.semanticReferenceUi.visibleByKey[item.key] = Math.min(maximum, desired);
    },

    async openActivityReference(reference) {
        const opened = await openPublicReference(reference, { actionService: this.actionService });
        this.state.publicReferenceNotice = opened
            ? ""
            : _t("This link is no longer available with your current permissions or context.");
        return opened;
    },

    async changeActivityDetailLevel(event) {
        const detailLevel = event?.target?.value;
        if (typeof this.panel.setActivityPresentationPreferences === "function") {
            await this.panel.setActivityPresentationPreferences({ detail_level: detailLevel });
        }
    },

    async changeActivityReasoningSummary(event) {
        const reasoningSummary = event?.target?.value;
        if (typeof this.panel.setActivityPresentationPreferences === "function") {
            await this.panel.setActivityPresentationPreferences({ reasoning_summary: reasoningSummary });
        }
    },

    async changeActivityExpandedLineCount(event) {
        const lineCount = Number(event?.target?.value);
        if (
            Number.isSafeInteger(lineCount) &&
            typeof this.panel.setActivityPresentationPreferences === "function"
        ) {
            await this.panel.setActivityPresentationPreferences({
                expanded_line_count: lineCount,
            });
        }
    },

    async toggleActivityTechnicalNames() {
        if (typeof this.panel.setActivityPresentationPreferences === "function") {
            await this.panel.setActivityPresentationPreferences({
                show_technical_names: !this.semanticActivity.preferences.show_technical_names,
            });
        }
    },
});

export {
    durationLabel,
    plainReasoningText,
    resultSummaryLabel,
    semanticLabel,
    visibleReasoningParts,
};
