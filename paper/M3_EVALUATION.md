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
