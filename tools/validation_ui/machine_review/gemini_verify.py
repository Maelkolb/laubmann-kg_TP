"""Second, independent opinion on the machine review batches from Gemini.

The Claude subagents answer each batch of a check (taxa, persons, places,
habitats) from its INSTRUCTIONS.md; this script gives the SAME instructions and
the SAME batch to Gemini (without the Claude answer) and stores Gemini's answer
in ``<check>/answers_gemini/batch_N.json`` in the same contract. merge.py counts
an agreeing Gemini answer as one more independent source, so a verdict can
reach the pipeline's threshold (confidence ≥ 0.9 and ≥ 2 sources) without a
human; a disagreeing one lowers the confidence and sends the case to the
reviewer. Calls are cached and their tokens logged (usage.jsonl in the cache
directory; ``tools/llm_cost.py`` prices them); ``--budget`` stops the run
when the estimated spend reaches it.

    python tools/validation_ui/machine_review/gemini_verify.py --work <workdir> \\
        [--checks taxa persons places habitats] [--model gemini-3.8-flash] [--budget 8] [--concurrency 8]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

ADAPTER = """You work without file access. Where the instructions below say to read a batch file, the batch is given at
the end of this prompt (BATCH); where they say to read another listed file, its content is given as well. Where they
say to write the answer file, output exactly that JSON instead — nothing else, no Markdown, no reply line. Answer every
item of the batch, in input order, keeping the ids of the batch (`entity`, `form`).

"""

PRICES = {"gemini-3.8-flash": (0.75, 3.75, 0.075), "gemini-3.5-flash": (1.5, 9.0, 0.15)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--checks", nargs="*", default=["taxa", "persons", "places", "habitats"])
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--cache", default=str(REPO / "data" / "cache" / "machine_review_gemini"))
    ap.add_argument("--budget", type=float, default=8.0, help="stop when the estimated USD of this run reaches it")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="at most this many batches per check (0 = all)")
    args = ap.parse_args()

    from laubmann_kg.env import load_dotenv
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.structured_output import extract_json

    load_dotenv(REPO / ".env")                     # GOOGLE_API_KEY
    client = build_client(cache=LLMCache(Path(args.cache)), config={
        "backend": "google", "model": args.model, "api_key_env": "GOOGLE_API_KEY", "temperature": 0.0,
        "max_output_tokens": 32768, "timeout": 600, "thinking_level": "low", "context_cache": False,
        "retry_attempts": 3, "retry_backoff": 2.0})
    p_in, p_out, _ = PRICES.get(args.model, PRICES["gemini-3.8-flash"])
    spent = [0.0]
    lock = threading.Lock()
    work = Path(args.work)

    jobs = []
    for check in args.checks:
        d = work / check
        ins = d / "INSTRUCTIONS.md"
        if not ins.exists():
            print(f"{check}: no INSTRUCTIONS.md, skipped")
            continue
        extra = ""
        if check == "habitats" and (d / "eunis_levels_1-3.txt").exists():
            extra = "\n\nEUNIS list (the file eunis_levels_1-3.txt):\n" + (d / "eunis_levels_1-3.txt").read_text(encoding="utf-8")
        batches = sorted((d / "batches").glob("batch_*.json"))
        if args.limit:
            batches = batches[:args.limit]
        (d / "answers_gemini").mkdir(exist_ok=True)
        for b in batches:
            out = d / "answers_gemini" / b.name
            if out.exists():
                continue
            prompt = ADAPTER + ins.read_text(encoding="utf-8") + extra + "\n\nBATCH (" + b.name + "):\n" + b.read_text(encoding="utf-8")
            jobs.append((check, b, out, prompt))
    print(f"{len(jobs)} batches to ask")

    def one(job):
        check, b, out, prompt = job
        with lock:
            if spent[0] >= args.budget:
                return "budget"
        try:
            raw = client.complete(prompt)
        except Exception as exc:  # noqa: BLE001
            return f"error {exc}"
        inner = getattr(client, "client", client)
        u = inner.last_usage() if hasattr(inner, "last_usage") else None
        if u:
            cost = (u.get("prompt_token_count", 0) * p_in
                    + (u.get("candidates_token_count", 0) + u.get("thoughts_token_count", 0)) * p_out) / 1e6
            with lock:
                spent[0] += cost
        try:
            data = extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            return f"unparseable {exc}"
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        out.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        return "ok"

    results = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for job, r in zip(jobs, pool.map(one, jobs)):
            results[r.split(" ")[0]] = results.get(r.split(" ")[0], 0) + 1
            if r != "ok":
                print(job[0], job[1].name, r[:200])
    print("results", results, f"estimated spend this run ${spent[0]:.2f} (cache hits cost nothing)")


if __name__ == "__main__":
    main()
