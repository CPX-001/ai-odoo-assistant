# P5 response-language policy

Date: 2026-08-29  
Status: planned product contract; no current implementation claim  
Primary roadmap ownership: P5.6 `ConversationContextManager` + P5.7 conversation-scoped preferences  
Current P5.4/P5.5 work: not blocked by this document

## Problem

A multilingual conversation can contain old messages, quoted text, code, documents or explicit translation tasks in several languages. Letting the reasoning model infer the reply language from the whole prompt/history can therefore make the Assistant drift into a language that the user did not intend.

The final product should resolve a response language deliberately instead of treating whichever language dominates accumulated context as an accidental instruction.

## Product rule

Resolve one **response-language preference for the current turn** before generating the final answer. Conversation history may provide evidence, but it must not override a newer explicit user instruction or an established preference merely because older context contains more text in another language.

The initial precedence should be evaluated in this order:

1. **Explicit current-turn instruction** — e.g. `respóndeme en inglés`, `answer in French`, or an explicit target-language requirement for the requested output.
2. **Explicit conversation-scoped preference** — e.g. `a partir de ahora háblame en alemán`.
3. **Configured Assistant/user preference** — a user-selectable preferred response language in Odoo settings.
4. **Language of the latest substantive user message** when no stronger preference exists.
5. **Previously resolved conversation language** for language-neutral/too-short turns such as `ok`, `sí`, `continue`, record identifiers or isolated numbers.
6. **Odoo user language / installation default** as the final fallback.

A language detected in quoted material, code, logs, source snippets, retrieved evidence or an attached document must not by itself switch the Assistant response language.

## Translation and mixed-language requests

The system must distinguish the language **being discussed or transformed** from the language in which the Assistant should explain itself.

Examples:

- A Spanish user asking `traduce este texto al francés` may require the translated artifact in French while surrounding explanation remains Spanish unless the user asked otherwise.
- A Spanish prompt containing a long English traceback should not make the Assistant answer in English merely because English dominates token count.
- An English conversation followed by `a partir de ahora contéstame en español` must switch immediately and persist for later turns until changed.

Do not implement a naive `majority language of entire conversation` rule.

## Ambiguity handling

Do not ask for language confirmation on every mixed-language turn. Clarification is appropriate only when the intended response language is genuinely ambiguous and the choice materially affects the requested output.

If clarification is needed, ask directly which language the user prefers and allow that answer to become a conversation-scoped preference when appropriate.

Short or language-neutral follow-ups should normally inherit the previously resolved conversation language rather than trigger a new guess.

## Configuration

P5.7 should expose a user-facing preference with at least:

```text
Automatic / follow conversation
Odoo user language
Explicit fixed language
```

A conversation may temporarily override the user default through an explicit host-owned preference transition. The user/admin configuration remains the durable default for new conversations.

The exact UI and persistence model should be chosen when P5.7 is implemented after inspecting the then-current preference infrastructure; this document does not require a new parallel settings subsystem.

## P5.6 ConversationContextManager responsibility

P5.6 should carry bounded language state alongside other conversation/session context, for example:

```text
resolved_response_language
resolution_source
conversation_language_preference
last_substantive_user_language
```

These are product/context facts, not execution authority. Full messages remain history authority and summaries must not silently change the resolved response language.

The language state supplied to the reasoning provider should be compact and explicit so that multilingual history does not leave the provider guessing which language to use.

## Turn stability

Once a turn has resolved its response language, later preference changes should affect future turns rather than mutate the already-running turn. This follows the P5.3 stable-turn-settings principle, although the exact persistence/snapshot representation should be decided during P5.6/P5.7 rather than retrofitted prematurely.

## Implementation guidance

Prefer a small host-owned resolver over adding a heavy language framework immediately. Inputs may combine deterministic preference state with bounded language detection of the latest substantive user message.

Do not add a new dependency solely for language detection until multilingual evals show that a lightweight/local implementation is insufficient.

The reasoning model may help interpret explicit natural-language instructions, but host state must remain the source of truth for a persisted conversation/user preference. Model inference alone must not silently rewrite a durable preference.

## Required deterministic/eval coverage

P5.6/P5.7 acceptance should add multilingual cases covering at least:

- Spanish prompt -> Spanish answer by automatic resolution;
- English prompt after Spanish history -> English when no fixed preference exists;
- explicit `answer in X` overrides prior conversation language for that turn;
- explicit `from now on use X` persists to later turns;
- user fixed-language preference survives multilingual history;
- quoted foreign text does not switch reply language;
- code/log/source text in another language does not switch reply language;
- translation target language is not confused with explanation language;
- mixed-language ambiguous request asks a concise clarification only when necessary;
- language-neutral follow-ups inherit the resolved conversation language;
- switching conversations does not leak language preference across scopes;
- a queued/running Turn A keeps its resolved language after the preference changes for future Turn B;
- rolling summary/context compaction cannot cause language drift.

## Real product-path gate

Add a Phase 5 hard real gate when P5.6/P5.7 are implemented:

```text
P5-REAL-LANGUAGE-PREFERENCE
```

The gate should exercise the real Odoo Assistant UI with at least one multilingual conversation, an explicit language switch, a short neutral follow-up, and a second conversation to prove scope isolation.

## Roadmap placement

This is deliberately **not** part of P5.4 final activity/answer/failure presentation and should not expand that validation slice. It belongs primarily to:

```text
P5.6 ConversationContextManager
  -> resolve/carry compact response-language state

P5.7 Conversation-scoped preferences
  -> durable user default + explicit temporary conversation override
```

P5.5 post-effect reasoning should consume the same resolved turn language once this contract exists, so the post-effect natural answer cannot unexpectedly switch language after execution/verification.
