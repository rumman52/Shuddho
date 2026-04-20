from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.corrector.infer import load_corrector_bundle
from ml.corrector.tokenizer import load_corrector_examples
from ml.corrector.train import CorrectorDataset, _run_epoch, build_collate_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained Shuddho corrector checkpoint.")
    parser.add_argument("--checkpoint-dir", required=True, help="Directory containing metadata.json and model checkpoints.")
    parser.add_argument("--dataset", required=True, help="JSONL dataset to evaluate.")
    parser.add_argument("--batch-size", type=int, default=16, help="Evaluation batch size.")
    parser.add_argument("--device", default="auto", help="Device override: auto, cpu, or cuda.")
    args = parser.parse_args()

    metrics = evaluate_checkpoint(
        checkpoint_dir=args.checkpoint_dir,
        dataset_path=args.dataset,
        batch_size=args.batch_size,
        device=args.device,
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def evaluate_checkpoint(
    *,
    checkpoint_dir: str | Path,
    dataset_path: str | Path,
    batch_size: int = 16,
    device: str = "auto",
) -> dict[str, float]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader
    except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
        raise RuntimeError("PyTorch is required to evaluate the corrector") from error

    bundle = load_corrector_bundle(checkpoint_dir, device=device)
    metadata = bundle.metadata
    dataset = CorrectorDataset(
        load_corrector_examples(dataset_path),
        tokenizer=bundle.tokenizer,
        max_source_length=int(metadata.get("max_source_length", 192)),
        max_target_length=int(metadata.get("max_target_length", 192)),
    )
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=build_collate_fn(bundle.tokenizer.pad_token_id, torch),
    )
    loss_function = nn.CrossEntropyLoss(ignore_index=bundle.tokenizer.pad_token_id)
    return _run_epoch(
        model=bundle.model,
        dataloader=dataloader,
        optimizer=None,
        loss_function=loss_function,
        tokenizer=bundle.tokenizer,
        device=bundle.device,
        torch_module=torch,
        teacher_forcing_ratio=1.0,
        training=False,
    )


if __name__ == "__main__":
    main()
