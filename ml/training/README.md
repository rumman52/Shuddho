# Training

Training code stays separate from inference code.

Responsibilities:
- load cleaned corpus and dataset contracts
- generate minibatches for detector/corrector tasks
- read JSON configs from `ml/training/configs`
- keep reproducible training settings in versioned files

Current state:
- configs are real files
- model training entrypoints are placeholders with explicit TODOs
- no pretrained checkpoints are used anywhere in this repo

