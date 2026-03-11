import torch

from ml.corrector.model import BanglaCorrectorSeq2Seq
from ml.detector.model import BanglaDetectorEncoder


def test_detector_shape_contract() -> None:
    model = BanglaDetectorEncoder(vocab_size=128, hidden_size=32, num_heads=4, num_layers=1, num_labels=3, max_length=32)
    input_ids = torch.randint(0, 128, (2, 10))
    attention_mask = torch.ones((2, 10), dtype=torch.long)
    outputs = model(input_ids, attention_mask)
    assert outputs["logits"].shape == (2, 10, 3)


def test_corrector_shape_contract() -> None:
    model = BanglaCorrectorSeq2Seq(vocab_size=128, hidden_size=32)
    source_ids = torch.randint(0, 128, (2, 8))
    target_ids = torch.randint(0, 128, (2, 7))
    outputs = model(source_ids, target_ids)
    assert outputs["logits"].shape == (2, 7, 128)

