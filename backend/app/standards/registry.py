import hashlib
from pathlib import Path

import yaml

from app.config import REPOSITORY_ROOT
from app.domain.models import RegulatorySource, StandardsManifest


class StandardsRegistryError(RuntimeError):
    """Base error for a standards registry integrity failure."""


class SourceDigestMismatchError(StandardsRegistryError):
    """Raised when a pinned source differs from its reviewed digest."""


class StandardsRegistry:
    def __init__(self, manifest_path: Path | None = None) -> None:
        default_manifest = REPOSITORY_ROOT / "data" / "standards" / "manifest.yaml"
        self.manifest_path = manifest_path or default_manifest
        self.standards_directory = self.manifest_path.parent.resolve()

    def load(self, *, verify_digests: bool = True) -> StandardsManifest:
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            payload = yaml.safe_load(manifest_file)
        manifest = StandardsManifest.model_validate(payload)
        if verify_digests:
            for source in manifest.sources:
                self._verify_source(source)
        return manifest

    def _verify_source(self, source: RegulatorySource) -> None:
        source_path = (self.standards_directory / source.local_path).resolve()
        try:
            source_path.relative_to(self.standards_directory)
        except ValueError as error:
            raise StandardsRegistryError(
                f"source path escapes standards directory: {source.id}"
            ) from error
        if not source_path.is_file():
            raise StandardsRegistryError(f"pinned source is missing: {source.id}")

        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if digest != source.sha256:
            raise SourceDigestMismatchError(
                f"source digest mismatch for {source.id}: expected {source.sha256}, got {digest}"
            )
