# P11 post-acceptance spreadsheet/chat import extension

Date: 2026-09-03  
Status: **IMPLEMENTED / FOCUSED VALIDATION PENDING**

P11 was already accepted as a create-only CSV core. This is a post-acceptance breadth
extension prompted by a product-path defect: the chat attachment control and temporary
attachment model still inherited the P9 Knowledge document allowlist, so an `.xlsx`
file could not reach the accepted P11 import workflow at all.

This record does not rewrite P11 acceptance evidence. The accepted CSV evidence remains
immutable; spreadsheet breadth has its own validation debt.

## Problem

The UI accepted only document/text formats and CSV. The backend temporary attachment
model immediately validated every upload as a Knowledge document. Separately, P11's
import seam required `text/csv` even though Odoo `base_import` supports native Excel
input.

That made the product contradictory: durable imports existed, but a user could not
attach the most common spreadsheet format to ask the Assistant to import it.

## Implementation

The chat attachment boundary now accepts temporary tabular artifacts:

```text
.csv
.xls
.xlsx
.ods
```

Spreadsheet attachments remain short-lived turn artifacts. They are not silently
indexed into Company Knowledge. P9 Knowledge source ingestion keeps its existing
document-format contract.

The import preparation path delegates native parsing to Odoo 18 `base_import`, then
normalizes the selected mapped rows into the same accepted P11 staged representation.
After staging, durable workers still execute bounded canonical CSV chunks, so cursor,
receipt and no-replay semantics remain unchanged.

Format-neutral capability aliases were added:

```text
assistant.data_import.inspect_file
assistant.data_import.start_file
```

The original `inspect_csv` / `start_csv` ids remain for compatibility.

## Authority invariants

- attachment belongs to the current user/company/turn;
- extension and MIME are host-validated;
- target model and fields remain effective-user validated;
- no binary workbook/base64 is dumped into the model prompt;
- model mapping is still restricted to the safe field set;
- business writes still run under the originating effective user with `su=False`;
- a spreadsheet does not become Knowledge merely because it was attached;
- imports remain create-only under the accepted P11 scope.

## Focused validation required

Prepared Odoo coverage:

```text
TestPhase11SpreadsheetImport
```

It must prove at minimum:

1. browser/backend temporary `.xlsx` upload is accepted and canonicalized;
2. the attachment binds to the durable turn;
3. generic inspect returns native headers/examples/mapping evidence;
4. a two-row workbook imports through two durable chunks without replay;
5. the spreadsheet is not automatically persisted as Knowledge;
6. prior CSV focused coverage remains green.

The browser file-input `accept` list must also be checked on the actual chat composer.
No spreadsheet PASS claim exists until those checks execute.
