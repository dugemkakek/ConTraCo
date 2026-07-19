"""LLM brain provider.

Plug a chat-completions LLM in as the brain behind the council.
Default endpoint is InferHub (``https://api.inferhub.dev/v1``), which
serves ``provider/model`` IDs like ``ocg/minimax-m3`` (the default
model).  When ``LLM_API_KEY`` is unset the module returns a
deterministic :class:`StubClient` so the server stays runnable
offline.

The clients satisfy a tiny :class:`LLMClient` Protocol — see the
council module for how each role invokes ``chat_json(system, user)``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.services.llm.compression import (
    compress_at_threshold,
    compress_role_prompt,
    estimate_prompt_tokens,
)

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "https://api.inferhub.dev/v1"
DEFAULT_MODEL = "ocg/minimax-m3"
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MAX_RETRIES = 2
# Default context window we defend. Override via
# ``LLM_CONTEXT_COMPRESS_AT_TOKENS`` in ``.env``.
DEFAULT_MAX_CONTEXT_TOKENS = 100_000


# --- compression telemetry ---------------------------------------------------
# Module-level ring buffer (size 1) of the most recent compression event.
# Surfaced via :func:`last_compression` so the /health endpoint can show
# whether auto-compress has fired recently and how aggressive it had to
# be. We deliberately keep it minimal: just (timestamp, before, after,
# steps). When the buffer is empty the endpoint reports "never fired",
# which is the steady state.
@dataclass
class _CompressionEvent:
    at: float
    before_tokens: int
    after_tokens: int
    threshold: int
    steps: list[str] = field(default_factory=list)


_LAST_COMPRESS: list[_CompressionEvent] = []
_LAST_BEFORE_TOKENS: list[int] = []  # 1-slot ring: tokens of the most recent call


def last_compression() -> dict[str, Any] | None:
    """Return a small dict describing the most recent auto-compress event.

    Returns ``None`` when no compression has fired (steady state).
    """
    if not _LAST_COMPRESS:
        return None
    ev = _LAST_COMPRESS[-1]
    return {
        "at": ev.at,
        "before_tokens": ev.before_tokens,
        "after_tokens": ev.after_tokens,
        "threshold": ev.threshold,
        "steps": list(ev.steps),
    }


def last_request_tokens() -> int | None:
    """Return the estimated token count of the most recent outgoing call,
    or ``None`` if no call has been observed this process."""
    if not _LAST_BEFORE_TOKENS:
        return None
    return _LAST_BEFORE_TOKENS[-1]


class LLMClient(Protocol):
    """Minimal contract the council needs.

    ``chat_json`` MUST return a dict; on any failure the implementation
    should raise :class:`LLMError` so the council can fall back to a
    sentinel opinion.
    """

    name: str
    model: str

    async def chat_json(self, system: str, user: str) -> dict[str, Any]: ...


class LLMError(RuntimeError):
    """Raised when an LLM call cannot produce a valid JSON response."""


@dataclass
class StubClient:
    """Deterministic stand-in used when no real API key is configured.

    Echoes a structured opinion derived from the gate scores embedded
    in the prompt so the run still produces a valid council output.
    Marked ``name == "ocg-stub"`` so callers can distinguish it from
    a live response.
    """

    name: str = "ocg-stub"
    model: str = DEFAULT_MODEL

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        # Cheap heuristic: average the signed gate scores from the
        # user prompt.  This mirrors the legacy deterministic behaviour
        # closely enough that the smoke + existing tests still pass.
        scores: list[float] = []
        for line in user.splitlines():
            for tok in line.replace("=", " ").replace(":", " ").split():
                try:
                    v = float(tok)
                except ValueError:
                    continue
                if -100.0 <= v <= 100.0:
                    scores.append(v)
        avg = sum(scores) / len(scores) if scores else 0.0

        if avg > 5.0:
            direction = "LONG"
        elif avg < -5.0:
            direction = "SHORT"
        else:
            direction = "WAIT"

        # Special-case the risk + skeptic roles so the deterministic
        # cap behaviour (always confidence <= 0.35 for those) survives.
        is_skeptic_or_risk = any(
            tag in system
            for tag in ("SKEPTICAL", "RISK", "COUNTER-ARGUMENT")
        )
        confidence_cap = 0.35 if is_skeptic_or_risk else 1.0
        confidence = min(abs(avg) / 100.0 + 0.2, confidence_cap)

        return {
            "status": "VALID",
            "direction": direction,
            "confidence": round(confidence, 3),
            "risk_flags": [],
            "evidence_ids": [],
            "reason": (
                f"ocg-stub deterministic echo: avg gate score {avg:+.1f}, "
                f"direction {direction}"
            ),
        }


@dataclass
class OpenAICompatClient:
    """OpenAI-compatible chat completions client.

    Default base URL is InferHub (``https://api.inferhub.dev/v1``)
    which serves ``provider/model`` IDs.  The exact request body is
    the OpenAI ``/v1/chat/completions`` shape so any compatible
    endpoint (OpenRouter, local llama.cpp, etc.) works with the same
    code.
    """

    base_url: str
    api_key: str
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    name: str = "ocg"
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS

    def __post_init__(self) -> None:
        if self.base_url.endswith("/"):
            self.base_url = self.base_url.rstrip("/")
        # Honor the operator-supplied threshold if present so a single
        # ``.env`` knob retunes both the council budget and the brain.
        self.max_context_tokens = compress_at_threshold()

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        # 1. Estimate + auto-compress before we touch the wire. This
        #    keeps the request under the operator's defended context
        #    window even when the council hands us an unusually fat
        #    user prompt.
        pre_tokens = estimate_prompt_tokens(system, user)
        _LAST_BEFORE_TOKENS.append(pre_tokens)
        if len(_LAST_BEFORE_TOKENS) > 1:
            _LAST_BEFORE_TOKENS.pop(0)
        compressed = compress_role_prompt(
            system,
            user,
            threshold=self.max_context_tokens,
        )
        if compressed.was_compressed:
            import time as _t
            _LAST_COMPRESS.append(
                _CompressionEvent(
                    at=_t.time(),
                    before_tokens=pre_tokens,
                    after_tokens=compressed.estimated_tokens,
                    threshold=self.max_context_tokens,
                    steps=list(compressed.steps),
                )
            )
            if len(_LAST_COMPRESS) > 1:
                _LAST_COMPRESS.pop(0)
        system, user = compressed.system, compressed.user

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "model": self.model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.post(url, json=body, headers=headers)
                if resp.status_code >= 500 and attempt < self.max_retries:
                    await _sleep_backoff(attempt)
                    continue
                if resp.status_code != 200:
                    raise LLMError(
                        f"HTTP {resp.status_code} from {self.name}: "
                        f"{resp.text[:200]}"
                    )
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if not content:
                    raise LLMError(f"{self.name} returned empty content")
                blob = _extract_json_blob(content)
                try:
                    return json.loads(blob)
                except json.JSONDecodeError as exc:
                    raise LLMError(
                        f"{self.name} returned non-JSON content: {blob[:120]}"
                    ) from exc
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise LLMError(f"{self.name} transport error: {exc}") from exc
                await _sleep_backoff(attempt)
        # Should be unreachable.
        raise LLMError(f"{self.name} failed after retries: {last_exc}")


async def _sleep_backoff(attempt: int) -> None:
    """Tiny exponential backoff with jitter, async-friendly."""
    import asyncio
    import random

    base = 0.4 * (2 ** attempt)
    await asyncio.sleep(base + random.uniform(0, 0.2))


_THINK_RE = None
_FENCE_RE = None


def _extract_json_blob(raw: str) -> str:
    """Strip a leading ``<think>…</think>`` block or markdown ```json
    fences from a model's reply.

    Reasoning-capable models (DeepSeek-R1, MiniMax, etc.) wrap their
    JSON answer either in a ``<think>`` block, in ```` ```json …
    ```` ``` fences, or both. Naively ``json.loads``-ing the full
    content fails because of the leading scaffolding. We strip the
    think block first, then unwrap a single ```` ```json ```` fence
    if present, falling back to the raw content otherwise.

    Exposed at module scope so unit tests can pin the contract.
    """
    global _THINK_RE, _FENCE_RE
    if not raw:
        return raw
    if _THINK_RE is None:
        import re
        _THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
        _FENCE_RE = re.compile(
            r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?\s*```\s*$",
            re.DOTALL,
        )
    s = _THINK_RE.sub("", raw, count=1).strip()
    if not s:
        s = raw.strip()
    m = _FENCE_RE.match(s)
    if m:
        s = m.group(1).strip()
    return s or raw.strip()


def build_client() -> LLMClient:
    """Factory: pick OpenAICompatClient when a key is set, else StubClient.

    Read order (first non-empty wins):
      * ``$LLM_API_KEY``         — primary knob
      * ``$INFERHUB_API_KEY``    — alias #1
      * ``$INFERHUB_KEY``        — alias #2 (the name InferHub's own
        OpenAI SDK snippet uses)
    Any of them starting with ``sk-airo-…`` will be accepted.
    """
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("INFERHUB_API_KEY")
        or os.getenv("INFERHUB_KEY")
        or ""
    ).strip()
    if api_key:
        return OpenAICompatClient(
            base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
            api_key=api_key,
            model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
            timeout_s=float(os.getenv("LLM_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))),
        )
    return StubClient(model=os.getenv("LLM_MODEL", DEFAULT_MODEL))


def current_provider() -> dict[str, str]:
    """Return a small dict describing which brain is wired up.

    Used by ``/health`` and by tests to assert the wiring without
    pulling in the real client.
    """
    client = build_client()
    info: dict[str, str] = {
        "llm_provider": client.name,
        "llm_model": client.model,
    }
    if isinstance(client, OpenAICompatClient):
        info["llm_base_url"] = client.base_url
        info["llm_max_context_tokens"] = str(client.max_context_tokens)
    last = last_request_tokens()
    if last is not None:
        info["llm_last_request_tokens_est"] = str(last)
    last_compress = last_compression()
    if last_compress is not None:
        info["llm_last_compress_at"] = str(int(last_compress["at"]))
        info["llm_last_compress_before"] = str(last_compress["before_tokens"])
        info["llm_last_compress_after"] = str(last_compress["after_tokens"])
        info["llm_last_compress_steps"] = " | ".join(last_compress["steps"])
    return info


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "LLMClient",
    "LLMError",
    "OpenAICompatClient",
    "StubClient",
    "build_client",
    "current_provider",
]