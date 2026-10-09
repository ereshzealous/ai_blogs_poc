# Scenario results

| scenario | group | outcome | production changes | attempts reaching the API | agent processes | evidence events | L0 | L1 | L2 |
|---|---|---|---|---|---|---|---|---|---|
| e01-success | happy path | MITIGATED | 1 | 1 | 1 | 27 | 10/13 | 10/13 | 13/13 |
| e02-tool-failure | runtime failures | FAILED_NO_EFFECT | 0 | 3 | 1 | 31 | 10/13 | 10/13 | 13/13 |
| e03-policy-denial | governance failures | DENIED | 0 | 0 | 1 | 20 | 10/13 | 10/13 | 13/13 |
| e04-human-rejection | governance failures | REJECTED | 0 | 0 | 1 | 22 | 10/13 | 10/13 | 13/13 |
| e05a-crash-awaiting-approval | runtime failures | MITIGATED | 1 | 1 | 2 | 28 | 10/13 | 10/13 | 13/13 |
| e05b-crash-after-dispatch | runtime failures | MITIGATED | 1 | 1 | 2 | 28 | 10/13 | 10/13 | 13/13 |
| e06-duplicate-delivery | side-effect ambiguity | MITIGATED | 1 | 2 | 1 | 29 | 10/13 | 10/13 | 13/13 |
| e07-unexpected-capability | governance failures | DENIED | 0 | 0 | 1 | 21 | 10/13 | 10/13 | 13/13 |
| e08a-policy-v41 | version drift | MITIGATED | 1 | 1 | 1 | 26 | 10/13 | 10/13 | 13/13 |
| e08b-policy-v42 | version drift | MITIGATED | 1 | 1 | 1 | 27 | 10/13 | 10/13 | 13/13 |
| e09-config-v9 | version drift | MITIGATED | 1 | 1 | 1 | 27 | 10/13 | 10/13 | 13/13 |
| e10-restricted-data | governance failures | MITIGATED | 1 | 1 | 1 | 28 | 10/13 | 10/13 | 13/13 |
| e11-false-success | side-effect ambiguity | EFFECT_NOT_OBSERVED | 0 | 1 | 1 | 27 | 9/13 | 9/13 | 13/13 |
| e12a-lost-response | side-effect ambiguity | MITIGATED | 1 | 2 | 1 | 29 | 10/13 | 10/13 | 13/13 |
| e12b-lost-response-no-key | side-effect ambiguity | MITIGATED | 2 | 2 | 1 | 29 | 10/13 | 10/13 | 13/13 |
