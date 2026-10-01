"""Export the crops of the multimodal regions (drawings, maps, photographs, objects, text inserts) as JPEGs.

    python tools/export_region_crops.py --regions data/corpus_patched/multimodal_regions.jsonl \
        --source "G:/My Drive/HistOrniGraph_output" --out data/region_crops [--max-side 1400] [--workers 8]

Reads ``<source>/Laubmann_NN_gemini/<crop>`` (``regions/<page_id>/rNN_<Type>.png``)
of every region and writes ``<out>/<region_uid>.jpg``: the local copies the
review pages fall back to when a crop cannot be loaded from Drive. Existing
files are skipped. Needs Pillow.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _convert(job) -> str:
    src, dst, max_side = job
    from PIL import Image
    if Path(dst).exists():
        return "skip"
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            tmp = Path(dst).with_suffix(".tmp")
            im.save(tmp, "JPEG", quality=85)
            tmp.replace(dst)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error {src}: {exc}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-side", type=int, default=1400)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    regions = [json.loads(line) for line in Path(args.regions).read_text(encoding="utf-8").splitlines() if line.strip()]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(str(Path(args.source) / f"Laubmann_{int(r['volume']):02d}_gemini" / r["crop"]), str(out / f"{r['region_uid']}.jpg"), args.max_side)
            for r in regions if r.get("crop") and r.get("region_uid")]
    results = {"ok": 0, "skip": 0, "error": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:       # reading from the Drive mount is the slow part
        for r in pool.map(_convert, jobs):
            key = r.split(" ", 1)[0]
            results[key] = results.get(key, 0) + 1
            if key == "error":
                print(r)
    print(results)


if __name__ == "__main__":
    main()
