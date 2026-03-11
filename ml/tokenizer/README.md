# Tokenizer

This module owns future custom Bangla tokenization.

Current responsibilities:
- train a SentencePiece model from our own cleaned corpus
- load locally trained tokenizer files for experiments
- avoid any pretrained tokenizer checkpoints

Current status:
- `train_sentencepiece.py` is a real training entrypoint
- `loader.py` defines the runtime loading interface
- the repository only includes sample corpus files, not trained weights

