const MAX_MARKDOWN_LENGTH = 32768;

function textToken(text) {
    return { type: "text", text };
}

function pushToken(tokens, token) {
    if (!token.text) {
        return;
    }
    const previous = tokens[tokens.length - 1];
    if (token.type === "text" && previous?.type === "text") {
        previous.text += token.text;
        return;
    }
    tokens.push(token);
}

export function safeMarkdownLink(value) {
    if (typeof value !== "string") {
        return null;
    }
    const href = value.trim();
    if (!href || /[\u0000-\u001f\u007f]/.test(href)) {
        return null;
    }
    if (href.startsWith("/") || href.startsWith("#")) {
        return href;
    }
    const scheme = href.match(/^([a-z][a-z0-9+.-]*):/i)?.[1]?.toLowerCase();
    if (["http", "https", "mailto"].includes(scheme)) {
        return href;
    }
    return null;
}

function trimAutolink(value) {
    let href = value;
    let suffix = "";
    while (/[.,!?;:]$/.test(href)) {
        suffix = href.slice(-1) + suffix;
        href = href.slice(0, -1);
    }
    return { href, suffix };
}

const INLINE_PATTERNS = [
    { type: "code", regex: /`([^`\n]+)`/g, text: (match) => match[1] },
    { type: "strong", regex: /\*\*([^*\n]+)\*\*/g, text: (match) => match[1] },
    { type: "strong", regex: /__([^_\n]+)__/g, text: (match) => match[1] },
    { type: "strike", regex: /~~([^~\n]+)~~/g, text: (match) => match[1] },
    {
        type: "link",
        regex: /\[([^\]\n]+)\]\(([^)\s]+)\)/g,
        text: (match) => match[1],
        href: (match) => safeMarkdownLink(match[2]),
    },
    { type: "em", regex: /\*([^*\n]+)\*/g, text: (match) => match[1] },
    { type: "em", regex: /_([^_\n]+)_/g, text: (match) => match[1] },
    {
        type: "autolink",
        regex: /https?:\/\/[^\s<>()]+/gi,
        text: (match) => trimAutolink(match[0]).href,
        href: (match) => safeMarkdownLink(trimAutolink(match[0]).href),
        suffix: (match) => trimAutolink(match[0]).suffix,
    },
];

export function tokenizeMarkdownInline(value) {
    const source = typeof value === "string" ? value : "";
    const tokens = [];
    let cursor = 0;

    while (cursor < source.length) {
        let candidate = null;
        for (let priority = 0; priority < INLINE_PATTERNS.length; priority += 1) {
            const pattern = INLINE_PATTERNS[priority];
            pattern.regex.lastIndex = cursor;
            const match = pattern.regex.exec(source);
            if (!match) {
                continue;
            }
            if (
                !candidate ||
                match.index < candidate.match.index ||
                (match.index === candidate.match.index && priority < candidate.priority)
            ) {
                candidate = { match, pattern, priority };
            }
        }

        if (!candidate) {
            pushToken(tokens, textToken(source.slice(cursor)));
            break;
        }
        if (candidate.match.index > cursor) {
            pushToken(tokens, textToken(source.slice(cursor, candidate.match.index)));
        }

        const { match, pattern } = candidate;
        const text = pattern.text(match);
        const href = pattern.href ? pattern.href(match) : null;
        if ((pattern.type === "link" || pattern.type === "autolink") && !href) {
            pushToken(tokens, textToken(match[0]));
        } else if (pattern.type === "autolink") {
            pushToken(tokens, { type: "link", text, href });
            const suffix = pattern.suffix(match);
            if (suffix) {
                pushToken(tokens, textToken(suffix));
            }
        } else {
            pushToken(tokens, { type: pattern.type, text, ...(href ? { href } : {}) });
        }
        cursor = match.index + match[0].length;
    }

    return tokens.map((token, index) => ({ ...token, key: index }));
}

function splitTableRow(line) {
    let source = line.trim();
    if (source.startsWith("|")) {
        source = source.slice(1);
    }
    if (source.endsWith("|") && !source.endsWith("\\|")) {
        source = source.slice(0, -1);
    }
    const cells = [];
    let current = "";
    let escaped = false;
    let inCode = false;
    for (const char of source) {
        if (escaped) {
            current += char;
            escaped = false;
            continue;
        }
        if (char === "\\") {
            escaped = true;
            continue;
        }
        if (char === "`") {
            inCode = !inCode;
            current += char;
            continue;
        }
        if (char === "|" && !inCode) {
            cells.push(current.trim());
            current = "";
            continue;
        }
        current += char;
    }
    if (escaped) {
        current += "\\";
    }
    cells.push(current.trim());
    return cells;
}

