# Detector

This package contains the lightweight Bangla error detector stack.

Current scope:
- token-level encoder in PyTorch
- config-driven training entrypoint with checkpoint + metadata output
- checkpoint-backed runtime wrapper for optional service integration
- narrow label taxonomy: spelling, grammar, punctuation, spacing
- no pretrained checkpoints and no broad quality claims yet
