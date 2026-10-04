"""Corpus tiers of the records: four nested corpora, calibrated on a blind scan audit.

Every record of the export gets a tier and the reasons that keep it out of the next tier:

    0  outside the core     the occurrence itself is in doubt (species, count, date, status, or the record
                            does not exist as such)
    1  core                 the occurrence is not in doubt, but another field is (observer, record type,
                            place, identification, reading)
    2  strict core          no field is in doubt, but the coordinates are missing or not reliable
    3  strict core with coordinates

A reason is a code; ``RULES`` lists them with the tier they keep a record out of. The rules use the
machine checks of the export (Gemini on every entry, Claude on a sample), the QA flags and reading
corrections, and deterministic checks of the record against the entry text: is the written name in the text,
is the count, does a record credited to the diarist sit inside a pasted report of somebody else.

Calibration: 723 records in 645 entries, stratified over every signal, checked blind against the page
scans by Claude Opus subagents. docs/corpus_tiers.md gives the estimated error per corpus,
evaluation/corpus_tiers/evaluate_tiers.py recomputes it from a record_tiers.csv.

``Tiers`` is filled record by record (``add``) and decided at the end (``assign``), because the place doubt
depends on all records: how often the other records at the same coordinates are flagged.
"""
from __future__ import annotations

import collections
import csv
import difflib
import re
from pathlib import Path

DIARIST = "Alfred Laubmann"

# code: (tier the reason keeps a record out of: 1 = core, 2 = strict core, 3 = with coordinates, de, en)
RULES = {
    "spurious": (1, "eine Scanprüfung findet den Datensatz nicht auf der Seite", "a scan check does not find the record on the page"),
    "flagged": (1, "eine Scanprüfung nennt Art, Anzahl, Datum oder Status falsch", "a scan check calls the species, count, date or status wrong"),
    "unchecked": (1, "von keiner Scanprüfung beurteilt", "judged by no scan check"),
    "duplicate": (1, "Doppel eines früheren Datensatzes (gleiches Ereignis, Taxon, Anzahl, Ort, Datum)", "duplicate of an earlier record (same event, taxon, count, place, date)"),
    "no-taxon": (1, "kein GBIF-Taxon verknüpft", "no GBIF taxon linked"),
    "list": (1, "Eintrag ist eine Artenliste oder ein Rückblick", "the entry is a species list or a retrospective"),
    "literature-date": (1, "Literaturbeleg mit dem Datum des Tagebucheintrags statt eigenem Datum", "literature record dated with the diary entry instead of its own date"),
    "entry-checks": (1, "ein Viertel der übrigen Datensätze des Eintrags beanstandet, Eintragsdatum falsch oder Scan unlesbar",
                     "a quarter of the entry's other records flagged, entry date judged wrong, or scan illegible"),
    "ungrounded": (1, "geschriebener Name oder Anzahl steht nicht im Eintragstext", "written name or count not found in the entry text"),
    "long-entry": (1, "Eintrag mit mehr als 100 Datensätzen", "entry with more than 100 records"),
    "flagged-attribution": (2, "eine Scanprüfung nennt Beobachter oder Nachweistyp falsch", "a scan check calls the observer or record type wrong"),
    "flagged-place": (2, "eine Scanprüfung nennt den Ort falsch", "a scan check calls the place wrong"),
    "flagged-georef": (2, "eine Scanprüfung nennt die Koordinaten falsch", "a scan check calls the coordinates wrong"),
    "attribution": (2, "Zuschreibung zweifelhaft: Laubmann zugeschrieben, steht aber in einem eingeklebten Bericht, oder der Beobachtername widerspricht dem Text",
                    "attribution in doubt: credited to Laubmann inside a pasted report, or the observer's name contradicts the text"),
    "identification": (2, "Bestimmung unsicher: Vorbehalt des Tagebuchschreibers, nicht auf Artniveau oder Name nicht belegt",
                       "identification in doubt: the diarist's own hedge, not at species level, or the written name not attested"),
    "count": (2, "Anzahl geschätzt oder 100 und mehr", "count approximate or 100 and more"),
    "absence": (2, "Abwesenheitsnachweis", "record of absence"),
    "reading": (2, "Lesung strittig: beanstandete Lesekorrektur in der Textstelle oder Transkription des Eintrags stark fehlerhaft",
                "reading in doubt: an objected reading correction in the passage, or the entry's transcription badly flawed"),
    "entry": (2, "Art des Eintrags von der Scanprüfung beanstandet", "the entry's kind judged wrong by the scan check"),
    "entry-place": (2, "Ort des Eintrags zweifelhaft (beanstandet, Kopfzeile anders gelesen oder selten), der Datensatz hat keinen eigenen Ort",
                    "the entry's place in doubt (objected, header read differently or rare) and the record has no place of its own"),
    "no-coords": (3, "Ort ohne Koordinaten", "place without coordinates"),
    "georef-unconfirmed": (3, "Koordinaten nur aus einem Namenstreffer im Ortsverzeichnis, nicht geprüft", "coordinates only from a gazetteer name match, not reviewed"),
    "place-doubt": (3, "die übrigen Datensätze an diesen Koordinaten werden oft wegen des Orts beanstandet", "the other records at these coordinates are often flagged for their place"),
}
ORDER = list(RULES)
TIER_NAMES = ["outside the core", "core", "strict core", "strict core with coordinates"]
OCCURRENCE_FIELDS = {"species", "count", "date", "status"}
OTHERS_FLAGGED = 0.25          # share of the entry's other records a check flags (entry-checks)
LONG_ENTRY = 100
BIG_COUNT = 100
RARE_PLACE = 3                 # an entry place used by this many entries or fewer
PLACE_DOUBT = 0.15             # share of the other records at the same coordinates flagged for place or coordinates

