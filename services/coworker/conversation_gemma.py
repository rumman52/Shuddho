"""Explicit Gemma text-chat adapter; no tools, retries or provider fallback."""
from __future__ import annotations

import asyncio

import httpx

from .conversation_replies import MAX_OUTPUT_BYTES, MAX_OUTPUT_TOKENS


class GemmaReplyModel:
    def __init__(self, settings, client_factory=None):
        self.settings = settings
        self.client_factory = client_factory

    async def stream(self, messages):
        from google import genai
        from google.genai import types

        timeout = min(60, self.settings.model_timeout_seconds)
        if not messages or messages[0]["role"] != "system":
            raise ValueError("Missing chat policy")
        contents = []
        for message in messages[1:]:
            if message["role"] not in {"user", "assistant"}:
                raise ValueError("Invalid chat role")
            contents.append(types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=message["content"])],
            ))
        config = types.GenerateContentConfig(
            system_instruction=messages[0]["content"],
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.4,
            candidate_count=1,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level="minimal", include_thoughts=False),
        )
        factory = self.client_factory or genai.Client
        client = factory(api_key=self.settings.gemma_api_key, http_options=types.HttpOptions(
            timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1),
            # Pin httpx even when the optional aiohttp SDK transport is installed.
            async_client_args={"transport": httpx.AsyncHTTPTransport(retries=0)},
        ))
        output_bytes = 0
        finished = False
        chunks = 0
        async with asyncio.timeout(timeout):
            async with client.aio as api:
                stream = await api.models.generate_content_stream(
                    model=self.settings.gemma_model, contents=contents, config=config,
                )
                async for chunk in stream:
                    chunks += 1
                    if chunks > 8192:
                        raise ValueError("Provider stream too large")
                    if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                        raise ValueError("Provider blocked reply")
                    candidates = chunk.candidates or []
                    if not candidates:  # Optional usage-only chunk.
                        continue
                    if len(candidates) != 1 or finished:
                        raise ValueError("Invalid provider stream")
                    candidate = candidates[0]
                    for part in (candidate.content.parts if candidate.content else []) or []:
                        if set(part.model_dump(exclude_none=True)) - {"text", "thought", "thought_signature"}:
                            raise ValueError("Unexpected non-text reply")
                        if part.thought:
                            continue
                        if part.text:
                            output_bytes += len(part.text.encode("utf-8"))
                            if output_bytes > MAX_OUTPUT_BYTES:
                                raise ValueError("Reply too long")
                            yield part.text
                    if candidate.finish_reason is not None:
                        if candidate.finish_reason != types.FinishReason.STOP:
                            raise ValueError("Incomplete provider reply")
                        finished = True
        if not finished or not output_bytes:
            raise ValueError("Provider reply did not complete")

    async def generate(self, messages):
        return "".join([part async for part in self.stream(messages)]).strip()
