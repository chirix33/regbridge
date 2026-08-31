# Shared action definitions — author review checkpoint

The eleven codes and all eleven definitions were approved by `author-01` on
2026-08-31 at 22:52:53Z. This approval authorizes one fresh Phase 1 train/development run;
it does not authorize held-out access or a prompt freeze.
No new live evaluation or prompt freeze is authorized by this document. Code order is
alphabetical, not a frequency or priority ordering. Definitions contain no case mappings,
reference-label hints, predicates, or decision associations.

| Code | Proposed definition |
|---|---|
| `AUTHOR_REVIEW_HEADING_MAPPING` | Have an author review a proposed content-placement mapping and its supporting evidence. |
| `CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT` | Change content placement through a new context group, suspend the legacy placement, and reuse the unchanged document by identifier without resubmitting its file or element. |
| `CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD` | Change context-group metadata through a new context group, suspend the previous group, and reuse the unchanged document by identifier without resubmitting its file or element. |
| `DECLARE_MANUFACTURER_PARTITIONING` | Record the manufacturer's content-partitioning requirements and distinguishing values. |
| `DECLARE_METADATA_MIGRATION_INTENT` | Record the intended preservation or modification of context-group metadata. |
| `HUMAN_VERIFY_STALE_CONTENT` | Have a human review cited content and references against the target context and document any corrections needed. |
| `NO_MATERIAL_REPAIR` | Retain the document and its context without material changes. |
| `PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS` | Retain the existing context-group keyword codes and values unchanged. |
| `SELECT_SUPPORTED_REUSE_OPERATION` | Record either a supported identifier-based content-reuse operation or a human-reviewed operation outside the supported operation vocabulary. |
| `VERIFY_HYPERLINK_RELEVANCE` | Have a human check hyperlink targets and relevance to the target context and document any corrections needed. |
| `WAIT_FOR_OPERATIONAL_AVAILABILITY` | Defer operational submission activity pending availability of the submission pathway. |

The distinction between the two context-creation codes is the changed property (placement
versus metadata), not a disclosed trigger or decision mapping. Neither code changes the
underlying document or resubmits its physical file/document element.

## Implementation and disclosure

`backend/app/domain/vocabulary.py` owns the single packet used by B0, B1, RegBridge's
semantic serialization, and B2's scoring contract. All six decisions remain permitted.
The packet, definitions, origin disclosure, serializers, schemas, and scorer participate
in the configuration digest. Packet changes invalidate approval and future held-out gates.

The action vocabulary is derived from RegBridge's existing repair semantics. B0 and B1
receive this proposed-system taxonomy in their inputs; they are not naive generic-LLM
baselines. This disclosure is included in configuration, manifests, and development summaries
for later inclusion in the paper. Existing fixture-validation artifacts are not rewritten.

The next authorized Phase 1 run first recomputes B2 using the production parser, graph,
and rules with semantic capability omitted. It uses only the isolated train/development
bundle, not the full catalog or frozen combined benchmark. Labels are joined only for
scoring. No saved B2 prediction is loaded. Its separate artifact contains the shared packet,
option (a) metrics, all 18 predictions, bundle/configuration digests, and genuine deterministic
experimental status. It uses no live requests and is outside the 54-outcome live schedule.
Missing or mismatched B2 coverage/configuration prevents comparison; no live-model comparison
is complete until all 18 outcomes for each of B0, B1, and RegBridge are recorded.

## Mandatory stop

The author approval record identifies these definitions and the recomputed digests. Execute
one fresh complete
Phase 1 (subject to the existing failure-stop policy), without reusing any prior responses.
Report defect counts, before/after metrics as diagnostics rather than acceptance criteria,
outside-class diagnostics, review-bypass alongside unsafe-FNR, and per-system reasoning
usage. Propose a Phase 2 cap only from completed, untruncated, fully observed Phase 1 usage.
Held-out data remains untouched. `not_operational` and `expert_validated: false` remain fixed.

## Verification at this checkpoint

The following focused command passed **55 tests** on 2026-08-31:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_m3_action_definitions.py backend/tests/unit/test_m3_live_phase1.py backend/tests/unit/test_m3_live_integrity.py backend/tests/unit/test_m3_contract_corrections.py backend/tests/unit/test_openai_compatible.py -q
```

Also passed:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend --no-cache
.\.venv\Scripts\python.exe -m mypy backend/app backend/tests
.\.venv\Scripts\python.exe -m app.schemas check
git diff --check
```

Type checking covered 75 source files. Tests verify eleven complete one-line definitions,
exact packet equality across all four contracts, source-derived enum equality, definition
mutation invalidating digests and held-out callbacks, unchanged B0/B1 case serialization,
fixed evidence ordering, full input size bounds, all 18 B2 predictions through production
rules without network/catalog access, and rejection of missing or mismatched B2 rescoring.
Synthetic comparison artifacts exist only in test temporary directories and are not empirical
live observations. Acceptance uses contract invariants, not movement in accuracy or F1.

The isolated bundle SHA-256 remains
`0ba12ccabb61f77c44c722dd06bb309e51fbb9efb636433de0d9be7f1da69122`.
Full benchmark suites were intentionally not run because they load held-out material.
No new paid call, author approval event, live result, Phase 2 cap, or prompt freeze was created.
After approval, B2 will be recomputed again in the fresh run; test outputs will not be reused.
