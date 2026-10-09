# Reconstruction comparison

Each cell: the layer's verdict for that question, scored against ground truth from the systems of record (`lineage/truth.py`). ✓ correct · partial = some parts unrecorded · — = not recorded at all · WRONG = a recorded answer that is false.

## L0 · Application logs

| scenario | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | correct | key joins | heuristic joins |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e01-success | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e02-tool-failure | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e03-policy-denial | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e04-human-rejection | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e05a-crash-awaiting-approval | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e05b-crash-after-dispatch | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e06-duplicate-delivery | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e07-unexpected-capability | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e08a-policy-v41 | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e08b-policy-v42 | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e09-config-v9 | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e10-restricted-data | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e11-false-success | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | WRONG | — | 9/13 | 4 | 1 |
| e12a-lost-response | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |
| e12b-lost-response-no-key | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 4 | 1 |

## L1 · Logs + traces

| scenario | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | correct | key joins | heuristic joins |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e01-success | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e02-tool-failure | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e03-policy-denial | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e04-human-rejection | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e05a-crash-awaiting-approval | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e05b-crash-after-dispatch | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e06-duplicate-delivery | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e07-unexpected-capability | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e08a-policy-v41 | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e08b-policy-v42 | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e09-config-v9 | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e10-restricted-data | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e11-false-success | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | WRONG | — | 9/13 | 5 | 0 |
| e12a-lost-response | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |
| e12b-lost-response-no-key | ✓ | partial | ✓ | partial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | 10/13 | 5 | 0 |

## L2 · Execution lineage

| scenario | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | correct | key joins | heuristic joins |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e01-success | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e02-tool-failure | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 1 | 0 |
| e03-policy-denial | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 1 | 0 |
| e04-human-rejection | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 1 | 0 |
| e05a-crash-awaiting-approval | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e05b-crash-after-dispatch | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e06-duplicate-delivery | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e07-unexpected-capability | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 1 | 0 |
| e08a-policy-v41 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e08b-policy-v42 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e09-config-v9 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e10-restricted-data | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e11-false-success | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e12a-lost-response | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 2 | 0 |
| e12b-lost-response-no-key | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13/13 | 1 | 0 |
