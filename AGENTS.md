# RegBridge — Instructions for Codex

This repository implements **RegBridge**, a research prototype for evidence-grounded, version-aware risk analysis when reusing legacy FDA eCTD v3.2.2 content in an eCTD v4.0 submission.

Before changing code, read [IMPLEMENTATION.md](./IMPLEMENTATION.md) in full. It is the authoritative build specification, evaluation plan, and milestone sequence. If code and documentation disagree, stop, identify the conflict, and update the documentation or obtain a user decision before relying on the changed behavior.

## 1. Research goal

RegBridge tests this research question:

> Can a typed, version-aware regulatory graph plus executable constraints identify unsafe or ambiguous reuse of legacy FDA eCTD content more reliably and explainably than a document-context agent, flat retrieval, or rules alone?

The system must answer a narrower, defensible question than “Will FDA accept this submission?” It should determine whether a legacy leaf or document appears suitable for reuse in a specified target context, what risk prevents confident reuse, what evidence supports that finding, and what minimum repair or escalation is appropriate.

The primary audience is an AAAI 2027 Demonstration Track reviewer. The prototype must therefore be:

- technically credible;
- visibly interactive and user-friendly;
- grounded in traceable regulatory evidence;
- reproducible on a controlled benchmark;
- honest about uncertainty and research limitations;
- clearly stronger than a domain chatbot or a hard-coded rules demo.

## 2. Settled product decisions

Treat these as fixed unless the user explicitly changes them:

- **Regulatory scope:** FDA/CDER first. Do not silently generalize findings to CBER, other FDA centers, or other regulators.
- **Legacy input:** selected eCTD v3.2.2 backbone material, especially `index.xml`, `us-regional.xml`, and, when present, `stf.xml`, plus referenced dossier files.
- **Target context:** selected FDA eCTD v4.0 requirements and controlled terminology relevant to the three demonstration cases.
- **Backend:** Python and FastAPI.
- **Frontend:** React with TypeScript, Tailwind CSS, and Iconoir icons.
- **Model integration:** provider-neutral, OpenAI-compatible HTTP adapter, with deterministic offline fixtures for tests and repeatable demonstrations.
- **Human role:** the user will steer the research and test the completed implementation. Build autonomously within this specification; ask only when a decision would materially change scope, public claims, data handling, or the evaluation design.

## 3. Claims and non-goals

Use the terms **risk analyzer**, **decision support**, and **research prototype**. Never present RegBridge as FDA-certified, as a substitute for regulatory review, or as a predictor or guarantee of filing or application acceptance.

The MVP does not attempt to provide:

- complete coverage of every FDA center, application type, CTD heading, validation criterion, or eCTD lifecycle operation;
- production-grade v3.2.2-to-v4.0 conversion;
- automatic generation of a submission-ready eCTD v4.0 package;
- automatic rewriting of regulated documents;
- legal, medical, or regulatory advice;
- integration with enterprise RIM or document-management systems;
- ingestion of confidential sponsor submissions;
- an automatically generated ontology treated as validated without source verification and author adjudication.

Use public, synthetic, or deliberately de-identified fixtures only. Do not add real sponsor data, personal data, trade secrets, or credentials to the repository.

The MVP does not assume access to a regulatory professional with eCTD experience. Its rules and benchmark labels are research-team operationalizations grounded in official sources, not expert-validated regulatory ground truth. Preserve that limitation in the system, paper, and demonstration.

## 4. Core reasoning contract

RegBridge is a hybrid system. Keep the responsibilities separate.

### Deterministic components own

- XML parsing, namespace handling, file resolution, checksums, and structural validation;
- lifecycle and reference relationships that are explicitly represented in source data;
- exact heading availability and mapping facts encoded in the source-verified standards snapshot;
- exact keyword and metadata constraints;
- constraint precedence and final enforcement of eligible hard findings;
- provenance validation and evidence-presence checks.

### Model-assisted components may own

- candidate extraction of regulatory entities and relations from prose;
- semantic comparison of a dossier passage against a target context;
- detection of potentially stale wording, names, headings, or internal references;
- ranking of already-supported explanations or repair suggestions;
- classification into an allowed schema when evidence is supplied.

The model must return structured output, cite evidence identifiers supplied in its prompt, and be able to abstain. It may not invent standards, silently fill missing provenance, override a deterministic hard rule, or downgrade a hard risk. All model-originated graph facts remain `candidate`; neither Codex nor a model may promote an assertion to `source_verified` or `author_adjudicated_for_demo`.

