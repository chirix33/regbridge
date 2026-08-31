# M3 evaluation disclosure

RegBridge is an FDA/CDER-scoped research prototype and risk analyzer. FDA eCTD v4.0 forward
compatibility is currently recorded as **`not_operational`**. The benchmark is a controlled
prospective research scenario; it does not predict FDA acceptance and is not regulatory advice.

The 30 reference labels are `author_adjudicated_for_demo` by `author-01`, with
`expert_validated: false`. The 12-case held-out test set supplies headline tables; all-30 results
are secondary diagnostics. The held-out cases form six non-overlapping fixture families, but no
independence or statistical-significance claim is made.

The committed run is `deterministic_fixture_validation`. B0, B1, and RegBridge outputs are
synthetic contract fixtures (`empirical_model_run: false`) and are ineligible for performance or
superiority claims. B2 is the only genuine rule-only experimental output. Any later comparison of
model performance must use a separately declared live-model run with its own manifest.

## Table selection safeguards

Use `tables/deterministic/m3-b2-held-out.csv` for B2's genuine deterministic experimental
result. Do not copy the B0/RegBridge perfect scores or B1's 0.917 end-to-end accuracy from
`tables/validation/m3-held-out-validation.csv` into an empirical results table. Those canned
scores establish only that the harness and output contracts execute correctly. Every decision
table carries a `Result status` column (machine-readable `result_status`).

B1's BM25 retrieval is actually executed: recall@3, precision@3, and MRR are valid measured
retrieval results. Present `tables/retrieval/m3-bm25-held-out.csv` separately, with its evaluated
case count. The denominator excludes cases with no relevant official evidence span in the
six-span corpus; these measurements are not B1 end-to-end decision performance.

Wilson and bootstrap calculations for canned outputs remain in raw scorer JSON for testing
only, with no statistical interpretation. Presentation tables suppress those intervals. B2
intervals remain exploratory, without independence or significance claims.

B2's two unsafe misses occurred in one of the three held-out families containing
action-required cases (`c-applicant-mismatch`). There are six held-out families in total;
the other three contain no action-required cases. This is a descriptive family-level result,
not an independence claim or an estimate of FDA acceptance risk.
