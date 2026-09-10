from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import psycopg
from pydantic import BaseModel

from app.domain.models import AnalysisResult
from app.graph.models import GraphNeighborhood
from app.parsers.models import ApplicationInventory
from app.product.models import InventoryEnvelope
from app.product.repository import validate_opaque_id

T = TypeVar("T", bound=BaseModel)
Connect = Callable[..., Any]


def _connect(url: str) -> Any:
    return psycopg.connect(url, connect_timeout=10)


class PostgresSchema:
    def __init__(self, url: str, *, connect: Connect | None = None) -> None:
        self.url = url
        self._connect = connect or _connect
        self._initialized = False
        self._lock = threading.Lock()

    def connect(self) -> Any:
        connection = self._connect(self.url)
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._initialize(connection)
                    self._initialized = True
        return connection

    @staticmethod
    def _initialize(connection: Any) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                graph_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inventories (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.commit()


class PostgresAnalysisRepository:
    """Analysis store backed by Neon/Postgres on Vercel."""

    def __init__(self, url: str, *, connect: Connect | None = None) -> None:
        self.url = url
        self._schema = PostgresSchema(url, connect=connect)

    def _connect(self) -> Any:
        return self._schema.connect()

    def save(self, result: AnalysisResult, graph: GraphNeighborhood) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses(id, result_json, graph_json)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    result_json = EXCLUDED.result_json,
                    graph_json = EXCLUDED.graph_json,
                    created_at = NOW()
                """,
                (result.id, result.model_dump_json(), graph.model_dump_json()),
            )
            connection.commit()

    def get(self, analysis_id: str) -> AnalysisResult:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM analyses WHERE id = %s",
                (analysis_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"analysis not found: {analysis_id}")
        return AnalysisResult.model_validate_json(row[0])

    def graph(self, analysis_id: str) -> GraphNeighborhood:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT graph_json FROM analyses WHERE id = %s",
                (analysis_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"analysis graph not found: {analysis_id}")
        return GraphNeighborhood.model_validate_json(row[0])


class PostgresInventoryRepository:
    def __init__(
        self,
        url: str,
        *,
        capacity: int,
        ttl_seconds: int,
        connect: Connect | None = None,
    ) -> None:
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._schema = PostgresSchema(url, connect=connect)

    def put(self, inventory: ApplicationInventory) -> InventoryEnvelope:
        identifier = f"inv-{secrets.token_hex(16)}"
        expires = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        stored = inventory.model_copy(update={"id": identifier})
        with self._schema.connect() as connection:
            connection.execute(
                """
                INSERT INTO inventories(id, payload_json, expires_at)
                VALUES (%s, %s, %s)
                """,
                (identifier, stored.model_dump_json(), expires),
            )
            self._enforce_capacity(connection)
            connection.commit()
        return InventoryEnvelope(
            inventory_id=identifier,
            expires_at=expires,
            restart_persistence="database",
            inventory=stored,
        )

    def get(self, identifier: str) -> ApplicationInventory:
        validate_opaque_id(identifier, "inv")
        with self._schema.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM inventories
                WHERE id = %s AND expires_at > NOW()
                """,
                (identifier,),
            ).fetchone()
        if row is None:
            raise KeyError("inventory not found or expired")
        return ApplicationInventory.model_validate_json(row[0])

    def count(self) -> int:
        with self._schema.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM inventories WHERE expires_at > NOW()"
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def _enforce_capacity(self, connection: Any) -> None:
        connection.execute("DELETE FROM inventories WHERE expires_at <= NOW()")
        connection.execute(
            """
            DELETE FROM inventories
            WHERE id IN (
                SELECT id FROM inventories
                ORDER BY created_at ASC
                OFFSET %s
            )
            """,
            (self.capacity,),
        )


class PostgresJobRepository[T: BaseModel]:
    def __init__(
        self,
        url: str,
        *,
        model: type[T],
        kind: str,
        prefix: str,
        capacity: int,
        ttl_seconds: int,
        connect: Connect | None = None,
    ) -> None:
        self.model = model
        self.kind = kind
        self.prefix = prefix
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._schema = PostgresSchema(url, connect=connect)

    def put(self, identifier: str, value: T) -> None:
        validate_opaque_id(identifier, self.prefix)
        expires = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        with self._schema.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(id, kind, payload_json, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    expires_at = EXCLUDED.expires_at,
                    created_at = NOW()
                """,
                (identifier, self.kind, value.model_dump_json(), expires),
            )
            connection.execute("DELETE FROM jobs WHERE expires_at <= NOW()")
            connection.execute(
                """
                DELETE FROM jobs
                WHERE kind = %s AND id IN (
                    SELECT id FROM jobs
                    WHERE kind = %s
                    ORDER BY created_at ASC
                    OFFSET %s
                )
                """,
                (self.kind, self.kind, self.capacity),
            )
            connection.commit()

    def get(self, identifier: str) -> T:
        validate_opaque_id(identifier, self.prefix)
        with self._schema.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM jobs
                WHERE id = %s AND kind = %s AND expires_at > NOW()
                """,
                (identifier, self.kind),
            ).fetchone()
        if row is None:
            raise KeyError("job not found or expired")
        return self.model.model_validate_json(row[0])
