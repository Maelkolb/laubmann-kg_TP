"""Place linking: coordinates, GeoNames ids and Wikidata items for the diary's
places (``lkg:Place``), from three sources that cross-check each other:

1. **Nominatim / OpenStreetMap** — from a pre-warmed cache
   (``tools/prewarm_nominatim.py``; the pipeline calls Nominatim live only when
   ``linking.places.nominatim.live`` is set, at 1 request / 1.1 s). OSM knows
   the forests, moors, lakes and hamlets the diarist names; the hit's
   ``extratags.wikidata`` gives a Wikidata item for free.
2. **GeoNames** — the country dumps (DE, AT, CH, IT, FR, GR, … under
   ``linking_cache/geonames/``, downloaded once), indexed by folded name and
   alternate names. A GeoNames record within ``max_km`` of the Nominatim point
   with the same name confirms the location and supplies the GeoNames id
   (``owl:sameAs https://sws.geonames.org/<id>/``); without a Nominatim hit a
   record that is unique in Bavaria (or in the corpus's home region) is taken
   with lower confidence.
3. **Wikidata** — QIDs for GeoNames ids (P1566) in batches, cached, when
   Nominatim had none.

Every label lands in ``review/place_link_review.csv`` (label, uses, kind,
source, GeoNames id/name/feature, lat/lon, QID, confidence, status
linked | review | no_match, decision); ``reviewed_csv`` rows with an accepted
decision override. Coordinates come with ``dwc:coordinateUncertaintyInMeters``
derived from the feature type (a town centroid is not a point).

Labels that cannot be a gazetteer entry are skipped up front: prepositional
fragments ("an der Halde bei Hirschzell"), generic nouns ("Wald", "See"),
micro-localities (Garten, Fenster, Nistkasten), anything with digits/brackets.

**Entry context.** The diaries are spatially coherent: a place named in an
entry lies near the other places of that entry (Tutzing, Pöcking and the
Maisinger See; Korfu and Brindisi). After a first pass the strong links
(OSM + GeoNames agree) give every label a context centroid from the entries
it shares with them; the second pass uses it to pick among same-name
candidates ("Bernried" am Starnberger See, not the one near Deggendorf), to
confirm weak OSM hits (a track named "Maisinger Schlucht", an information
board "Wollmatinger Ried") and to demote hits far from every context (a
"Tafelberg" 90 km from the entries that mention it → review).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.model import Place
from laubmann_kg.linking import review
from laubmann_kg.linking.cache import JsonCache
from laubmann_kg.linking.http import USER_AGENT

logger = logging.getLogger(__name__)

PLACE_REVIEW_FIELDS = ["place_name", "n_uses", "kind", "status", "source", "lat", "lon", "uncertainty_m",
                       "geonames_id", "geonames_name", "feature", "country", "admin1", "qid", "osm",
                       "confidence", "note", "decision"]
GEONAMES_DUMP = "https://download.geonames.org/export/dump/{cc}.zip"
GEONAMES_IRI = "https://sws.geonames.org/{id}/"
WIKIDATA_ENTITY_NS = "http://www.wikidata.org/entity/"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
DEFAULT_COUNTRIES = ("DE", "AT", "CH", "IT", "FR", "GR", "HR", "SI", "CZ", "NL", "BE", "LI", "DK", "SE", "NO", "PL", "HU", "GB", "ES")
# Bavaria-ish bias box for Nominatim (left, top, right, bottom) and the "home" test
VIEWBOX = "8.5,50.8,14.2,47.0"
HOME = {"cc": "DE", "admin1": "02"}           # GeoNames admin1 code of Bayern

# --------------------------------------------------------------------------
# label filter
# --------------------------------------------------------------------------
_PREP_RE = re.compile(r"^(bei|beim|an|am|auf|im|in|hinter|vor|unter|über|zwischen|nahe|unweit|entlang|längs|gegen|ober|"
                      r"unterhalb|oberhalb|mit|nach|von|vom|zum|zur|zu|der|die|das|den|dem|des|ein|eine|einem|um|bis|durch|aus)\b",
                      re.IGNORECASE)
_MICRO_RE = re.compile(r"(garten|fenster|zimmer|terrasse|balkon|nistkasten|futterplatz|futterhaus|käfig|voliere|areal|"
                       r"vkl\.|k\d|w/\d|\bhaus\b|wohnung|dach|hof\b|straße|strasse|platz\b|weg\b|ecke\b)", re.IGNORECASE)
_GENERIC = {"see", "forst", "wald", "berg", "tal", "au", "auen", "moos", "moor", "heide", "insel", "bach", "fluss", "fluß",
            "weiher", "teich", "ort", "dorf", "stadt", "wiese", "wiesen", "feld", "felder", "alm", "alpe", "halde", "halbinsel",
            "park", "anlagen", "friedhof", "kirche", "schloss", "schloß", "bahnhof", "brücke", "mühle", "turm", "ufer",
            "frühling", "sommer", "herbst", "winter", "holz", "graben", "kanal", "küste", "strand", "hafen", "becken",
            "westbecken", "ostbecken", "nordbecken", "südbecken", "speichersee", "stausee", "damm", "wehr", "schleuse",
            "nord", "süd", "ost", "west", "wb", "ob", "sb", "nb", "stadt", "land", "umgebung", "gegend", "heim", "zoo", "tierpark",
            "isarauen", "ried", "filz", "schilf", "röhricht", "e werk", "ewerk", "kraftwerk", "forsthaus", "fischteich",
            "fischteiche", "kiesinsel", "kiesbank", "querdamm", "norddamm", "suddamm", "westdamm", "ostdamm", "vorfluter",
            "klaeranlage", "klaranlage", "teichgebiet", "gebiet", "revier", "jagdrevier", "schlucht", "hang", "wand", "grube",
            "kiesgrube", "lehmgrube", "steinbruch", "baggersee", "altwasser", "weiherkette", "moorgebiet"}


def fold(label: str) -> str:
    s = unicodedata.normalize("NFKD", (label or "").strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ß", "ss").replace("æ", "ae").replace("ø", "o")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def geocodable(label: str) -> bool:
    """Could this label be a gazetteer entry at all?"""
    label = (label or "").strip()
    if not label or len(label) < 3 or len(label) > 40 or len(label.split()) > 4:
        return False
    if _PREP_RE.match(label) or _MICRO_RE.search(label):
        return False
    if re.search(r"[\d()\[\]/?!;:]", label):
        return False
    if not label[:1].isupper():
        return False
    if fold(label) in _GENERIC or fold(label).replace(" ", "") in _GENERIC:
        return False
    return True


# --------------------------------------------------------------------------
# Nominatim
# --------------------------------------------------------------------------
class NominatimClient:
    """Cached Nominatim search (cache = {label: [hits]}); live calls are
    rate-limited (1.1 s) and carry the contact UA the usage policy asks for."""

    def __init__(self, cache_path: Path, email: str = "", live: bool = False, sleep_s: float = 1.1) -> None:
        self.path = Path(cache_path)
        self.cache: dict = {}
        if self.path.exists():
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        self.live = live
        self.sleep_s = sleep_s
        self.email = email
        self._pending = 0
        self._last = 0.0

    def search(self, label: str) -> Optional[list]:
        """Hits for ``label``; None = unknown (not cached, not live)."""
        if label in self.cache:
            return self.cache[label]
        if not self.live:
            return None
        wait = self.sleep_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        params = {"q": label, "format": "jsonv2", "limit": 5, "extratags": 1, "namedetails": 1,
                  "accept-language": "de", "viewbox": VIEWBOX}
        if self.email:
            params["email"] = self.email
        req = urllib.request.Request(NOMINATIM + "?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": USER_AGENT})
        self._last = time.time()
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                hits = json.load(r)
        except Exception as exc:  # noqa: BLE001
            logger.warning("nominatim %r failed: %s", label, exc)
            return None
        keep = [{k: h.get(k) for k in ("osm_type", "osm_id", "lat", "lon", "category", "type", "place_rank",
                                         "importance", "name", "display_name", "addresstype")}
                | {"wikidata": (h.get("extratags") or {}).get("wikidata"),
                   "name_de": (h.get("namedetails") or {}).get("name:de")} for h in hits]
        self.cache[label] = keep
        self._pending += 1
        if self._pending >= 25:
            self.flush()
        return keep

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        self._pending = 0


# --------------------------------------------------------------------------
# GeoNames
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class GeoRecord:
    id: int
    name: str
    fclass: str
    fcode: str
    cc: str
    admin1: str
    lat: float
    lon: float
    population: int


class GeoNamesIndex:
    """Folded name -> GeoNames records, from the country dumps (downloaded into
    ``directory`` once; a pickle of the index is kept next to them)."""

    def __init__(self, directory: Path, countries=DEFAULT_COUNTRIES, download: bool = True) -> None:
        self.dir = Path(directory)
        self.countries = tuple(countries)
        self.index: dict[str, list[GeoRecord]] = defaultdict(list)
        self.primary: dict[str, set[int]] = defaultdict(set)     # folded key -> ids matched on name/asciiname (not an alternate)
        self.loaded: list[str] = []
        self._load(download)

    def _load(self, download: bool) -> None:
        import pickle
        pkl = self.dir / ("geonames_index2_" + "_".join(self.countries) + ".pkl")
        if pkl.exists():
            self.index, self.primary, self.loaded = pickle.load(pkl.open("rb"))
            return
        for cc in self.countries:
            path = self.dir / f"{cc}.zip"
            if not path.exists():
                if not download:
                    continue
                try:
                    self.dir.mkdir(parents=True, exist_ok=True)
                    req = urllib.request.Request(GEONAMES_DUMP.format(cc=cc), headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=600) as r:
                        path.write_bytes(r.read())
                except Exception as exc:  # noqa: BLE001
                    logger.warning("geonames dump %s not available: %s", cc, exc)
                    continue
            self._index_zip(path, cc)
            self.loaded.append(cc)
        if self.loaded:
            pickle.dump((dict(self.index), dict(self.primary), self.loaded), pkl.open("wb"))

    def _index_zip(self, path: Path, cc: str) -> None:
        with zipfile.ZipFile(path) as z:
            with z.open(f"{cc}.txt") as fh:
                for line in io.TextIOWrapper(fh, encoding="utf-8"):
                    p = line.rstrip("\n").split("\t")
                    if len(p) < 15:
                        continue
                    fclass = p[6]
                    if fclass in ("R", "S") and p[7] not in ("RSTN", "CSTL", "MNMT", "ZOO", "PRK", "GDN", "AIRP", "BDG", "HTL", "MUS"):
                        continue          # roads/spots are noise for a gazetteer match
                    rec = GeoRecord(int(p[0]), p[1], fclass, p[7], p[8], p[10], float(p[4]), float(p[5]), int(p[14] or 0))
                    prim = {fold(p[1]), fold(p[2])}
                    keys = set(prim)
                    for alt in (p[3].split(",") if p[3] else []):
                        if alt and len(alt) < 60:
                            keys.add(fold(alt))
                    for k in keys:
                        if k:
                            self.index[k].append(rec)
                            if k in prim:
                                self.primary[k].add(rec.id)

    def lookup(self, label: str) -> list[GeoRecord]:
        return list(self.index.get(fold(label), []))

    def is_primary(self, label: str, rec: GeoRecord) -> bool:
        return rec.id in self.primary.get(fold(label), ())


# --------------------------------------------------------------------------
# Wikidata (GeoNames id -> QID)
# --------------------------------------------------------------------------
def wikidata_qids_for_geonames(ids: list[int], cache: JsonCache, offline: bool, sleep_s: float = 2.0) -> dict[int, str]:
    out: dict[int, str] = {}
    todo = []
    for i in ids:
        hit = cache.get(f"gn:{i}")
        if hit is not None:
            if hit:
                out[i] = hit
        else:
            todo.append(i)
    if offline or not todo:
        return out
    for start in range(0, len(todo), 100):
        batch = todo[start:start + 100]
        values = " ".join(f'"{i}"' for i in batch)
        query = f"SELECT ?gn ?item WHERE {{ VALUES ?gn {{ {values} }} ?item wdt:P1566 ?gn }}"
        req = urllib.request.Request("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": query}),
                                     headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wikidata P1566 batch failed: %s", exc)
            time.sleep(sleep_s * 3)
            continue
        found = {}
        for b in data["results"]["bindings"]:
            found[int(b["gn"]["value"])] = b["item"]["value"].rsplit("/", 1)[-1]
        for i in batch:
            cache.put(f"gn:{i}", found.get(i, ""))
            if i in found:
                out[i] = found[i]
        time.sleep(sleep_s)
    return out


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
# OSM hits by (category, type): strong = a place/natural feature; weak = a
# named thing that only stands for the place (station, track, board, pub) —
# accepted when the entry context confirms it; bad = never
_OSM_STRONG_CATEGORIES = {"place", "natural", "waterway", "water", "mountain_pass"}
_OSM_STRONG = {("boundary", "administrative"), ("boundary", "protected_area"), ("boundary", "national_park"),
               ("leisure", "nature_reserve"), ("leisure", "park"), ("leisure", "garden"), ("landuse", "reservoir"),
               ("landuse", "forest"), ("landuse", "meadow"), ("landuse", "basin"), ("landuse", "salt_pond"),
               ("landuse", "quarry"), ("landuse", "village_green"), ("landuse", "allotments"), ("landuse", "cemetery"),
               ("landuse", "orchard"), ("landuse", "farmyard"), ("natural", "water"), ("tourism", "zoo"), ("tourism", "viewpoint"),
               ("historic", "castle"), ("historic", "monastery"), ("man_made", "reservoir_covered"), ("aeroway", "aerodrome")}
_OSM_WEAK_CATEGORIES = {"railway", "historic", "man_made", "tourism", "amenity", "aeroway", "building", "shop", "craft", "office",
                        "information", "emergency", "club"}
_OSM_WEAK = {("highway", "track"), ("highway", "path"), ("highway", "footway"), ("highway", "bridleway"), ("highway", "pedestrian"),
             ("landuse", "residential"), ("landuse", "industrial"), ("landuse", "farmland"), ("landuse", "grass"), ("landuse", "landfill"),
             ("leisure", "pitch"), ("leisure", "playground"), ("leisure", "sports_centre"), ("power", "plant")}
# uncertainty radius (m) by GeoNames feature code / OSM type: a centroid is not a point
_UNCERT_GN = {"PPLC": 5000, "PPLA": 5000, "PPLA2": 3000, "PPLA3": 2000, "PPLA4": 2000, "PPL": 1500, "PPLX": 1000,
              "PPLL": 800, "PPLF": 800, "PPLH": 1500, "PPLQ": 1500, "LK": 1000, "LKS": 1000, "RSV": 1000, "PND": 500,
              "STM": 3000, "STMI": 2000, "CNL": 2000, "FRST": 1500, "WOOD": 1000, "MOOR": 1500, "SWMP": 1000, "MRSH": 1000,
              "MT": 500, "MTS": 5000, "PK": 300, "HLL": 500, "RDGE": 2000, "VAL": 5000, "ISL": 2000, "PRK": 800,
              "ADM1": 50000, "ADM2": 20000, "ADM3": 8000, "ADM4": 3000, "RGN": 20000, "AREA": 10000, "RSTN": 300, "ZOO": 500,
              "CSTL": 200, "MNMT": 100, "GDN": 500, "AIRP": 1500, "BDG": 100, "HTL": 100, "MUS": 100}
_UNCERT_OSM = {"city": 5000, "town": 2000, "village": 1000, "hamlet": 500, "suburb": 1000, "neighbourhood": 500,
               "isolated_dwelling": 300, "locality": 500, "municipality": 3000, "administrative": 3000, "water": 1000,
               "lake": 1000, "reservoir": 1000, "river": 3000, "stream": 1500, "wood": 1000, "forest": 1500, "wetland": 1000,
               "peak": 300, "ridge": 2000, "valley": 5000, "island": 2000, "park": 800, "nature_reserve": 1500, "protected_area": 1500,
               "region": 20000, "county": 20000, "state": 50000, "bay": 2000, "beach": 500, "station": 200, "zoo": 500, "castle": 200,
               "track": 500, "path": 500, "footway": 300, "information": 500, "biergarten": 100, "restaurant": 100}
# GeoNames feature classes that fit an OSM hit: settlement-ish hits want populated places, natural hits want H/T/V/L
_GN_PREF_SETTLEMENT = {"P": 0, "A": 1, "S": 2, "L": 3, "H": 4, "T": 4, "V": 4}
_GN_PREF_NATURAL = {"H": 0, "T": 0, "V": 0, "L": 0, "S": 2, "P": 3, "A": 4}
_STOP_TOKENS = {"naturschutzgebiet", "nsg", "landschaftsschutzgebiet", "schloss", "schlosspark", "bei", "am", "an", "der", "die",
                "das", "im", "in", "und", "ehem", "ehemalige", "ehemaliger", "gemeinde", "stadt", "markt", "ortsteil"}


def _km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _stem(tok: str) -> str:
    # German adjectival place forms: Ismaninger -> Ismaning, Nymphenburger -> Nymphenburg, Maisinger -> Maising
    if len(tok) > 5 and tok.endswith("er"):
        return tok[:-2]
    return tok


def _tokens(s: str) -> set[str]:
    return {_stem(x) for x in fold(s).split() if x and x not in _STOP_TOKENS}


def _osm_name_matches(label: str, hit: dict) -> bool:
    f = fold(label)
    cands = [c for c in (hit.get("name_de"), hit.get("name"), (hit.get("display_name") or "").split(",")[0]) if c]
    for cand in cands:
        if fold(cand) == f:
            return True
    lt = _tokens(label)
    if not lt:
        return False
    for cand in cands:
        ct = _tokens(cand)
        # "Maisinger See" ⊆ "Maisinger See (Naturschutzgebiet)"; "Hagnau" ⊆ "Hagnau am Bodensee"; "Nymphenburger Schlosspark" == "Schlosspark Nymphenburg"
        if lt <= ct and len(ct) <= len(lt) + 2:
            return True
    return False


def _osm_tier(hit: dict) -> Optional[str]:
    """strong | weak | None (never)."""
    cat, typ = hit.get("category"), hit.get("type")
    if cat in _OSM_STRONG_CATEGORIES or (cat, typ) in _OSM_STRONG:
        return "strong"
    if (cat, typ) in _OSM_WEAK or cat in _OSM_WEAK_CATEGORIES:
        return "weak"
    return None


def _osm_candidates(label: str, hits: Optional[list]) -> list[tuple[dict, str]]:
    out = []
    for h in hits or []:
        tier = _osm_tier(h)
        if tier and _osm_name_matches(label, h):
            out.append((h, tier))
    return out


def _pick_geonames(lat: float, lon: float, recs: list[GeoRecord], max_km: float, natural: bool) -> Optional[GeoRecord]:
    near = [r for r in recs if _km(lat, lon, r.lat, r.lon) <= max_km]
    if not near:
        return None
    pref = _GN_PREF_NATURAL if natural else _GN_PREF_SETTLEMENT
    near.sort(key=lambda r: (pref.get(r.fclass, 5), _km(lat, lon, r.lat, r.lon), -r.population))
    return near[0]


@dataclass
class PlaceLink:
    lat: Optional[float] = None
    lon: Optional[float] = None
    uncertainty_m: Optional[int] = None
    geonames: Optional[GeoRecord] = None
    qid: Optional[str] = None
    osm: Optional[str] = None
    source: str = ""
    confidence: float = 0.0
    status: str = "no_match"
    note: str = ""


_BIG_CITY_CODES = {"PPLC", "PPLA", "PPLA2", "PPLA3"}


def _name_tier(label: str, rec: GeoRecord, primary_ids: Optional[set]) -> str:
    """primary | contains | alternate — how the label relates to the GeoNames record's own name."""
    if primary_ids is None or rec.id in primary_ids:
        return "primary"
    fl, fr = fold(label), fold(rec.name)
    if fr and (fr in fl or fl in fr):          # "Moosburg" in "Moosburg an der Isar"; "Dießen" in "Dießen am Ammersee"
        return "contains"
    return "alternate"


