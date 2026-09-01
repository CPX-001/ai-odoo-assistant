# Chat workflow and activity repair — 2026-09-01

## Scope

This checkpoint addresses a general product failure, not a contacts/quotations special case:

- one prompt containing dependent operations stopped after its prerequisite;
- approved destructive plans could exhaust their claims before execution and remain stuck;
- a terminal turn could be restored as active, duplicating activity and error state;
- reasoning disappeared/reappeared, leaked raw Markdown headings and was not attached durably to its answer;
- the panel used nested cards, excessive spacing and an ambiguous expanded-by-default activity block.

## Implemented contract

`odoo.workflow.batch_create_graph` composes two to five ordered create batches inside one bounded
`CapabilityDefinition`. Later many2one fields can reference exact rows created by earlier steps. Odoo validates ACLs,
models, fields, types, relation targets and reference indices, executes the graph transactionally as the effective
user (`su=False`) and verifies every record. Independent bulk writes still use the existing batch capability.

The public request is an outcome, not an ORM recipe. An explicit prompt such as “create 10 test quotations” is
therefore expected to derive mandatory related records from effective schema and create the minimum coherent
synthetic prerequisites in the same workflow without requiring the user to mention contacts. The agent must not
reuse unrelated real records for test data; outside an explicit test/demo context, a material related-party choice
still requires clarification.

Approved turns receive at least one subsequent worker claim. Historical chat restoration returns only genuinely
nonterminal turns as active. Every settled Assistant message carries its own browser-safe semantic activity/readable
summary; it is rendered immediately above the answer, collapsed by default, and expands to a settings-driven
five-line scroll area. The only running animation is the semantic text wave and only one live disclosure exists per
conversation.

## Design evidence

The rendered panel was checked at 1366×768 in Odoo 18 against the supplied current-state and Codex references.

```text
panel                    544 × 672 px
message-area padding      14.4 px vertical / 16 px horizontal
conversation gap          16 px
user bubble               435.6 × 80.7 px; 8 × 11.2 px padding
settled activity header   495 × 25.3 px
expanded detail           112 px; overflow-y auto; exactly 5 visible lines
composer                  542 × 94.2 px
textarea                  456.6 × 32 px
```

The final render has no nested Assistant card, spinner, duplicate terminal error or visible raw
`**Planning ...**` entry. The activity header is a full-width quiet divider with a right caret when closed.

## Focused validation

```text
Odoo capability/action/storage classes   PASS — 24 counted tests, 0 failures/errors
active-turn storage regression           PASS — 5 counted tests, 0 failures/errors
HOOT focused filters                      PASS — 99 tests / 364 assertions
Python compile / JS syntax / XML parse    PASS
git diff --check                         PASS
browser render + collapsed/expanded QA   PASS
```

The full repository/periodic regression was not run because this checkpoint requires focused incremental validation
and the roadmap keeps the expensive suite as explicit validation debt. No provider turn or usage reset was consumed.

## External pattern review and RAG direction

Mature products converge on visible multi-step ownership with drill-down rather than dumping internal reasoning into
the main conversation. Lovable exposes progress tasks and a separate details view; Base44 workflows chain ordered
backend steps and record per-step outcomes. OpenAI Agents documents programmatic orchestration for loops/branching
without a model round trip for every inner call and serializable human approval state.

RAG should enter through the existing `ContextProvider` boundary. A future read-only Odoo context/evidence provider
can retrieve likely model/field/view/domain knowledge and company documentation with ACL/company binding,
provenance, freshness and cache identity. Contextual retrieval can combine semantic and lexical evidence. This should
reduce repetitive discovery calls, but cannot replace live authorization, capability validation, approval,
transactional execution or verification.

References:

- https://docs.lovable.dev/features/agent-mode
- https://docs.base44.com/Building-your-app/Creating-workflows
- https://openai.github.io/openai-agents-python/tools/
- https://openai.github.io/openai-agents-python/human_in_the_loop/
- https://www.anthropic.com/engineering/contextual-retrieval