function tableAlignment(cell) {
    const value = cell.trim();
    if (!/^:?-{3,}:?$/.test(value)) {
        return undefined;
    }
    if (value.startsWith(":") && value.endsWith(":")) {
        return "center";
    }
    if (value.endsWith(":")) {
        return "end";
    }
    if (value.startsWith(":")) {
        return "start";
    }
    return null;
}

function parseTable(lines, index) {
    if (index + 1 >= lines.length || !lines[index].includes("|")) {
        return null;
    }
    const header = splitTableRow(lines[index]);
    const separator = splitTableRow(lines[index + 1]);
    if (header.length < 2 || separator.length !== header.length) {
        return null;
    }
    const alignments = separator.map(tableAlignment);
    if (alignments.some((value) => value === undefined)) {
        return null;
    }
    const rows = [];
    let cursor = index + 2;
    while (cursor < lines.length && lines[cursor].trim() && lines[cursor].includes("|")) {
        const cells = splitTableRow(lines[cursor]);
        while (cells.length < header.length) {
            cells.push("");
        }
        rows.push(cells.slice(0, header.length).map(tokenizeMarkdownInline));
        cursor += 1;
    }
    return {
        block: {
            type: "table",
            header: header.map(tokenizeMarkdownInline),
            alignments,
            rows,
        },
        nextIndex: cursor,
    };
}

function isBlockStart(lines, index) {
    const line = lines[index] || "";
    if (!line.trim()) {
        return true;
    }
    return (
        /^\s*(`{3,}|~{3,})/.test(line) ||
        /^\s{0,3}#{1,4}\s+/.test(line) ||
        /^\s{0,3}>\s?/.test(line) ||
        /^\s{0,3}([-+*])\s+/.test(line) ||
        /^\s{0,3}\d+[.)]\s+/.test(line) ||
        /^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line) ||
        parseTable(lines, index) !== null
    );
}

export function parseMarkdown(value) {
    const source = (typeof value === "string" ? value : "")
        .slice(0, MAX_MARKDOWN_LENGTH)
        .replace(/\r\n?/g, "\n");
    const lines = source.split("\n");
    const blocks = [];
    let index = 0;

    while (index < lines.length) {
        const line = lines[index];
        if (!line.trim()) {
            index += 1;
            continue;
        }

        const fence = line.match(/^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+#.-]{0,32})\s*$/);
        if (fence) {
            const marker = fence[1][0];
            const minimumLength = fence[1].length;
            const code = [];
            index += 1;
            while (index < lines.length) {
                const closing = lines[index].match(/^\s*(`{3,}|~{3,})\s*$/);
                if (closing && closing[1][0] === marker && closing[1].length >= minimumLength) {
                    index += 1;
                    break;
                }
                code.push(lines[index]);
                index += 1;
            }
            blocks.push({ type: "code", language: fence[2] || "", content: code.join("\n") });
            continue;
        }

        const table = parseTable(lines, index);
        if (table) {
            blocks.push(table.block);
            index = table.nextIndex;
            continue;
        }

        const heading = line.match(/^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$/);
        if (heading) {
            blocks.push({
                type: "heading",
                level: heading[1].length,
                tokens: tokenizeMarkdownInline(heading[2]),
            });
            index += 1;
            continue;
        }

        if (/^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)) {
            blocks.push({ type: "hr" });
            index += 1;
            continue;
        }

        if (/^\s{0,3}>\s?/.test(line)) {
            const quote = [];
            while (index < lines.length) {
                const match = lines[index].match(/^\s{0,3}>\s?(.*)$/);
                if (!match) {
                    break;
                }
                quote.push(match[1]);
                index += 1;
            }
            blocks.push({ type: "blockquote", tokens: tokenizeMarkdownInline(quote.join(" ")) });
            continue;
        }

        const unordered = line.match(/^\s{0,3}([-+*])\s+(.+)$/);
        const ordered = line.match(/^\s{0,3}(\d+)[.)]\s+(.+)$/);
        if (unordered || ordered) {
            const isOrdered = Boolean(ordered);
            const items = [];
            const start = isOrdered ? Number(ordered[1]) : 1;
            while (index < lines.length) {
                const match = isOrdered
                    ? lines[index].match(/^\s{0,3}(\d+)[.)]\s+(.+)$/)
                    : lines[index].match(/^\s{0,3}([-+*])\s+(.+)$/);
                if (!match) {
                    break;
                }
                items.push(tokenizeMarkdownInline(match[2]));
                index += 1;
            }
            blocks.push({ type: "list", ordered: isOrdered, start, items });
            continue;
        }

        const paragraph = [line.trim()];
        index += 1;
        while (index < lines.length && !isBlockStart(lines, index)) {
            paragraph.push(lines[index].trim());
            index += 1;
        }
        blocks.push({ type: "paragraph", tokens: tokenizeMarkdownInline(paragraph.join(" ")) });
    }

    return blocks.map((block, blockIndex) => ({ ...block, key: blockIndex }));
}
