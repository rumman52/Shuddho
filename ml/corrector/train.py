from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

from ml.corrector.model import BanglaCorrectorSeq2Seq
from ml.corrector.tokenizer import CharacterTokenizer, CorrectorExample, load_corrector_examples, split_examples


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CorrectorTrainingConfig:
    name: str
    seed: int
    max_source_length: int
    max_target_length: int
    batch_size: int
    epochs: int
    learning_rate: float
    teacher_forcing_ratio: float
    device: str
    train_path: Path
    validation_path: Path | None
    validation_split: float
    output_dir: Path
    model: dict[str, int | float]


def load_training_config(config_path: str | Path) -> CorrectorTrainingConfig:
    config_path = Path(config_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    model_config = dict(raw_config.get("model", {}))
    name = raw_config.get("name", "corrector-base")
    max_length = int(raw_config.get("max_length", 192))

    data_config = raw_config.get("data", {})
    output_config = raw_config.get("output", {})

    validation_path_value = data_config.get("validation_path")
    validation_path = _resolve_repo_path(validation_path_value) if validation_path_value else None

    return CorrectorTrainingConfig(
        name=name,
        seed=int(raw_config.get("seed", 42)),
        max_source_length=int(raw_config.get("max_source_length", max_length)),
        max_target_length=int(raw_config.get("max_target_length", max_length)),
        batch_size=int(raw_config.get("batch_size", 12)),
        epochs=int(raw_config.get("epochs", 12)),
        learning_rate=float(raw_config.get("learning_rate", 3e-4)),
        teacher_forcing_ratio=float(raw_config.get("teacher_forcing_ratio", 1.0)),
        device=str(raw_config.get("device", "auto")),
        train_path=_resolve_repo_path(data_config["train_path"]),
        validation_path=validation_path,
        validation_split=float(data_config.get("validation_split", 0.1)),
        output_dir=_resolve_repo_path(output_config.get("dir", f"artifacts/corrector/{name}")),
        model={
            "max_vocab_size": int(model_config.get("vocab_size", 512)),
            "embedding_size": int(model_config.get("embedding_size", 128)),
            "hidden_size": int(model_config.get("hidden_size", 192)),
            "dropout": float(model_config.get("dropout", 0.15)),
            "min_frequency": int(model_config.get("min_frequency", 1)),
            "pad_token_id": 0,
        },
    )


def build_training_artifacts(config: CorrectorTrainingConfig) -> dict[str, object]:
    train_examples = load_corrector_examples(config.train_path)
    if config.validation_path is not None:
        validation_examples = load_corrector_examples(config.validation_path)
    else:
        train_examples, validation_examples = split_examples(
            train_examples,
            validation_ratio=config.validation_split,
            seed=config.seed,
        )

    tokenizer = CharacterTokenizer.train(
        [example.source_text for example in [*train_examples, *validation_examples]]
        + [example.target_text for example in [*train_examples, *validation_examples]],
        max_vocab_size=int(config.model["max_vocab_size"]),
        min_frequency=int(config.model["min_frequency"]),
    )

    train_dataset = CorrectorDataset(
        train_examples,
        tokenizer=tokenizer,
        max_source_length=config.max_source_length,
        max_target_length=config.max_target_length,
    )
    validation_dataset = CorrectorDataset(
        validation_examples,
        tokenizer=tokenizer,
        max_source_length=config.max_source_length,
        max_target_length=config.max_target_length,
    )

    return {
        "train_examples": train_examples,
        "validation_examples": validation_examples,
        "tokenizer": tokenizer,
        "train_dataset": train_dataset,
        "validation_dataset": validation_dataset,
    }


def train_corrector(config: CorrectorTrainingConfig) -> dict[str, object]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader
    except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
        raise RuntimeError("PyTorch is required to train the corrector") from error

    _set_seed(config.seed, torch)
    artifacts = build_training_artifacts(config)
    tokenizer: CharacterTokenizer = artifacts["tokenizer"]  # type: ignore[assignment]
    train_dataset: CorrectorDataset = artifacts["train_dataset"]  # type: ignore[assignment]
    validation_dataset: CorrectorDataset = artifacts["validation_dataset"]  # type: ignore[assignment]

    model = BanglaCorrectorSeq2Seq(
        vocab_size=tokenizer.vocab_size,
        embedding_size=int(config.model["embedding_size"]),
        hidden_size=int(config.model["hidden_size"]),
        dropout=float(config.model["dropout"]),
        pad_token_id=tokenizer.pad_token_id,
    )
    device = _resolve_device(config.device, torch)
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    loss_function = nn.CrossEntropyLoss(ignore_index=tokenizer.pad_token_id)
    collate_fn = build_collate_fn(tokenizer.pad_token_id, torch)
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        collate_fn=collate_fn,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        collate_fn=collate_fn,
    )

    best_metrics: dict[str, float] | None = None
    history: list[dict[str, float | int]] = []

    for epoch in range(1, config.epochs + 1):
        train_metrics = _run_epoch(
            model=model,
            dataloader=train_loader,
            optimizer=optimizer,
            loss_function=loss_function,
            tokenizer=tokenizer,
            device=device,
            torch_module=torch,
            teacher_forcing_ratio=config.teacher_forcing_ratio,
            training=True,
        )
        validation_metrics = _run_epoch(
            model=model,
            dataloader=validation_loader,
            optimizer=None,
            loss_function=loss_function,
            tokenizer=tokenizer,
            device=device,
            torch_module=torch,
            teacher_forcing_ratio=1.0,
            training=False,
        )
        epoch_metrics = {
            "epoch": epoch,
            **{f"train_{key}": value for key, value in train_metrics.items()},
            **{f"validation_{key}": value for key, value in validation_metrics.items()},
        }
        history.append(epoch_metrics)

        if best_metrics is None or validation_metrics["loss"] <= best_metrics["loss"]:
            best_metrics = dict(validation_metrics)
            _save_checkpoint(
                output_dir=config.output_dir,
                checkpoint_name="best_model.pt",
                model=model,
                optimizer=optimizer,
                epoch=epoch,
                tokenizer=tokenizer,
                config=config,
                metrics=validation_metrics,
                torch_module=torch,
            )

    _save_checkpoint(
        output_dir=config.output_dir,
        checkpoint_name="last_model.pt",
        model=model,
        optimizer=optimizer,
        epoch=config.epochs,
        tokenizer=tokenizer,
        config=config,
        metrics=history[-1] if history else {},
        torch_module=torch,
    )

    metrics = {
        "best_validation": best_metrics or {},
        "history": history,
        "train_examples": len(artifacts["train_examples"]),
        "validation_examples": len(artifacts["validation_examples"]),
    }
    _write_metadata(config=config, tokenizer=tokenizer, metrics=metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Shuddho local seq2seq corrector.")
    parser.add_argument("--config", required=True, help="Path to corrector config JSON.")
    args = parser.parse_args()

    config = load_training_config(args.config)
    metrics = train_corrector(config)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


@dataclass(frozen=True)
class CorrectorDataset:
    examples: list[CorrectorExample]
    tokenizer: CharacterTokenizer
    max_source_length: int
    max_target_length: int

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, object]:
        example = self.examples[index]
        return {
            "source_ids": self.tokenizer.encode(
                example.source_text,
                add_bos=True,
                add_eos=True,
                max_length=self.max_source_length,
            ),
            "target_ids": self.tokenizer.encode(
                example.target_text,
                add_bos=False,
                add_eos=True,
                max_length=self.max_target_length,
            ),
            "source_text": example.source_text,
            "target_text": example.target_text,
        }


