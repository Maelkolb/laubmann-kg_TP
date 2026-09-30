"""Sum the token ledger of LLM caches (``<cache_dir>/usage.jsonl``) into a cost.

Every live Gemini call appends one line to ``usage.jsonl`` in its cache folder
(src/laubmann_kg/llm/cache.py ``log_usage``), truncated answers included - they
are not cached but were paid for. Thinking tokens are billed as output; cached
prompt tokens (implicit prefix caching) at the discounted cached-input price.

    python tools/llm_cost.py data/cache/llm_v4 [more cache dirs ...]
    python tools/llm_cost.py data/cache/llm_v4 --since 2026-10-01T00:00

Prices default to Gemini 3.5 Flash (USD per million tokens; check
https://ai.google.dev/gemini-api/docs/pricing before quoting a bill).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# USD per 1M tokens: input, cached input, output (incl. thinking)
PRICES = {
    "gemini-3.5-flash": (1.50, 0.15, 9.00),
    "gemini-3.5-flash-lite": (0.30, 0.03, 2.50),
    # promo prices through 2026-12-31 (from 2027: 1.50 / 0.15 / 7.50)
    "gemini-3.8-flash": (0.75, 0.075, 3.75),
    "gemini-3.7-flash": (0.75, 0.075, 3.75),
}


def summarize(paths: list[Path], since: str = "", prices: tuple[float, float, float] | None = None) -> dict:
    total = {"calls": 0, "truncated": 0, "prompt": 0, "cached": 0, "output": 0, "thoughts": 0, "usd": 0.0}
    for path in paths:
        ledger = path / "usage.jsonl" if path.is_dir() else path
        if not ledger.exists():
            continue
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if since and rec.get("ts", "") < since:
                continue
            usage = rec.get("usage") or {}
            prompt = int(usage.get("prompt_token_count", 0))
            cached = int(usage.get("cached_content_token_count", 0))
            output = int(usage.get("candidates_token_count", 0))
            thoughts = int(usage.get("thoughts_token_count", 0))
            p_in, p_cached, p_out = prices or PRICES.get(rec.get("model", ""), PRICES["gemini-3.5-flash"])
            total["calls"] += 1
            total["truncated"] += bool(rec.get("truncated"))
            total["prompt"] += prompt
            total["cached"] += cached
            total["output"] += output
            total["thoughts"] += thoughts
            usd = ((prompt - cached) * p_in + cached * p_cached + (output + thoughts) * p_out) / 1e6
            total["usd"] += usd * (0.5 if usage.get("batch") else 1.0)   # Batch API: half price
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help="cache folders (or usage.jsonl files)")
    ap.add_argument("--since", default="", help="only calls at/after this ISO timestamp (UTC)")
    args = ap.parse_args()
    t = summarize(args.paths, args.since)
    n = max(t["calls"], 1)
    print(f"calls {t['calls']} (truncated {t['truncated']})")
    print(f"prompt {t['prompt']:,} tokens (cached {t['cached']:,}), output {t['output']:,}, thinking {t['thoughts']:,}")
    print(f"per call: prompt {t['prompt'] / n:,.0f}, output {t['output'] / n:,.0f}, thinking {t['thoughts'] / n:,.0f}")
    print(f"cost ${t['usd']:.2f}  (${t['usd'] / n:.4f} per call)")


if __name__ == "__main__":
    main()
