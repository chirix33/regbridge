# M3 deterministic fixture validation

> These outputs are `deterministic_fixture_validation`, not empirical model results, and are ineligible for RegBridge-superiority or model-performance claims. Only B2 is a genuine rule-only experimental output. FDA availability remains `not_operational`.

Labels are controlled prospective `author_adjudicated_for_demo` research labels with `expert_validated: false`.

## Headline: 12 held-out cases

| System | Unsafe FNR (n/N) | 95% Wilson interval | Review bypass | Macro-F1 | Accuracy |
|---|---:|---:|---:|---:|---:|
| B0 | 0.000 (0/8) | 0.000-0.324 | 0.000 | 1.000 | 1.000 |
| B1 | 0.000 (0/8) | 0.000-0.324 | 0.000 | 0.915 | 0.917 |
| B2 | 0.250 (2/8) | 0.071-0.591 | 0.500 | 0.822 | 0.833 |
| RegBridge | 0.000 (0/8) | 0.000-0.324 | 0.000 | 1.000 | 1.000 |

Family-clustered intervals are exploratory. No independence or significance claims are made.
All six non-overlapping held-out families are included in cluster resampling; zero-denominator replicates are omitted.

| System | Held-out family | Unsafe misses | Action-required cases |
|---|---|---:|---:|
| B0 | a-removed-3212-lifecycle | 0 | 2 |
| B0 | a-valid-321-lifecycle | 0 | 0 |
| B0 | b-manufacturer-all-normalization | 0 | 4 |
| B0 | c-applicant-mismatch | 0 | 2 |
| B0 | c-clean-current | 0 | 0 |
| B0 | c-relevant-internal-link | 0 | 0 |
| B1 | a-removed-3212-lifecycle | 0 | 2 |
| B1 | a-valid-321-lifecycle | 0 | 0 |
| B1 | b-manufacturer-all-normalization | 0 | 4 |
| B1 | c-applicant-mismatch | 0 | 2 |
| B1 | c-clean-current | 0 | 0 |
| B1 | c-relevant-internal-link | 0 | 0 |
| B2 | a-removed-3212-lifecycle | 0 | 2 |
| B2 | a-valid-321-lifecycle | 0 | 0 |
| B2 | b-manufacturer-all-normalization | 0 | 4 |
| B2 | c-applicant-mismatch | 2 | 2 |
| B2 | c-clean-current | 0 | 0 |
| B2 | c-relevant-internal-link | 0 | 0 |
| RegBridge | a-removed-3212-lifecycle | 0 | 2 |
| RegBridge | a-valid-321-lifecycle | 0 | 0 |
| RegBridge | b-manufacturer-all-normalization | 0 | 4 |
| RegBridge | c-applicant-mismatch | 0 | 2 |
| RegBridge | c-clean-current | 0 | 0 |
| RegBridge | c-relevant-internal-link | 0 | 0 |

## Secondary diagnostic: all 30 cases

| System | Unsafe FNR | Macro-F1 | Accuracy |
|---|---:|---:|---:|
| B0 | 0.000 | 1.000 | 1.000 |
| B1 | 0.000 | 0.877 | 0.900 |
| B2 | 0.217 | 0.855 | 0.833 |
| RegBridge | 0.000 | 1.000 | 1.000 |