def build_collate_fn(pad_token_id: int, torch_module):
    def collate(batch: list[dict[str, object]]) -> dict[str, object]:
        batch_size = len(batch)
        max_source_length = max(len(item["source_ids"]) for item in batch)  # type: ignore[arg-type]
        max_target_length = max(len(item["target_ids"]) for item in batch)  # type: ignore[arg-type]
        source_ids = torch_module.full((batch_size, max_source_length), pad_token_id, dtype=torch_module.long)
        target_ids = torch_module.full((batch_size, max_target_length), pad_token_id, dtype=torch_module.long)

        for row_index, item in enumerate(batch):
            source_row = item["source_ids"]  # type: ignore[assignment]
            target_row = item["target_ids"]  # type: ignore[assignment]
            source_ids[row_index, : len(source_row)] = torch_module.tensor(source_row, dtype=torch_module.long)
            target_ids[row_index, : len(target_row)] = torch_module.tensor(target_row, dtype=torch_module.long)

        return {
            "source_ids": source_ids,
            "target_ids": target_ids,
            "source_texts": [str(item["source_text"]) for item in batch],
            "target_texts": [str(item["target_text"]) for item in batch],
        }

    return collate


def _run_epoch(
    *,
    model,
    dataloader,
    optimizer,
    loss_function,
    tokenizer: CharacterTokenizer,
    device,
    torch_module,
    teacher_forcing_ratio: float,
    training: bool,
) -> dict[str, float]:
    if len(dataloader.dataset) == 0:
        return {
            "loss": 0.0,
            "exact_match": 0.0,
            "char_accuracy": 0.0,
            "char_error_rate": 0.0,
            "mean_sequence_confidence": 0.0,
        }

    model.train(mode=training)
    total_loss = 0.0
    batch_count = 0
    total_examples = 0
    exact_matches = 0
    total_characters = 0
    matched_characters = 0
    total_char_error = 0.0
    sequence_confidences: list[float] = []

    for batch in dataloader:
        source_ids = batch["source_ids"].to(device)
        target_ids = batch["target_ids"].to(device)
        logits = _decode_with_teacher_forcing(
            model,
            source_ids=source_ids,
            target_ids=target_ids,
            bos_token_id=tokenizer.bos_token_id,
            teacher_forcing_ratio=teacher_forcing_ratio if training else 1.0,
            torch_module=torch_module,
        )
        loss = loss_function(logits.reshape(-1, logits.shape[-1]), target_ids.reshape(-1))

        if training and optimizer is not None:
            optimizer.zero_grad()
            loss.backward()
            torch_module.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        total_loss += float(loss.item())
        batch_count += 1

        predictions = model.greedy_decode(
            source_ids,
            bos_token_id=tokenizer.bos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            max_length=target_ids.size(1) + 4,
        )
        predicted_token_ids = predictions["token_ids"].detach().cpu().tolist()
        predicted_confidences = predictions["token_confidences"].detach().cpu().tolist()
        target_token_ids = target_ids.detach().cpu().tolist()

        for predicted_ids, confidence_row, gold_ids in zip(predicted_token_ids, predicted_confidences, target_token_ids):
            predicted_text = tokenizer.decode(predicted_ids)
            gold_text = tokenizer.decode(gold_ids)
            total_examples += 1
            exact_matches += int(predicted_text == gold_text)
            total_characters += max(len(gold_text), 1)
            matched_characters += _matching_prefix_characters(predicted_text, gold_text)
            total_char_error += _char_error_rate(predicted_text, gold_text)
            valid_confidences = [
                float(confidence)
                for token_id, confidence in zip(predicted_ids, confidence_row)
                if token_id != tokenizer.eos_token_id
            ]
            if valid_confidences:
                sequence_confidences.append(sum(valid_confidences) / len(valid_confidences))

    return {
        "loss": round(total_loss / max(batch_count, 1), 4),
        "exact_match": round(exact_matches / max(total_examples, 1), 4),
        "char_accuracy": round(matched_characters / max(total_characters, 1), 4),
        "char_error_rate": round(total_char_error / max(total_examples, 1), 4),
        "mean_sequence_confidence": round(sum(sequence_confidences) / max(len(sequence_confidences), 1), 4),
    }


