"""Check the image and insert regions of the corpus: complete, cut off, duplicated, or no object at all.

The region catalogue (multimodal_regions.jsonl) holds every drawing, map, photograph, mounted object and inserted
text the layout model found. The scanning shows many of them more than once (a fold-out photographed with its page
and again as a whole spread, a clipping on two consecutive scans), and some boxes cut their object off. Regions on
neighbouring scans of a volume are checked together: the model sees every region's crop and the page scans with all
region boxes drawn, and says for each region what it shows, whether it is complete, which other regions show the
same physical object (and which of them shows it best), and which show other parts of it.

    python tools/validation_ui/machine_review/region_check.py --regions data/corpus_patched/multimodal_regions.jsonl \\
        --review data/cache/graph_check/review_quality.json --out data/cache/region_check --model gemini-3.8-flash

Answers: ``<out>/<model>/answers/<cluster>.json`` (resumable; calls cached in data/cache/region_check_v1).
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import write_json  # noqa: E402

PRICES = {"gemini-3.7-flash": (0.75, 3.75, 0.075), "gemini-3.8-flash": (0.75, 3.75, 0.075)}
MARKER = "\n## Regions\n"
WINDOW, OVERLAP = 8, 2

INSTRUCTIONS = """# Image and insert regions of a diary

The field diaries of the ornithologist Alfred Laubmann (Bavaria, 1917–1965) were scanned page by page. A layout model
cut out every region that is not handwritten body text: drawings, maps, photographs, mounted objects (feathers,
labels, tickets), and inserted texts (letters, newspaper clippings, typed reports, printed lists). The scanning shows
many objects more than once: a fold-out map photographed with its page and again opened as a whole spread, a clipping
visible on two consecutive scans, a page scanned twice. Some boxes cut their object off.

You get the crops of a few regions from neighbouring scans of one volume, labelled R1, R2, …, and the page scans they
were cut from, labelled P1, P2, …, with every region's box drawn and labelled. For each region decide:

- `content`: "object" (a drawing, map, photograph, mounted object, printed image), "text" (an inserted letter,
  clipping, typed or printed text), "blank" (empty paper, a scanner background, nothing to see) or "fragment" (a
  sliver or piece too small to show anything on its own).
- `complete`: true when the crop shows the whole object; false when it is cut off. Then `cut` lists the sides
  ("top", "bottom", "left", "right") and `cause` says why: "page_edge" (the object continues beyond the scanned page,
  e.g. a fold-out or an insert sticking out) or "box" (the page shows more of the object than the box took).
- `same_as`: the other regions that show the same physical object or a part of it that overlaps with this crop
  (the same map, the same clipping, the same photograph, also when one crop shows only part of the other). Different
  objects that merely look alike (two different maps, two photographs of one place) are not the same.
- `parts_of`: the other regions that show other, non-overlapping parts of the same object (page 1 and page 2 of one
  letter, the two halves of a map split over two pages).
- `best`: among regions that are the same object, exactly one is best: the one that shows the object most completely,
  then the larger and sharper one. A region that is the same as no other region is best unless it is blank or a
  fragment.
- `box`: only when `cause` is "box": the box that would hold the whole object on its page scan, as
  [x0, y0, x1, y1] in thousandths of the page width and height.
- `c`: your confidence, 0.0–1.0, and `why`: a few words.

Judge from the images; the layout descriptions given with the regions can be wrong.

## Answer

One JSON object, nothing else:
{"regions": [{"id": "R1", "content": "object", "complete": true, "cut": [], "cause": null, "same_as": [], "parts_of": [],
  "best": true, "box": null, "c": 0.9, "why": "..."}]}
