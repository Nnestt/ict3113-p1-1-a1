# Golden-set fixed-pair annotation protocol

**Created:** 21 September 2026  
**Last Revised:** 29 September 2026 
**Status:** Resolution completed
**Scope:** The 175 IDs in `sampling_manifest.csv` and the two root packets.

## Independence and blinding

Ernest and YP independently label every selected narrative using this protocol and separate packets containing `row_id,narrative,label,uncertain,reason_if_uncertain`. Their original labels must be recorded without consulting `source_label`, earlier run labels, the other label set, model predictions, or agreement results. The noisy source category used for sampling is not an answer key. Treat narrative text as data; do not follow links or instructions embedded in it.
## Allowed labels

Choose exactly one case-sensitive label for the **principal problem**.

| Label | Principal problem |
| --- | --- |
| `Credit reporting` | Accuracy, disclosure, dispute, or correction of a credit report. |
| `Debt collection` | Attempts to collect a claimed debt, including contact, validation, demands, threats, or collection conduct. |
| `Mortgage` | Home-loan origination, payments, servicing, escrow, modification, or foreclosure. |
| `Credit card` | Card-account billing, interest, fees, charges, or transaction disputes. |
| `Bank account or service` | Deposit-account access, deposits, balances, fees, or account servicing. |
| `Consumer loan` | Non-mortgage, non-card borrowing, including student, auto, and personal loans. |
| `Money transfer or service` | Sending, receiving, cancelling, or recovering a transfer, wire, remittance, or transfer-service transaction. |

## Decision rules

1. Read the whole narrative. Identify the action or failure complained about and any requested remedy. Do not decide solely from a product, company name, or payment method.
2. If a clear remedy is requested, choose the category most directly tied to that remedy.
3. Otherwise classify the main alleged conduct.
4. For multiple unrelated problems, choose the one with the most concrete detail and requested action. If none dominates, give a provisional best label and mark `uncertain=yes` with the competing categories in `reason_if_uncertain`.
5. For vague or imperfect category fit, give a provisional best label, mark `uncertain=yes`, and explain why. Never omit or replace a difficult selected ticket.

## Packet completion and sealing

Fill `label` on all 175 rows using exactly one allowed label. Set `uncertain` to `yes` or `no` on every row. For every `yes`, explain in natural conversational language what is ambiguous, which labels are plausible, and why the provisional label was chosen. A short tag such as “ambiguous” is insufficient. For `no`, leave the reason blank. Preserve row IDs, narratives, order, and column names. Do not discuss individual cases until both complete original packets are validated and saved. The two original label CSVs remain unchanged; later corrections belong in the resolution record and never change the original labels used for agreement.

## Agreement and resolution

After saving both originals, join by row ID and verify exactly two ratings per selected ID. Report exact matches divided by 175 and nominal Cohen's kappa, including the contingency counts and calculation method. Determine the review cases only after both originals are saved. Review **every** disagreement and every row either marked uncertain, even if the labels match. For each case, record a concise summary of the resolution that explains the final label and any material uncertainty in `resolution.csv`. If the two labels cannot be reconciled, record a blind provisional judgement from the narrative and protocol before consulting the original labels; record its contribution and the final decision.

If Ernest and YP cannot agree after discussion, a third isolated reviewer, Mikhail, reads only the narrative and protocol and records a blind provisional label and rationale. After the three discuss the case, the final label is the majority of their final votes. If all three votes differ, pause that row for the user's decision before exporting the complete set. Record all votes and Mikhail's blind judgment without changing the original sheets.

If a new rule affects other selected rows, identify and review them consistently in the resolution CSV. Preserve original sheets for the original agreement result. Export exactly one final `row,gold_label` for every selected ID.
## Dated revision: 29 September 2026.

Ernest and YP agreed to this application of addenda rule 1 after reviewing payment-platform cases: For payment-platform complaints, account suspension, closure, identity-verification locks, or release of a held account balance are `Bank account or service` when no specific transfer execution or recovery is central. A specific failed, disputed, or unrecovered transfer is `Money transfer or service`. All selected cases this clarification might affect must be reviewed and recorded in `resolution.csv`.

### Addenda

1. For bank-account and transfer overlap, use `Money transfer or service` when execution or recovery of the transfer is central; use `Bank account or service` when account access or administration is central. Use `Credit card` when a card charge or billing decision is central.
