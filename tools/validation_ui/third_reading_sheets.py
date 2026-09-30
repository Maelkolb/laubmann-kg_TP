"""Contact sheets for a third reading of doubtful taxon mentions by a second model.

Takes the mentions where the Gemini second reading (second_reading.py)
disagrees with the transcription or with the linked taxon, cuts the line of
each from the scan (with a line of context above and below, the line
outlined), and lays them out ten to a sheet with big numbers. A reviewer or a
model reads a sheet and answers per number: what is written at the marked
position, which bird is it. The manifest next to each sheet carries the
mention keys, the transcription, the Gemini reading and the current taxon,
so answers can be joined back (third_reading_merge.py).

    python tools/validation_ui/third_reading_sheets.py payload.b64 second_reading.json \
        --pages "<HistOrniGraph_output>" --out sheets/ [--per-sheet 10] [--limit 0]
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_payload(path: str) -> dict:
    return json.loads(gzip.decompress(base64.b64decode(Path(path).read_text(encoding="utf-8"))))


def letters(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def same_word(a: str, b: str) -> bool:
    a, b = letters(a), letters(b)
    if a == b:
        return True
    if (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 3:
        return True
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.88


def mention_keys(P: dict) -> list[str]:
    occ: dict[str, int] = {}
    keys = []
    for m in P["taxon"]["men"]:
        k = P["E"][m[1]][1] + "|" + P["taxon"]["forms"][m[0]][0].lower()
        n = occ.get(k, 0)
        occ[k] = n + 1
        keys.append(f"{k}|{n}")
    return keys


def select(P: dict, answers: dict, keys: list[str]) -> list[int]:
    """Mentions whose second reading contradicts the transcription word or the taxon."""
    T = P["taxon"]
    out = []
    for i, m in enumerate(T["men"]):
        a = answers.get(keys[i])
        if not a or not a.get("reading") or not (isinstance(m[4], list) and len(m[4]) == 5):
            continue
        f = T["forms"][m[0]]
        ent = T["ent"][f[2]]
        text = P["E"][m[1]][7]
        written = text[m[2]:m[3]] if m[2] >= 0 else f[0]
        differs = False
        if a.get("kind") != "bird":
            differs = True
        elif not a.get("same") and not same_word(a["reading"], written):
            differs = True
        else:
            sci = (a.get("sci") or "").lower().split()
            cur = (ent[1] or "").lower().split()
            if sci and cur and sci[:2] != cur[:2]:
                names = [ent[0]] + list(ent[9])
                if not any(same_word(n, a.get("species_de") or "") for n in names):
                    differs = True
        if differs:
            out.append(i)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("answers", help="second_reading.json")
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", default="sheets")
    ap.add_argument("--per-sheet", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    P = load_payload(args.payload)
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    keys = mention_keys(P)
    sel = select(P, answers, keys)
    if args.limit:
        sel = sel[: args.limit]
    print(len(sel), "mentions for a third reading")
    root = Path(args.pages)
    pages_dir = {}
    for vol in root.glob("Laubmann_*_gemini"):
        first = next((vol / "pages").glob("*.png"), None) if (vol / "pages").is_dir() else None
        if first:
            pages_dir[first.name.split("_")[0]] = vol / "pages"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 34)
        small = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = small = ImageFont.load_default()
    T = P["taxon"]
    W = 1300
    for s in range(0, len(sel), args.per_sheet):
        chunk = sel[s:s + args.per_sheet]
        crops, manifest = [], []
        for n, i in enumerate(chunk, 1):
            m = T["men"][i]
            pidx, x0, y0, x1, y1 = m[4]
            pg = P["PG"][pidx]
            png = pages_dir.get(pg[0].split("_")[0], Path("")) / f"{pg[0]}.png"
            if not png.exists() or not pg[5]:
                continue
            im = Image.open(png).convert("RGB")
            sx, sy = im.width / pg[5], im.height / pg[6]
            lh = max(24.0, (y1 - y0) / max(1, round((y1 - y0) / 60)))
            top, bot = max(0, y0 - 1.3 * lh), min(pg[6], y1 + 1.3 * lh)
            c = im.crop((int(x0 * sx), int(top * sy), int(x1 * sx), int(bot * sy)))
            d = ImageDraw.Draw(c)
            d.rectangle([2, int((y0 - top) * sy) - 3, c.width - 3, int((y1 - top) * sy) + 3], outline=(230, 110, 20), width=4)
            c = c.resize((W - 90, int(c.height * (W - 90) / c.width)))
            crops.append((n, c))
            f = T["forms"][m[0]]
            ent = T["ent"][f[2]]
            e = P["E"][m[1]]
            text = e[7]
            a = answers[keys[i]]
            ctx = text[max(0, m[2] - 120):m[3] + 120] if m[2] >= 0 else text[:240]
            manifest.append({"n": n, "mention": i, "key": keys[i], "entry_id": e[0], "written": text[m[2]:m[3]] if m[2] >= 0 else f[0],
                             "context": ctx, "transcription_taxon": ent[0], "transcription_sci": ent[1],
                             "gemini_reading": a.get("reading"), "gemini_kind": a.get("kind"), "gemini_species": a.get("species_de"),
                             "gemini_sci": a.get("sci"), "gemini_confidence": a.get("confidence")})
        if not crops:
            continue
        H = sum(c.height + 46 for _, c in crops) + 20
        sheet = Image.new("RGB", (W, H), "white")
        y = 10
        d = ImageDraw.Draw(sheet)
        for n, c in crops:
            d.rectangle([8, y + 4, 78, y + 52], fill=(30, 58, 95))
            d.text((18, y + 8), f"{n:2d}", fill="white", font=font)
            sheet.paste(c, (85, y))
            y += c.height + 46
            d.line([(85, y - 23), (W - 10, y - 23)], fill=(200, 200, 200), width=2)
        k = s // args.per_sheet + 1
        sheet.save(out / f"sheet_{k:03d}.png", "PNG", optimize=True)
        (out / f"sheet_{k:03d}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("sheets in", out)


if __name__ == "__main__":
    main()
