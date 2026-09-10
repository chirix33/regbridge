"""Network-free tests for local SQLite vs Vercel Postgres selection."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.analyzer.repository import AnalysisRepository
from app.analyzer.service import AnalysisService
from app.config import Settings
from app.domain.enums import LlmMode
from app.domain.models import TargetContext
from app.parsers.ectd322 import FixtureCatalog
from app.persistence.factory import create_analysis_repository, create_product_stores
from app.persistence.postgres import (
    PostgresAnalysisRepository,
    PostgresInventoryRepository,
    PostgresJobRepository,
)
from app.product.models import DossierAnalysisRequest, DossierAnalysisRun
from app.product.models_registry import ModelProfileRegistry
from app.product.repository import DossierRunRepository, InventoryRepository
from app.product.services import DossierAnalysisManager


def _target() -> TargetContext:
    return TargetContext.model_validate(
        {
            "authority": "FDA",
            "center": "CDER",
            "application_type": "NDA",
            "source_standard": "eCTD-3.2.2",
            "target_standard": "eCTD-4.0",
            "analysis_date": date(2026, 8, 29),
            "reuse_operation": "reference-existing-content",
            "standards_snapshot_id": "fda-cder-demo-v1",
            "scenario_mode": "prospective_forward_compatibility",
        }
    )


class MemoryConnection:
    def __init__(self, store: MemoryPostgres) -> None:
        self.store = store
        self._row: tuple[Any, ...] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> MemoryConnection:
        self.store.execute(sql, params or ())
        self._row = self.store.last_row
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def commit(self) -> None:
        return None

    def __enter__(self) -> MemoryConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class MemoryPostgres:
    def __init__(self) -> None:
        self.analyses: dict[str, tuple[str, str]] = {}
        self.inventories: dict[str, tuple[str, datetime]] = {}
        self.jobs: dict[str, tuple[str, str, datetime]] = {}
        self.created: dict[str, datetime] = {}
        self.last_row: tuple[Any, ...] | None = None

    def connect(self, _url: str) -> MemoryConnection:
        return MemoryConnection(self)

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        normalized = " ".join(sql.split()).upper()
        now = datetime.now(UTC)
        self.last_row = None
        if normalized.startswith("CREATE TABLE") or normalized.startswith("DELETE FROM"):
            if "DELETE FROM INVENTORIES WHERE EXPIRES_AT" in normalized:
                self.inventories = {
                    key: value for key, value in self.inventories.items() if value[1] > now
                }
            elif "DELETE FROM INVENTORIES" in normalized and "OFFSET" in normalized:
                keep = int(params[0])
                ordered = sorted(self.inventories, key=lambda key: self.created[key])
                extras = ordered[: max(0, len(ordered) - keep)]
                for key in extras:
                    self.inventories.pop(key, None)
                    self.created.pop(key, None)
            elif "DELETE FROM JOBS WHERE EXPIRES_AT" in normalized:
                self.jobs = {key: value for key, value in self.jobs.items() if value[2] > now}
            elif "DELETE FROM JOBS" in normalized and "OFFSET" in normalized:
                kind, _kind, keep = params
                matching = [key for key, value in self.jobs.items() if value[0] == kind]
                matching.sort(key=lambda key: self.created[key])
                extras = matching[: max(0, len(matching) - int(keep))]
                for key in extras:
                    self.jobs.pop(key, None)
                    self.created.pop(key, None)
            return
        if "INSERT INTO ANALYSES" in normalized:
            identifier, result_json, graph_json = params
            self.analyses[str(identifier)] = (str(result_json), str(graph_json))
            return
        if "SELECT RESULT_JSON FROM ANALYSES" in normalized:
            analysis = self.analyses.get(str(params[0]))
            self.last_row = (analysis[0],) if analysis else None
            return
        if "SELECT GRAPH_JSON FROM ANALYSES" in normalized:
            analysis = self.analyses.get(str(params[0]))
            self.last_row = (analysis[1],) if analysis else None
            return
        if "INSERT INTO INVENTORIES" in normalized:
            identifier, payload, expires = params
            self.inventories[str(identifier)] = (str(payload), expires)
            self.created[str(identifier)] = now
            return
        if "SELECT PAYLOAD_JSON FROM INVENTORIES" in normalized:
            inventory = self.inventories.get(str(params[0]))
            if inventory is None or inventory[1] <= now:
                self.last_row = None
            else:
                self.last_row = (inventory[0],)
            return
        if "SELECT COUNT(*) FROM INVENTORIES" in normalized:
            count = sum(1 for value in self.inventories.values() if value[1] > now)
            self.last_row = (count,)
            return
        if "INSERT INTO JOBS" in normalized:
            identifier, kind, payload, expires = params
            self.jobs[str(identifier)] = (str(kind), str(payload), expires)
            self.created[str(identifier)] = now
            return
        if "SELECT PAYLOAD_JSON FROM JOBS" in normalized:
            job = self.jobs.get(str(params[0]))
            if job is None or job[0] != params[1] or job[2] <= now:
                self.last_row = None
            else:
                self.last_row = (job[1],)
            return
        raise AssertionError(f"unhandled SQL in memory postgres: {normalized}")


def test_default_settings_use_sqlite_path() -> None:
    settings = Settings(llm_mode=LlmMode.FIXTURE, reg_bridge_database_url=None)
    assert settings.uses_postgres is False
    repository = create_analysis_repository(settings)
    assert isinstance(repository, AnalysisRepository)


def test_database_url_selects_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    settings = Settings(
        llm_mode=LlmMode.FIXTURE,
        reg_bridge_database_url="postgresql://user:pass@localhost/regbridge",
    )
    assert settings.uses_postgres is True
    repository = create_analysis_repository(settings)
    assert isinstance(repository, PostgresAnalysisRepository)


def test_vercel_without_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    settings = Settings(llm_mode=LlmMode.FIXTURE, reg_bridge_database_url=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_analysis_repository(settings)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_product_stores(settings)


def test_postgres_analysis_round_trip(tmp_path: Path) -> None:
    sqlite = AnalysisRepository(tmp_path / "source.sqlite3")
    inventory = FixtureCatalog().parse("case-a-removed-3211")
    result = AnalysisService(repository=sqlite).analyze(
        inventory, inventory.leaves[0].id, _target()
    )
    graph = sqlite.graph(result.id)
    memory = MemoryPostgres()
    repository = PostgresAnalysisRepository("postgresql://unused", connect=memory.connect)
    repository.save(result, graph)
    loaded = repository.get(result.id)
    assert loaded.decision == result.decision
    assert repository.graph(result.id).model_dump() == graph.model_dump()


def test_postgres_inventory_and_jobs_round_trip() -> None:
    inventory = FixtureCatalog().parse("case-a-removed-3211")
    memory = MemoryPostgres()
    inventories = PostgresInventoryRepository(
        "postgresql://unused",
        capacity=4,
        ttl_seconds=3600,
        connect=memory.connect,
    )
    envelope = inventories.put(inventory)
    assert envelope.restart_persistence == "database"
    loaded = inventories.get(envelope.inventory_id)
    assert loaded.id == envelope.inventory_id
    assert inventories.count() == 1

    memory_jobs = MemoryPostgres()
    settings = Settings(llm_mode=LlmMode.FIXTURE)
    local = InventoryRepository(capacity=2, ttl_seconds=60)
    local_envelope = local.put(inventory)
    manager = DossierAnalysisManager(
        inventories=local,
        runs=DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier"),
        registry=ModelProfileRegistry(settings),
        settings=settings,
    )
    run = manager.create(
        DossierAnalysisRequest(
            inventory_id=local_envelope.inventory_id,
            model_id="gpt-5.5",
            target_context=_target(),
            leaf_ids=(inventory.leaves[0].id,),
        )
    )
    jobs: PostgresJobRepository[DossierAnalysisRun] = PostgresJobRepository(
        "postgresql://unused",
        model=DossierAnalysisRun,
        kind="dossier",
        prefix="dossier",
        capacity=4,
        ttl_seconds=3600,
        connect=memory_jobs.connect,
    )
    jobs.put(run.run_id, run)
    restored = jobs.get(run.run_id)
    assert restored.run_id == run.run_id
    assert restored.state == "queued"


def test_postgres_inventory_hides_expired_rows() -> None:
    inventory = FixtureCatalog().parse("case-a-removed-3211")
    memory = MemoryPostgres()
    inventories = PostgresInventoryRepository(
        "postgresql://unused",
        capacity=4,
        ttl_seconds=3600,
        connect=memory.connect,
    )
    envelope = inventories.put(inventory)
    identifier = envelope.inventory_id
    payload, _expires = memory.inventories[identifier]
    memory.inventories[identifier] = (payload, datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(KeyError, match="expired"):
        inventories.get(identifier)
