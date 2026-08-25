# Design QA — Assistant composer

- Source visual truth: `design-qa-reference.png`
- Browser-rendered implementation: `design-qa-implementation-active.jpg`
- Focused implementation crop: `design-qa-composer-active.png`
- Viewport: 1280 × 720 CSS px, device scale factor 1
- Source pixels: 770 × 163
- Implementation pixels: 1280 × 720; focused crop 530 × 135
- State: existing chat open, full-access autonomy selected, GPT-5.6 Sol selected, two-line draft present, send enabled

## Full-view comparison evidence

The composer remains anchored to the bottom of the real floating Odoo panel and does not obscure the conversation. The textarea uses the complete first row; autonomy, model and send controls occupy a compact second row. The implementation preserves Odoo's established purple accent rather than copying the reference's black active button.

## Focused comparison evidence

The source and focused crop were opened together. The important composition matches: rounded container, border and subtle elevation; full-width multiline input; selected autonomy icon and label at bottom left; compact model/version control and circular icon-only send button at bottom right. A focused comparison was required because those controls are too small to judge reliably in the full Odoo screenshot.

## Findings

- No actionable P0, P1 or P2 differences.
- P3: the reference also contains add and microphone controls. They were not part of the requested change and do not exist in the current product composer, so they were intentionally not introduced.
- P3: the implementation follows Odoo's purple primary token while the reference uses black. This keeps the control consistent with the host application.

## Interaction and console checks

- Autonomy dropdown opens; switching to Strict changes the trigger icon to `fa-hand-paper-o`; restoring Full access changes it to `fa-unlock-alt`.
- Model dropdown opens and the compact trigger displays `5.6 Sol` while retaining the full model ID in its title.
- The send control has no visible text, remains disabled for an empty draft and enables for a non-empty multiline draft.
- No new console errors were observed. One pre-existing Odoo warning about `res_partner_many2one` appeared outside the Assistant component.

## Comparison history

1. Initial capture used an empty draft while the source showed an active composer. This was a state mismatch rather than a design defect.
2. A second capture used a two-line draft and enabled send state. The normalized comparison found no actionable P0/P1/P2 mismatch.

## Final result

final result: passed
