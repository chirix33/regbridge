.PHONY: setup lint typecheck test build check dev schemas

PYTHON ?= python3
VENV_PYTHON := .venv/bin/python

setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install "pip==26.2.1"
	$(VENV_PYTHON) -m pip install -r backend/requirements.lock
	$(VENV_PYTHON) -m pip install --no-deps --no-build-isolation -e ./backend
	npm --prefix frontend ci --ignore-scripts --no-audit --no-fund
	$(VENV_PYTHON) -m app.schemas export

lint:
	$(VENV_PYTHON) -m ruff check backend
	npm --prefix frontend run lint

typecheck:
	$(VENV_PYTHON) -m mypy backend/app backend/tests
	npm --prefix frontend run typecheck

test:
	$(VENV_PYTHON) -m pytest backend/tests
	npm --prefix frontend run test

build:
	$(VENV_PYTHON) -m app.schemas check
	npm --prefix frontend run build

check: lint typecheck test build

schemas:
	$(VENV_PYTHON) -m app.schemas export

dev:
	@echo "Use ./scripts/dev.ps1 on Windows or run the backend and frontend commands from README.md."
