# MVP Roadmap

## Completed in the current repo

- FastAPI backend with health, analyze, and feedback endpoints
- Bangla normalization, lexicon spell checking, conservative rules, and suggestion merging
- Staged analysis runtime with detector, candidate-generation, and ranking interfaces
- Tiptap web editor with multiline text extraction, issue marks, and feedback actions
- Chrome extension with safe overlay rendering and first inline decoration support for `textarea` and simple text `input`
- SQLite feedback logging
- Detector training data loaders, lightweight detector training, heuristic ranking, and regression tests

## Next milestones

1. Improve multiline span mapping further for richer document structures and heavier editing churn.
2. Extend safe inline rendering beyond `textarea` and simple `input` into selected `contenteditable` editors.
3. Grow the detector dataset from real feedback, curated fixtures, and synthetic error generation.
4. Train and evaluate stronger detector checkpoints from scratch, then enable them behind conservative runtime thresholds.
5. Replace heuristic reranking weights with a lightweight learned reranker once feedback volume is large enough.
6. Add offline precision dashboards and regression tracking for Bangla error categories.