def resolve_label(label: str, kind: Optional[str], osm_hits: Optional[list], gn_recs: list[GeoRecord],
                  max_km: float = 10.0, context=None, primary_ids: Optional[set] = None,
                  near_km: float = 40.0, far_km: float = 150.0) -> PlaceLink:
    """Score every candidate — each name-matching OSM hit (with the GeoNames
    record it agrees with, if any) and every GeoNames record — and take the
    best. Base scores: OSM strong+GeoNames 0.95, OSM strong 0.85, OSM weak
    (+GeoNames) 0.6, GeoNames primary name in Bavaria 0.7 / DACH 0.6 / elsewhere
    0.5, label⊂name 0.55, alternate 0.4. Entry context: ≤ near_km +0.3 (cap
    0.95), > 2·near_km −0.15, > far_km −0.3 (big cities that OSM and GeoNames
    agree on keep their score); ties go to the candidate nearest the context.
    linked at ≥ 0.8, review ≥ 0.4, else no_match."""
    link = PlaceLink()
    home = [r for r in gn_recs if r.cc == HOME["cc"] and r.admin1 == HOME["admin1"]]
    cands: list[tuple[float, PlaceLink]] = []
    used_gn: set[int] = set()
    # context: one (lat, lon), a flat list of anchor points, or one list of points per entry
    if not context:
        per_entry: list[list[tuple[float, float]]] = []
    elif isinstance(context[0], (int, float)):
        per_entry = [[tuple(context)]]
    elif isinstance(context[0], (tuple, list)) and context[0] and isinstance(context[0][0], (int, float)):
        per_entry = [[tuple(pt)] for pt in context]
    else:
        per_entry = [list(pts) for pts in context]
    points = [pt for pts in per_entry for pt in pts]
    # a weak OSM hit (pub, track, board) named after a settlement that GeoNames knows as a
    # real place elsewhere is just named after it — the context must not "confirm" it
    settlement_elsewhere = any(g.fclass == "P" and (g.population >= 5000 or (primary_ids is not None and g.id in primary_ids))
                               for g in gn_recs)

    def nearest_km(lat: float, lon: float) -> float:
        return min(_km(a, b, lat, lon) for a, b in points)

    def support(lat: float, lon: float, radius: float) -> float:
        """Fraction of the label's context entries with an anchor within ``radius`` km."""
        return sum(1 for pts in per_entry if any(_km(a, b, lat, lon) <= radius for a, b in pts)) / len(per_entry)

    def ctx_adjust(score: float, lat: float, lon: float, exempt: bool, weak: bool = False) -> tuple[float, str]:
        if not per_entry:
            return score, ""
        f_near, f_mid = support(lat, lon, near_km), support(lat, lon, 2 * near_km)
        d = nearest_km(lat, lon)
        if f_near >= 0.2 or (len(per_entry) <= 2 and f_near > 0):
            if weak and settlement_elsewhere:
                return score, f"named after a settlement elsewhere; not confirmed by context ({d:.0f} km)"
            return min(score + 0.3, 0.95), f"entry context {d:.0f} km ({f_near:.0%} of the entries)"
        if exempt:
            return score, ""
        if f_mid >= 0.2:
            return score, ""
        if d > far_km:
            return score - 0.3, f"{d:.0f} km from the entries' other places ({f_mid:.0%} within {2 * near_km:.0f} km)"
        return score - 0.15, f"far from most of the entries' other places ({f_mid:.0%} within {2 * near_km:.0f} km, nearest {d:.0f} km)"

    def dist(l: PlaceLink) -> float:
        return nearest_km(l.lat, l.lon) if points and l.lat is not None else 0.0

    # --- OSM hits (each with the GeoNames record it agrees with)
    for h, tier in _osm_candidates(label, osm_hits) if osm_hits else []:
        lat, lon = float(h["lat"]), float(h["lon"])
        natural = h.get("category") in ("natural", "waterway", "water", "leisure") or h.get("type") in ("protected_area", "nature_reserve", "reservoir", "forest", "wood")
        g = _pick_geonames(lat, lon, gn_recs, max_km, natural)
        l = PlaceLink(lat=lat, lon=lon, osm=f"{h.get('osm_type')}/{h.get('osm_id')}", qid=h.get("wikidata"))
        if g is not None:
            used_gn.add(g.id)
            l.geonames, l.lat, l.lon = g, g.lat, g.lon          # the GeoNames point is the identity we cite
            l.uncertainty_m = _UNCERT_GN.get(g.fcode, 2000)
            l.source, score = "osm+geonames", (0.95 if tier == "strong" else 0.6)
        else:
            l.uncertainty_m = _UNCERT_OSM.get(h.get("type"), 1500)
            l.source, score = "osm", (0.85 if tier == "strong" else 0.6)
        notes = []
        if tier == "weak":
            notes.append(f"OSM {h.get('category')}/{h.get('type')} named after the place")
        if kind == "settlement" and h.get("category") not in ("place", "boundary"):
            score -= 0.15
        exempt = g is not None and tier == "strong" and (g.fcode in _BIG_CITY_CODES or g.population >= 20000)
        score, note = ctx_adjust(score, l.lat, l.lon, exempt, weak=(tier == "weak"))
        if note:
            notes.append(note)
        l.note = "; ".join(notes)
        cands.append((score, l))
    # --- GeoNames records on their own
    for g in gn_recs:
        if g.id in used_gn:
            continue
        nt = _name_tier(label, g, primary_ids)
        if nt == "primary":
            score = 0.7 if (g.cc == HOME["cc"] and g.admin1 == HOME["admin1"]) else (0.6 if g.cc in ("DE", "AT", "CH") else 0.5)
        elif nt == "contains":
            score = 0.55
        elif g.fclass == "P" and g.population >= 10000 and not home:
            score = 0.65           # an exonym of a town (Korfu, Mailand, Venedig …): alternate names are how GeoNames knows it
        else:
            score = 0.4
        if g.fclass == "S":
            score -= 0.05 if g.fcode in ("RSTN", "ZOO", "CSTL", "PRK") else 0.2   # a station stands for the place, but the place is better
        if g.fclass == "A":
            score -= 0.1                                      # the admin unit stands for the place but is not it
        l = PlaceLink(lat=g.lat, lon=g.lon, geonames=g, uncertainty_m=_UNCERT_GN.get(g.fcode, 2000), source="geonames")
        notes = [f"GeoNames {nt} name match ({g.cc})"]
        score, note = ctx_adjust(score, g.lat, g.lon, g.fcode in _BIG_CITY_CODES or g.population >= 20000)
        if note:
            notes.append(note)
        l.note = "; ".join(notes)
        cands.append((score, l))
    if not cands:
        link.note = "no gazetteer entry" if osm_hits is not None else "not geocoded yet (no Nominatim cache entry)"
        return link
    # several equally good GeoNames-only candidates without context are ambiguous
    # ties: both sources agreeing beats one source, a populated place beats a station/admin unit, then the nearer one
    _src_rank = {"osm+geonames": 0, "osm": 1, "geonames": 2}
    _cls_rank = {"P": 0, "H": 1, "T": 1, "V": 1, "L": 1, "A": 2, "S": 3}
    cands.sort(key=lambda c: (-c[0], _src_rank.get(c[1].source, 3), _cls_rank.get(c[1].geonames.fclass, 2) if c[1].geonames else 1,
                              dist(c[1]), -(c[1].geonames.population if c[1].geonames else 0)))
    score, link = cands[0]
    if link.source == "geonames" and not per_entry:
        same = [c for c in cands if abs(c[0] - score) < 1e-9 and c[1].geonames is not None
                and (round(c[1].geonames.lat, 1), round(c[1].geonames.lon, 1)) != (round(link.geonames.lat, 1), round(link.geonames.lon, 1))]
        if same:
            score = min(score, 0.5)
            link.note += f"; {len(same) + 1} GeoNames candidates"
        elif home and link.geonames in home and score >= 0.7:
            score = max(score, 0.8)                          # unique primary match in Bavaria
            link.note += "; unique in Bavaria"
    link.confidence = round(max(0.0, min(score, 0.95)), 2)
    link.status = "linked" if link.confidence >= 0.8 else ("review" if link.confidence >= 0.4 else "no_match")
    link.note = link.note.strip("; ")
    return link


