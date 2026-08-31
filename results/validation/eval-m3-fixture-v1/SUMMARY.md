# M3 deterministic fixture validation

> These outputs are `deterministic_fixture_validation`, not empirical model results, and are ineligible for RegBridge-superiority or model-performance claims. Only B2 is a genuine rule-only experimental output. FDA availability remains `not_operational`.

Labels are controlled prospective `author_adjudicated_for_demo` research labels with `expert_validated: false`.

## M3 harness validation: 12 held-out cases

B0/B1/RegBridge decision scores confirm harness and contract execution only. They are not empirical results and must not enter the paper's empirical results table.

| System | Result status | Unsafe FNR (n/N) | Wilson 95% (B2 only) | Review bypass | Macro-F1 | Accuracy |
|---|---|---:|---:|---:|---:|---:|
| B0 | fixture validation only | 0.000 (0/8) | not interpreted | 0.000 | 1.000 | 1.000 |
| B1 | fixture validation only | 0.000 (0/8) | not interpreted | 0.000 | 0.915 | 0.917 |
| B2 | genuine deterministic experimental output | 0.250 (2/8) | 0.071-0.591 | 0.500 | 0.822 | 0.833 |
| RegBridge | fixture validation only | 0.000 (0/8) | not interpreted | 0.000 | 1.000 | 1.000 |

Wilson and bootstrap calculations for canned outputs are retained only in raw scorer data for testing; they have no statistical interpretation. B2 intervals are exploratory only. No independence or significance claims are made.
All six non-overlapping held-out families are included in cluster resampling; zero-denominator replicates are omitted.

| System | Result status | Held-out family | Unsafe misses | Action-required cases |
|---|---|---|---:|---:|
| B0 | fixture validation only | a-removed-3212-lifecycle | 0 | 2 |
| B0 | fixture validation only | a-valid-321-lifecycle | 0 | 0 |
| B0 | fixture validation only | b-manufacturer-all-normalization | 0 | 4 |
| B0 | fixture validation only | c-applicant-mismatch | 0 | 2 |
| B0 | fixture validation only | c-clean-current | 0 | 0 |
| B0 | fixture validation only | c-relevant-internal-link | 0 | 0 |
| B1 | fixture validation only | a-removed-3212-lifecycle | 0 | 2 |
| B1 | fixture validation only | a-valid-321-lifecycle | 0 | 0 |
| B1 | fixture validation only | b-manufacturer-all-normalization | 0 | 4 |
| B1 | fixture validation only | c-applicant-mismatch | 0 | 2 |
| B1 | fixture validation only | c-clean-current | 0 | 0 |
| B1 | fixture validation only | c-relevant-internal-link | 0 | 0 |
| B2 | genuine deterministic experimental output | a-removed-3212-lifecycle | 0 | 2 |
| B2 | genuine deterministic experimental output | a-valid-321-lifecycle | 0 | 0 |
| B2 | genuine deterministic experimental output | b-manufacturer-all-normalization | 0 | 4 |
| B2 | genuine deterministic experimental output | c-applicant-mismatch | 2 | 2 |
| B2 | genuine deterministic experimental output | c-clean-current | 0 | 0 |
| B2 | genuine deterministic experimental output | c-relevant-internal-link | 0 | 0 |
| RegBridge | fixture validation only | a-removed-3212-lifecycle | 0 | 2 |
| RegBridge | fixture validation only | a-valid-321-lifecycle | 0 | 0 |
| RegBridge | fixture validation only | b-manufacturer-all-normalization | 0 | 4 |
| RegBridge | fixture validation only | c-applicant-mismatch | 0 | 2 |
| RegBridge | fixture validation only | c-clean-current | 0 | 0 |
| RegBridge | fixture validation only | c-relevant-internal-link | 0 | 0 |

B2 unsafe misses occurred in 1 of the 3 held-out families containing action-required cases (six held-out families total).

## Measured B1 BM25 retrieval — held-out cases

These are actual deterministic retrieval measurements, separate from B1's non-empirical end-to-end decision accuracy. Cases without an official relevant span in the six-span corpus are excluded from retrieval denominators.

| Component | Result status | Evaluated cases | Recall@3 | Precision@3 | MRR |
|---|---|---:|---:|---:|---:|
| B1 BM25 | genuine deterministic retrieval measurement | 7 | 0.702 | 0.476 | 1.000 |

## Secondary diagnostic: all 30 cases

| System | Result status | Unsafe FNR | Macro-F1 | Accuracy |
|---|---|---:|---:|---:|
| B0 | fixture validation only | 0.000 | 1.000 | 1.000 |
| B1 | fixture validation only | 0.000 | 0.877 | 0.900 |
| B2 | genuine deterministic experimental output | 0.217 | 0.855 | 0.833 |
| RegBridge | fixture validation only | 0.000 | 1.000 | 1.000 |