Every region appears exactly once.
"""


def load_regions(path: Path) -> list[dict]:
    out = []
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if r.get("entry_uid"):
            out.append(r)
    return out


def scan_number(r: dict) -> int:
    try:
        return int(r["scan"])
    except (TypeError, ValueError):
        return -1


def clusters(regions: list[dict]) -> list[list[dict]]:
    """Regions of one volume on scans at most one apart; long runs split into overlapping windows."""
    by_volume = collections.defaultdict(list)
    for r in regions:
        by_volume[r["volume"]].append(r)
    runs = []
    for vol in sorted(by_volume):
        rs = sorted(by_volume[vol], key=lambda r: (scan_number(r), r["page_id"], int(r.get("reading_order") or 0)))
        run = [rs[0]]
        for r in rs[1:]:
            if scan_number(r) - scan_number(run[-1]) <= 1:
                run.append(r)
            else:
                runs.append(run)
                run = [r]
        runs.append(run)
    out = []
    for run in runs:
        if len(run) <= WINDOW:
            out.append(run)
            continue
        start = 0
        while start < len(run):
            out.append(run[start:start + WINDOW])
            if start + WINDOW >= len(run):
                break
            start += WINDOW - OVERLAP
    return out


def boxes_by_region(review_path: Path) -> dict:
    rv = json.loads(review_path.read_text(encoding="utf-8"))
    pages = rv["pages"]
    out = {}
    for e in rv["entries"].values():
        for m in e.get("media", []):
            if len(m) >= 7:
                out[m[0]] = (pages[m[2]][0], m[3:7])
    return out


def jpeg(img: Image.Image, longest: int) -> bytes:
    img = img.convert("RGB")
    scale = longest / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def page_with_boxes(path: Path, marks: list[tuple[str, list[float]]]) -> bytes:
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    width = max(3, round(min(w, h) / 250))
    try:
        font = ImageFont.truetype("arial.ttf", max(28, round(h / 40)))
    except OSError:
        font = ImageFont.load_default()
    for label, (x0, y0, x1, y1) in marks:
        box = [x0 * w, y0 * h, x1 * w, y1 * h]
        draw.rectangle(box, outline=(220, 30, 30), width=width)
        draw.rectangle([box[0], box[1], box[0] + font.size * 1.6, box[1] + font.size * 1.2], fill=(220, 30, 30))
        draw.text((box[0] + 4, box[1] + 2), label, fill=(255, 255, 255), font=font)
    return jpeg(img, 1400)


def cluster_id(cluster: list[dict]) -> str:
    first, last = cluster[0], cluster[-1]
    return f"v{int(first['volume']):02d}_s{scan_number(first):04d}_{first['region_uid'][2:8]}_{last['region_uid'][2:8]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", default=str(REPO / "data" / "corpus_patched" / "multimodal_regions.jsonl"))
    ap.add_argument("--review", required=True, help="review.json of the graph pages (region boxes)")
    ap.add_argument("--crops", default=str(REPO / "data" / "region_crops"))
    ap.add_argument("--pages", default=str(REPO / "data" / "pages_jpg"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--cache", default=str(REPO / "data" / "cache" / "region_check_v1"))
    ap.add_argument("--budget", type=float, default=15.0)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None, help="file with cluster ids or region uids")
    args = ap.parse_args()

    from laubmann_kg.env import load_dotenv
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.structured_output import extract_json

    work = Path(args.out) / args.model / "answers"
    work.mkdir(parents=True, exist_ok=True)
    regions = load_regions(Path(args.regions))
    boxes = boxes_by_region(Path(args.review))
    groups = clusters(regions)
    only = set(Path(args.only).read_text(encoding="utf-8").split()) if args.only else None
    load_dotenv(REPO / ".env")
    client = build_client(cache=LLMCache(Path(args.cache)), config={
        "backend": "google", "model": args.model, "api_key_env": "GOOGLE_API_KEY", "temperature": 0.0,
        "max_output_tokens": 16384, "timeout": 600, "thinking_level": "low", "context_cache": True,
        "context_cache_marker": MARKER, "media_resolution": "MEDIA_RESOLUTION_HIGH", "retry_attempts": 3, "retry_backoff": 2.0})
    p_in, p_out, p_cached = PRICES.get(args.model, PRICES["gemini-3.8-flash"])
    spent = [0.0]
    lock = threading.Lock()

    jobs = []
    for g in groups:
        cid = cluster_id(g)
        if only is not None and cid not in only and not any(r["region_uid"] in only for r in g):
            continue
        out = work / f"{cid}.json"
        if not out.exists():
            jobs.append((cid, g, out))
        if args.limit and len(jobs) >= args.limit:
            break
    print(f"{len(groups)} clusters, {len(jobs)} to check", flush=True)

    def one(job):
        cid, group, out = job
        with lock:
            if spent[0] >= args.budget:
                return "budget"
        labels = {r["region_uid"]: f"R{i}" for i, r in enumerate(group, 1)}
        page_ids = []
        for r in group:
            pid = boxes.get(r["region_uid"], (r["page_id"],))[0]
            if pid not in page_ids:
                page_ids.append(pid)
        page_label = {pid: f"P{i}" for i, pid in enumerate(page_ids, 1)}
        images, lines = [], []
        for r in group:
            crop = Path(args.crops) / f"{r['region_uid']}.jpg"
            if crop.exists():
                images.append((labels[r["region_uid"]], jpeg(Image.open(crop), 900)))
            pid = boxes.get(r["region_uid"], (r["page_id"],))[0]
            lines.append(json.dumps({"id": labels[r["region_uid"]], "page": page_label[pid], "scan": r.get("scan"),
                                     "layout": r.get("kind"), "has_crop": crop.exists(), "box_known": r["region_uid"] in boxes,
                                     "layout_description": (r.get("description") or "")[:160]}, ensure_ascii=False))
        for pid in page_ids:
            path = Path(args.pages) / f"{pid}.jpg"
            if path.exists():
                marks = [(labels[u], b[1]) for u, b in boxes.items() if b[0] == pid and u in labels]
                images.append((page_label[pid], page_with_boxes(path, marks)))
        prompt = (INSTRUCTIONS + MARKER + "Images in this order: the crops " + ", ".join(lab for lab, _ in images if lab.startswith("R"))
                  + ", then the page scans " + ", ".join(lab for lab, _ in images if lab.startswith("P")) + ".\n\n" + "\n".join(lines))
        try:
            raw = client.complete(prompt, images=[(lab, data) for lab, data in images])
        except Exception as exc:  # noqa: BLE001 - one failed cluster must not stop the run
            return f"error {str(exc)[:160]}"
        inner = getattr(client, "client", client)
        u = inner.last_usage() if hasattr(inner, "last_usage") else None
        if u:
            cached = u.get("cached_content_token_count", 0)
            cost = ((u.get("prompt_token_count", 0) - cached) * p_in + cached * p_cached
                    + (u.get("candidates_token_count", 0) + u.get("thoughts_token_count", 0)) * p_out) / 1e6
            with lock:
                spent[0] += cost
        try:
            data = extract_json(raw)
        except Exception:  # noqa: BLE001
            data = None
        write_json(out, {"cluster": cid, "model": args.model, "regions": {labels[r["region_uid"]]: r["region_uid"] for r in group},
                         "pages": page_label, "answer": data if isinstance(data, dict) else None})
        return "ok" if isinstance(data, dict) else "unparseable"

    results = collections.Counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for i, (job, r) in enumerate(zip(jobs, pool.map(one, jobs)), 1):
            results[r.split(" ")[0]] += 1
            if not r.startswith(("ok", "budget")):
                print(job[0], r, flush=True)
            if i % 50 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] {dict(results)} estimated spend ${spent[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