def _decode_with_teacher_forcing(
    model,
    *,
    source_ids,
    target_ids,
    bos_token_id: int,
    teacher_forcing_ratio: float,
    torch_module,
):
    encoder_outputs, hidden, source_mask = model.encode(source_ids)
    next_input = torch_module.full(
        (source_ids.size(0),),
        bos_token_id,
        dtype=torch_module.long,
        device=source_ids.device,
    )

    logits_steps = []
    for step_index in range(target_ids.size(1)):
        logits, hidden, _attention = model.decode_step(
            next_input,
            hidden,
            encoder_outputs,
            source_mask,
        )
        logits_steps.append(logits.unsqueeze(1))
        predicted_ids = logits.argmax(dim=-1)
        if teacher_forcing_ratio >= 1.0:
            next_input = target_ids[:, step_index]
            continue
        teacher_mask = torch_module.rand(source_ids.size(0), device=source_ids.device) < teacher_forcing_ratio
        next_input = torch_module.where(teacher_mask, target_ids[:, step_index], predicted_ids)

    return torch_module.cat(logits_steps, dim=1)


def _save_checkpoint(
    *,
    output_dir: Path,
    checkpoint_name: str,
    model,
    optimizer,
    epoch: int,
    tokenizer: CharacterTokenizer,
    config: CorrectorTrainingConfig,
    metrics: dict[str, object],
    torch_module,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    torch_module.save(
        {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "tokenizer": tokenizer.to_dict(),
            "training_config": _config_to_dict(config),
            "metrics": metrics,
        },
        output_dir / checkpoint_name,
    )


def _write_metadata(
    *,
    config: CorrectorTrainingConfig,
    tokenizer: CharacterTokenizer,
    metrics: dict[str, object],
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "format": "shuddho-corrector-v1",
        "name": config.name,
        "max_source_length": config.max_source_length,
        "max_target_length": config.max_target_length,
        "teacher_forcing_ratio": config.teacher_forcing_ratio,
        "tokenizer": tokenizer.to_dict(),
        "model": dict(config.model),
        "metrics": metrics,
    }
    (config.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (config.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")


def _config_to_dict(config: CorrectorTrainingConfig) -> dict[str, object]:
    return {
        "name": config.name,
        "seed": config.seed,
        "max_source_length": config.max_source_length,
        "max_target_length": config.max_target_length,
        "batch_size": config.batch_size,
        "epochs": config.epochs,
        "learning_rate": config.learning_rate,
        "teacher_forcing_ratio": config.teacher_forcing_ratio,
        "device": config.device,
        "train_path": str(config.train_path),
        "validation_path": str(config.validation_path) if config.validation_path else None,
        "validation_split": config.validation_split,
        "output_dir": str(config.output_dir),
        "model": dict(config.model),
    }


def _matching_prefix_characters(predicted_text: str, gold_text: str) -> int:
    matched = 0
    for predicted_character, gold_character in zip(predicted_text, gold_text):
        if predicted_character != gold_character:
            break
        matched += 1
    return matched


def _char_error_rate(predicted_text: str, gold_text: str) -> float:
    distance = _levenshtein_distance(predicted_text, gold_text)
    return distance / max(len(gold_text), 1)


def _levenshtein_distance(source: str, target: str) -> int:
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)

    previous = list(range(len(target) + 1))
    for row_index, source_character in enumerate(source, start=1):
        current = [row_index]
        for column_index, target_character in enumerate(target, start=1):
            insert_cost = current[column_index - 1] + 1
            delete_cost = previous[column_index] + 1
            replace_cost = previous[column_index - 1] + (0 if source_character == target_character else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


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
