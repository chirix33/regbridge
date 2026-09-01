# RegBridge

RegBridge is an FDA/CDER-scoped **risk analyzer**, **decision-support tool**, and **research
prototype** for assessing whether legacy eCTD v3.2.2 content appears suitable for reuse in a
selected eCTD v4.0 context.

It is not FDA-certified, is not a substitute for regulatory review, and does not predict or
guarantee filing or application acceptance. Use only public, synthetic, or deliberately
de-identified materials. Do not upload confidential sponsor submissions.

## Current delivery state: M3

M3 preserves the shared analyzer path and adds a frozen, auditable evaluation capability:

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
- an interactive shared UI for parsed inventory, findings, evidence, model record, repair,
  uncertainty, graph, and chronological trace.

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
are development diagnostics with `eligible_for_performance_claims: false`. Phase 2 remains
gated on explicit author-01 approval, with three separate repetitions to characterize variation.
See [the reproducibility record](IMPLEMENTATION.md#143-reproducibility-record).

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
- unavailable-heading case: <http://127.0.0.1:5173/case-a>
- metadata/lifecycle case: <http://127.0.0.1:5173/case-b>
- semantic PDF/hyperlink case: <http://127.0.0.1:5173/case-c>

The server binds only to `127.0.0.1`. Authentication and public deployment are out of scope.

## Repository map

- `backend/app/domain/` — storage-, API-, and model-vendor-neutral contracts
- `backend/app/parsers/` — secure scoped legacy-package parser
- `backend/app/graph/` and `backend/app/rules/` — typed graph and adjudicated constraints
- `backend/app/standards/` — frozen registry, evidence loader, and digest validation
- `backend/app/llm/` — structured model protocol and deterministic fixture implementation
- `backend/app/baselines/` and `backend/app/evaluation/` — comparison systems, benchmark,
  scoring, manifests, and exports
- `frontend/src/` — accessible scope-first demonstration shell
- `data/standards/` — source-verified registry, source ledger, and immutable source snapshots
- `data/model-fixtures/` — versioned offline structured outputs
- `schemas/` — generated, reviewable JSON contracts
- `scripts/` — repeatable setup, verification, and local demo commands

The authoritative implementation and research plan is [IMPLEMENTATION.md](./IMPLEMENTATION.md).
