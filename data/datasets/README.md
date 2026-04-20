# Datasets

Shuddho keeps dataset ownership explicit.

Directory layout:
- `synthetic/`: clean seed text plus generator docs for deterministic synthetic bootstrapping
- `human_gold/`: small manually reviewed fixtures and annotation instructions
- `feedback_derived/`: future aggregated feedback exports for retraining, never raw runtime event logs
- `train/`, `valid/`, `test/`: materialized JSONL splits consumed by local training and offline evaluation
- `contracts/`: schema and field-level documentation

Current status:
- the repo ships small honest sample splits
- synthetic data is generated locally from repo-owned rules
- human-gold data is intentionally small and hand-curated
- larger reviewed corpora still require manual collection and review

Useful commands:
```bash
python scripts/generate_synthetic_errors.py --input data/datasets/synthetic/bootstrap_clean_train.txt --output data/datasets/train/detector.synthetic.jsonl --task detector
python scripts/generate_synthetic_errors.py --input data/datasets/synthetic/bootstrap_clean_train.txt --output data/datasets/train/corrector.synthetic.jsonl --task corrector
```
