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
    )
    snapshot = repository.snapshot
    return RuntimeLexicon(
        accepted_words=snapshot.accepted_words,
        candidate_words=snapshot.candidate_words,
        correction_map=snapshot.correction_map,
        source=snapshot.runtime_source,
        version=snapshot.version,
        checksum=snapshot.checksum,
        loaded_at=snapshot.loaded_at,
    )
