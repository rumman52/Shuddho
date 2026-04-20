from __future__ import annotations

import torch
from torch import nn


class BanglaCorrectorSeq2Seq(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        *,
        embedding_size: int = 128,
        hidden_size: int = 192,
        dropout: float = 0.15,
        pad_token_id: int = 0,
    ) -> None:
        super().__init__()
        self.pad_token_id = pad_token_id
        self.embedding = nn.Embedding(vocab_size, embedding_size, padding_idx=pad_token_id)
        self.encoder = nn.GRU(embedding_size, hidden_size, batch_first=True)
        self.decoder = nn.GRU(embedding_size + hidden_size, hidden_size, batch_first=True)
        self.output_projection = nn.Linear(hidden_size * 2, vocab_size)
        self.dropout = nn.Dropout(dropout)

    def encode(
        self,
        source_ids: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        source_mask = source_ids.ne(self.pad_token_id)
        embedded = self.dropout(self.embedding(source_ids))
        encoder_outputs, hidden = self.encoder(embedded)
        return encoder_outputs, hidden, source_mask

    def decode_step(
        self,
        input_token_ids: torch.Tensor,
        hidden: torch.Tensor,
        encoder_outputs: torch.Tensor,
        source_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        embedded = self.dropout(self.embedding(input_token_ids.unsqueeze(1)))
        context, attention_weights = self._attend(hidden, encoder_outputs, source_mask)
        decoder_input = torch.cat([embedded, context], dim=-1)
        decoder_output, hidden = self.decoder(decoder_input, hidden)
        logits = self.output_projection(torch.cat([decoder_output, context], dim=-1)).squeeze(1)
        return logits, hidden, attention_weights

    def forward(
        self,
        source_ids: torch.Tensor,
        decoder_input_ids: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        encoder_outputs, hidden, source_mask = self.encode(source_ids)

        logits_steps: list[torch.Tensor] = []
        attention_steps: list[torch.Tensor] = []
        for step_index in range(decoder_input_ids.size(1)):
            logits, hidden, attention_weights = self.decode_step(
                decoder_input_ids[:, step_index],
                hidden,
                encoder_outputs,
                source_mask,
            )
            logits_steps.append(logits.unsqueeze(1))
            attention_steps.append(attention_weights.unsqueeze(1))

        return {
            "logits": torch.cat(logits_steps, dim=1),
            "decoder_hidden": hidden,
            "attention": torch.cat(attention_steps, dim=1),
        }

    @torch.inference_mode()
    def greedy_decode(
        self,
        source_ids: torch.Tensor,
        *,
        bos_token_id: int,
        eos_token_id: int,
        max_length: int,
    ) -> dict[str, torch.Tensor]:
        encoder_outputs, hidden, source_mask = self.encode(source_ids)
        batch_size = source_ids.size(0)
        next_input = torch.full(
            (batch_size,),
            bos_token_id,
            dtype=torch.long,
            device=source_ids.device,
        )

        generated_tokens: list[torch.Tensor] = []
        generated_confidences: list[torch.Tensor] = []
        finished = torch.zeros(batch_size, dtype=torch.bool, device=source_ids.device)

        for _ in range(max_length):
            logits, hidden, _attention_weights = self.decode_step(
                next_input,
                hidden,
                encoder_outputs,
                source_mask,
            )
            probabilities = torch.softmax(logits, dim=-1)
            confidences, next_input = probabilities.max(dim=-1)
            generated_tokens.append(next_input.unsqueeze(1))
            generated_confidences.append(confidences.unsqueeze(1))
            finished = finished | next_input.eq(eos_token_id)
            if bool(finished.all()):
                break

        if not generated_tokens:
            empty = torch.empty((batch_size, 0), dtype=torch.long, device=source_ids.device)
            empty_confidences = torch.empty((batch_size, 0), dtype=torch.float32, device=source_ids.device)
            return {
                "token_ids": empty,
                "token_confidences": empty_confidences,
            }

        return {
            "token_ids": torch.cat(generated_tokens, dim=1),
            "token_confidences": torch.cat(generated_confidences, dim=1),
        }

    def _attend(
        self,
        hidden: torch.Tensor,
        encoder_outputs: torch.Tensor,
        source_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        query = hidden[-1].unsqueeze(2)
        scores = torch.bmm(encoder_outputs, query).squeeze(2)
        scores = scores.masked_fill(~source_mask, float("-inf"))
        attention_weights = torch.softmax(scores, dim=-1)
        context = torch.bmm(attention_weights.unsqueeze(1), encoder_outputs)
        return context, attention_weights
