/** @odoo-module **/

import { Component } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { parseMarkdown } from "@odoo_ai_assistant/components/assistant_markdown/assistant_markdown_parser";

export class AssistantMarkdownInline extends Component {
    static template = "odoo_ai_assistant.AssistantMarkdownInline";
    static props = { tokens: Array };
}

export class AssistantMarkdown extends Component {
    static template = "odoo_ai_assistant.AssistantMarkdown";
    static props = { content: String };
    static components = { AssistantMarkdownInline };

    setup() {
        this._cachedContent = null;
        this._cachedBlocks = [];
    }

    get blocks() {
        if (this._cachedContent !== this.props.content) {
            this._cachedContent = this.props.content;
            this._cachedBlocks = parseMarkdown(this.props.content);
        }
        return this._cachedBlocks;
    }
}

patch(AssistantPanel, {
    components: {
        ...(AssistantPanel.components || {}),
        AssistantMarkdown,
    },
});
