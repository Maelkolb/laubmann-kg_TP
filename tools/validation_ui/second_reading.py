"""Model second reading of doubtful taxon mentions for the validation UI.

For every mention of a doubtful species name (evidence class C = unattested,
and rare L/B names), the line of the scan is cut out (region box from the
PAGE-XML, line from the transcription, the line outlined), sent to Gemini with
the transcribed context, and the model is asked what is actually written there
and which bird (if any) it names. The UI shows the answer as a suggestion that
the reviewer accepts with one key (reading correction + species) or ignores.

    python tools/validation_ui/second_reading.py payload.b64 --pages "<HistOrniGraph_output>" \
        --out second_reading.json [--limit 40] [--concurrency 8]

Resumable: answers are cached by mention key (entry_uid|name|occurrence) in the
output file; failed calls are retried on the next run. Needs GOOGLE_API_KEY (or
--key-file) and the page PNGs (Drive for desktop).
"""
from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

PROMPT = """Du siehst einen Ausschnitt aus Alfred Laubmanns handschriftlichem ornithologischem Tagebuch (deutsch, 1917–1965).
Die orange umrandete Zeile wurde maschinell transkribiert. Der transkribierte Text um die Stelle lautet:
«{context}»
An der Stelle steht in der Transkription «{written}». Ein Sprachmodell hat daraus „{label}“{sci} gemacht.

Aufgabe:
1. Lies im Bild genau, was an dieser Stelle geschrieben steht: nur das Wort oder die Wortgruppe, die «{written}» entspricht (in der Schreibweise des Tagebuchs, mit Flexion).
2. Entscheide, was das Gelesene bezeichnet: eine Vogelart oder -gruppe, ein anderes Tier, einen Ort, eine Person oder etwas anderes.
3. Wenn es ein Vogel ist: der heute übliche deutsche Artname und der wissenschaftliche Name (Art, sonst Gattung oder Familie).

Antworte nur mit JSON:
{{"reading": "...", "same_as_transcription": true, "kind": "bird|other_animal|place|person|other", "species_de": "..." oder null, "scientific_name": "..." oder null, "confidence": 0.0, "note": "kurze Begründung auf Deutsch"}}
confidence: wie sicher du beim Lesen UND beim Bestimmen bist (0 bis 1). Wenn die Stelle im Bild nicht zu finden oder unleserlich ist: reading = null, confidence = 0."""


def load_payload(path: str) -> dict:
    return json.loads(gzip.decompress(base64.b64decode(Path(path).read_text(encoding="utf-8"))))


def mention_keys(P: dict, sec: str = "taxon") -> list[str]:
    """Stable mention keys, computed exactly as the UI does (entry_uid|name|occurrence)."""
    occ: dict[str, int] = {}
    keys = []
    for m in P[sec]["men"]:
        name = P[sec]["forms"][m[0]][0].lower()
        k = P["E"][m[1]][1] + "|" + name
        n = occ.get(k, 0)
        occ[k] = n + 1
        keys.append(f"{k}|{n}")
    return keys


class PageImages:
    def __init__(self, root: Path):
        self.root = root
        self.by_prefix = {}
        for vol in root.glob("Laubmann_*_gemini"):
            pages = vol / "pages"
            first = next(pages.glob("*.png"), None) if pages.is_dir() else None
            if first:
                self.by_prefix[first.name.split("_")[0]] = pages
        self.lock = threading.Lock()

    def path(self, pid: str) -> Path | None:
        d = self.by_prefix.get(pid.split("_")[0])
        p = d / f"{pid}.png" if d else None
        return p if p and p.exists() else None


def crop(page_png: Path, page_w: int, page_h: int, box, max_w: int = 1400) -> bytes:
    """The line of ``box`` (page coordinates of the PAGE-XML) with ~1.5 lines of
    context above and below, the line outlined in orange; JPEG bytes."""
    im = Image.open(page_png).convert("RGB")
    sx, sy = im.width / page_w, im.height / page_h
    x0, y0, x1, y1 = box
    lh = max(24.0, (y1 - y0) / max(1, round((y1 - y0) / 60)))
    top, bot = max(0, y0 - 1.6 * lh), min(page_h, y1 + 1.6 * lh)
    c = im.crop((int(x0 * sx), int(top * sy), int(x1 * sx), int(bot * sy)))
    d = ImageDraw.Draw(c)
    d.rectangle([2, int((y0 - top) * sy) - 3, c.width - 3, int((y1 - top) * sy) + 3], outline=(230, 110, 20), width=3)
    if c.width > max_w:
        c = c.resize((max_w, int(c.height * max_w / c.width)))
    out = io.BytesIO()
    c.save(out, "JPEG", quality=88)
    return out.getvalue()


