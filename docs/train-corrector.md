# Train The Corrector

Shuddho's sentence-level corrector is optional. The main grammar pipeline still runs without it, but `/health/deep` and the frontends will report degraded mode until the artifact is available.

## Expected Artifact Path

The default artifact location is:

`artifacts/corrector/corrector-base`

You can override it with:

`SHUDDHO_CORRECTOR_CHECKPOINT`

## Training Data Shape

Prepare wrong-to-correct Bangla pairs as JSONL. Each line should contain at least:

```json
{
  "source_text": "আমি ভাত খায়।",
  "target_text": "আমি ভাত খাই।"
}
```

Recommended data split paths:

- `data/datasets/train/corrector.synthetic.jsonl`
- `data/datasets/valid/corrector.synthetic.jsonl`
- `data/datasets/test/corrector.synthetic.jsonl`

Guidelines:

- Keep pairs local and conservative.
- Prefer single-span or small multi-span sentence corrections.
- Avoid paraphrases and full rewrites in the training pairs.
- Keep named entities stable.
- Include punctuation, spacing, spelling, and narrow agreement mistakes.

## Config

Base config:

`ml/training/configs/corrector.base.json`

It now points to explicit train, validation, and test files.

## Train

From the repo root:

```bash
python -m ml.corrector.train --config ml/training/configs/corrector.base.json
```

The trainer writes checkpoints and metadata under:

`artifacts/corrector/corrector-base`

Expected files include:

- `metadata.json`
- `best_model.pt`
- `last_model.pt`
- `metrics.json`

## Use The Artifact

Set the runtime environment variable if you want a non-default path:

```bash
set SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
```

When the artifact loads successfully:

- `/health/deep` reports `corrector.status = ready`
- `/analyze` may use corrector output only when it can be projected to exact inline spans

## Important Runtime Guardrail

The corrector is not allowed to dump whole-sentence rewrites into normal grammar analysis.

Runtime behavior:

- sentence predictions are diffed into minimal inline edits
- weakly anchored or rewrite-like diffs are dropped
- only exact anchored spans survive validation and ranking
