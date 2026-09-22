# Multilingual Coworker Quality Evaluation

This release gate checks content fidelity separately from routing, infrastructure, and capacity.

It uses synthetic, non-sensitive English, Bangla, Spanish, and Arabic cases. Each case declares exact facts that must survive, known unsupported claims that must not appear, required source IDs, missing-information behavior, and selected fields that must remain empty.

CI mode is deterministic and does not call a paid provider:

```bash
uv run --extra coworker python scripts/coworker_quality_eval.py --min-pass-rate 1.0 --min-fact-recall 1.0
```

Controlled staging must also run the same cases through the configured DeepSeek draft model:

```bash
uv run --extra coworker python scripts/coworker_quality_eval.py --live --min-pass-rate 1.0 --min-fact-recall 1.0 --max-average-tokens 20000 --max-p95-latency-ms 90000 --output /secure/release/coworker-quality-eval.json
```

The live artifact records objective contract results, token use, and latency. Reference it from the `quality` staging evidence item.

A passing result is a bounded regression signal. It is not proof of universal language quality and does not authorize cohort expansion or autonomous actions.
