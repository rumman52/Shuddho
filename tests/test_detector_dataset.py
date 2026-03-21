import json
from pathlib import Path

from ml.detector.labels import DETECTOR_LABEL_TO_ID
from ml.detector.train import build_training_artifacts, load_training_config
from ml.training.dataset import build_detector_example, build_token_vocabulary, encode_tokens


def test_build_detector_example_labels_tokens_from_issue_spans() -> None:
    record = {
        "input_text": "আমি কিন্ত স্কুলে যাই।",
        "issues": [
            {"start": 4, "end": 9, "label": "spelling", "subtype": "variant_mapping"},
        ],
    }

    example = build_detector_example(record)

    assert example.tokens == ("আমি", "কিন্ত", "স্কুলে", "যাই", "।")
    assert example.token_labels == (
        DETECTOR_LABEL_TO_ID["ok"],
        DETECTOR_LABEL_TO_ID["spelling"],
        DETECTOR_LABEL_TO_ID["ok"],
        DETECTOR_LABEL_TO_ID["ok"],
        DETECTOR_LABEL_TO_ID["ok"],
    )


def test_load_training_config_and_artifacts_build_real_vocab(tmp_path: Path) -> None:
    train_path = tmp_path / "detector_train.jsonl"
    valid_path = tmp_path / "detector_valid.jsonl"
    output_dir = tmp_path / "artifacts"

    train_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "input_text": "আমি আমি স্কুলে যাই।।",
                        "issues": [
                            {"start": 0, "end": 7, "label": "grammar", "subtype": "repeated_word"},
                            {"start": 19, "end": 21, "label": "punctuation", "subtype": "duplicate_punctuation"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "input_text": "আমি কিন্ত স্কুলে যাই।",
                        "issues": [
                            {"start": 4, "end": 9, "label": "spelling", "subtype": "variant_mapping"},
                        ],
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(
            {
                "input_text": "সে  স্কুলে যায় ।",
                "issues": [
                    {"start": 2, "end": 4, "label": "spacing", "subtype": "extra_whitespace"},
                    {"start": 15, "end": 17, "label": "punctuation", "subtype": "space_before_punctuation"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config_path = tmp_path / "detector.base.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "detector-test",
                "seed": 7,
                "max_length": 32,
                "batch_size": 2,
                "epochs": 1,
                "learning_rate": 0.001,
                "device": "cpu",
                "model": {"vocab_size": 32, "hidden_size": 16, "num_heads": 2, "num_layers": 1, "num_labels": 2},
                "data": {
                    "train_path": str(train_path),
                    "validation_path": str(valid_path),
                },
                "output": {"dir": str(output_dir)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = load_training_config(config_path)
    artifacts = build_training_artifacts(config)

    assert config.model["num_labels"] == len(DETECTOR_LABEL_TO_ID)
    assert artifacts["train_examples"]
    assert artifacts["validation_examples"]
    assert "আমি" in artifacts["vocabulary"]
    assert artifacts["train_records"][0]["input_ids"]
    assert artifacts["train_records"][0]["label_ids"]


def test_build_token_vocabulary_and_encoding_are_stable() -> None:
    first = build_detector_example({"input_text": "আমি কিন্ত স্কুলে যাই।"})
    second = build_detector_example({"input_text": "সে স্কুলে যায়।"})

    vocabulary = build_token_vocabulary([first, second], max_size=16)
    encoded = encode_tokens(first.tokens, vocabulary)

    assert vocabulary["<pad>"] == 0
    assert vocabulary["<unk>"] == 1
    assert len(encoded) == len(first.tokens)
