# Corrector

This package contains the local sentence-level Bangla corrector used by the backend.

What is included:
- a character-level seq2seq model with attention in `model.py`
- local tokenizer, dataset loading, batching, and checkpointing
- training and evaluation CLIs in `train.py` and `evaluate.py`
- runtime inference plus inline span projection in `infer.py`

Training data format:
- JSONL
- one object per line
- required keys: `source_text`, `target_text`

Example:
```json
{"source_text":"আমি বাংলা বাংলা লিখি।","target_text":"আমি বাংলা লিখি।"}
```

Useful commands:
```bash
python -m ml.corrector.train --config ml/training/configs/corrector.base.json
python -m ml.corrector.evaluate --checkpoint-dir artifacts/corrector/corrector-base --dataset data/datasets/valid/corrector.synthetic.jsonl
python -m ml.corrector.infer --checkpoint-dir artifacts/corrector/corrector-base --text "আমি বাংলা বাংলা লিখি"
```

Checkpoint layout:
- `metadata.json`
- `best_model.pt`
- `last_model.pt`
- `metrics.json`

Runtime behavior:
- the backend loads a locally trained checkpoint directory
- the corrector predicts sentence-level fixes
- predicted rewrites are projected back into inline editor suggestions with local spans and anchors
