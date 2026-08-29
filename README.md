# RegBridge

RegBridge is an FDA/CDER-scoped **risk analyzer**, **decision-support tool**, and **research
prototype** for assessing whether legacy eCTD v3.2.2 content appears suitable for reuse in a
selected eCTD v4.0 context.

It is not FDA-certified, is not a substitute for regulatory review, and does not predict or
guarantee filing or application acceptance. Use only public, synthetic, or deliberately
de-identified materials. Do not upload confidential sponsor submissions.

## Current delivery state: M0

M0 establishes the reviewable contracts and runnable shell for later analysis:

- FastAPI health, FDA/CDER scope, and frozen-snapshot endpoints;
- React/TypeScript/Tailwind scope UI with a visible research disclaimer;
- closed decision and severity vocabularies plus typed provenance, evidence, result, and target
  context contracts;
- committed JSON Schemas and a reviewable OpenAPI document;
- a validated standards manifest with one immutable official FDA source;
- a deterministic, citation-validating fixture model that requires no network or model key.

M0 does **not** analyze uploaded content or produce reuse decisions. The secure legacy parser,
first graph facts, reviewed evidence spans, and heading constraint are M1 work.

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

## Run the M0 application

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

The server binds only to `127.0.0.1`. Authentication and public deployment are out of scope.

## Repository map

- `backend/app/domain/` — storage-, API-, and model-vendor-neutral contracts
- `backend/app/standards/` — frozen registry loader and digest validation
- `backend/app/llm/` — structured model protocol and deterministic fixture implementation
- `frontend/src/` — accessible scope-first demonstration shell
- `data/standards/` — reviewed registry, source ledger, and immutable source snapshots
- `data/model-fixtures/` — versioned offline structured outputs
- `schemas/` — generated, reviewable JSON contracts
- `scripts/` — repeatable setup, verification, and local demo commands

The authoritative implementation and research plan is [IMPLEMENTATION.md](./IMPLEMENTATION.md).
