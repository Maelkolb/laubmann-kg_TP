"""Export the page scans of a corpus as JPEGs for the visual extraction pass.

    python tools/export_page_images.py --corpus data/corpus_patched/corpus.json \
        --source "G:/My Drive/HistOrniGraph_output" --out data/pages_jpg [--max-side 2000] [--workers 8]

Reads ``<source>/Laubmann_NN_gemini/pages/<image>`` for every page of the
corpus and writes ``<out>/<page_id>.jpg`` (longest side ``--max-side`` px,
quality 85). Gemini bills an image by its media resolution, not its pixel size,
so the smaller file only saves upload time. Existing files are skipped.
Needs Pillow.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
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
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-side", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    pages = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(str(Path(args.source) / f"Laubmann_{int(p['volume']):02d}_gemini" / "pages" / p["image"]),
             str(out / f"{p['page_id']}.jpg"), args.max_side) for p in pages if p.get("image")]
    results = {"ok": 0, "skip": 0, "error": 0}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(_convert, jobs, chunksize=8):
            key = r.split(" ", 1)[0]
            results[key] = results.get(key, 0) + 1
            if key == "error":
                print(r)
    print(results)


if __name__ == "__main__":
    main()
