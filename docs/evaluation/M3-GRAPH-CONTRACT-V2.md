# M3 graph contract v2 and live-run integrity correction

This is a declared M3 development-contract correction. It does not change frozen benchmark
bytes, labels, fixture families, split assignments, FDA operational availability
(`not_operational`), or `expert_validated: false`. Prior fixture-validation and live-run
artifacts remain retained and are not rewritten.

## Graph correction

The saved first RegBridge response for B003 correctly cited the supplied manufacturer metadata
occurrence. Graph schema v1 incorrectly materialized that occurrence as a `KEYWORD`, making the
otherwise correct citation fail the `MODEL_FINDING --CITES--> DOSSIER_EVIDENCE` domain/range
contract. The corrected graph is:

```text
MODEL_FINDING --CITES--> DOSSIER_EVIDENCE
MODEL_FINDING --ABOUT--> KEYWORD
DOSSIER_EVIDENCE --OBSERVES--> KEYWORD
```

Each dossier-evidence node is an exact occurrence carrying server-side raw value, owner,
locator, file digest, extraction method, and durable evidence ID. The model receives only a
request-local alias. It never receives these durable identity fields. A direct
`CITES → KEYWORD` edge remains invalid, and `ABOUT` without an occurrence citation is invalid.
For the M3 metadata rule, `ABOUT` must exactly equal the keyword observed by cited metadata
evidence. No cross-concept relationship is currently encoded.

`CITES` and `ABOUT` remain disabled `candidate` semantic signals. They cannot promote a model
finding, cited evidence, or keyword to source-verified or author-adjudicated status, and they
cannot independently produce a hard outcome.

The untouched B003 first response from run
`m3-live-phase1-20260831T225610474936Z` now replays successfully. It yields a candidate finding
that cites the exact manufacturer occurrence, is about `keyword-manufacturer-all`, and agrees
with the occurrence's `OBSERVES` target. The contaminated second response remains untouched and
is not reused.

Case B regression coverage constructs a metadata finding for all ten frozen Case B records and
commits each graph successfully. Case A records without extracted dossier occurrences cannot
form a schema-valid semantic finding because a finding requires supplied evidence. Every Case A
or C record with an extracted occurrence uses the same `CITES → DOSSIER_EVIDENCE` range and
commits without the prior metadata retyping failure.

## Retry and persistence correction

Only transport failures and provider-API failures are retryable. Refusal, schema, citation,
graph, persistence, synthesis, incomplete-response, and final-answer-length failures are
non-retryable. A downstream failure changes the case outcome to `invalid_output`, records a
non-null stage/type cause, halts the phase, and cannot issue another paid request. Failed
attempts with null causes are rejected before artifact publication. Transactional persistence
is rolled back, and graph construction occurs before the repository is called.

Terminal state, stop reason, RegBridge completeness, comparison status, and the Phase 2 cap
status are derived from the same validated outcome records used by the audit and scorer. A
failed audit cannot coexist with a null stop reason or a Phase 2 cap proposal. Running snapshots
use `.partial` artifact names; terminal artifacts are published separately.

## Direct versus semantic severity

The observed B0 value `"severity":"unresolved"` was produced under
`DirectDecisionOutput`. It is intended there as final decision-level uncertainty accompanying a
human-review decision. The informational/low/medium/high restriction applies only to
`SemanticFinding`, whose output remains a non-enforceable semantic signal. Both boundaries have
explicit regression tests; no severity was remapped.

## Defect acceptance record

Acceptance is based on defect cessation, not metric movement.

| Defect | Before | Corrected contract check |
|---|---:|---:|
| Downstream graph/persistence failure followed by an unauthorized retry | 1 | 0 |
| Retry records with a null cause | 1 | 0; rejected at write time |
| Contaminated downstream-retry outcome recorded as bare valid prediction | 1 | 0; structurally rejected |
| B003 correct manufacturer citation rejected by graph domain/range | 1 | 0; untouched first response replays |
| Frozen Case B records whose metadata finding cannot commit | Contract covered 0/10 safely | 10/10 commit |
| Known summary/audit contradictions | 3 | 0 in derived-state tests |
| Metadata requests leaking tested case/fixture/UUID/locator/durable evidence IDs | 14/18 before contract v2 | 0 in corrected alias regressions |

Fresh Phase 1 before/after decision metrics remain diagnostics only and are recorded in the
new live run. They are never acceptance criteria for these fixes. Held-out data remains outside
the live development runner, and no prompt freeze is created here.

## Declared configuration and digest change

The author-approved development configuration is
`m3-live-phase1-gpt-5.5-contract-v3-graph-v2`, with configuration SHA-256
`e374ded10e622ee1e6dfd3be982b4510e8e7d581d9b40e12679a6ad06045bbb0` and prompt-packet digest
`e7e140da12fe33c91e5203a9e070d27037fa755d0b12ad9305bfa970dbb04167`.
The approval record is `data/evaluation/phase1-v3-approval.json`. This is development-only
authorization; held-out execution and prompt freezing remain false.

The direct prompt, semantic prompt, system instructions, direct schema, semantic schema,
direct serializer, and shared vocabulary component digests did not change from run
`m3-live-phase1-20260831T225610474936Z`. The `semantic_serializer` digest did change—from
`ef9783783aa8ddfde1eb7b0559f2feea2f23192312cc249f2de325770b80f4be` to
`9e1f5d50efe6b6457e310430c9c9efaaf20c5ffcca5a5bc4df175ea50d05d586`—because the digest scope
was corrected from the whole analyzer service to the actual model-facing serialization module.
The serialized semantic packet behavior did not change. The broader configuration digest also
changes because graph schema, evidence identity, retry classification, pipeline persistence,
and summary derivation are now explicit inputs.