Use the governance vocabulary defined in `IMPLEMENTATION.md`:

- `candidate` — proposed but not permitted to drive an enforceable conclusion;
- `source_verified` — an author has checked the pinned official source, digest, locator, transcription, version, and scope;
- `author_adjudicated_for_demo` — the research team has accepted a formalization for the controlled benchmark;
- `rejected` — unsupported, incorrect, duplicated, contradicted, or outside scope.

`author_adjudicated_for_demo` is an internal research status. It does not represent FDA approval, professional eCTD validation, or regulatory ground truth. Keep `expert_validated: false` unless a qualified external reviewer actually performs and records a review.

Only rules based on `direct_standard_encoding` or `mechanical_derivation`, backed by exact official evidence and author-adjudicated for the demo, may use `enforcement_mode: hard`. Rules based on `author_interpretation` must be `advisory`; model-assisted `semantic_inference` must be a `semantic_signal`. Advisory and semantic findings may escalate to `HUMAN_REGULATORY_REVIEW`, but cannot alone declare noncompliance, `DO_NOT_REUSE`, or `BREAK_LIFECYCLE_AND_RESUBMIT`.

## 5. Decision vocabulary

Use only these primary decisions in the MVP:

- `REUSE_AS_LEGACY_REFERENCE`
- `REUSE_WITH_NEW_CONTEXT`
- `REUSE_AFTER_METADATA_REPAIR`
- `BREAK_LIFECYCLE_AND_RESUBMIT`
- `DO_NOT_REUSE`
- `HUMAN_REGULATORY_REVIEW`

Every completed analysis must include:

- the decision and severity;
- the analyzed source artifact and target context;
- triggered rule identifiers;
- exact evidence spans and source-document metadata;
- a plain-language rationale;
- the minimum proposed repair or next action;
- confidence and unresolved uncertainty;
- whether human approval is required;
- a machine-readable trace of deterministic and model-assisted steps.

When evidence is missing, contradictory, outside scope, or too ambiguous, choose `HUMAN_REGULATORY_REVIEW`. Do not convert uncertainty into a confident recommendation.

## 6. Required demonstration cases

The end-to-end system must support three independently testable archetypes. Do not hard-code their outputs.

1. **Removed or unavailable target heading.** A legacy leaf located below a v3.2.2 heading such as `3.2.S.1.1` cannot retain the same lower-level placement in the selected v4.0 context. The analyzer must identify the structural mismatch, show the applicable heading evidence, and recommend relocation with a lifecycle-breaking resubmission when required by the encoded rule.
2. **Legacy metadata or keyword tension.** A technically referenceable legacy leaf carries a discouraged or target-inappropriate metadata value, such as a deliberately scoped fixture using manufacturer attribute `all`. The analyzer must distinguish preservation of an existing lifecycle from creation of a clean target artifact, explain the trade-off, and recommend metadata repair or lifecycle break according to context.
3. **Semantically stale but technically reusable PDF.** A legacy PDF is structurally referenceable yet contains an obsolete internal hyperlink, old heading, applicant name, or other controlled stale reference. The analyzer must surface the semantic risk with quoted evidence and avoid claiming that technical referenceability makes the content safe.

Each archetype needs multiple controlled variants, including clean negatives and ambiguous examples, so the benchmark measures generalization rather than memorization.

## 7. Research integrity and baselines

Implement and preserve these comparison systems:

- **B0 — Long-context document agent:** receives the same regulatory source snapshot and case materials in context, without graph lookup or executable constraints.
- **B1 — Flat retrieval agent:** retrieves from the same corpus without graph-aware expansion or constraint execution.
- **B2 — Rule-only analyzer:** uses the same deterministic rules and parsed fields but no model-assisted semantic analysis.
- **Proposed — RegBridge:** typed version-aware graph, executable constraints, and evidence-bounded model analysis.

Comparisons must use the same case split, regulatory snapshot, evidence corpus, allowed output labels, and—where a model is involved—the same model, temperature, and token budget where practicable. Do not give RegBridge privileged author-adjudicated reference labels at inference time. Do not weaken baselines artificially.

The principal safety metric is **unsafe false-negative rate**. Also report macro-F1 or balanced decision accuracy, high-risk recall, heading-mapping accuracy, evidence-citation accuracy, repair-recommendation accuracy, abstention/calibration, latency, and model usage. Preserve raw per-case outputs so all aggregate claims can be audited.

