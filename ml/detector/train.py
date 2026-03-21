from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

from ml.detector.labels import DETECTOR_LABEL_TO_ID, DETECTOR_PAD_LABEL_ID
from ml.training.dataset import build_token_vocabulary, encode_tokens, load_detector_examples


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DetectorTrainingConfig:
    name: str
    seed: int
    max_length: int
    batch_size: int
    epochs: int
    learning_rate: float
    device: str
    train_path: Path
    validation_path: Path
    output_dir: Path
    confidence_threshold: float
    model: dict[str, int]


def load_training_config(config_path: str | Path) -> DetectorTrainingConfig:
    config_path = Path(config_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    model_config = dict(raw_config["model"])
    model_config["num_labels"] = len(DETECTOR_LABEL_TO_ID)

    output_config = raw_config.get("output", {})
    inference_config = raw_config.get("inference", {})

    return DetectorTrainingConfig(
        name=raw_config.get("name", "detector-base"),
        seed=int(raw_config.get("seed", 42)),
        max_length=int(raw_config.get("max_length", 256)),
        batch_size=int(raw_config.get("batch_size", 16)),
        epochs=int(raw_config.get("epochs", 10)),
        learning_rate=float(raw_config.get("learning_rate", 3e-4)),
        device=str(raw_config.get("device", "auto")),
        train_path=_resolve_repo_path(raw_config["data"]["train_path"]),
        validation_path=_resolve_repo_path(raw_config["data"]["validation_path"]),
        output_dir=_resolve_repo_path(output_config.get("dir", f"artifacts/detector/{raw_config.get('name', 'detector-base')}")),
        confidence_threshold=float(inference_config.get("confidence_threshold", 0.8)),
        model=model_config,
    )


def build_training_artifacts(config: DetectorTrainingConfig) -> dict[str, object]:
    train_examples = load_detector_examples(config.train_path)
    validation_examples = load_detector_examples(config.validation_path)
    vocabulary = build_token_vocabulary(
        train_examples + validation_examples,
        max_size=int(config.model["vocab_size"]),
    )
    train_records = _encode_examples(train_examples, vocabulary, config.max_length)
    validation_records = _encode_examples(validation_examples, vocabulary, config.max_length)

    return {
        "train_examples": train_examples,
        "validation_examples": validation_examples,
        "vocabulary": vocabulary,
        "train_records": train_records,
        "validation_records": validation_records,
    }


def train_detector(config: DetectorTrainingConfig) -> dict[str, object]:
    try:
        import torch
        from torch import nn
    except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
        raise RuntimeError("PyTorch is required to train the detector") from error

    from ml.detector.model import BanglaDetectorEncoder

    _set_seed(config.seed, torch)
    artifacts = build_training_artifacts(config)
    vocabulary = artifacts["vocabulary"]
    train_records = artifacts["train_records"]
    validation_records = artifacts["validation_records"]

    model = BanglaDetectorEncoder(
        vocab_size=len(vocabulary),
        hidden_size=config.model["hidden_size"],
        num_heads=config.model["num_heads"],
        num_layers=config.model["num_layers"],
        num_labels=config.model["num_labels"],
        max_length=config.max_length,
    )
    device = _resolve_device(config.device, torch)
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    loss_function = nn.CrossEntropyLoss(ignore_index=DETECTOR_PAD_LABEL_ID)

    best_metrics: dict[str, float] | None = None
    history: list[dict[str, float | int]] = []

    for epoch in range(1, config.epochs + 1):
        train_metrics = _run_epoch(
            model=model,
            dataset=train_records,
            batch_size=config.batch_size,
            device=device,
            torch_module=torch,
            loss_function=loss_function,
            optimizer=optimizer,
            training=True,
        )
        validation_metrics = _run_epoch(
            model=model,
            dataset=validation_records,
            batch_size=config.batch_size,
            device=device,
            torch_module=torch,
            loss_function=loss_function,
            optimizer=None,
            training=False,
        )
        epoch_metrics = {"epoch": epoch, **train_metrics, **{f"validation_{key}": value for key, value in validation_metrics.items()}}
        history.append(epoch_metrics)

        if best_metrics is None or validation_metrics["loss"] <= best_metrics["loss"]:
            best_metrics = dict(validation_metrics)
            _save_checkpoint(
                output_dir=config.output_dir,
                checkpoint_name="best_model.pt",
                model=model,
                optimizer=optimizer,
                epoch=epoch,
                torch_module=torch,
            )

    _save_checkpoint(
        output_dir=config.output_dir,
        checkpoint_name="last_model.pt",
        model=model,
        optimizer=optimizer,
        epoch=config.epochs,
        torch_module=torch,
    )

    metrics = {
        "best_validation": best_metrics or {},
        "history": history,
        "train_examples": len(artifacts["train_examples"]),
        "validation_examples": len(artifacts["validation_examples"]),
    }
    _write_metadata(config=config, vocabulary=vocabulary, metrics=metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Shuddho detector with a lightweight token classifier.")
    parser.add_argument("--config", required=True, help="Path to detector config JSON.")
    args = parser.parse_args()

    config = load_training_config(args.config)
    metrics = train_detector(config)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def _encode_examples(examples, vocabulary: dict[str, int], max_length: int) -> list[dict[str, list[int]]]:
    encoded_records: list[dict[str, list[int]]] = []
    for example in examples:
        token_ids = encode_tokens(example.tokens[:max_length], vocabulary)
        label_ids = list(example.token_labels[:max_length])
        encoded_records.append({"input_ids": token_ids, "label_ids": label_ids})
    return encoded_records


def _run_epoch(
    *,
    model,
    dataset: list[dict[str, list[int]]],
    batch_size: int,
    device,
    torch_module,
    loss_function,
    optimizer,
    training: bool,
) -> dict[str, float]:
    if not dataset:
        return {"loss": 0.0, "token_accuracy": 0.0, "error_precision": 0.0, "error_recall": 0.0, "error_f1": 0.0}

    model.train(mode=training)
    total_loss = 0.0
    total_tokens = 0
    correct_tokens = 0
    true_error_tokens = 0
    predicted_error_tokens = 0
    matched_error_tokens = 0

    for batch_start in range(0, len(dataset), batch_size):
        batch_records = dataset[batch_start : batch_start + batch_size]
        input_ids, attention_mask, labels = _collate_batch(batch_records, torch_module, device)
        outputs = model(input_ids, attention_mask)
        logits = outputs["logits"]
        loss = loss_function(logits.view(-1, logits.shape[-1]), labels.view(-1))

        if training and optimizer is not None:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        total_loss += float(loss.item())

        predictions = logits.argmax(dim=-1)
        valid_mask = labels != DETECTOR_PAD_LABEL_ID
        correct_tokens += int(((predictions == labels) & valid_mask).sum().item())
        total_tokens += int(valid_mask.sum().item())

        error_mask = labels > 0
        predicted_error_mask = predictions > 0
        matched_error_tokens += int((predicted_error_mask & error_mask & valid_mask).sum().item())
        predicted_error_tokens += int((predicted_error_mask & valid_mask).sum().item())
        true_error_tokens += int((error_mask & valid_mask).sum().item())

    precision = matched_error_tokens / predicted_error_tokens if predicted_error_tokens else 0.0
    recall = matched_error_tokens / true_error_tokens if true_error_tokens else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0

    return {
        "loss": round(total_loss / max((len(dataset) + batch_size - 1) // batch_size, 1), 4),
        "token_accuracy": round(correct_tokens / max(total_tokens, 1), 4),
        "error_precision": round(precision, 4),
        "error_recall": round(recall, 4),
        "error_f1": round(f1, 4),
    }


def _collate_batch(batch_records: list[dict[str, list[int]]], torch_module, device):
    max_length = max(len(record["input_ids"]) for record in batch_records)
    batch_size = len(batch_records)

    input_ids = torch_module.zeros((batch_size, max_length), dtype=torch_module.long, device=device)
    attention_mask = torch_module.zeros((batch_size, max_length), dtype=torch_module.long, device=device)
    labels = torch_module.full((batch_size, max_length), DETECTOR_PAD_LABEL_ID, dtype=torch_module.long, device=device)

    for index, record in enumerate(batch_records):
        length = len(record["input_ids"])
        input_ids[index, :length] = torch_module.tensor(record["input_ids"], dtype=torch_module.long, device=device)
        attention_mask[index, :length] = 1
        labels[index, :length] = torch_module.tensor(record["label_ids"], dtype=torch_module.long, device=device)

    return input_ids, attention_mask, labels


def _save_checkpoint(*, output_dir: Path, checkpoint_name: str, model, optimizer, epoch: int, torch_module) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    torch_module.save(
        {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
        },
        output_dir / checkpoint_name,
    )


def _write_metadata(*, config: DetectorTrainingConfig, vocabulary: dict[str, int], metrics: dict[str, object]) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "format": "shuddho-detector-v1",
        "name": config.name,
        "max_length": config.max_length,
        "confidence_threshold": config.confidence_threshold,
        "label_to_id": DETECTOR_LABEL_TO_ID,
        "vocabulary": vocabulary,
        "model": config.model,
        "metrics": metrics,
    }
    (config.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (config.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_repo_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def _resolve_device(device_name: str, torch_module):
    if device_name == "cpu":
        return torch_module.device("cpu")
    if device_name == "cuda":
        return torch_module.device("cuda")
    return torch_module.device("cuda" if torch_module.cuda.is_available() else "cpu")


def _set_seed(seed: int, torch_module) -> None:
    random.seed(seed)
    torch_module.manual_seed(seed)
    if torch_module.cuda.is_available():
        torch_module.cuda.manual_seed_all(seed)


if __name__ == "__main__":
    main()