TAG = re.compile(r"</?[a-zA-Z][^>]*>")
SECTION_TERMS = re.compile(r"\b(Wb|Vkl|Ob|Ft|Hb|Ob\.|Wb\.|Vkl\.|Ft\.|SD|QD|E-Werk|Querdamm|Süddamm|Norddamm|Westbecken|Ostbecken|Begehung|Sps)\b")
TYPED_ITEM = re.compile(r"(?:^|\s)\d{1,3}\)\s?[A-ZÄÖÜ][a-zäöüß]+[,;:]")
SPLIT_ENTRY = re.compile(r"e\d{4}[a-z]$")
NUMBER_WORDS = {"ein": 1, "eine": 1, "einen": 1, "einem": 1, "einer": 1, "eines": 1, "einzeln": 1, "einzelne": 1, "einzelner": 1, "einzelnes": 1,
                "einzig": 1, "einzige": 1, "einzigen": 1, "einziger": 1, "zwei": 2, "paar": 2, "paerchen": 2, "beide": 2, "beiden": 2, "drei": 3,
                "fier": 4, "wier": 4, "fuenf": 5, "seks": 6, "sechs": 6, "siben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwoelf": 12,
                "dutzend": 12, "zwanzig": 20, "dreissig": 30, "dreisig": 30, "fierzig": 40, "wierzig": 40, "fuenfzig": 50, "hundert": 100, "tausend": 1000}
PLACE_STOP = {"bei", "am", "an", "im", "in", "der", "die", "das", "dem", "den", "des", "und", "von", "zum", "zur", "auf", "nach", "see", "bad", "sankt", "st"}


