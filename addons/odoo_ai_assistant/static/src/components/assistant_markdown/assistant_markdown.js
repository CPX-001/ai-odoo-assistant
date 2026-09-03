/** @odoo-module **/

import { Component } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    parseMarkdown,
    prepareStreamingMarkdown,
} from "@odoo_ai_assistant/components/assistant_markdown/assistant_markdown_parser";

export class AssistantMarkdownInline extends Component {
    static template = "odoo_ai_assistant.AssistantMarkdownInline";
    static props = { tokens: Array };
}

export class AssistantMarkdown extends Component {
    static template = "odoo_ai_assistant.AssistantMarkdown";
    static props = { content: String, streaming: { type: Boolean, optional: true } };
    static components = { AssistantMarkdownInline };

    setup() {
        this._cachedContent = null;
        this._cachedBlocks = [];
    }

    get blocks() {
        const content = this.props.streaming
            ? prepareStreamingMarkdown(this.props.content)
            : this.props.content;
        if (this._cachedContent !== content) {
            this._cachedContent = content;
            this._cachedBlocks = parseMarkdown(content);
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
