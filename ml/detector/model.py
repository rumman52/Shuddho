from __future__ import annotations

import torch
from torch import nn


class BanglaDetectorEncoder(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 128,
        num_heads: int = 4,
        num_layers: int = 2,
        num_labels: int = 4,
        max_length: int = 512
    ) -> None:
        super().__init__()
        self.token_embeddings = nn.Embedding(vocab_size, hidden_size)
        self.position_embeddings = nn.Embedding(max_length, hidden_size)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_size,
            nhead=num_heads,
            dim_feedforward=hidden_size * 4,
            batch_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.classifier = nn.Linear(hidden_size, num_labels)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        batch_size, sequence_length = input_ids.shape
        positions = torch.arange(sequence_length, device=input_ids.device).unsqueeze(0).expand(batch_size, sequence_length)
        hidden_states = self.token_embeddings(input_ids) + self.position_embeddings(positions)
        key_padding_mask = attention_mask == 0 if attention_mask is not None else None
        encoded = self.encoder(hidden_states, src_key_padding_mask=key_padding_mask)
        logits = self.classifier(encoded)
        return {"hidden_states": encoded, "logits": logits}

