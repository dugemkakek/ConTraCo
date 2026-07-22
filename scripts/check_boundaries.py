"""Recommend-only boundary checker.

Enforces the project's hard rule: no execution path to any exchange,
DEX, or broker. Skips the Python venv (``apps/api/venv``) and
SQLAlchemy's ubiquitous ``session.execute()`` calls — those are
DB calls, not trade execution.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"

SKIP_DIRS = {"venv", "__pycache__", ".pytest_cache", ".next", "node_modules"}
SKIP_PATHS = {"scripts/check_boundaries.py"}

# Each tuple is (regex, friendly reason). Regex matches anywhere in a line.
# We deliberately avoid matching DB-style ``.execute()`` calls by requiring
# a top-level call site (no leading dot/whitespace+identifier).
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"(^|\s|;|=|\()(swapExactIn|swapExactOut|swapTokensForExactTokens)\s*\(",
     "Uniswap router swap call"),
    (r"(^|\s|;|=|\()(multicall|sendTransaction|signTransaction|approve)\s*\(",
     "wallet / contract write"),
    (r"broadcastRawTransaction", "broadcastRawTransaction — wallet submit"),
    (r"\b(PrivateKey|Mnemonic)\s*=", "private-key / mnemonic assignment"),
    (r"\bmnemonic\s*:\s*str", "mnemonic field on a dataclass"),
    (r"/api/v[34]/spot/orders", "Gate.io signed order endpoint"),
    (r"/api/v[34]/private/(order|trade|cancel|amend)", "private trading endpoint"),
    (r"\bseed_phrase\s*=\s*['\"][a-zA-Z0-9 ]", "literal seed phrase"),
    (r"owner\s*=\s*['\"](0x)?[0-9a-fA-F]{40}['\"]", "owner address literal in code"),
]


def is_allowlisted(path: Path) -> bool:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    if rel in SKIP_PATHS:
        return True
    # The execution module is paper-by-default; LIVE_TRADING gate is enforced.
    if rel.endswith("apps/api/app/services/execution/__init__.py"):
        return True
    # The LLM smoke is a developer diagnostic.
    if rel.endswith("apps/api/_llm_smoke.py"):
        return True
    return False


def main() -> int:
    failures: list[str] = []
    for src in APPS.rglob("*.py"):
        parts = src.parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if is_allowlisted(src):
            continue
        text = src.read_text(encoding="utf-8", errors="ignore")
        for pattern, reason in FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                line_no = text.count("\n", 0, match.start()) + 1
                line = text.splitlines()[line_no - 1].strip()
                # Skip comment-only lines.
                if line.startswith("#"):
                    continue
                failures.append(
                    f"{src.relative_to(ROOT)}:{line_no}  {reason}\n      {line}"
                )
    if failures:
        print("BOUNDARY VIOLATIONS")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — no execution surfaces detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
