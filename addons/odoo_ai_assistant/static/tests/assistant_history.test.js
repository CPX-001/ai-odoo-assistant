import { expect, test } from "@odoo/hoot";
import {
    toggleHistorySelection,
    toggleVisibleHistorySelection,
} from "@odoo_ai_assistant/components/assistant_history/assistant_history";
import { historyActionsForScope } from "@odoo_ai_assistant/components/assistant_history/assistant_history_actions";

const FIRST = "12345678-1234-5678-9234-567812345678";
const SECOND = "22345678-1234-5678-9234-567812345678";
const THIRD = "32345678-1234-5678-9234-567812345678";


test("history actions are registered by scope", () => {
    expect(historyActionsForScope("item").map((action) => action.id)).toEqual([
        "select",
        "delete",
    ]);
    expect(historyActionsForScope("bulk").map((action) => action.id)).toEqual(["delete"]);
});


test("history selection toggles individual conversations", () => {
    expect(toggleHistorySelection([], FIRST)).toEqual([FIRST]);
    expect(toggleHistorySelection([FIRST, SECOND], FIRST)).toEqual([SECOND]);
});


test("select all toggles only visible conversations", () => {
    expect(toggleVisibleHistorySelection([THIRD], [FIRST, SECOND])).toEqual([
        THIRD,
        FIRST,
        SECOND,
    ]);
    expect(toggleVisibleHistorySelection([THIRD, FIRST, SECOND], [FIRST, SECOND])).toEqual([
        THIRD,
    ]);
});
