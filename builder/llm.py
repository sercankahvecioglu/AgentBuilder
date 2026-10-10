"""Anthropic API wrapper for the builder (DEV_PLAN T3.1).

Rules (memory.md C5, DEV_PLAN T3.1):
- model claude-opus-5-5; effort set explicitly (default medium on this model, we pass it every time)
- structured outputs through output_config.format (JSON schema from the pydantic model)
- never send temperature, budget_tokens, a thinking budget or a forced tool_choice (400s)
- always stream (large outputs), check stop_reason (refusal, max_tokens)
- one trace line per call: model, purpose, seconds, tokens, request id
- the brief text goes in a cached system block so stage 1a, 1b, re-extracts and votes share the prefix
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from builder.schema import strict_schema
from builder.trace import Trace

MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")
DEFAULT_MAX_TOKENS = 64000
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class Refused(LLMError):
    pass


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # credentials from ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / a profile; SDK retries 429/5xx
        _client = anthropic.Anthropic(max_retries=3, timeout=900.0)
    return _client


def _system_blocks(stable: str, instructions: str) -> list[dict[str, Any]]:
    """Stable (cached) block first, stage instructions second."""
    blocks: list[dict[str, Any]] = []
    if stable:
        blocks.append({"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}})
    if instructions:
        blocks.append({"type": "text", "text": instructions})
    return blocks


def structured(
    purpose: str,
    output_model: type[T],
    user: str,
    *,
    stable_system: str = "",
    instructions: str = "",
    effort: str = "high",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    trace: Trace | None = None,
    model: str = MODEL,
    retries_on_invalid: int = 1,
) -> tuple[T, dict[str, Any]]:
    """One structured-output call. Returns (validated model, meta).

    meta: seconds, input_tokens, output_tokens, request_id, stop_reason, raw_text.
    Raises Refused on a refusal, LLMError after retries on max_tokens or invalid JSON.
    """
    schema = strict_schema(output_model)
    attempt = 0
    last_err: Exception | None = None
    while attempt <= retries_on_invalid:
        attempt += 1
        t0 = time.monotonic()
        msg = None
        try:
            with client().messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=_system_blocks(stable_system, instructions),
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            ) as stream:
                msg = stream.get_final_message()
        except anthropic.APIError as e:
            seconds = time.monotonic() - t0
            if trace:
                trace.model_call(model, purpose, seconds, 0, 0, getattr(e, "request_id", None), f"error:{type(e).__name__}", effort, ok=False)
            raise LLMError(f"{purpose}: API error {type(e).__name__}: {e}") from e
        seconds = time.monotonic() - t0
        u = msg.usage
        meta = {
            "seconds": seconds,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "request_id": getattr(msg, "_request_id", None),
            "stop_reason": msg.stop_reason,
            "model": msg.model,
        }
        text = "".join(b.text for b in msg.content if b.type == "text")
        meta["raw_text"] = text
        ok = msg.stop_reason == "end_turn"
        if trace:
            trace.model_call(msg.model, purpose, seconds, u.input_tokens, u.output_tokens, meta["request_id"],
                             msg.stop_reason, effort, meta["cache_read"], meta["cache_write"], ok=ok)
        if msg.stop_reason == "refusal":
            det = getattr(msg, "stop_details", None)
            raise Refused(f"{purpose}: model refused ({getattr(det, 'category', None)}: {getattr(det, 'explanation', '')})")
        if msg.stop_reason == "max_tokens":
            last_err = LLMError(f"{purpose}: hit max_tokens={max_tokens}; output truncated")
            max_tokens = min(max_tokens * 2, 128000)
            if trace:
                trace.warn(f"{purpose}: truncated, retrying with max_tokens={max_tokens}")
            continue
        try:
            parsed = output_model.model_validate(json.loads(text))
            return parsed, meta
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = LLMError(f"{purpose}: output did not validate: {str(e)[:500]}")
            if trace:
                trace.warn(f"{purpose}: invalid structured output, retrying ({str(e)[:200]})")
            continue
    raise last_err or LLMError(f"{purpose}: failed")


def smoke_test(trace: Trace | None = None) -> dict[str, Any]:
    """T3.1 acceptance check: one tiny structured call returns a validated model and writes a trace line."""

    class Ping(BaseModel):
        model_config = {"extra": "forbid"}
        answer: str
        number: int

    parsed, meta = structured(
        "llm smoke test",
        Ping,
        "Reply with answer='pong' and number=4.",
        instructions="You are a test endpoint. Follow the user exactly.",
        effort="low",
        max_tokens=2000,
        trace=trace,
    )
    assert parsed.answer.lower() == "pong" and parsed.number == 4, parsed
    return meta


if __name__ == "__main__":
    import sys

    tr = Trace(None)
    if "--schema-check" in sys.argv:
        # compile the real schemas on the API with a minimal prompt (structured-output limits check)
        from builder.schema import Extraction, Spec

        for m in (Extraction, Spec):
            t0 = time.monotonic()
            try:
                with client().messages.stream(
                    model=MODEL, max_tokens=64,
                    messages=[{"role": "user", "content": "Return the smallest valid object: empty lists everywhere, empty strings, zeros, false."}],
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": strict_schema(m)}},
                ) as st:
                    msg = st.get_final_message()
                print(f"{m.__name__}: schema accepted (stop={msg.stop_reason}, {time.monotonic()-t0:.1f}s)")
            except anthropic.BadRequestError as e:
                print(f"{m.__name__}: REJECTED: {e}")
                sys.exit(1)
    else:
        print(smoke_test(tr))
