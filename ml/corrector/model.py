from __future__ import annotations

import torch
from torch import nn


class BanglaCorrectorSeq2Seq(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 128,
        pad_token_id: int = 0
    ) -> None:
        super().__init__()
        self.pad_token_id = pad_token_id
        self.encoder_embeddings = nn.Embedding(vocab_size, hidden_size, padding_idx=pad_token_id)
        self.decoder_embeddings = nn.Embedding(vocab_size, hidden_size, padding_idx=pad_token_id)
        self.encoder = nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.decoder = nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.output_projection = nn.Linear(hidden_size, vocab_size)

    def forward(self, source_ids: torch.Tensor, target_ids: torch.Tensor) -> dict[str, torch.Tensor]:
        encoder_inputs = self.encoder_embeddings(source_ids)
        _, hidden = self.encoder(encoder_inputs)

        decoder_inputs = self.decoder_embeddings(target_ids)
        decoder_outputs, hidden = self.decoder(decoder_inputs, hidden)
        logits = self.output_projection(decoder_outputs)
        return {"logits": logits, "decoder_hidden": hidden}