# --------------------------------------------------------------------------
# stage
# --------------------------------------------------------------------------
def _all_places(result) -> tuple[Counter, dict[str, Place], dict[str, set[int]]]:
    """usage per name, one object per name, and the entries each name occurs in."""
    usage: Counter = Counter()
    objs: dict[str, Place] = {}
    where: dict[str, set[int]] = defaultdict(set)
    for k, entry in enumerate(result.entries):
        def see(p, w=1):
            if p is None:
                return
            usage[p.name] += w
            objs.setdefault(p.name, p)
            where[p.name].add(k)
        see(entry.place)
        for obs in entry.observations:
            see(obs.place); see(obs.locality)
        for ev in entry.travel_events:
            for leg in ev.legs:
                see(leg.departure_place); see(leg.arrival_place)
                for v in leg.via_places:
                    see(v)
    return usage, objs, where


def _context_points(where: dict[str, set[int]], anchors: dict[str, tuple[float, float]]) -> dict[str, list[list[tuple[float, float]]]]:
    """Per label: one list of anchor points (strong links sharing the entry,
    the label itself excluded) for every entry that has any. The matcher scores
    a candidate by the FRACTION of these entries with an anchor nearby — a
    journey entry that mentions München and Lovran does not pull Lovran to
    Bavaria, and one stray entry does not pull a Munich locality to the
    Oberpfalz."""
    by_entry: dict[int, list[tuple[str, float, float]]] = defaultdict(list)
    for name, (lat, lon) in anchors.items():
        for k in where.get(name, ()):
            by_entry[k].append((name, lat, lon))
    out: dict[str, list[list[tuple[float, float]]]] = {}
    for name, entries in where.items():
        per_entry = []
        for k in sorted(entries):
            pts = sorted({(round(lat, 3), round(lon, 3)) for other, lat, lon in by_entry.get(k, ()) if other != name})
            if pts:
                per_entry.append(pts)
        if per_entry:
            out[name] = per_entry
    return out


