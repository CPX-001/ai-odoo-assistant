# Design QA — compact Assistant pickers

- Source visual truth: `C:/Users/Kiril/AppData/Local/Temp/codex-clipboard-8ae1e3b0-e0f8-4607-8f28-06296aa5c963.png`
- Implementation screenshot: `docs/research/evidence/phase5/2026-08-29/P5.7-COMPACT-PICKERS.png`
- Full comparison: `docs/research/evidence/phase5/2026-08-29/P5.7-COMPACT-PICKERS-COMPARISON.png`
- Focused comparison: `docs/research/evidence/phase5/2026-08-29/P5.7-COMPACT-PICKERS-FOCUS.png`

- Viewport: 954 × 609 CSS px, desktop, device scale factor 1.
- Source pixels: 954 × 609.
- Implementation pixels: 954 × 609.
- Density normalization: none required; both artifacts are 1× and pixel-aligned.
- State: Assistant open, empty conversation, model menu and GPT-5.6 variant submenu open.

## Full-view comparison evidence

The implementation intentionally replaces the reference's multi-line preference labels with one bottom control row. Model, reasoning and autonomy are 28 px-high pills; the send action stays right-aligned. The open model menu is reduced from roughly 446 px to 288 px while retaining model names and descriptions. The GPT-5.6 submenu is also smaller, retains Sol/Terra/Luna descriptions, removes selection ticks, and relies on Odoo's single submenu arrow plus a quiet selected-row background.

The Assistant occupies a different horizontal position because the reference and implementation were captured from different Odoo screen contexts. This does not affect the compared component geometry or interaction state.

## Focused comparison evidence

The focused comparison makes the dense control region readable at original scale. It confirms:

- the three closed controls occupy one compact row instead of multiple text rows;
- full names and explanatory copy remain available inside the menus;
- the model family has one submenu arrow and no check icon;
- Sol/Terra/Luna use compact letter tokens and a selected-row background;
- the send button remains visually separated at the right edge;
- menu text wraps without clipping or horizontal overflow.

## Required fidelity surfaces

- Fonts and typography: the implementation preserves Odoo's native UI font and weights. Pill labels use 0.7 rem/600; menu labels use 0.78 rem and descriptions use 0.7 rem with 1.25 line height. No observed clipping or illegible wrapping.
- Spacing and layout rhythm: pills are 28 px high on one grid row, with 0.35 rem horizontal gaps. Menus use smaller 0.45/0.55 rem option padding, 1.55 rem icon/token boxes and 0.65 rem radii. The composer remains 97.19 px high and does not overflow.
- Colors and visual tokens: existing Odoo surface, border, secondary text and brand tokens are reused. Selection uses a low-contrast brand tint instead of an added glyph.
- Image and icon fidelity: there are no custom raster assets in this control. Existing Font Awesome/Odoo icons are used; no inline SVG, CSS drawing or placeholder icon was introduced.
- Copy and content: complete model names, model descriptions, reasoning explanations and autonomy safety explanations remain in the open menus. The closed pills deliberately show bounded tokens only.

## Interaction and accessibility checks

- Opened model, reasoning and autonomy menus through real pointer events.
- Selected GPT-5.6 Terra, `Alto` reasoning and `Estricto` autonomy through the rendered UI, then restored the original preferences.
- Confirmed visible reasoning choices stop at `Alto`; `Muy alto`, `Máximo` and `Ultra` are absent.
- Confirmed the model menu contains zero check icons and zero custom right-arrow icons.
- Confirmed native accessible names and full-value `title` text remain on every pill.
- Confirmed zero browser runtime/log errors.

## Comparison history

1. Initial compact pass: `P2` — the send button started immediately after the pills because its grid item was aligned to the start of the flexible column.
2. Fix: added `justify-self: end` to the send action and rebuilt Odoo assets.
3. Post-fix capture: the send button is aligned to the right edge; all three pills remain aligned at 28 px and no P0/P1/P2 issue remains.

## Findings

No actionable P0, P1 or P2 visual mismatch remains for the requested compact-picker redesign.

## Follow-up polish

No required P3 follow-up. A future localization pass may replace provider-authored English model descriptions if the provider supplies localized metadata.

final result: passed
