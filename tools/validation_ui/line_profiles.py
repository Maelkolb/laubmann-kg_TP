"""Physical text lines of every region, found in the scan by a horizontal ink
profile (the PAGE-XML has region boxes only, no TextLine coordinates).

    python tools/validation_ui/line_profiles.py <corpus_dir> pages_geometry.json "<HistOrniGraph_output>" [--procs 6] [--out pages_geometry.json]

Adds ``"l": {region id: [[y0, y1], ...]}`` (page coordinates, top to bottom) to
every region of ``pages_geometry.json`` whose page image exists under
``Laubmann_XX_gemini/pages/<page id>.png``. build_payload.py then maps the i-th
transcription line of a region to a physical line instead of dividing the box
into equal parts. Rows are text where the darkness of the row (region width
clipped to the box) exceeds a fraction of the region's darkest rows; bands
shorter than a third of the median band are merged into their neighbour.
Resumable: regions already carrying ``l`` are skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def bands(gray: np.ndarray, box: list[int]) -> list[list[int]]:
    x0, y0, x1, y1 = box
    h, w = gray.shape
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if y1 - y0 < 8 or x1 - x0 < 8:
        return []
    sub = 255 - gray[y0:y1, x0:x1].astype(np.float32)
    # ink per row, normalised against the paper (row median of the region) and smoothed a little
    prof = np.clip(sub - np.median(sub), 0, None).mean(axis=1)
    k = 5
    prof = np.convolve(prof, np.ones(k) / k, mode="same")
    hi = np.percentile(prof, 90)
    if hi <= 1.0:
        return []
    thr = 0.28 * hi
    on = prof > thr
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append([start, i])
            start = None
    if start is not None:
        out.append([start, len(on)])
    if not out:
        return []
    # bridge short gaps (the x-height/ascender split of one line), drop specks
    med = float(np.median([b - a for a, b in out]))
    merged = [out[0]]
    for a, b in out[1:]:
        if a - merged[-1][1] <= max(3, 0.25 * med):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    med = float(np.median([b - a for a, b in merged]))
    res = []
    for a, b in merged:
        if b - a < 0.34 * med:
            continue
        parts = max(1, int(round((b - a) / med))) if b - a > 1.6 * med else 1   # two tight lines in one band
        step = (b - a) / parts
        for q in range(parts):
            res.append([int(a + q * step), int(a + (q + 1) * step)])
    # [y0, y1, ink]: the ink of a band tracks the length of its text line, which lets
    # build_payload.py align transcription lines to bands when the counts differ
    return [[y0 + a, y0 + b, int(prof[a:b].sum())] for a, b in res]


def one_page(args) -> tuple[str, dict]:
    pid, path, regions = args
    try:
        img = Image.open(path)
        img.draft("L", (img.width // 2, img.height // 2))   # JPEG-style draft is ignored by PNG; halve manually
        g = np.asarray(img.convert("L"))
    except Exception as e:  # noqa: BLE001
        return pid, {"_err": str(e)}
    out = {}
    for rid, box in regions.items():
        out[rid] = bands(g, box)
    return pid, out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus_dir")
    ap.add_argument("geometry")
    ap.add_argument("volumes_root")
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    geo = json.loads(Path(args.geometry).read_text(encoding="utf-8"))
    pages = json.loads((Path(args.corpus_dir) / "corpus.json").read_text(encoding="utf-8"))
    root = Path(args.volumes_root)
    stream = ("ParagraphRegion", "ListRegion")
    jobs = []
    for pg in pages:
        pid = pg["page_id"]
        g = geo.get(pid)
        if not g or not g.get("w"):
            continue
        regs = {r["id"]: g["r"][r["id"]] for r in pg["regions"] if r.get("type") in stream and r["id"] in g["r"]}
        if not regs or all(rid in g.get("l", {}) for rid in regs):
            continue
        cand = [root / f"Laubmann_{int(pg['volume']):02d}_gemini" / "pages" / f"{pid}.png"]
        if pid.endswith(("_L", "_R")):
            cand.append(root / f"Laubmann_{int(pg['volume']):02d}_gemini" / "pages" / (re.sub(r"_[LR]$", "_full", pid) + ".png"))
        path = next((c for c in cand if c.exists()), None)
        if path is None:
            continue
        jobs.append((pid, str(path), regs))
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"{len(jobs)} pages to profile")
    t = time.time()
    done = 0
    out = Path(args.out or args.geometry)
    with ProcessPoolExecutor(max_workers=args.procs) as ex:
        for pid, res in ex.map(one_page, jobs, chunksize=4):
            done += 1
            if "_err" in res:
                print("error", pid, res["_err"])
                continue
            geo[pid].setdefault("l", {}).update(res)
            if done % 250 == 0 or done == len(jobs):
                out.write_text(json.dumps(geo, separators=(",", ":")), encoding="utf-8")
                print(f"{done}/{len(jobs)} pages, {time.time() - t:.0f} s", flush=True)
    out.write_text(json.dumps(geo, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for g in geo.values() for v in g.get("l", {}).values())
    print(f"done: {done} pages, {n} line bands -> {out}")


if __name__ == "__main__":
    main()
