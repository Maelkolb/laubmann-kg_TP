"""Last check before a duplicate region is dropped: does it show anything the region it repeats does not?

    python tools/validation_ui/machine_review/region_duplicate_check.py data/review/machine/region_quality_machine.csv \\
        --out data/cache/region_check/duplicate_check.json [--model gemini-3.8-flash]

For every row dropped as a duplicate, the model sees both crops and says whether the dropped one adds anything (the
other side of a postcard, a handwritten note or caption, a part of the object the kept one lacks). region_check_combine.py
keeps the region when it does (--duplicate-check).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

PROMPT = """Two crops from the scanned field diaries of an ornithologist. A layout model cut both out and a check judged
that crop A repeats the object of crop B (the same photograph, map, clipping, drawing or mounted object, scanned
again, or seen as a cut-off strip or as a mirror image through the paper), and that B shows it better.

Does A show anything B does not show? For example the other side of a postcard or photograph, a handwritten note,
caption, stamp or date, a part of the object that is missing in B, or a different object altogether.

Answer with one JSON object, nothing else:
{"adds": true or false, "what": "a few words, empty when nothing", "c": confidence 0.0-1.0}
The first image is A, the second is B."""


def jpeg(path: Path, longest: int = 1000) -> bytes:
    img = Image.open(path).convert("RGB")
    img.thumbnail((longest, longest))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decisions")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crops", default=str(REPO / "data" / "region_crops"))
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--cache", default=str(REPO / "data" / "cache" / "region_check_v1"))
    args = ap.parse_args()

    from laubmann_kg.env import load_dotenv
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.structured_output import extract_json

    load_dotenv(REPO / ".env")
    client = build_client(cache=LLMCache(Path(args.cache)), config={
        "backend": "google", "model": args.model, "api_key_env": "GOOGLE_API_KEY", "temperature": 0.0,
        "max_output_tokens": 2048, "timeout": 300, "thinking_level": "low", "media_resolution": "MEDIA_RESOLUTION_HIGH",
        "retry_attempts": 3, "retry_backoff": 2.0})
    with open(args.decisions, encoding="utf-8", newline="") as h:
        pairs = [(r["region_uid"], r["duplicate_of"]) for r in csv.DictReader(h) if r.get("reason") == "duplicate" and r.get("duplicate_of")]
    out = Path(args.out)
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}

    def one(pair):
        a, b = pair
        if a in done:
            return a, done[a]
        crops = Path(args.crops)
        try:
            prompt = f"{PROMPT}\n\nA = {a}, B = {b}"   # the ids in the text: the cache keys on it
            raw = client.complete(prompt, images=[("A", jpeg(crops / f"{a}.jpg")), ("B", jpeg(crops / f"{b}.jpg"))])
            data = extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            return a, {"error": str(exc)[:160]}
        return a, data if isinstance(data, dict) else {"error": "unparseable"}

    with ThreadPoolExecutor(max_workers=10) as pool:
        for a, verdict in pool.map(one, pairs):
            done[a] = verdict
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    adds = [a for a, v in done.items() if v.get("adds") is True]
    print(f"{len(pairs)} duplicates checked; {len(adds)} add something: " + "; ".join(f"{a}: {done[a].get('what')}" for a in adds[:20]))


if __name__ == "__main__":
    main()
