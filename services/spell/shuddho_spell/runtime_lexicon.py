from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .repository import LexiconRepository


@dataclass(frozen=True)
class RuntimeLexicon:
    accepted_words: tuple[str, ...]
    candidate_words: tuple[str, ...]
    correction_map: dict[str, str]
    variant_map: dict[str, str]
    protected_words: tuple[str, ...]
    source: str
    version: str | None = None
    checksum: str | None = None
    loaded_at: datetime | None = None


def load_runtime_lexicon(
    clean_csv_path: Path,
    *,
    fallback_seed_path: Path | None = None,
) -> RuntimeLexicon:
    import_database_path = clean_csv_path.resolve().parents[2] / "shuddho_lexicon.db" if clean_csv_path.exists() else None
    repository = LexiconRepository(
        clean_csv_path,
        fallback_seed_path=fallback_seed_path,
        import_database_path=import_database_path,
        runtime_metadata_path=clean_csv_path.with_name("runtime_metadata.json") if clean_csv_path.name == "runtime_words.csv" else None,
    )
    snapshot = repository.snapshot
    return RuntimeLexicon(
        accepted_words=snapshot.accepted_words,
        candidate_words=snapshot.candidate_words,
        correction_map=snapshot.correction_map,
        variant_map=snapshot.variant_map,
        protected_words=snapshot.protected_words,
        source=snapshot.runtime_source,
        version=snapshot.version,
        checksum=snapshot.checksum,
        loaded_at=snapshot.loaded_at,
    )
