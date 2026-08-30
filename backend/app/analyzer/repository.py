import sqlite3
from pathlib import Path

from app.domain.models import AnalysisResult
from app.graph.models import GraphNeighborhood


class AnalysisRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    graph_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    version INTEGER NOT NULL
                );
                INSERT INTO schema_metadata(version)
                SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_metadata);
                """
            )

    def save(self, result: AnalysisResult, graph: GraphNeighborhood) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses(id, result_json, graph_json)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    result_json = excluded.result_json,
                    graph_json = excluded.graph_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (result.id, result.model_dump_json(), graph.model_dump_json()),
            )

    def get(self, analysis_id: str) -> AnalysisResult:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"analysis not found: {analysis_id}")
        return AnalysisResult.model_validate_json(row[0])

    def graph(self, analysis_id: str) -> GraphNeighborhood:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT graph_json FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"analysis graph not found: {analysis_id}")
        return GraphNeighborhood.model_validate_json(row[0])
