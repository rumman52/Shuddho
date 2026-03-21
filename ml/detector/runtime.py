from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ml.detector.labels import DETECTOR_ID_TO_LABEL
from ml.training.dataset import encode_tokens, tokenize_with_offsets


@dataclass(frozen=True)
class DetectorPrediction:
    label: str
    start: int
    end: int
    text: str
    confidence: float


class BanglaDetectorRuntime:
    def __init__(
        self,
        *,
        model,
        vocabulary: dict[str, int],
        label_to_id: dict[str, int],
        max_length: int,
        confidence_threshold: float = 0.8,
    ) -> None:
        self.model = model
        self.vocabulary = vocabulary
        self.label_to_id = label_to_id
        self.id_to_label = {index: label for label, index in label_to_id.items()}
        self.max_length = max_length
        self.confidence_threshold = confidence_threshold

    @classmethod
    def load(cls, checkpoint_dir: str | Path) -> "BanglaDetectorRuntime":
        checkpoint_dir = Path(checkpoint_dir)
        metadata = json.loads((checkpoint_dir / "metadata.json").read_text(encoding="utf-8"))
        model_config = metadata["model"]
        vocabulary = metadata["vocabulary"]
        label_to_id = metadata["label_to_id"]
        max_length = int(metadata["max_length"])
        confidence_threshold = float(metadata.get("confidence_threshold", 0.8))

        try:
            import torch
        except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
            raise RuntimeError("PyTorch is required to load detector checkpoints") from error

        from ml.detector.model import BanglaDetectorEncoder

        model = BanglaDetectorEncoder(
            vocab_size=len(vocabulary),
            hidden_size=model_config["hidden_size"],
            num_heads=model_config["num_heads"],
            num_layers=model_config["num_layers"],
            num_labels=model_config["num_labels"],
            max_length=max_length,
        )
        state = torch.load(checkpoint_dir / "best_model.pt", map_location="cpu")
        model.load_state_dict(state["model_state_dict"])
        model.eval()
        return cls(
            model=model,
            vocabulary=vocabulary,
            label_to_id=label_to_id,
            max_length=max_length,
            confidence_threshold=confidence_threshold,
        )

    def predict(self, text: str) -> list[DetectorPrediction]:
        tokens = tokenize_with_offsets(text)
        if not tokens:
            return []

        try:
            import torch
        except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
            raise RuntimeError("PyTorch is required to run detector inference") from error

        limited_tokens = tokens[: self.max_length]
        encoded_tokens = encode_tokens(tuple(token.text for token in limited_tokens), self.vocabulary)
        input_ids = torch.tensor([encoded_tokens], dtype=torch.long)
        attention_mask = torch.ones_like(input_ids)

        with torch.no_grad():
            outputs = self.model(input_ids, attention_mask)
            probabilities = torch.softmax(outputs["logits"], dim=-1)[0]
            predicted_ids = probabilities.argmax(dim=-1).tolist()

        return self._collapse_predictions(text, limited_tokens, predicted_ids, probabilities.tolist())

    def _collapse_predictions(
        self,
        text: str,
        tokens,
        predicted_ids: list[int],
        probabilities: list[list[float]],
    ) -> list[DetectorPrediction]:
        grouped_predictions: list[DetectorPrediction] = []
        active_label: str | None = None
        active_start = 0
        active_end = 0
        active_confidences: list[float] = []

        for token, predicted_id, token_probabilities in zip(tokens, predicted_ids, probabilities):
            label = self.id_to_label.get(predicted_id, DETECTOR_ID_TO_LABEL[0])
            if label == "ok":
                if active_label is not None:
                    grouped_predictions.append(
                        self._build_prediction(text, active_label, active_start, active_end, active_confidences)
                    )
                    active_label = None
                    active_confidences = []
                continue

            confidence = float(token_probabilities[predicted_id])
            if active_label == label and token.start <= active_end + 1:
                active_end = token.end
                active_confidences.append(confidence)
                continue

            if active_label is not None:
                grouped_predictions.append(
                    self._build_prediction(text, active_label, active_start, active_end, active_confidences)
                )

            active_label = label
            active_start = token.start
            active_end = token.end
            active_confidences = [confidence]

        if active_label is not None:
            grouped_predictions.append(self._build_prediction(text, active_label, active_start, active_end, active_confidences))

        return [prediction for prediction in grouped_predictions if prediction.confidence >= self.confidence_threshold]

    def _build_prediction(
        self,
        text: str,
        label: str,
        start: int,
        end: int,
        confidences: list[float],
    ) -> DetectorPrediction:
        mean_confidence = sum(confidences) / max(len(confidences), 1)
        return DetectorPrediction(
            label=label,
            start=start,
            end=end,
            text=text[start:end],
            confidence=round(mean_confidence, 4),
        )
