from __future__ import annotations

import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from app.parsers.models import ApplicationInventory
from app.product.models import ComparisonRun, DossierAnalysisRun, InventoryEnvelope

_OPAQUE_ID = re.compile(r"^(?:inv|dossier|comparison)-[a-f0-9]{24,64}$")
T = TypeVar("T")


def validate_opaque_id(value: str, prefix: str) -> None:
    if not _OPAQUE_ID.fullmatch(value) or not value.startswith(prefix + "-"):
        raise KeyError("malformed or unknown opaque identifier")


@dataclass
class _Entry[T]:
    value: T
    expires_at: float


class InventoryRepository:
    def __init__(self, *, capacity: int, ttl_seconds: int) -> None:
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, _Entry[ApplicationInventory]] = OrderedDict()
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.monotonic()
        for key in [key for key, entry in self._items.items() if entry.expires_at <= now]:
            self._items.pop(key, None)

    def put(self, inventory: ApplicationInventory) -> InventoryEnvelope:
        with self._lock:
            self._purge()
            identifier = f"inv-{secrets.token_hex(16)}"
            expires = time.monotonic() + self.ttl_seconds
            # Uploaded profile inventories already carry fixture_id=None. Preserve the explicit
            # fixture identifier only for the legacy controlled regression route so its offline
            # semantic contract remains intact.
            stored = inventory.model_copy(update={"id": identifier})
            self._items[identifier] = _Entry(stored, expires)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
            return InventoryEnvelope(
                inventory_id=identifier,
                expires_at=datetime.fromtimestamp(time.time() + self.ttl_seconds, UTC),
                inventory=stored,
            )

    def get(self, identifier: str) -> ApplicationInventory:
        validate_opaque_id(identifier, "inv")
        with self._lock:
            self._purge()
            entry = self._items.get(identifier)
            if entry is None:
                raise KeyError("inventory not found or expired")
            self._items.move_to_end(identifier)
            return entry.value

    def count(self) -> int:
        with self._lock:
            self._purge()
            return len(self._items)


class JobRepository[T]:
    def __init__(self, *, capacity: int, ttl_seconds: int, prefix: str) -> None:
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self._items: OrderedDict[str, _Entry[T]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, identifier: str, value: T) -> None:
        validate_opaque_id(identifier, self.prefix)
        with self._lock:
            self._items[identifier] = _Entry(value, time.monotonic() + self.ttl_seconds)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def get(self, identifier: str) -> T:
        validate_opaque_id(identifier, self.prefix)
        with self._lock:
            now = time.monotonic()
            for key in [key for key, entry in self._items.items() if entry.expires_at <= now]:
                self._items.pop(key, None)
            entry = self._items.get(identifier)
            if entry is None:
                raise KeyError("job not found or expired")
            return entry.value


DossierRunRepository = JobRepository[DossierAnalysisRun]
ComparisonRunRepository = JobRepository[ComparisonRun]
