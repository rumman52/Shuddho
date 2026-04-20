# Synthetic Datasets

This folder holds clean seed text and generation instructions for our local synthetic pipeline.

Use cases:
- detector bootstrapping
- corrector bootstrapping
- offline evaluation before real annotated datasets exist

Seed corpora shipped here:
- `bootstrap_clean_train.txt`
- `bootstrap_clean_valid.txt`
- `bootstrap_clean_test.txt`

The generator creates deterministic synthetic mutations such as:
- true spelling errors and orthography variants
- punctuation and spacing mistakes
- repeated words
- verb agreement and pronoun mismatch
- suffix and postposition errors
- missing and extra words
- register mismatch
- word-order noise
- mixed digit styles
- code-mix markers

Example commands:
```bash
python scripts/generate_synthetic_errors.py --input data/datasets/synthetic/bootstrap_clean_train.txt --output data/datasets/train/detector.synthetic.jsonl --task detector
python scripts/generate_synthetic_errors.py --input data/datasets/synthetic/bootstrap_clean_train.txt --output data/datasets/train/corrector.synthetic.jsonl --task corrector
```