def fold(s: str) -> str:
    s = TAG.sub("", s or "").casefold()
    for a, b in (("ß", "ss"), ("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("v", "w"), ("th", "t"), ("ph", "f"), ("ck", "k"), ("ie", "i"), ("y", "i"), ("dt", "t")):
        s = s.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", s)


def text_tokens(text: str) -> list[str]:
    t = TAG.sub("", text or "").replace("-\n", "").replace("=\n", "")
    return [fold(w) for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", t)]


def numbers(text: str) -> set[int]:
    s = TAG.sub("", text or "")
    out = set()
    for m in re.finditer(r"\d[\d\.]*", s):
        v = m.group().replace(".", "")
        if v.isdigit():
            out.add(int(v))
    for m in re.finditer(r"\d+(?:\s*\+\s*\d+)+", s):
        out.add(sum(int(x) for x in re.findall(r"\d+", m.group())))
    for m in re.finditer(r"[♂♀]+", s):
        out.add(len(m.group()))
    if re.search(r"♂.{0,3}♀|♀.{0,3}♂", s):
        out.add(2)
    for w in re.findall(r"[a-z]+", fold(s)):
        if w in NUMBER_WORDS:
            out.add(NUMBER_WORDS[w])
    return out


def count_in_text(count, passage: str, text: str) -> bool:
    try:
        c = int(float(count))
    except (TypeError, ValueError):
        return True
    return c == 1 or c in numbers(passage) or c in numbers(text)


def place_words(s: str) -> set[str]:
    out = set()
    for w in re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", s or ""):
        f = re.sub(r"[^a-z]", "", w.casefold().replace("ß", "ss").replace("ä", "a").replace("ö", "o").replace("ü", "u"))
        if f not in PLACE_STOP and len(f) >= 4:
            out.add(f)
    return out


def same_place_name(a: str, b: str):
    """True / False when both name a place, None when one of them has no place word."""
    wa, wb = place_words(a), place_words(b)
    if not wa or not wb:
        return None
    return any(x[:5] == y[:5] or difflib.SequenceMatcher(None, x, y).ratio() >= 0.8 for x in wa for y in wb)


def observer_conflict(observers: str, text: str) -> bool:
    """A named observer whose first name contradicts the initials or first names the entry text gives the same surname
    ("Heinrich Wüst" where the text has "W. Wüst")."""
    for n in (x.strip() for x in (observers or "").split("|")):
        if not n or n == DIARIST:
            continue
        parts = re.sub(r"\b(Dr|Prof|Frau|Fr|Herr|Hr|Frl)\.?\s", " ", n).split()
        if len(parts) < 2 or len(parts[0]) <= 2 or len(parts[-1]) < 3:
            continue
        sur = parts[-1]
        if sur.casefold() not in text.casefold():
            continue
        inits = {m.group(1) for m in re.finditer(r"\b([A-ZÄÖÜ])\.\s?(?:[A-ZÄÖÜ]\.\s?)?" + re.escape(sur), text)}
        fulls = {m.group(1)[0] for m in re.finditer(r"\b([A-ZÄÖÜ][a-zäöüß]{2,})\s" + re.escape(sur), text)}
        if (inits or fulls) and parts[0][0].upper() not in inits | fulls:
            return True
    return False


def flag_group(verdict: str, fields: list[str]) -> str:
    """What a check's finding says about the record: the occurrence, its place, its coordinates or its attribution."""
    if verdict == "spurious":
        return "spurious"
    if verdict != "wrong":
        return ""
    fs = {f for f in fields if f}
    if fs & OCCURRENCE_FIELDS:
        return "flagged"
    if fs <= {"georef"}:
        return "flagged-georef"
    if fs <= {"georef", "locality"}:
        return "flagged-place"
    if fs <= {"observer", "record_type"}:
        return "flagged-attribution"
    return "flagged"


class Tiers:
    """Collects the signals of every record (``add``) and decides the tiers (``assign``)."""

    def __init__(self, entry_place_uses: dict[str, int] | None = None):
        self.rows: list[dict] = []
        self.place_uses = entry_place_uses or {}

    def add(self, item: dict, *, index: int, occ: dict, entry: dict, record: dict, checks: tuple, reading_contested: bool, name_attested: bool,
            duplicate: bool) -> None:
        """One record. ``occ`` = its Darwin Core occurrence row, ``entry`` = facts of its entry (see ``entry_facts``),
        ``record`` = its graph record (graph_records), ``checks`` = ((verdict, fields), ...) of the scan checks, Gemini first."""
        groups = [flag_group(v, f) for v, f in checks]
        judged = [v for v, _ in checks if v in ("ok", "wrong", "spurious")]
        group = "spurious" if "spurious" in groups else "flagged" if "flagged" in groups else next((g for g in groups if g), "")
        text, passage = entry["text"], TAG.sub("", occ.get("occurrenceRemarks") or "")
        recorded_by = occ.get("recordedBy") or ""
        record_type = record.get("record_type") or ""
        own_date = (occ.get("eventDate") or "")[:10] != (entry["date"] or "")[:10]
        diarist = DIARIST in recorded_by
        in_report = diarist and (entry["split"] or bool(SECTION_TERMS.search(passage)) or entry["typed"] or bool(TYPED_ITEM.search(" " + passage))
                                 or any(_overlap(passage, s) >= 0.6 for s in entry["inserts"]))
        try:
            count = float(occ.get("individualCount") or "")
        except ValueError:
            count = None
        own_place = bool((occ.get("verbatimLocality") or "").strip())
        code = {
            "spurious": group == "spurious",
            "flagged": group == "flagged",
            "unchecked": not judged,
            "duplicate": duplicate,
            "no-taxon": not occ.get("taxonID"),
            "list": entry["kind"] in ("species-digest", "retrospective"),
            "literature-date": record_type == "literature-record" and not own_date,
            "entry-checks": entry["others_flagged"](index) >= OTHERS_FLAGGED or (entry["date_bad"] and not own_date) or entry["illegible"],
            "ungrounded": not name_in_text_cached(entry, item["w"]) or (occ.get("individualCount") not in (None, "")
                                                                         and not count_in_text(occ["individualCount"], passage, text)),
            "long-entry": entry["n"] > LONG_ENTRY,
            "flagged-attribution": group == "flagged-attribution",
            "flagged-place": group == "flagged-place",
            "flagged-georef": group == "flagged-georef",
            "attribution": in_report or observer_conflict(recorded_by, text),
            "identification": bool(occ.get("identificationQualifier")) or occ.get("taxonRank") not in ("species", "subspecies") or not name_attested,
            "count": record.get("count_qualifier") == "approximate" or (count is not None and count >= BIG_COUNT),
            "absence": occ.get("occurrenceStatus") == "absent",
            "reading": reading_contested or entry["poor"],
            "entry": entry["kind_bad"],
            "entry-place": not own_place and (entry["place_bad"] or entry["header_mismatch"] or self.place_uses.get(entry["place"], 0) <= RARE_PLACE),
            "no-coords": not occ.get("decimalLatitude"),
            "georef-unconfirmed": (occ.get("georeferenceSources") or "").startswith(("OpenStreetMap", "GeoNames")),
        }
        place_flag = bool(checks) and checks[0][0] == "wrong" and bool({"georef", "locality"} & set(checks[0][1]))
        self.rows.append({"item": item, "code": code, "coords": (occ.get("decimalLatitude"), occ.get("decimalLongitude")) if occ.get("decimalLatitude") else None,
                          "place_flag": place_flag})

    def assign(self) -> collections.Counter:
        """Decide every record's tier ``t`` and reasons ``tw`` (codes, in RULES order) and return the counts."""
        at = collections.defaultdict(lambda: [0, 0])
        for r in self.rows:
            if r["coords"]:
                at[r["coords"]][0] += 1
                at[r["coords"]][1] += r["place_flag"]
        counts = collections.Counter()
        for r in self.rows:
            n, f = at[r["coords"]] if r["coords"] else (0, 0)
            r["code"]["place-doubt"] = bool(r["coords"]) and n > 1 and (f - r["place_flag"]) / (n - 1) > PLACE_DOUBT
            hit = [c for c in ORDER if r["code"].get(c)]
            tier = min([RULES[c][0] - 1 for c in hit], default=3)
            why = [c for c in hit if RULES[c][0] - 1 == tier]
            r["item"]["t"] = tier
            if why:
                r["item"]["tw"] = why
            else:
                r["item"].pop("tw", None)
            counts[f"tier {tier}"] += 1
            for c in why:
                counts[f"why {c}"] += 1
        return counts


def _grams(s: str) -> list[str]:
    w = re.findall(r"[a-zäöüß0-9]+", TAG.sub("", s or "").casefold())
    return [" ".join(w[i:i + 3]) for i in range(len(w) - 2)]


def _overlap(passage: str, gram_set: set) -> float:
    g = _grams(passage)
    return sum(1 for x in g if x in gram_set) / len(g) if g else 0.0


def name_in_text_cached(entry: dict, name: str) -> bool:
    cache = entry.setdefault("_names", {})
    if name not in cache:
        if "_tokens" not in entry:
            entry["_tokens"] = text_tokens(entry["text"])
            entry["_joined"] = "".join(entry["_tokens"])
        cache[name] = _name_in(name, entry["_tokens"], entry["_joined"])
    return cache[name]


def _name_in(name: str, tokens: list[str], joined: str) -> bool:
    n = fold(name)
    words = re.findall(r"[a-z]{3,}", n)
    if not words:
        return False
    if n.replace(" ", "") in joined:
        return True
    head = max(words, key=len)
    for t in tokens:
        if len(t) < 3 or abs(len(t) - len(head)) > 6:
            continue
        if t.startswith(head[:-1]) or (head.startswith(t[:-1]) and len(t) >= len(head) - 2):
            return True
    return False


def entry_facts(*, text: str, date: str, kind: str, entry_id: str, n_records: int, flags_by_index: dict, poor: bool, illegible: bool,
                date_bad: bool, kind_bad: bool, place_bad: bool, place: str, header_place: str, inserts: list[str]) -> dict:
    """What the tier rules need to know about an entry. ``flags_by_index`` = {obs_index: flagged by a check}."""
    flagged = sum(1 for v in flags_by_index.values() if v)
    clean = TAG.sub("", text or "")

    def others_flagged(index):
        own = 1 if flags_by_index.get(index) else 0
        return (flagged - own) / max(1, n_records - 1)

    match = same_place_name(header_place, place) if header_place and place else None
    return {"text": clean, "date": date, "kind": kind, "n": n_records, "others_flagged": others_flagged, "poor": poor, "illegible": illegible,
            "date_bad": date_bad, "kind_bad": kind_bad, "place_bad": place_bad, "place": place, "header_mismatch": match is False,
            "split": bool(SPLIT_ENTRY.search(entry_id)), "typed": len(TYPED_ITEM.findall(" " + clean)) >= 5,
            "inserts": [set(_grams(t)) for t in inserts if t]}


def tier_rows(review_entries: dict, occurrence_ids: dict) -> list[list]:
    """Rows of record_tiers.csv from the review layer's entries ({entry_id: {rec: {...}}}) and {(entry_id, obs_index): occurrenceID}."""
    rows = []
    for eid, e in review_entries.items():
        for k, r in (e.get("rec") or {}).items():
            if "t" not in r:
                continue
            t, why = r["t"], r.get("tw") or []
            rows.append([occurrence_ids.get((eid, int(k)), ""), eid, r["w"], t, TIER_NAMES[t], int(t >= 1), int(t >= 2), int(t >= 3),
                         "; ".join(RULES[c][2] for c in why), " ".join(why)])
    return rows


def write_csv(path, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as h:
        w = csv.writer(h)
        w.writerow(["occurrenceID", "entry_id", "written_name", "tier", "corpus", "in_core", "in_strict_core", "in_strict_core_with_coordinates",
                    "why_not_next_tier", "reason_codes"])
        w.writerows(rows)
