from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.spell.shuddho_spell.lexicon_import import LexiconImportPaths, export_seed_lexicon, import_lexicon_to_sqlite


def main() -> int:
    defaults = LexiconImportPaths.defaults(REPO_ROOT)
    parser = argparse.ArgumentParser(
        description="Import cleaned lexicon files into the dedicated SQLite database for offline lexicon management."
    )
    parser.add_argument("--clean-csv", default=str(defaults.clean_csv_path))
    parser.add_argument("--review-csv", default=str(defaults.review_csv_path))
    parser.add_argument("--summary", default=str(defaults.summary_path))
    parser.add_argument("--database", default=str(defaults.database_path))
    parser.add_argument(
        "--export-seed-lexicon",
        action="store_true",
        help="Also export active normalized words into services/spell/data/seed_lexicon.txt.",
    )
    parser.add_argument("--seed-output", default=str(defaults.seed_lexicon_path))
    args = parser.parse_args()

    paths = LexiconImportPaths(
        clean_csv_path=_resolve_path(args.clean_csv),
        review_csv_path=_resolve_path(args.review_csv),
        summary_path=_resolve_path(args.summary),
        database_path=_resolve_path(args.database),
        seed_lexicon_path=_resolve_path(args.seed_output),
    )

    result = import_lexicon_to_sqlite(paths)
    print(f"Imported lexicon database: {result.database_path}")
    print(f"words_clean rows: {result.clean_rows}")
    print(f"words_review_flagged rows: {result.review_rows}")
    print(f"import_reports rows: {result.report_rows}")

    if args.export_seed_lexicon:
        exported_rows = export_seed_lexicon(result.database_path, paths.seed_lexicon_path)
        print(f"seed_lexicon.txt rows exported: {exported_rows}")
        print(f"Seed lexicon written to: {paths.seed_lexicon_path}")

    return 0


def _resolve_path(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


if __name__ == "__main__":
    raise SystemExit(main())
