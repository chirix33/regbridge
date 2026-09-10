from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.analyzer.repository import AnalysisRepository, AnalysisStore
from app.config import Settings
from app.product.models import ComparisonRun, DossierAnalysisRun
from app.product.repository import (
    ComparisonRunRepository,
    DossierRunRepository,
    InventoryRepository,
    InventoryStore,
    JobStore,
)


@dataclass(frozen=True)
class ProductStores:
    inventories: InventoryStore
    dossier_runs: JobStore[DossierAnalysisRun]
    comparison_runs: JobStore[ComparisonRun]


def create_analysis_repository(settings: Settings) -> AnalysisStore:
    if settings.uses_postgres:
        from app.persistence.postgres import PostgresAnalysisRepository

        return PostgresAnalysisRepository(settings.resolved_database_url)
    if os.environ.get("VERCEL"):
        raise RuntimeError(
            "Vercel deployments require DATABASE_URL or REG_BRIDGE_DATABASE_URL. "
            "Local SQLite is not persisted across serverless invocations."
        )
    return AnalysisRepository(Path(settings.reg_bridge_database_path))


def create_product_stores(settings: Settings) -> ProductStores:
    if settings.uses_postgres:
        from app.persistence.postgres import PostgresInventoryRepository, PostgresJobRepository

        url = settings.resolved_database_url
        return ProductStores(
            inventories=PostgresInventoryRepository(
                url,
                capacity=settings.product_inventory_capacity,
                ttl_seconds=settings.product_inventory_ttl_seconds,
            ),
            dossier_runs=PostgresJobRepository(
                url,
                model=DossierAnalysisRun,
                kind="dossier",
                prefix="dossier",
                capacity=settings.product_job_capacity,
                ttl_seconds=settings.product_job_ttl_seconds,
            ),
            comparison_runs=PostgresJobRepository(
                url,
                model=ComparisonRun,
                kind="comparison",
                prefix="comparison",
                capacity=settings.product_job_capacity,
                ttl_seconds=settings.product_job_ttl_seconds,
            ),
        )
    if os.environ.get("VERCEL"):
        raise RuntimeError(
            "Vercel deployments require DATABASE_URL or REG_BRIDGE_DATABASE_URL. "
            "In-memory product stores are not shared across serverless invocations."
        )
    return ProductStores(
        inventories=InventoryRepository(
            capacity=settings.product_inventory_capacity,
            ttl_seconds=settings.product_inventory_ttl_seconds,
        ),
        dossier_runs=DossierRunRepository(
            capacity=settings.product_job_capacity,
            ttl_seconds=settings.product_job_ttl_seconds,
            prefix="dossier",
        ),
        comparison_runs=ComparisonRunRepository(
            capacity=settings.product_job_capacity,
            ttl_seconds=settings.product_job_ttl_seconds,
            prefix="comparison",
        ),
    )
