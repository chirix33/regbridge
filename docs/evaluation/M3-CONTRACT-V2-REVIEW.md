# M3 development contract v2 — author approval checkpoint

No new live calls have been made. No held-out data has been loaded, no prompt freeze has
occurred, and Phase 2 remains inactive. FDA availability is `not_operational` and
`expert_validated: false`. Current development diagnostics cannot support cross-system
comparison. The prior failed A009 output and all raw historical outputs are unchanged.

## Root cause reported before implementation

The v1 direct `action` schema used `StableId` with
`^[A-Za-z0-9][A-Za-z0-9._-]*$` and no action enum. Strict structured generation therefore
permitted arbitrary identifier-shaped strings but prohibited spaces. The instructions gave
no canonical action choices. The corrupted actions are already in saved raw final JSON;
there is no downstream text-squashing operation. This establishes the defective schema and
generation constraint. Constrained prose is the supported mechanism; the exact malformed
syllables cannot be causally reconstructed without another experiment. The correction is
an explicit shared action enum, not a wider free-text field. OpenAI documents that
[Structured Outputs constrains output to the supplied schema](https://developers.openai.com/api/docs/guides/structured-outputs).

The UUID `78763013-836c-4015-bbb1-80dd2471b959` in B1's A001 action was checked against a
reconstructed request whose SHA-256 matched the saved attempt. It is absent from the request
input, schema, instructions, and isolated case input; it first occurs in raw model output.
This is unsupported identifier generation, not demonstrated internal-identifier copying.
Separately, original semantic requests did contain case/leaf-derived evidence IDs and
locators. Request-local aliasing now removes these, and UUID-bearing generated output is
rejected rather than accepted as an action or asserted identifier.

## Proposed shared action vocabulary — approval requested

These are the exact existing action codes, extracted from analyzer `RepairAction` constructors
and `data/rules/heading-rules.yaml` / `metadata-rules.yaml`. Tests compare the enum to that
source-derived set. No reference labels, model outputs, case mappings, or expected-action
hints determine this vocabulary. All codes remain available together to every system;
there are no case- or decision-conditioned restrictions.

| Action code | Existing meaning | Source |
|---|---|---|
| `AUTHOR_REVIEW_HEADING_MAPPING` | Author review of the evidence for an unsupported heading mapping. | Analyzer |
| `CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT` | New context and suspended legacy placement, retaining identifier reuse. | Heading rule |
| `CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD` | New context and suspended old group for declared metadata normalization. | Metadata rule |
| `DECLARE_MANUFACTURER_PARTITIONING` | Specify whether manufacturer differentiation is needed. | Analyzer |
| `DECLARE_METADATA_MIGRATION_INTENT` | Declare preservation versus normalization intent. | Analyzer |
| `HUMAN_VERIFY_STALE_CONTENT` | Human verification of potentially stale text or references. | Analyzer |
| `NO_MATERIAL_REPAIR` | No material repair identified within the scoped evidence. | Analyzer |
| `PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS` | Preserve the existing context group's exact keyword codes/values. | Metadata rule |
| `SELECT_SUPPORTED_REUSE_OPERATION` | Select supported identifier reuse or obtain review for another operation. | Analyzer |
| `VERIFY_HYPERLINK_RELEVANCE` | Human verification of hyperlink relevance to the target context. | Analyzer and metadata rule |
| `WAIT_FOR_OPERATIONAL_AVAILABILITY` | Report operational unavailability and wait for an operational pathway. | Analyzer |

The two context-creation codes remain distinct to preserve existing repair semantics and
reference-action compatibility; neither is renamed or merged. No new lifecycle-break or
non-reuse action is invented. All six primary decisions nevertheless remain permissible.
There is no schema-level decision/action mapping that would reveal the reference distribution.

B0/B1 `DirectDecisionOutput.action`, all-system `SystemPrediction.action`, and RegBridge/B2
`RepairAction.type` use this identical enum. The RegBridge semantic request receives the
same full six-decision and 11-action lists, but continues to produce evidence-bounded
semantic findings; deterministic synthesis owns the final decision/repair. The shared lists
contain codes only, not this provenance table or rule predicates. Existing prompt sentences
are unchanged; the vocabulary packet and corrected schemas are declared contract changes.

## Before/after defect validation

| Named defect and measurement | Before | After local correction | Acceptance basis |
|---|---:|---:|---|
| Runtime-prohibited semantic severities allowed by wire schema | 2 | 0 | Exhaustive enum check; validator remains a second boundary. |
| B0/B1 action fields lacking a canonical enum | 2 | 0 | Identical source-derived enum across final output schemas. |
| Isolated semantic candidate packets containing case-derived identifiers | 14/18 | 0/18 | Same isolated evidence serialized before/after; no inference. |
| Shared direct case packets containing tested internal identifiers | 0/18 | 0/18 | Old saved queries and new packet inspection; synthetic injections test UUIDs and locators too. |
| Noncanonical actions in the old live B0/B1 outputs | 36/36 | Not measured live | New enum rejects such strings; future live invalid-output counts must remain visible. |

Schema success is not evidence of improved model reasoning. Old failed responses still fail
the corrected contract; they were neither edited nor reclassified. After-live defect counts
and metrics are explicitly null until the vocabulary is approved and a new run executes.
Synthetic tests cannot establish that every future response will be valid.

Run the network-free audit with:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.contract_audit
```

It writes `results/live/contract-v2-review/defect-audit.json` and
`development-configuration.json`. The configuration identifies both schemas, serializers,
the shared vocabularies, scorer, model settings, and input/output bounds. It is declared but
not executed, and is not a Phase 2 prompt freeze.

Declared configuration: `m3-live-phase1-gpt-5.5-contract-v2`.
Configuration SHA-256:
`6cf16e5dbba0d74dae44a1e2fd82d46b4c8fbc25a67479d7917e24d4c8c42685`.
The 18 B0 model-facing inputs are below 16,000 characters (maximum 5,615), including
wrapper instructions and the full corrected JSON schema. No input truncation was used.

Verification: 47 focused network-free tests passed (Phase 1, contract integrity/corrections,
and the compatible adapter), along with backend lint, type checking of 73 files, and schema
export/drift checks. The full benchmark suites and all live model calls were intentionally
not run. These checks establish contract behavior, not live model quality.

## Metrics audit — historical, not a cross-system comparison

Rescoring the unchanged saved baseline predictions under explicit option (a) leaves accuracy
and macro-F1 unchanged. This verifies scorer behavior; it is not after-correction inference.
Neither metric improvement nor lack of improvement is an acceptance criterion.

### B0 historical diagnostics

| Scope | Before accuracy / macro-F1 | Same predictions rescored | Fresh after-run metrics | Unsafe-FNR | Review bypass |
|---|---|---|---|---|---|
| Train | 0.333 / 0.333 | unchanged | unavailable | 0/10 | 3/6 |
| Development | 0.333 / 0.190 | unchanged | unavailable | 0/5 | 2/4 |
| Combined | 0.333 / 0.299 | unchanged | unavailable | 0/15 | 5/10 |

Outside-class predictions: 5/18 (27.78%), comprising metadata repair 3/18 (16.67%), lifecycle
break 2/18 (11.11%), and non-reuse 0/18. Sensitivity-only accuracy excluding those five is
6/13 (0.462); primary accuracy remains 6/18 (0.333).

### B1 historical diagnostics

| Scope | Before accuracy / macro-F1 | Same predictions rescored | Fresh after-run metrics | Unsafe-FNR | Review bypass |
|---|---|---|---|---|---|
| Train | 0.333 / 0.311 | unchanged | unavailable | 0/10 | 3/6 |
| Development | 0.333 / 0.222 | unchanged | unavailable | 0/5 | 2/4 |
| Combined | 0.333 / 0.282 | unchanged | unavailable | 0/15 | 5/10 |

Outside-class predictions: 6/18 (33.33%), comprising metadata repair 3/18 (16.67%), lifecycle
break 0/18, and non-reuse 3/18 (16.67%). Sensitivity-only accuracy excluding those six is
6/12 (0.500); primary accuracy remains 6/18 (0.333).

Neither baseline predicted `REUSE_AS_LEGACY_REFERENCE`. A zero unsafe-FNR therefore does
not establish safety; both bypassed required review in five of ten HUMAN reference cases.
Split-specific counts/rates and all represented-class metrics are retained in the audit JSON.

### Withheld systems and remaining work

RegBridge metrics are withheld until all 18 cases complete. B2 is not part of the authorized
Phase 1 live schedule and has not been rescored here. Its permitted output vocabulary is
checked through synthetic schema/scorer tests without held-out access. No all-system or
RegBridge superiority comparison is supported by this run.

The new runner withholds partial RegBridge metrics, records not-run cases separately, and
blocks any paid execution until explicit author-01 approval of the vocabulary and current
configuration digest. After approval, a fresh declared Phase 1 configuration must evaluate
all 18 cases for each live system; do not append new-schema responses to the old run or
reuse the old responses as new observations. No Phase 2 cap is proposed now.

Frozen benchmark bytes, labels, families, splits, regulatory rules, `.env`, fixture-validation
artifacts, and historical A009 output remain untouched. Live-mode reproducibility concerns
configuration and artifacts only; fixture-mode determinism is unchanged.
