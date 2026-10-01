"""Shared helpers of the machine review ("Maschinelle Prüfung").

The machine review asks language-model subagents to check the graph's entity
links (species -> GBIF, persons -> Wikidata/GND, places -> GeoNames) and the
extracted records of sample entries against the diary text and the scans.
Every decision is keyed the way the reviewer UI keys its own decisions - the
written name form, the entity's authority id, the mention key
``entry_uid|written|occurrence`` - so the results survive a re-extraction with
another ontology or prompt (see docs/validation.md, section 4 and 8).

Scripts (all take the UI payload built by build_payload.py):

    prepare_taxa.py      text batches per taxon entity + contact sheets of doubtful forms
    prepare_persons.py   batches per person with Wikidata and GND candidates
    prepare_places.py    batches per place with GeoNames record, entry anchors, candidates
    prepare_entries.py   dossiers (scan + transcription + graph records) of sample entries
    merge.py             answers -> identities_machine.csv, value_corrections_machine.csv,
                         machine_review.json (UI), report.md
"""
from __future__ import annotations

import base64
import gzip
import io
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

UA = {"User-Agent": "laubmann-kg machine review (research use; totomail.tp@gmail.com)"}


def load_payload(path) -> dict:
    return json.loads(gzip.decompress(base64.b64decode(Path(path).read_text(encoding="utf-8"))))


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_bytes()
    try:
        txt = raw.decode("utf-8").strip()
    except UnicodeDecodeError:          # an agent wrote the Windows codepage
        txt = raw.decode("cp1252").strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError as exc:
        if "Extra data" not in str(exc):
            raise
        return json.JSONDecoder().raw_decode(txt)[0]     # trailing text after the answer


def write_json(path, obj, indent=1) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


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


def written_of(P: dict, sec: str, m) -> str:
    text = P["E"][m[1]][7]
    return text[m[2]:m[3]] if m[2] >= 0 else P[sec]["forms"][m[0]][0]


def context(text: str, s: int, e: int, width: int = 160) -> str:
    if s < 0:
        return text[:2 * width]
    a, b = max(0, s - width), min(len(text), e + width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


def letters(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def same_word(a: str, b: str) -> bool:
    a, b = letters(a), letters(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 3:
        return True
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.88


def known_verdicts(paths) -> dict:
    """Names an earlier machine round already judged, per section: the
    machine_review.json of merge.py (taxon forms with their GBIF key, person
    and place entities by label) and place_readings.json of the second round.
    A later round skips them (``--known``) and checks only new or changed names."""
    known = {"taxon": set(), "taxon_key": set(), "person": set(), "place": set()}
    for path in paths or []:
        d = read_json(path, {}) or {}
        if "taxon" in d or "person" in d or "place" in d:
            for v in (d.get("taxon") or {}).get("form", {}).values():
                if v.get("name"):
                    known["taxon"].add(v["name"].lower())
                    known["taxon_key"].add((v["name"].lower(), str(v.get("key") or "")))
            for sec in ("person", "place"):
                for v in (d.get(sec) or {}).get("ent", {}).values():
                    if v.get("label"):
                        known[sec].add(v["label"].lower())
        else:                                  # place_readings.json: entity -> [readings]
            for items in d.values():
                for r in items if isinstance(items, list) else []:
                    if r.get("written"):
                        known["place"].add(r["written"].lower())
    return known


# ---------------------------------------------------------------- scans
class PageImages:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.by_prefix = {}
        for vol in self.root.glob("Laubmann_*_gemini"):
            pages = vol / "pages"
            first = next(pages.glob("*.png"), None) if pages.is_dir() else None
            if first:
                self.by_prefix[first.name.split("_")[0]] = pages

    def path(self, pid: str) -> Path | None:
        flat = self.root / f"{pid}.jpg"          # a folder of page JPEGs (tools/export_page_images.py)
        if flat.exists():
            return flat
        d = self.by_prefix.get(pid.split("_")[0])
        p = d / f"{pid}.png" if d else None
        return p if p and p.exists() else None


def crop_line(page_png: Path, page_w: int, page_h: int, box, width: int, ctx_lines: float = 1.3) -> Image.Image:
    """The line of ``box`` (PAGE-XML page coordinates) with context above and
    below, the line outlined in orange, resized to ``width``."""
    im = Image.open(page_png).convert("RGB")
    sx, sy = im.width / page_w, im.height / page_h
    x0, y0, x1, y1 = box
    lh = max(24.0, (y1 - y0) / max(1, round((y1 - y0) / 60)))
    top, bot = max(0, y0 - ctx_lines * lh), min(page_h, y1 + ctx_lines * lh)
    c = im.crop((int(x0 * sx), int(top * sy), int(x1 * sx), int(bot * sy)))
    d = ImageDraw.Draw(c)
    d.rectangle([2, int((y0 - top) * sy) - 3, c.width - 3, int((y1 - top) * sy) + 3], outline=(230, 110, 20), width=4)
    return c.resize((width, max(1, int(c.height * width / c.width))))


def contact_sheet(crops: list[tuple[int, Image.Image]], width: int = 1200) -> Image.Image:
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    H = sum(c.height + 46 for _, c in crops) + 20
    sheet = Image.new("RGB", (width, H), "white")
    d = ImageDraw.Draw(sheet)
    y = 10
    for n, c in crops:
        d.rectangle([8, y + 4, 78, y + 52], fill=(30, 58, 95))
        d.text((18, y + 8), f"{n:2d}", fill="white", font=font)
        sheet.paste(c, (85, y))
        y += c.height + 46
        d.line([(85, y - 23), (width - 10, y - 23)], fill=(200, 200, 200), width=2)
    return sheet


def page_jpeg(page_png: Path, max_w: int = 1400, quality: int = 85) -> bytes:
    im = Image.open(page_png).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)
    return out.getvalue()


# ---------------------------------------------------------------- web lookups (cached, polite)
class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.data = read_json(self.path, {}) or {}
        self.dirty = 0

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value
        self.dirty += 1
        if self.dirty >= 25:
            self.flush()

    def flush(self):
        if self.dirty:
            write_json(self.path, self.data, indent=0)
            self.dirty = 0


def get_json(url: str, retries: int = 3, timeout: int = 60):
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def gbif_match(name: str, cache: Cache, rank: str | None = None) -> dict | None:
    """GBIF backbone match of a scientific name within Aves (as the pipeline does)."""
    key = "match:" + name.strip().lower()
    hit = cache.get(key)
    if hit is None:
        q = urllib.parse.urlencode({"name": name.strip(), "kingdom": "Animalia", "class": "Aves", "strict": "false"})
        try:
            hit = get_json("https://api.gbif.org/v1/species/match?" + q)
        except RuntimeError:
            return None
        cache.put(key, hit)
        time.sleep(0.15)
    if not hit or hit.get("matchType") in (None, "NONE"):
        return None
    return hit


def gbif_species(key: str | int, cache: Cache) -> dict | None:
    k = f"species:{key}"
    hit = cache.get(k)
    if hit is None:
        try:
            hit = get_json(f"https://api.gbif.org/v1/species/{key}")
        except RuntimeError:
            return None
        cache.put(k, hit)
        time.sleep(0.15)
    return hit or None


def instructions(path: Path, text: str, **subst) -> None:
    for k, v in subst.items():
        text = text.replace("{" + k + "}", str(v))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
