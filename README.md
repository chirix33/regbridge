# RegBridge

RegBridge is an FDA/CDER-scoped **risk analyzer**, **decision-support tool**, and **research
prototype** for assessing whether legacy eCTD v3.2.2 content appears suitable for reuse in a
selected eCTD v4.0 context.

It is not FDA-certified, is not a substitute for regulatory review, and does not predict or
guarantee filing or application acceptance. Use only public, synthetic, or deliberately
de-identified materials. Do not upload confidential sponsor submissions.

## Current delivery state: M1

M1 completes the first end-to-end unavailable-heading vertical slice:

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
- an interactive UI for parsed inventory, decision, evidence, repair, uncertainty, graph, and trace.

M1 is a **prospective forward-compatibility research scenario**. FDA forward compatibility is
currently **`not_operational`**, which is visible in the API and UI. Current-operational mode does
not execute the prospective rule. The rule and benchmark labels are author-adjudicated by
`author-01`; `expert_validated` remains `false`.

## Prerequisites

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

## Run the M1 application

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
- interactive Case A: <http://127.0.0.1:5173/case-a>

The server binds only to `127.0.0.1`. Authentication and public deployment are out of scope.

## Repository map

- `backend/app/domain/` — storage-, API-, and model-vendor-neutral contracts
- `backend/app/parsers/` — secure scoped legacy-package parser
- `backend/app/graph/` and `backend/app/rules/` — typed graph and adjudicated constraints
- `backend/app/standards/` — frozen registry, evidence loader, and digest validation
- `backend/app/llm/` — structured model protocol and deterministic fixture implementation
- `frontend/src/` — accessible scope-first demonstration shell
- `data/standards/` — source-verified registry, source ledger, and immutable source snapshots
- `data/model-fixtures/` — versioned offline structured outputs
- `schemas/` — generated, reviewable JSON contracts
- `scripts/` — repeatable setup, verification, and local demo commands

The authoritative implementation and research plan is [IMPLEMENTATION.md](./IMPLEMENTATION.md).