def link_places(result, cfg: dict, wikidata_cache: JsonCache, offline: bool) -> tuple[int, list[dict]]:
    cfg = cfg or {}
    cache_dir = Path(cfg.get("cache_dir", "data/cache/linking"))
    nom_cfg = dict(cfg.get("nominatim") or {})
    nominatim = NominatimClient(Path(nom_cfg.get("cache", cache_dir / "nominatim_cache.json")),
                                email=nom_cfg.get("email", ""), live=bool(nom_cfg.get("live", False)) and not offline)
    gn_cfg = dict(cfg.get("geonames") or {})
    geonames = GeoNamesIndex(Path(gn_cfg.get("dir", cache_dir / "geonames")),
                             countries=tuple(gn_cfg.get("countries", DEFAULT_COUNTRIES)),
                             download=bool(gn_cfg.get("download", True)) and not offline)
    min_uses = int(cfg.get("min_uses", 1))
    max_km = float(cfg.get("max_km", 10.0))
    keep_existing = bool(cfg.get("keep_gazetteer_coordinates", True))

    reviewed: dict[str, dict] = {}
    if cfg.get("reviewed_csv"):
        for row in review.load_reviewed(cfg["reviewed_csv"]):
            reviewed[(row.get("place_name") or "").strip()] = row
    rejected: set[str] = set()
    if cfg.get("reviewed_csv") and Path(cfg["reviewed_csv"]).exists():
        with Path(cfg["reviewed_csv"]).open(newline="", encoding="utf-8") as h:
            for row in csv.DictReader(h):
                if (row.get("decision") or "").strip().lower() in ("n", "no", "reject", "0"):
                    rejected.add((row.get("place_name") or "").strip())

    near_km = float(cfg.get("context_near_km", 40.0))
    far_km = float(cfg.get("context_far_km", 150.0))
    usage, objs, where = _all_places(result)
    rows: list[dict] = []
    links: dict[str, PlaceLink] = {}
    candidates: list[str] = []
    for name, n in sorted(usage.items(), key=lambda x: -x[1]):
        p = objs[name]
        if name in reviewed:
            r = reviewed[name]
            link = PlaceLink(lat=float(r["lat"]) if r.get("lat") else None, lon=float(r["lon"]) if r.get("lon") else None,
                             uncertainty_m=int(r["uncertainty_m"]) if r.get("uncertainty_m") else None,
                             qid=r.get("qid") or None, osm=r.get("osm") or None, source=r.get("source") or "reviewed",
                             confidence=1.0, status="reviewed")
            if r.get("geonames_id"):
                link.geonames = GeoRecord(int(r["geonames_id"]), r.get("geonames_name") or "", "", r.get("feature") or "",
                                          r.get("country") or "", r.get("admin1") or "", link.lat or 0.0, link.lon or 0.0, 0)
            links[name] = link
            continue
        if n < min_uses or not geocodable(name):
            continue            # not even a candidate: no row
        candidates.append(name)

    def run(name: str, context) -> PlaceLink:
        recs = geonames.lookup(name)
        return resolve_label(name, objs[name].kind, nominatim.search(name), recs, max_km, context=context,
                             primary_ids={r.id for r in recs if geonames.is_primary(name, r)}, near_km=near_km, far_km=far_km)

    # pass 1: no context; the strong links (and built-in gazetteer points, reviewed rows) become anchors
    first = {name: run(name, None) for name in candidates}
    anchors: dict[str, tuple[float, float]] = {}
    for name, p in objs.items():
        if p.lat is not None and p.long is not None:
            anchors[name] = (p.lat, p.long)
    for name, l in links.items():                       # reviewed
        if l.lat is not None:
            anchors[name] = (l.lat, l.lon)
    for name, l in first.items():
        if l.status == "linked" and l.confidence >= 0.9 and l.lat is not None:
            anchors[name] = (l.lat, l.lon)
    contexts = _context_points(where, anchors)
    # pass 2: with the entry context
    final: dict[str, PlaceLink] = {}
    for name in candidates:
        ctx = contexts.get(name)
        final[name] = run(name, ctx) if ctx else first[name]
        if name in rejected:
            final[name].status = "rejected"
        if final[name].status == "linked":
            links[name] = final[name]
    for name in candidates:
        p = objs[name]; link = final[name]; g = link.geonames
        rows.append({"place_name": name, "n_uses": usage[name], "kind": p.kind or "", "status": link.status, "source": link.source,
                     "lat": f"{link.lat:.5f}" if link.lat is not None else "", "lon": f"{link.lon:.5f}" if link.lon is not None else "",
                     "uncertainty_m": link.uncertainty_m or "", "geonames_id": g.id if g else "", "geonames_name": g.name if g else "",
                     "feature": f"{g.fclass}.{g.fcode}" if g else "", "country": g.cc if g else "", "admin1": g.admin1 if g else "",
                     "qid": link.qid or "", "osm": link.osm or "", "confidence": f"{link.confidence:.2f}", "note": link.note, "decision": ""})
    for name, r in reviewed.items():
        if name in usage:
            rows.append({**{k: r.get(k, "") for k in PLACE_REVIEW_FIELDS}, "place_name": name, "n_uses": usage[name],
                         "kind": objs[name].kind or "", "status": "reviewed", "decision": "y"})
    nominatim.flush()
    # Wikidata items for GeoNames ids that Nominatim did not tag
    need = sorted({l.geonames.id for l in links.values() if l.geonames and not l.qid})
    qids = wikidata_qids_for_geonames(need, wikidata_cache, offline, float(cfg.get("sleep", 2.0))) if need else {}
    for l in links.values():
        if l.geonames and not l.qid and l.geonames.id in qids:
            l.qid = qids[l.geonames.id]
    for row in rows:
        l = links.get(row["place_name"])
        if l and l.qid and not row["qid"]:
            row["qid"] = l.qid

    # apply: one canonical Place object per linked name, every reference re-pointed
    canon: dict[str, Place] = {}
    for name, l in links.items():
        p = objs[name]
        if keep_existing and p.lat is not None and l.source != "reviewed":
            lat, lon = p.lat, p.long            # the built-in gazetteer point stays; ids are added
        else:
            lat, lon = l.lat, l.lon
        canon[name] = replace(p, lat=lat, long=lon,
                              geonames_id=l.geonames.id if l.geonames else p.geonames_id,
                              wikidata_iri=(WIKIDATA_ENTITY_NS + l.qid) if l.qid else p.wikidata_iri,
                              coordinate_uncertainty_m=l.uncertainty_m or p.coordinate_uncertainty_m,
                              georef_source=l.source or p.georef_source)
    def fix(p):
        return canon.get(p.name, p) if p is not None else None
    n_ref = 0
    for entry in result.entries:
        if entry.place is not None and entry.place.name in canon:
            n_ref += 1
        entry.place = fix(entry.place)
        for obs in entry.observations:
            obs.place = fix(obs.place); obs.locality = fix(obs.locality)
        for ev in entry.travel_events:
            ev.legs = [replace(leg, departure_place=fix(leg.departure_place), arrival_place=fix(leg.arrival_place),
                               via_places=tuple(fix(v) for v in leg.via_places)) for leg in ev.legs]
    result.places = {}
    for entry in result.entries:
        if entry.place is not None:
            result.places.setdefault(entry.place.uid, entry.place)
        for obs in entry.observations:
            if obs.place is not None:
                result.places.setdefault(obs.place.uid, obs.place)
    logger.info("places: %d of %d candidate labels linked (%d with GeoNames id, %d with Wikidata item); %d entry places re-pointed",
                len(links), len(rows), sum(1 for l in links.values() if l.geonames), sum(1 for l in links.values() if l.qid), n_ref)
    return len(links), rows
