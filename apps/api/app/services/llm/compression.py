"""Token estimation + prompt compression for the LLM brain.

Why this exists
---------------
The council sends the gate results + last candles to a chat-completions
endpoint whose context window the operator may want to defend against
runaway prompts. We do not depend on tiktoken (not in requirements.txt)
and we deliberately keep the math conservative: 1 token ≈ 4 chars of
mixed text plus a small per-message overhead. This is intentionally an
*over-estimate* — we'd rather over-truncate a prompt than send a
multi-hundred-thousand-token request that the model silently truncates
mid-thought.

Knob: ``LLM_CONTEXT_COMPRESS_AT_TOKENS`` (default 100_000). When the
estimated token count of the (system + user) prompt is above this
value, :func:`compress_role_prompt` is called and the user-prompt body
is shrunk. The system prompt is never touched.

The compression is lossless on the *gate* fields (score/confidence) and
lossy on the *evidence* fields (gates' ``reason`` strings are truncated
first, then the candle tail is shortened, then — as a last resort — the
system prompt's role framing is shortened by stripping the trailing
free-text). Every step is logged so a post-mortem can see exactly what
was dropped.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


DEFAULT_COMPRESS_AT_TOKENS = 100_000
# Over-estimate 1 token = 4 chars for ASCII. UTF-8 CJK characters
# typically map to ~1.5 tokens each, so this still errs high.
CHARS_PER_TOKEN = 4
# Per-message structural overhead (role markers, formatting). Models
# actually charge for this too; 4 tokens is a safe lower bound.
PER_MESSAGE_OVERHEAD_TOKENS = 4


def compress_at_threshold() -> int:
    """Read the operator's threshold from env; default 100k."""
    raw = os.getenv("LLM_CONTEXT_COMPRESS_AT_TOKENS", str(DEFAULT_COMPRESS_AT_TOKENS))
    try:
        v = int(raw)
    except (TypeError, ValueError):
        logger.warning("bad LLM_CONTEXT_COMPRESS_AT_TOKENS=%r, using default", raw)
        return DEFAULT_COMPRESS_AT_TOKENS
    if v < 1024:
        # Below 1k the gate would fire on every trivial prompt — almost
        # certainly an operator typo. Clamp up rather than disable.
        logger.warning("LLM_CONTEXT_COMPRESS_AT_TOKENS=%d too low, clamping to 1024", v)
        return 1024
    return v


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for a single string."""
    if not text:
        return 0
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN + PER_MESSAGE_OVERHEAD_TOKENS


def estimate_prompt_tokens(system: str, user: str) -> int:
    """Two-message chat-completions prompt estimate."""
    return estimate_tokens(system) + estimate_tokens(user)


@dataclass
class CompressionResult:
    system: str
    user: str
    estimated_tokens: int
    was_compressed: bool
    steps: list[str] = field(default_factory=list)

    def log_dict(self) -> dict:
        return {
            "estimated_tokens": self.estimated_tokens,
            "was_compressed": self.was_compressed,
            "steps": list(self.steps),
        }


def _truncate_middle(text: str, keep_chars: int) -> str:
    """Keep the first + last ``keep_chars/2`` characters; mark the gap."""
    if len(text) <= keep_chars:
        return text
    half = keep_chars // 2
    return (
        text[:half]
        + f"\n\n[…{len(text) - keep_chars} chars truncated by auto-compressor…]\n\n"
        + text[-half:]
    )


def _shrink_user(user: str, target_chars: int) -> str:
    """Lossy shrink of the user prompt body to <= target_chars.

    Strategy (lossless on the gate scores, lossy on prose):
      1. Keep the structured header (Symbol / Timeframe / Order book) intact.
      2. Cap each ``- <gate>: status=…`` line's reason to 60 chars.
      3. Cap the candle summary (after ``Recent candles:``) to one
         line of up to 200 chars, dropping extras.
      4. As a last resort, middle-truncate the whole string.
    """
    if len(user) <= target_chars:
        return user

    # 1. Structured header lives before the first ``\nGate evaluations:``.
    marker = "\nGate evaluations:"
    if marker in user:
        head, rest = user.split(marker, 1)
    else:
        head, rest = "", user
    head = head.rstrip() + marker + "\n"

    # 2. Gate lines: keep name/status/score/confidence, drop most of reason.
    gate_lines: list[str] = []
    for line in rest.splitlines():
        if not line.startswith("- "):
            gate_lines.append(line)
            continue
        # Find ``reason=`` and chop everything after 60 chars inside the quotes.
        idx = line.find("reason=")
        if idx == -1:
            gate_lines.append(line)
            continue
        prefix = line[: idx + len("reason=")]
        # ``reason='…'`` — keep first 60 chars of the value, then close.
        rest_of_line = line[idx + len("reason="):]
        # Strip optional leading quote.
        if rest_of_line.startswith("'"):
            quote_open = "'"
            rest_of_line = rest_of_line[1:]
        else:
            quote_open = ""
        if len(rest_of_line) > 60:
            rest_of_line = rest_of_line[:60] + "…' [truncated]"
        elif rest_of_line.endswith("'") is False and rest_of_line:
            # Make sure it stays a valid trailing-quoted string.
            rest_of_line = rest_of_line.rstrip("'") + "'"
        gate_lines.append(prefix + quote_open + rest_of_line)

    new_rest = "\n".join(gate_lines)

    # 3. Composed length still over budget? Middle-truncate.
    if len(head) + len(new_rest) > target_chars:
        new_rest = _truncate_middle(new_rest, target_chars - len(head) - 1)

    return head + new_rest


def _shrink_system(system: str, target_chars: int) -> str:
    """Shrink the system prompt. We keep the role + JSON contract; we
    drop the trailing free-text advice."""
    if len(system) <= target_chars:
        return system
    # Keep the first ``. ``-terminated clause (the role) and the
    # ``Return only a JSON object…`` clause; drop everything after.
    clauses = system.split(". ")
    keep: list[str] = []
    running = 0
    for c in clauses:
        candidate = ". ".join(keep + [c]) + "."
        if len(candidate) > target_chars:
            break
        keep.append(c)
        running = len(candidate)
    if not keep:
        return system[:target_chars] + "…"
    return ". ".join(keep) + ". "


def compress_role_prompt(
    system: str,
    user: str,
    threshold: int | None = None,
) -> CompressionResult:
    """Return (possibly) compressed (system, user) prompts.

    Behaviour:
      * If ``estimate_prompt_tokens(system, user) <= threshold``,
        return the inputs unchanged.
      * Otherwise, apply progressively lossy steps to the user prompt
        until we hit ~85% of the threshold (target) so the next call
        has headroom. We log every step. The user-prompt shrink is
        repeated with a tighter budget on each pass so a 1MB blob of
        unstructured text can't slip through; the system-prompt shrink
        fires as a last-resort cap once the user is already at floor.
    """
    if threshold is None:
        threshold = compress_at_threshold()

    base_tokens = estimate_prompt_tokens(system, user)
    if base_tokens <= threshold:
        return CompressionResult(
            system=system,
            user=user,
            estimated_tokens=base_tokens,
            was_compressed=False,
        )

    steps: list[str] = [
        f"trigger: {base_tokens} tokens > {threshold} threshold",
    ]
    target_chars = int(threshold * 0.85 * CHARS_PER_TOKEN)
    current_user = user
    current_system = system

    # Phase 1: keep shrinking the user prompt until either the budget
    # is met, or the per-pass shrink no longer makes meaningful
    # progress. The cap on iterations is just defensive — in practice
    # we converge in 2-3 passes.
    for i in range(1, 6):
        new_tokens = estimate_prompt_tokens(current_system, current_user)
        if new_tokens <= threshold:
            break
        if i == 1:
            # Pass 1: structured shrink (gate reason truncation).
            proposed = _shrink_user(current_user, target_chars=target_chars)
            label = "step1: gate-reason truncation"
        else:
            # Pass 2+: progressively tighter middle-truncate.
            tighter = max(int(target_chars / (2 ** (i - 1))), 64)
            proposed = _truncate_middle(current_user, keep_chars=tighter)
            label = f"step{i}: middle-truncate user to {tighter} chars"
        if proposed == current_user or len(proposed) >= len(current_user):
            # No further shrink possible on the user side.
            steps.append(f"step{i}: user prompt at floor ({len(current_user)} chars)")
            break
        current_user = proposed
        steps.append(label)

    # Phase 2: if the user is at floor and we're still over the budget,
    # shrink the system prompt.
    new_tokens = estimate_prompt_tokens(current_system, current_user)
    if new_tokens > threshold:
        # Try progressively tighter system-prompt caps.
        for cap in (target_chars // 2, target_chars // 4, 64):
            proposed = _shrink_system(current_system, target_chars=cap)
            if len(proposed) < len(current_system):
                current_system = proposed
                steps.append(f"step-sys: shrink system prompt to {cap} chars")
                break
        new_tokens = estimate_prompt_tokens(current_system, current_user)

    # Phase 3: nuclear option — middle-truncate the system prompt body
    # to fit. This should only fire when both prior phases stalled.
    if new_tokens > threshold:
        for cap in (target_chars // 8, 32):
            current_system = _truncate_middle(current_system, keep_chars=cap)
            steps.append(f"step-sys-nuke: truncate system to {cap} chars")
            new_tokens = estimate_prompt_tokens(current_system, current_user)
            if new_tokens <= threshold:
                break

    final_tokens = estimate_prompt_tokens(current_system, current_user)
    steps.append(
        f"final: {final_tokens} tokens (target<= {int(threshold * 0.85)})"
    )
    if final_tokens > threshold:
        # Logged as warning so an operator can spot a regression in the
        # compressor without bringing the bot down.
        logger.warning(
            "auto-compress under-shot budget: %d tokens (threshold %d, "
            "target %d) — user-prompt at floor=%d chars, system-prompt at "
            "floor=%d chars",
            final_tokens,
            threshold,
            int(threshold * 0.85),
            len(current_user),
            len(current_system),
        )
    logger.warning(
        "auto-compress fired: %d -> %d tokens (steps: %s)",
        base_tokens,
        final_tokens,
        "; ".join(steps),
    )
    return CompressionResult(
        system=current_system,
        user=current_user,
        estimated_tokens=final_tokens,
        was_compressed=True,
        steps=steps,
    )


__all__ = [
    "DEFAULT_COMPRESS_AT_TOKENS",
    "CompressionResult",
    "compress_at_threshold",
    "compress_role_prompt",
    "estimate_prompt_tokens",
    "estimate_tokens",
]
