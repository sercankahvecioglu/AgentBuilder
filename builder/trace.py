"""Plain-text build trace (DEV_PLAN T7.4, D19).

One file per build, written incrementally so a crash still leaves a usable trace.
Required content: start and end time (UTC), one line per model call (model, purpose,
seconds, tokens, request id), what was created on Freya, self-tests and results.
Secrets are redacted from every line.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone

_SECRET_ENV = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_SECRET_PATTERNS = [re.compile(r"fak_[A-Za-z0-9_\-]+"), re.compile(r"sk-ant-[A-Za-z0-9_\-]+")]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(dt: datetime | None = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact(text: str) -> str:
    for name in _SECRET_ENV:
        val = os.environ.get(name, "")
        if len(val) >= 8:
            text = text.replace(val, f"<{name}>")
    for pat in _SECRET_PATTERNS:
        text = pat.sub("<redacted>", text)
    return text


class Trace:
    """Append-only trace writer. Also echoes to stderr when `echo` is true."""

    def __init__(self, path: str | None, echo: bool = True):
        self.path = path
        self.echo = echo
        self.t0 = time.monotonic()
        self.started = _now()
        self.model_calls: list[dict] = []
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("")

    # -- low level ---------------------------------------------------------
    def line(self, text: str = "") -> None:
        text = redact(text)
        stamp = f"[{utc_stamp()} +{time.monotonic() - self.t0:7.1f}s] " if text else ""
        out = stamp + text
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(out + "\n")
        if self.echo:
            print(out, file=sys.stderr, flush=True)

    def section(self, title: str) -> None:
        self.line("")
        self.line(f"== {title} ==")

    def kv(self, key: str, value) -> None:
        self.line(f"{key}: {value}")

    def warn(self, text: str) -> None:
        self.line(f"WARNING: {text}")

    # -- required entries --------------------------------------------------
    def start(self, command: str, inputs: list[str]) -> None:
        self.line(f"BUILD START {utc_stamp(self.started)}")
        self.kv("command", command)
        self.kv("inputs", ", ".join(inputs))

    def model_call(self, model: str, purpose: str, seconds: float, input_tokens: int, output_tokens: int,
                   request_id: str | None, stop_reason: str | None, effort: str, cache_read: int = 0,
                   cache_write: int = 0, ok: bool = True) -> None:
        rec = {
            "model": model, "purpose": purpose, "seconds": round(seconds, 1), "input_tokens": input_tokens,
            "output_tokens": output_tokens, "cache_read": cache_read, "cache_write": cache_write,
            "request_id": request_id or "", "stop_reason": stop_reason or "", "effort": effort, "ok": ok,
        }
        self.model_calls.append(rec)
        self.line(
            f"MODEL CALL model={model} effort={effort} purpose=\"{purpose}\" seconds={seconds:.1f} "
            f"in={input_tokens} out={output_tokens} cache_read={cache_read} cache_write={cache_write} "
            f"stop={stop_reason} request_id={request_id} {'ok' if ok else 'FAILED'}"
        )

    def created(self, what: str, **fields) -> None:
        self.line(f"CREATED {what} " + " ".join(f"{k}={v}" for k, v in fields.items()))

    def test(self, name: str, passed: bool, detail: str = "") -> None:
        self.line(f"TEST {name}: {'PASS' if passed else 'FAIL'}" + (f" ({detail})" if detail else ""))

    def end(self, status: str = "ok") -> None:
        total_in = sum(c["input_tokens"] for c in self.model_calls)
        total_out = sum(c["output_tokens"] for c in self.model_calls)
        self.line("")
        self.kv("model calls", f"{len(self.model_calls)} (tokens in={total_in} out={total_out})")
        self.line(f"BUILD END {utc_stamp()} status={status} duration={time.monotonic() - self.t0:.0f}s")
