# Golden test set

The 175-ticket golden test set for ICT3113 Team 1, labelled independently by Ernest and YP.

| File | Contents |
| --- | --- |
| `gold_labels.csv` | The golden test set: one final `row,gold_label` per selected ticket. |
| `protocol.md` | Labelling protocol: seven labels, decision rules, resolution procedure, and the dated payment-platform revision. |
| `ernest-packet.csv`, `yp-packet.csv` | The two independent label sheets (`row_id,narrative,label,uncertain,reason_if_uncertain`). |
| `agreement.md` | Agreement statistic on the original labels: 165/175 exact matches (0.942857), nominal Cohen's kappa 0.932819, 51 review cases. |
| `resolution.csv` | Decision and explanation for each of the 51 review cases: every disagreement and every row either rater marked uncertain. |
| `ict3113_tickets.csv` | The 50,000-row source extract (`row,source_label,narrative`) that the draw is taken from. Too large for the repository, so it is git-ignored: place it in this folder to rerun the selection notebook. |
| `selection_seed.json` | The saved random seed for the draw. |
| `selection_and_packets.ipynb` | Data exploration, the seeded stratified draw (25 per source category), and packet formation. Reads `ict3113_tickets.csv` from this folder. |
| `analysis_and_agreement.ipynb` | Derives the agreement statistic, review cases and final labels from the CSVs; compares source labels with the golden labels; and discusses results. |
| `artifacts/` | `sampling_manifest.csv` (the 175 selected row IDs, written by the selection notebook), `review_list.csv` (written by the analysis notebook: the 51 review cases with both raters' answers side by side, for the reviewers' ease of reference), and `source_vs_gold.csv` (written by the analysis notebook: each selected ID's raw source label beside its golden label). |

Rerunning `selection_and_packets.ipynb` after labelling only verifies the packets; it never overwrites them.