## 8. Source and provenance policy

Regulatory findings must be grounded in pinned official FDA or ICH materials. Secondary sources may help discovery or user-interface explanation, but they cannot be the sole source for an executable regulatory rule.

For every standards artifact, record at least:

- stable internal source identifier;
- title, authority, jurisdiction, and issuing organization;
- source URL and retrieval date;
- published/effective version or date when available;
- local immutable snapshot path and SHA-256 digest;
- relevant page, section, table, or XML node locator;
- bindingness (`requirement`, `validation`, `recommendation`, or `informative`);
- applicability qualifiers such as FDA center, application type, standard version, and validity interval;
- review status and reviewer note;
- verification basis and enforcement mode;
- `expert_validated`, defaulting to `false`;
- author-review event, rationale, date, and unresolved assumptions.

Never silently replace a standards snapshot. Add a new version and make applicability explicit. A rule without supporting evidence must fail validation and cannot participate in a release evaluation. Author verification must never be described as expert, FDA, or professional validation.

## 9. Engineering rules

- Build in the milestone order in `IMPLEMENTATION.md`, using end-to-end vertical slices.
- Keep domain models independent of FastAPI routes, React components, storage, and model vendors.
- Keep rule definitions declarative and versioned; do not bury regulatory policy in route handlers or prompts.
- Make graph construction deterministic from source-verified and author-adjudicated inputs. Treat graph visualization as a view, not as the source of truth.
- Validate all external and model-produced data at boundaries with typed schemas.
- Make tests network-free by default. Live-model tests must be explicitly opted into.
- Pin dependencies and provide single-command local setup, test, lint, evaluation, and demo-start workflows.
- Use UTC timestamps and stable random seeds in benchmark runs.
- Log identifiers and decisions, not full confidential document text. Redact secrets from errors.
- Protect uploads against path traversal, XML external-entity expansion, decompression bombs, unexpected MIME types, and unbounded file size.
- Store secrets only in environment variables. Commit an `.env.example`, never an `.env` containing credentials.
- Preserve accessibility: keyboard operation, visible focus, semantic labels, adequate contrast, and text alternatives for graph-only information.
- Use Iconoir for interface icons. Do not substitute emoji or improvised SVG icons for product controls.

## 10. Working behavior for Codex

Before implementation:

1. Inspect the repository and existing changes.
2. Read this file and `IMPLEMENTATION.md` completely.
3. State the current milestone and the acceptance criteria being targeted.
4. Identify assumptions that affect scientific validity or user-visible behavior.

While implementing:

- prefer small, reviewable changes that complete a vertical capability;
- add or update tests with each behavior change;
- keep fixtures explicit and readable;
- update documentation when an interface, schema, rule, metric, or claim changes;
- do not overwrite unrelated user changes;
- do not stop for minor implementation choices already bounded by the specification;
- ask the user before expanding regulatory scope, changing benchmark reference labels, setting `expert_validated: true`, using non-public data, adding a paid infrastructure dependency, or making a stronger regulatory claim.

After each milestone:

- run its required tests and record exact commands and results;
- report remaining limitations and any failed or skipped checks;
- leave the repository runnable without a live model key;
- keep the demonstration fixtures and benchmark outputs reproducible.

## 11. Definition of done

The implementation is complete only when all of the following hold:

- the three archetypes run end to end through the same production analysis path;
- the FastAPI service and React UI can be started locally with documented commands;
- the user can inspect the parsed legacy artifact, target context, decision, evidence, graph neighborhood, rule trace, repair, and uncertainty;
- B0, B1, B2, and RegBridge run through one evaluation harness on the same controlled cases;
- tests cover parsing, schemas, rules, graph construction, decision precedence, provenance, model fixtures, APIs, and the critical UI journey;
- security tests cover hostile paths and XXE-style XML input;
- a frozen benchmark and machine-readable run manifest produce repeatable result tables;
- benchmark labels are described as author-adjudicated reference labels rather than expert regulatory ground truth;
- no candidate assertion supports an enforceable decision;
- no interpretive or semantic rule operates in `hard` mode;
- no release result depends on a network call or an unpinned standards page;
- the interface displays the research-prototype disclaimer, scope limitations, and absence of regulatory-expert validation;
- the repository contains enough result and provenance exports to support the two-page demonstration paper and five-minute video without manually reconstructing claims.

Passing a happy-path demo alone is not completion. The system must also show a clean negative, an abstention, and a baseline failure that can be explained from recorded evidence.
