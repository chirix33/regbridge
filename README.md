# RegBridge

RegBridge is an FDA/CDER-scoped **risk analyzer**, **decision-support tool**, and **research
prototype** for assessing whether legacy eCTD v3.2.2 content appears suitable for reuse in a
selected eCTD v4.0 context.

It is not FDA-certified, is not a substitute for regulatory review, and does not predict or
guarantee filing or application acceptance. Use only public, synthetic, or deliberately
de-identified materials. Do not upload confidential sponsor submissions.

## Current delivery state: M4

M4 preserves the shared analyzer path and frozen M3 evaluation, then adds an offline-first
presentation layer:

- FastAPI health, FDA/CDER scope, and frozen-snapshot endpoints;
- React/TypeScript/Tailwind scope UI with a visible research disclaimer;
- closed decision and severity vocabularies plus typed provenance, evidence, result, and target
  context contracts;
- committed JSON Schemas and a reviewable OpenAPI document;
- a validated standards manifest with two immutable, source-verified official FDA sources;
- a deterministic, citation-validating fixture model that requires no network or model key;
- a secure scoped eCTD v3.2.2 ZIP/directory parser with path, size, MIME/signature, and XML
  DTD/entity protections;
- a typed heading/version graph with an accessible text alternative;
- the author-adjudicated explicit mappings `3.2.S.1.1`, `3.2.S.1.2`, and `3.2.S.1.3` →
  `3.2.S.1`;
- deterministic positive, clean-negative, ambiguous-abstention, and current-operational paths;
- lifecycle-sensitive `manufacturer="all"` advisory, preservation, normalization, and intent-
  missing paths;
- bounded PDF text and hyperlink extraction with author-verified fixture-link governance;
- strict offline fixtures, a disabled-model abstention, and an opt-in OpenAI-compatible structured
  adapter with redacted run metadata;
- deterministic decision precedence and SQLite result/graph trace persistence;
- an atomically frozen 30-case benchmark with author-adjudicated labels, immutable input hashes,
  12 held-out cases, and six non-overlapping held-out fixture families;
- B0 long-context contract fixtures, dependency-free BM25 B1, genuine rule-only B2, and the full
  RegBridge path through one label-isolated runner;
- unsafe false-negative, review-bypass, per-class, retrieval, Wilson-interval, and exploratory
  family-clustered metrics;
- deterministic manifests, raw outputs, CSV/JSON/Markdown exports, evaluation APIs, and one-
  command evaluation;
- an immutable, digest-verified M4 presentation snapshot derived from the held-out Phase 2 run;
- read-only presentation APIs and a comparison dashboard for repetitions, safety, stability,
  retrieval, usage, cost, and per-case traces;
- a guided three-case demonstration with reset behavior and accessible evidence/graph tables;
- screenshot and five-minute recording workflow documentation.

M1/M2 are a **prospective forward-compatibility research scenario**. FDA forward compatibility is
currently **`not_operational`**, which is visible in the API and UI. Current-operational mode does
not execute prospective rules or semantic inspection. The executable rules and frozen benchmark
labels are author-adjudicated by `author-01` for the controlled demonstration only.
`expert_validated` remains `false`.

## Prerequisites

