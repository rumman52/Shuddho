import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from ml.corrector.evaluate import evaluate_checkpoint
from ml.corrector.infer import CorrectorPrediction, load_corrector_backend, load_corrector_bundle
from ml.corrector.train import load_training_config, train_corrector
from shared.schemas.python_models import AnalyzeMode, SuggestionCategory


def test_corrector_training_writes_local_checkpoint_bundle(tmp_path: Path) -> None:
    train_path = tmp_path / "train.jsonl"
    valid_path = tmp_path / "valid.jsonl"
    output_dir = tmp_path / "artifacts" / "corrector-smoke"

    _write_dataset(
        train_path,
        [
            ("আমি বাংলা বাংলা লিখি।", "আমি বাংলা লিখি।"),
            ("বাংলা  ভাষা সুন্দর ।", "বাংলা ভাষা সুন্দর।"),
            ("সে স্কুলে যায় ।", "সে স্কুলে যায়।"),
        ],
    )
    _write_dataset(
        valid_path,
        [
            ("তুমি বাংলা বাংলা পড়ো।", "তুমি বাংলা পড়ো।"),
        ],
    )
    config_path = tmp_path / "corrector.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "corrector-smoke",
                "seed": 7,
                "max_source_length": 96,
                "max_target_length": 96,
                "batch_size": 2,
                "epochs": 1,
                "learning_rate": 0.001,
                "teacher_forcing_ratio": 0.85,
                "device": "cpu",
                "model": {
                    "vocab_size": 128,
                    "embedding_size": 32,
                    "hidden_size": 48,
                    "dropout": 0.1,
                    "min_frequency": 1,
                },
                "data": {
                    "train_path": _to_repo_relative(train_path),
                    "validation_path": _to_repo_relative(valid_path),
                },
                "output": {
                    "dir": _to_repo_relative(output_dir),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    config = load_training_config(config_path)
    metrics = train_corrector(config)

    assert metrics["train_examples"] == 3
    assert metrics["validation_examples"] == 1
    assert (output_dir / "metadata.json").exists()
    assert (output_dir / "best_model.pt").exists()
    assert (output_dir / "last_model.pt").exists()
    assert (output_dir / "metrics.json").exists()

    bundle = load_corrector_bundle(output_dir, device="cpu")
    assert bundle.metadata["format"] == "shuddho-corrector-v1"
    assert bundle.metadata["name"] == "corrector-smoke"
    assert bundle.tokenizer.vocab_size >= 8

    evaluation_metrics = evaluate_checkpoint(
        checkpoint_dir=output_dir,
        dataset_path=valid_path,
        batch_size=1,
        device="cpu",
    )
    assert set(evaluation_metrics) == {
        "loss",
        "exact_match",
        "char_accuracy",
        "char_error_rate",
        "mean_sequence_confidence",
    }


def test_corrector_backend_projects_sentence_predictions_into_inline_suggestions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = _train_smoke_checkpoint(tmp_path)
    backend = load_corrector_backend(output_dir, confidence_threshold=0.0)

    def fake_correct_sentence(sentence: str) -> CorrectorPrediction:
        if "বংলা" in sentence:
            corrected = sentence.replace("বংলা", "বাংলা")
        else:
            corrected = f"{sentence.rstrip('।')}।"
        return CorrectorPrediction(
            source_text=sentence,
            corrected_text=corrected,
            confidence=0.96,
            token_ids=(1, 2, 3),
            token_confidences=(0.97, 0.96, 0.95),
        )

    monkeypatch.setattr(backend, "correct_sentence", fake_correct_sentence)

    suggestions = backend.suggest("আমি বংলা লিখি। তুমি ভালো আছ", AnalyzeMode.STRICT)

    assert len(suggestions) == 2
    spelling = next(suggestion for suggestion in suggestions if suggestion.category == SuggestionCategory.SPELLING)
    punctuation = next(suggestion for suggestion in suggestions if suggestion.category == SuggestionCategory.PUNCTUATION)

    assert spelling.original_text
    assert spelling.replacement_options
    assert spelling.span_end - spelling.span_start < len("আমি বংলা লিখি।")
    assert spelling.sentence_index == 0
    assert spelling.source_trace == ["corrector_seq2seq", "exact_unique_match"]

    assert punctuation.original_text == "আছ"
    assert punctuation.replacement_options == ["আছ।"]
    assert punctuation.sentence_index == 1
    assert punctuation.anchor_before is not None or punctuation.anchor_after is not None


def _train_smoke_checkpoint(tmp_path: Path) -> Path:
    train_path = tmp_path / "train.jsonl"
    valid_path = tmp_path / "valid.jsonl"
    output_dir = tmp_path / "artifacts" / "corrector-smoke"

    _write_dataset(
        train_path,
        [
            ("আমি বাংলা বাংলা লিখি।", "আমি বাংলা লিখি।"),
            ("বাংলা  ভাষা সুন্দর ।", "বাংলা ভাষা সুন্দর।"),
            ("তুমি ভালো আছ", "তুমি ভালো আছ।"),
        ],
    )
    _write_dataset(
        valid_path,
        [
            ("সে বাংলা বাংলা বলে।", "সে বাংলা বলে।"),
        ],
    )

    config_path = tmp_path / "corrector.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "corrector-smoke",
                "seed": 11,
                "max_source_length": 96,
                "max_target_length": 96,
                "batch_size": 2,
                "epochs": 1,
                "learning_rate": 0.001,
                "teacher_forcing_ratio": 0.85,
                "device": "cpu",
                "model": {
                    "vocab_size": 128,
                    "embedding_size": 24,
                    "hidden_size": 40,
                    "dropout": 0.1,
                    "min_frequency": 1,
                },
                "data": {
                    "train_path": _to_repo_relative(train_path),
                    "validation_path": _to_repo_relative(valid_path),
                },
                "output": {
                    "dir": _to_repo_relative(output_dir),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    train_corrector(load_training_config(config_path))
    return output_dir


def _write_dataset(path: Path, rows: list[tuple[str, str]]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "source_text": source_text,
                    "target_text": target_text,
                },
                ensure_ascii=False,
            )
            for source_text, target_text in rows
        )
        + "\n",
        encoding="utf-8",
    )


def _to_repo_relative(path: Path) -> str:
    return path.resolve().as_posix()
