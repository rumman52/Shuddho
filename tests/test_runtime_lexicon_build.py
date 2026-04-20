import csv
import json
from pathlib import Path

from scripts.build_runtime_lexicon import RuntimeLexiconBuildPaths, build_runtime_lexicon
from services.spell.shuddho_spell.engine import SpellEngine
from services.spell.shuddho_spell.repository import LexiconRepository
from services.spell.shuddho_spell.runtime_lexicon import load_runtime_lexicon


def test_build_runtime_lexicon_creates_layered_runtime_outputs(tmp_path: Path) -> None:
    imports_dir = tmp_path / "imports" / "lexicon"
    runtime_dir = tmp_path / "runtime" / "lexicon"
    imports_dir.mkdir(parents=True)

    clean_csv_path = imports_dir / "words_clean.csv"
    review_csv_path = imports_dir / "words_review_flagged.csv"
    summary_path = imports_dir / "cleaning_summary.txt"
    provenance_path = imports_dir / "provenance.json"

    clean_csv_path.write_text(
        "\n".join(
            [
                "word,normalized_word,source,is_trusted,is_common,is_active",
                "বাংলা,বাংলা,common.csv,1,1,1",
                "নিয়ে,নিয়ে,variant.csv,1,0,1",
                "ঢাকা,ঢাকা,named_entity_seed.csv,1,0,1",
                "অই,অই,seed.csv,1,0,1",
                "পুরোনো,পুরোনো,seed.csv,1,0,0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    review_csv_path.write_text(
        "\n".join(
            [
                "original_word,normalized_word,reasons",
                "অংঙ্গন,অঙ্গন,possible_inflected_form",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        "\n".join(
            [
                "Raw tokens: 5",
                "Clean unique rows exported: 5",
                "Duplicates removed: 0",
                "Hard rejected: 1",
                "Flagged for review: 1",
                "",
                "Sample cleaned words:",
                "বাংলা",
                "নিয়ে",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    provenance_path.write_text(
        json.dumps({"policy_version": "shuddho-lexicon-policy-v1"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = build_runtime_lexicon(
        RuntimeLexiconBuildPaths(
            clean_csv_path=clean_csv_path,
            review_csv_path=review_csv_path,
            summary_path=summary_path,
            provenance_path=provenance_path,
            runtime_dir=runtime_dir,
        )
    )

    assert result.runtime_words_path.exists()
    assert result.runtime_metadata_path.exists()
    assert result.runtime_review_path.exists()
    assert result.runtime_reject_path.exists()
    assert result.accepted_word_count == 3
    assert result.candidate_word_count == 3
    assert result.correction_map_count == 1
    assert result.layer_counts == {
        "core_formal_words": 1,
        "accepted_variants": 1,
        "named_entities": 1,
        "colloquial_or_dialect_review": 1,
        "reject_list": 1,
    }

    runtime_rows = list(csv.DictReader(result.runtime_words_path.open("r", encoding="utf-8")))
    review_rows = list(csv.DictReader(result.runtime_review_path.open("r", encoding="utf-8")))
    reject_rows = list(csv.DictReader(result.runtime_reject_path.open("r", encoding="utf-8")))
    metadata = json.loads(result.runtime_metadata_path.read_text(encoding="utf-8"))

    assert {row["layer"] for row in runtime_rows} == {
        "core_formal_words",
        "accepted_variants",
        "named_entities",
    }
    assert any(row["word"] == "অই" and row["layer"] == "colloquial_or_dialect_review" for row in review_rows)
    assert any(row["word"] == "পুরোনো" and row["layer"] == "reject_list" for row in reject_rows)
    assert metadata["runtime_source_of_truth"] == "built_runtime_csv"
    assert metadata["user_dictionary_supported"] is True


def test_spell_engine_loads_built_runtime_artifact_and_variant_map(tmp_path: Path) -> None:
    imports_dir = tmp_path / "imports" / "lexicon"
    runtime_dir = tmp_path / "runtime" / "lexicon"
    imports_dir.mkdir(parents=True)

    (imports_dir / "words_clean.csv").write_text(
        "\n".join(
            [
                "word,normalized_word,source,is_trusted,is_common,is_active",
                "বাংলা,বাংলা,common.csv,1,1,1",
                "নিয়ে,নিয়ে,variant.csv,1,0,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (imports_dir / "words_review_flagged.csv").write_text(
        "original_word,normalized_word,reasons\n",
        encoding="utf-8",
    )
    (imports_dir / "cleaning_summary.txt").write_text(
        "Raw tokens: 2\nClean unique rows exported: 2\nDuplicates removed: 0\nHard rejected: 0\nFlagged for review: 0\n",
        encoding="utf-8",
    )
    (imports_dir / "provenance.json").write_text(
        json.dumps({"policy_version": "shuddho-lexicon-policy-v1"}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = build_runtime_lexicon(
        RuntimeLexiconBuildPaths(
            clean_csv_path=imports_dir / "words_clean.csv",
            review_csv_path=imports_dir / "words_review_flagged.csv",
            summary_path=imports_dir / "cleaning_summary.txt",
            provenance_path=imports_dir / "provenance.json",
            runtime_dir=runtime_dir,
        )
    )

    engine = SpellEngine(runtime_csv_path=result.runtime_words_path)
    suggestions = engine.analyze("নিয়ে")

    assert engine.lexicon_source == "runtime_words.csv"
    assert suggestions
    assert suggestions[0].replacement_options == ["নিয়ে"]

    repository = LexiconRepository(
        result.runtime_words_path,
        runtime_metadata_path=result.runtime_metadata_path,
    )
    assert repository.snapshot.runtime_source_of_truth == "built_runtime_csv"

    runtime_lexicon = load_runtime_lexicon(result.runtime_words_path)
    assert runtime_lexicon.source == "runtime_words.csv"