def context(text: str, s: int, e: int, width: int = 160) -> str:
    if s < 0:
        return text[:2 * width]
    a, b = max(0, s - width), min(len(text), e + width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


def parse(raw: str) -> dict | None:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    return d if isinstance(d, dict) else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("--pages", required=True, help="folder with Laubmann_XX_gemini/pages/*.png")
    ap.add_argument("--out", default="second_reading.json")
    ap.add_argument("--classes", default="C", help="evidence classes read for every mention (default C)")
    ap.add_argument("--rare-classes", default="L,B", help="classes read only for rare names")
    ap.add_argument("--rare-max", type=int, default=3, help="a rare name has at most this many mentions")
    ap.add_argument("--limit", type=int, default=0, help="read at most this many uncached mentions (0 = all)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--key-file", default=None)
    ap.add_argument("--thinking", default="low", help="Gemini thinking level (minimal|low|medium|high)")
    args = ap.parse_args()

    from google import genai
    from google.genai import types
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if args.key_file:
        key = Path(args.key_file).read_text(encoding="utf-8").strip()
    if not key:
        sys.exit("no API key (GOOGLE_API_KEY or --key-file)")
    client = genai.Client(api_key=key)
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2, max_output_tokens=4096,
                                         thinking_config=types.ThinkingConfig(thinking_level=args.thinking))

    P = load_payload(args.payload)
    T = P["taxon"]
    keys = mention_keys(P)
    full = set(args.classes.split(","))
    rare = set(args.rare_classes.split(",")) if args.rare_classes else set()
    todo = []
    for i, m in enumerate(T["men"]):
        f = T["forms"][m[0]]
        cls = f[3]
        if not (cls in full or (cls in rare and f[1] <= args.rare_max)):
            continue
        if not (isinstance(m[4], list) and len(m[4]) == 5):
            continue
        todo.append(i)
    out_path = Path(args.out)
    cache = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    todo = [i for i in todo if keys[i] not in cache]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} mentions to read ({len(cache)} cached)", flush=True)
    pages = PageImages(Path(args.pages))
    lock = threading.Lock()
    usage = {"in": 0, "out": 0, "calls": 0, "failed": 0}

    def work(i: int):
        m = T["men"][i]
        f = T["forms"][m[0]]
        ent = T["ent"][f[2]]
        pidx, x0, y0, x1, y1 = m[4]
        pg = P["PG"][pidx]
        png = pages.path(pg[0])
        if png is None or not pg[5]:
            return
        img = crop(png, pg[5], pg[6], (x0, y0, x1, y1))
        e = P["E"][m[1]]
        prompt = PROMPT.format(context=context(e[7], m[2], m[3]), written=f[0], label=ent[0],
                               sci=f" ({ent[1]})" if ent[1] else "")
        for attempt in range(3):
            try:
                r = client.models.generate_content(model=args.model, config=config,
                                                   contents=[types.Part.from_bytes(data=img, mime_type="image/jpeg"), prompt])
                d = parse(r.text)
                if d is None:
                    raise ValueError("unparseable: " + (r.text or "")[:120])
                um = r.usage_metadata
                with lock:
                    usage["calls"] += 1
                    usage["in"] += (um.prompt_token_count or 0) if um else 0
                    usage["out"] += ((um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)) if um else 0
                    cache[keys[i]] = {"reading": d.get("reading"), "same": bool(d.get("same_as_transcription")),
                                      "kind": d.get("kind"), "species_de": d.get("species_de"),
                                      "sci": d.get("scientific_name"), "confidence": d.get("confidence"),
                                      "note": d.get("note"), "model": args.model}
                return
            except Exception as exc:  # noqa: BLE001 - retried, then left uncached
                err = str(exc)
                time.sleep(2 * (attempt + 1))
        with lock:
            usage["failed"] += 1
        print("failed", keys[i], err[:160], flush=True)

    def flush():
        tmp = out_path.with_suffix(".tmp")
        with lock:
            tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(out_path)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for n, _ in enumerate(pool.map(work, todo), 1):
            if n % 50 == 0:
                flush()
                print(f"{n}/{len(todo)} · {time.time() - t0:.0f} s · tokens in {usage['in']:,} out {usage['out']:,}", flush=True)
    flush()
    print(f"done: {usage['calls']} calls, {usage['failed']} failed, tokens in {usage['in']:,} / out+thinking {usage['out']:,}, "
          f"{time.time() - t0:.0f} s -> {out_path} ({len(cache)} answers)")


if __name__ == "__main__":
    main()
