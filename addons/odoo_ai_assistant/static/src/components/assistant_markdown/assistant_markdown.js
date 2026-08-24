/** @odoo-module **/

import { Component } from "@odoo/owl";
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

    get blocks() {
        return parseMarkdown(this.props.content);
    }
}

AssistantPanel.components = {
    ...(AssistantPanel.components || {}),
    AssistantMarkdown,
};
