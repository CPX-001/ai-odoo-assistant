import { expect, test } from "@odoo/hoot";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { AssistantMarkdown } from "@odoo_ai_assistant/components/assistant_markdown/assistant_markdown";
import {
    parseMarkdown,
    safeMarkdownLink,
} from "@odoo_ai_assistant/components/assistant_markdown/assistant_markdown_parser";

defineMailModels();

test("markdown parses emphasis without exposing delimiter text", () => {
    const blocks = parseMarkdown("Resultado **correcto** y *visible*.");

    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("paragraph");
    expect(blocks[0].tokens.map((token) => token.type).join("|")).toBe("text|strong|text|em|text");
    expect(blocks[0].tokens[1].text).toBe("correcto");
});

test("markdown pipe syntax becomes a table with alignment metadata", () => {
    const blocks = parseMarkdown(
        "| Nombre | Total |\n|:---|---:|\n| Facturas | **12** |\n| Pedidos | `4` |"
    );

    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("table");
    expect(blocks[0].alignments.join("|")).toBe("start|end");
    expect(blocks[0].rows).toHaveLength(2);
    expect(blocks[0].rows[0][1][0].type).toBe("strong");
    expect(blocks[0].rows[1][1][0].type).toBe("code");
});

test("markdown supports headings lists quotes and fenced code", () => {
    const blocks = parseMarkdown(
        "## Resumen\n\n- Uno\n- Dos\n\n> Nota importante\n\n```python\nprint('ok')\n```"
    );

    expect(blocks.map((block) => block.type).join("|")).toBe("heading|list|blockquote|code");
    expect(blocks[1].items).toHaveLength(2);
    expect(blocks[3].language).toBe("python");
    expect(blocks[3].content).toBe("print('ok')");
});

test("unsafe link schemes remain plain text", () => {
    const blocks = parseMarkdown("[abrir](javascript:alert(1))");

    expect(safeMarkdownLink("javascript:alert(1)")).toBe(null);
    expect(safeMarkdownLink("https://odoo.com")).toBe("https://odoo.com");
    expect(blocks[0].tokens).toHaveLength(1);
    expect(blocks[0].tokens[0].type).toBe("text");
    expect(blocks[0].tokens[0].text).toBe("[abrir](javascript:alert(1))");
});

test("raw html is kept as escaped text for Owl to render", () => {
    const blocks = parseMarkdown("<script>alert('x')</script>");

    expect(blocks[0].tokens).toHaveLength(1);
    expect(blocks[0].tokens[0].type).toBe("text");
    expect(blocks[0].tokens[0].text).toBe("<script>alert('x')</script>");
});

test("Owl renderer creates semantic markup instead of exposing markdown delimiters", async () => {
    await mountWithCleanup(AssistantMarkdown, {
        props: {
            content: "## Resumen\n\n**Total:** 12\n\n| Tipo | Cantidad |\n|---|---:|\n| Facturas | 12 |",
        },
    });

    const root = document.querySelector(".o_ai_assistant_markdown");
    expect(root !== null).toBe(true);
    expect(root.querySelector("strong")?.textContent).toBe("Total:");
    expect(root.querySelector("table") !== null).toBe(true);
    expect(root.textContent.includes("**")).toBe(false);
    expect(root.textContent.includes("|---|")).toBe(false);
});

test("Owl renderer never turns raw assistant HTML into executable DOM", async () => {
    await mountWithCleanup(AssistantMarkdown, {
        props: { content: "<script>globalThis.markdownXssProbe = true</script>" },
    });

    const root = document.querySelector(".o_ai_assistant_markdown");
    expect(root !== null).toBe(true);
    expect(root.querySelector("script")).toBe(null);
    expect(root.textContent).toBe("<script>globalThis.markdownXssProbe = true</script>");
    expect(globalThis.markdownXssProbe).toBe(undefined);
});
