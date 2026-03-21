# Ranking

This module currently provides a heuristic, feedback-aware ranking layer.

The current system still relies on the conservative service-side merger in `services/suggestion_manager`,
but `ml/ranking/pipeline.py` now provides a lightweight scoring path that favors high-confidence rule and lexicon candidates,
penalizes exact-span conflicts, and can reuse saved accept/dismiss history when available.
Later work here can learn ranking features from feedback logs and offline datasets without depending on external models.
