"""Run the entry extraction through the Gemini Batch API (half the price of
live calls) and fill the normal LLM cache with the answers.

The prompts are rendered by the pipeline's own code (pipeline.load_entries +
extraction.llm_observations.render_prompt), so every answer lands under the
cache key a live call would use: sha256(model, prompt). Afterwards
``laubmann-kg export-all`` with the same config replays the cache; entries the
batch could not answer (errors, truncated at max_output_tokens) are simply
called live then.

    python tools/batch_extract.py prepare --config configs/local_full.yaml --input-dir data/corpus_patched --work data/batch/2026-10-01
    python tools/batch_extract.py submit  --work data/batch/2026-10-01
    python tools/batch_extract.py status  --work data/batch/2026-10-01
    python tools/batch_extract.py collect --config configs/local_full.yaml --work data/batch/2026-10-01

Each step is idempotent: ``prepare`` skips prompts already in the cache,
``collect`` never overwrites a cached answer.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from laubmann_kg.env import load_dotenv
from laubmann_kg.extraction.llm_observations import render_prompt
from laubmann_kg.llm.cache import LLMCache, cache_key
from laubmann_kg.llm.prompts import PromptLibrary
from laubmann_kg.pipeline import load_config, load_entries

logger = logging.getLogger("batch_extract")


def _client():
    from google import genai
    load_dotenv()
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GOOGLE_API_KEY missing (.env)")
    return genai.Client(api_key=key)


def _generation_config(extraction: dict) -> dict:
    cfg = {"temperature": float(extraction.get("temperature", 0.0)),
           "responseMimeType": "application/json",
           "maxOutputTokens": int(extraction.get("max_output_tokens", 32768))}
    if extraction.get("thinking_level"):
        cfg["thinkingConfig"] = {"thinkingLevel": extraction["thinking_level"]}
    return cfg


def prepare(args) -> None:
    config = load_config(Path(args.config))
    extraction = config["extraction"]
    model = extraction["model"]
    cache = LLMCache(Path(extraction["cache_dir"]))
    prompts = PromptLibrary(Path(extraction.get("prompt_dir", "prompts")))
    entries, _ = load_entries(config, Path(args.input_dir) if args.input_dir else None)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    gen = _generation_config(extraction)
    n = cached = 0
    index = {}
    with (work / "requests.jsonl").open("w", encoding="utf-8") as out:
        for entry in entries:
            prompt = render_prompt(entry, prompts)
            if prompt is None:
                continue
            key = cache_key(model, prompt)
            if key in index:
                continue
            if cache.get(key) is not None:
                cached += 1
                continue
            index[key] = entry.entry_id
            out.write(json.dumps({"key": key, "request": {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": gen}}, ensure_ascii=False) + "\n")
            n += 1
    # the prompt text per key, so collect can write complete cache records
    with (work / "prompts.jsonl").open("w", encoding="utf-8") as out:
        for entry in entries:
            prompt = render_prompt(entry, prompts)
            if prompt is not None and cache_key(model, prompt) in index:
                out.write(json.dumps({"key": cache_key(model, prompt), "entry_id": entry.entry_id,
                                      "prompt": prompt}, ensure_ascii=False) + "\n")
    (work / "meta.json").write_text(json.dumps({"model": model, "requests": n, "already_cached": cached,
                                                "cache_dir": extraction["cache_dir"], "generation": gen},
                                               indent=1), encoding="utf-8")
    print(f"{n} requests to batch ({cached} already cached) -> {work / 'requests.jsonl'}")


def submit(args) -> None:
    work = Path(args.work)
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    client = _client()
    uploaded = client.files.upload(file=str(work / "requests.jsonl"),
                                   config={"mime_type": "jsonl", "display_name": work.name})
    job = client.batches.create(model=meta["model"], src=uploaded.name,
                                config={"display_name": f"laubmann-extraction-{work.name}"})
    meta.update(job=job.name, input_file=uploaded.name)
    (work / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"submitted {job.name} ({meta['requests']} requests)")


def status(args) -> None:
    meta = json.loads((Path(args.work) / "meta.json").read_text(encoding="utf-8"))
    client = _client()          # keep a reference: the SDK closes an unreferenced client
    job = client.batches.get(name=meta["job"])
    print(job.name, job.state, getattr(job, "batch_stats", None) or "")


def _text(response: dict) -> tuple[str, str]:
    cands = response.get("candidates") or []
    if not cands:
        return "", ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text, str(cands[0].get("finishReason") or "")


def _usage(response: dict) -> dict:
    meta = response.get("usageMetadata") or {}
    names = {"promptTokenCount": "prompt_token_count", "cachedContentTokenCount": "cached_content_token_count",
             "candidatesTokenCount": "candidates_token_count", "thoughtsTokenCount": "thoughts_token_count",
             "totalTokenCount": "total_token_count"}
    return {v: int(meta[k]) for k, v in names.items() if isinstance(meta.get(k), int)}


def collect(args) -> None:
    work = Path(args.work)
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    config = load_config(Path(args.config))
    extraction = config["extraction"]
    cache = LLMCache(Path(extraction["cache_dir"]))
    client = _client()
    job = client.batches.get(name=meta["job"])
    state = str(job.state)
    if not state.endswith("SUCCEEDED"):
        sys.exit(f"batch not finished: {state}")
    raw = client.files.download(file=job.dest.file_name)
    (work / "results.jsonl").write_bytes(raw)
    prompts = {}
    for line in (work / "prompts.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        prompts[rec["key"]] = rec["prompt"]
    ok = truncated = failed = skipped = 0
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        key = rec.get("key")
        response = rec.get("response")
        if not key or key not in prompts or not response:
            failed += 1
            continue
        if cache.get(key) is not None:
            skipped += 1
            continue
        text, reason = _text(response)
        usage = _usage(response)
        if reason.upper().endswith("MAX_TOKENS"):
            # never cached: export-all calls it live (and flags it if it truncates again)
            cache.log_usage(key, meta["model"], {**usage, "batch": True}, truncated=True)
            truncated += 1
            continue
        if not text:
            failed += 1
            continue
        request = {"model": meta["model"], "prompt": prompts[key],
                   "params": {"temperature": extraction.get("temperature", 0.0),
                              "max_output_tokens": extraction.get("max_output_tokens"),
                              "thinking_level": extraction.get("thinking_level"), "mode": "batch"}}
        cache.log_usage(key, meta["model"], {**usage, "batch": True})
        cache.set(key, request, text, usage={**usage, "batch": True})
        ok += 1
    print(f"cached {ok}, truncated {truncated} (live later), failed {failed} (live later), "
          f"already cached {skipped}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "submit", "status", "collect"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        if name in ("prepare", "collect"):
            p.add_argument("--config", required=True)
        if name == "prepare":
            p.add_argument("--input-dir")
    args = ap.parse_args()
    {"prepare": prepare, "submit": submit, "status": status, "collect": collect}[args.cmd](args)


if __name__ == "__main__":
    main()