Declared M3 live development evaluation: ` .\scripts\evaluate-live-phase1.ps1` (or
`make evaluate-live-phase1`) uses only the isolated train/development bundle and explicitly
configured `gpt-5.5` credentials. Temperature is omitted with
`temperature_handling: unsupported_by_endpoint_parameter`. Live runs reproduce configuration
and artifacts, **not model outputs**; fixture-mode determinism is unchanged. Phase 1 outputs
are development diagnostics with `eligible_for_performance_claims: false`. Author-01 approved
the frozen Phase 2 configuration with `max_output_tokens: 4000`, while retaining the 800-token
structured-answer bound. Phase 2 uses three separate held-out repetitions to characterize
variation; it never votes or pools predictions.
See [the reproducibility record](IMPLEMENTATION.md#143-reproducibility-record).

Phase 2 is deliberately two-step so its manifest and frozen digests are inspectable before the
held-out bundle is loaded:

```powershell
.\scripts\evaluate-live-phase2.ps1 -Prepare
.\scripts\evaluate-live-phase2.ps1 -Execute <generated-run-id>
```

- Python 3.12 or 3.13
- Node.js 22 or later and npm 11 or later
- PowerShell 7 on Windows, or GNU Make on macOS/Linux

All direct and transitive Python packages are pinned in `backend/requirements.lock`; frontend
packages are pinned in `frontend/package-lock.json`. Runtime defaults to `LLM_MODE=fixture`.

## Setup and verification

On Windows PowerShell:

```powershell
.\scripts\setup.ps1
.\scripts\check.ps1
```

If `python` is not the desired interpreter, pass it explicitly:

```powershell
.\scripts\setup.ps1 -Python "C:\path\to\python.exe"
```

On macOS/Linux:

```bash
make setup
make check
```

`check` runs backend lint, type checking, tests, and schema drift validation, followed by frontend
lint, type checking, component tests, and a production build. No default check uses the network or
requires a model key.

Run the deterministic M3 evaluation on Windows:

```powershell
.\scripts\evaluate.ps1
```

On macOS/Linux, use `make evaluate`. Validation-only artifacts are written beneath
`results/validation/` and `paper/tables/validation/`. B0, B1, and RegBridge outputs are synthetic
contract fixtures—not empirical model observations. Only B2 is a genuine rule-only result. No
model-comparison or RegBridge-superiority claim is permitted without a declared live-model run.

## Run the M3 application

On Windows, one command starts the local API and UI:

```powershell
.\scripts\dev.ps1
```

Then open <http://127.0.0.1:5173>. Stop both processes with `Ctrl+C`.

Portable two-terminal alternative:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

Useful endpoints:

- API documentation: <http://127.0.0.1:8000/docs>
- health: <http://127.0.0.1:8000/health>
- supported scope and disclaimer: <http://127.0.0.1:8000/api/v1/config/scope>
- frozen source snapshot: <http://127.0.0.1:8000/api/v1/standards/snapshots>
- controlled fixture catalog: <http://127.0.0.1:8000/api/v1/fixtures>
- baseline runner: `POST http://127.0.0.1:8000/api/v1/baselines/run`
- deterministic evaluation: `POST http://127.0.0.1:8000/api/v1/evaluations`
- evaluation status: `GET http://127.0.0.1:8000/api/v1/evaluations/eval-m3-fixture-v2-graph-contract`
- M4 presentation snapshot: <http://127.0.0.1:8000/api/v1/presentation/m3>
- demo presets: <http://127.0.0.1:8000/api/v1/demo/presets>
- unavailable-heading case: <http://127.0.0.1:5173/demo/case-a>
- metadata/lifecycle case: <http://127.0.0.1:5173/demo/case-b>
- semantic PDF/hyperlink case: <http://127.0.0.1:5173/demo/case-c>
- held-out dashboard: <http://127.0.0.1:5173/evaluation>

Verify the M4 presentation layer:

```powershell
.\scripts\m4-verify.ps1
```

`m4-verify` validates the committed presentation snapshot, checks protected M3 hashes, and runs
the scripted fixture-mode demo twice to compare decision, evidence, graph, and trace digests. The
GNU Make target additionally runs frontend component/build/E2E checks when Playwright browsers are
installed.

## M4.1 end-to-end dossier workspace

The primary route `/` accepts the deterministic controlled-profile dossier and analyzes every
supported PDF using uploaded `index.xml`, `m1/us/us-regional.xml`, lifecycle metadata, legacy MD5,
and extracted PDF evidence. `/baselines` runs B0, B1, model-free B2, and RegBridge on the same
package-derived inputs without reference labels or performance metrics. `/evaluation` remains the
immutable held-out Phase 2 presentation.

The exact capability boundary is: “RegBridge securely parses and validates a controlled FDA eCTD
v3.2.2 package profile for supported structural, lifecycle, metadata, checksum, and
document-evidence predicates. It does not perform complete FDA submission validation.”

Generate the public synthetic package with
`.\.venv\Scripts\python.exe scripts\generate_m4_1_dossier.py`; its manifest and stable hash are in
`data/demo-dossiers/m4-1/`. Run `.\scripts\m4-1-verify.ps1` twice for the additive milestone gate.
See `docs/DEMO_M4_1.md` for the operator workflow. Uploaded inventories are opaque, bounded,
expiring, memory-local records; ZIP bytes are discarded and records do not survive restart.

New product endpoints:

- `GET /api/v1/models`
- `GET /api/v1/applications/{inventory_id}`
- `POST/GET /api/v1/dossier-analyses[/{run_id}]`
- `POST/GET /api/v1/comparisons[/{comparison_id}]`

The server binds only to `127.0.0.1`. Authentication and public deployment are out of scope.

## Repository map

- `backend/app/domain/` — storage-, API-, and model-vendor-neutral contracts
- `backend/app/parsers/` — secure scoped legacy-package parser
- `backend/app/graph/` and `backend/app/rules/` — typed graph and adjudicated constraints
- `backend/app/standards/` — frozen registry, evidence loader, and digest validation
- `backend/app/llm/` — structured model protocol and deterministic fixture implementation
- `backend/app/baselines/` and `backend/app/evaluation/` — comparison systems, benchmark,
  scoring, manifests, and exports
- `backend/app/presentation/` — M4 immutable snapshot loader, generator, and verifier
- `backend/app/product/` — M4.1 model profiles, bounded stores, dossier jobs, comparisons, verifier
- `frontend/src/` — accessible scope-first demonstration shell
- `data/standards/` — source-verified registry, source ledger, and immutable source snapshots
- `data/model-fixtures/` — versioned offline structured outputs
- `schemas/` — generated, reviewable JSON contracts
- `scripts/` — repeatable setup, verification, and local demo commands

The authoritative implementation and research plan is [IMPLEMENTATION.md](./IMPLEMENTATION.md).
