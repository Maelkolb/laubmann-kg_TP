"""Payload for the HistOrniGraph validation UI (v2, "Abgleich").

The review unit is the NAME FORM: a taxon, person, place or habitat name as it
is written in the diary, assigned to one entity of the graph (a GBIF taxon, a
person, a place, a habitat concept). A reviewer confirms or changes that
assignment for the name form as a whole, and can overrule it for single
mentions. Merges are a consequence of the assignments (all forms assigned to
the same entity are one node); there are no variant -> canonical pairs to
judge any more.

Inputs: one export (``rdf/*.ttl`` parsed by load.py, ``review/``), the
deduplicated corpus (corpus.json + entries.jsonl, for the pages an entry spans
and the line a mention sits on), the page geometry (page_geometry.py) and the
German vernacular names of the linked taxa (vernaculars.py).

    python tools/validation_ui/build_payload.py <export>/review --triples triples.pkl \
        --corpus <corpus_dir> --geometry pages_geometry.json --vernaculars vernaculars.json \
        --built 2026-09-28 --out payload.b64
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import difflib
import gzip
import hashlib
import json
import pickle
import random
import re
import unicodedata
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("review_dir", help="the export's review/ folder")
ap.add_argument("--triples", default="triples.pkl", help="output of load.py")
ap.add_argument("--corpus", required=True, help="folder with corpus.json and entries.jsonl (deduplicated corpus)")
ap.add_argument("--geometry", required=True, help="output of page_geometry.py")
ap.add_argument("--vernaculars", required=True, help="output of vernaculars.py")
ap.add_argument("--eunis", default=str(Path(__file__).resolve().parents[2] / "data" / "eunis_habitats.csv"))
ap.add_argument("--export-name", default=None)
ap.add_argument("--built", default="")
ap.add_argument("--sample", type=int, default=400, help="size of the random evaluation sample of taxon mentions")
ap.add_argument("--seed", type=int, default=20260928)
ap.add_argument("--second-reading", default=None, help="output of second_reading.py (model suggestions for doubtful taxon mentions)")
ap.add_argument("--third-reading", default=None, help="third_reading.json of model_answers_merge.py (second model)")
ap.add_argument("--person-matches", default=None, help="person_matches.json of model_answers_merge.py")
ap.add_argument("--machine-review", default=None, help="machine_review.json of machine_review/merge.py (verdicts per entity and name)")
ap.add_argument("--machine-readings", default=None, help="readings_machine.json of machine_review/merge.py (scan agent readings per mention)")
ap.add_argument("--out", default="payload.b64")
args = ap.parse_args()
R = Path(args.review_dir)

# ---------------------------------------------------------------- graph index
T = pickle.load(open(args.triples, "rb"))


def loc(u) -> str:
    u = str(u)
    return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


out = collections.defaultdict(lambda: collections.defaultdict(list))
typ: dict = {}
for s, p, o in T:
    pn = loc(p)
    if pn == "type":
        typ.setdefault(s, set()).add(loc(o))
    else:
        out[s][pn].append(o)
del T


def one(s, p, d=""):
    v = out[s].get(p) if s is not None else None
    return str(v[0]) if v else d


def of_type(t):
    return [s for s, ts in typ.items() if t in ts]


def labels(s) -> list[str]:
    seen, res = set(), []
    for x in out[s].get("prefLabel", []) + out[s].get("label", []) + out[s].get("name", []) + out[s].get("altLabel", []):
        x = str(x)
        if x and x not in seen:
            seen.add(x)
            res.append(x)
    return res


# ---------------------------------------------------------------- corpus: pages, entry spans, lines
corpus_pages = json.loads((Path(args.corpus) / "corpus.json").read_text(encoding="utf-8"))
geo = json.loads(Path(args.geometry).read_text(encoding="utf-8"))
corpus_entries = {}
with open(Path(args.corpus) / "entries.jsonl", encoding="utf-8") as h:
    for line in h:
        d = json.loads(line)
        corpus_entries[d["entry_uid"]] = d

TAG = re.compile(r"<[^>]+>")
PG = []                       # [page_id, volume, scan, side, printed page number, w, h]
page_idx = {}
# The corpus text stream of a volume = its paragraph and list regions in page and
# reading order, joined by a blank line; entries.jsonl stream_start/stream_end
# index into it. An entry that runs over the page break therefore spans regions
# of several pages.
STREAM_TYPES = ("ParagraphRegion", "ListRegion")
stream = collections.defaultdict(list)     # volume -> [(start, end, page index, region id)]
stream_pos = collections.defaultdict(int)
region_text = {}                           # (page index, region id) -> raw text
for pg in corpus_pages:
    pid = pg["page_id"]
    g = geo.get(pid, {"w": 0, "h": 0})
    m = re.search(r"_(\d{4})(?:_([LR]|full))?$", pid)
    page_idx[pid] = len(PG)
    vol = int(pg["volume"])
    PG.append([pid, vol, int(pg["scan"]), (m.group(2) or "") if m else "", (pg.get("page_number") or "").strip(), g["w"], g["h"]])
    for r in sorted(pg["regions"], key=lambda r: int(r.get("reading_order") or 0)):
        text = r.get("text") or ""
        region_text[(page_idx[pid], r["id"])] = text
        if r.get("type") not in STREAM_TYPES:
            continue
        a = stream_pos[vol]
        stream[vol].append((a, a + len(text), page_idx[pid], r["id"]))
        stream_pos[vol] = a + len(text) + 2

# entry_uid -> ordered list of (page index, region id, from, to) over the raw region text
spans = {}
for uid, ce in corpus_entries.items():
    try:
        a, b = int(ce["stream_start"]), int(ce["stream_end"])
    except (KeyError, TypeError, ValueError):
        continue
    segs = [(pidx, rid, max(a, s) - s, min(b, e) - s) for s, e, pidx, rid in stream[int(ce["volume"])] if s < b and e > a]
    spans[uid] = segs


def entry_lines(uid):
    """[(page index, region id, line index, lines in region, clean line text)] of an entry."""
    res = []
    for pidx, rid, a, b in spans.get(uid, []):
        text = region_text[(pidx, rid)]
        lines = text.split("\n")
        pos = 0
        for i, ln in enumerate(lines):
            lo, hi = pos, pos + len(ln)
            pos = hi + 1
            if hi < a or lo >= b:
                continue
            res.append((pidx, rid, i, len(lines), TAG.sub("", ln)))
    return res


def joined(lines):
    """Lower-cased text of the lines with hyphenated line breaks joined, the
    line index of every character, and (start, length) of every line in it."""
    buf, owner, pos, at = [], [], 0, {}
    for k, (_, _, _, _, t) in enumerate(lines):
        t = t.strip()
        if not t:
            continue
        hyph = t.endswith("-") and len(t) > 1 and t[-2].isalpha()
        seg = t[:-1] if hyph else t + " "
        buf.append(seg)
        owner.extend([k] * len(seg))
        at[k] = (pos, max(1, len(t)))
        pos += len(seg)
    return "".join(buf).lower(), owner, at


# ---------------------------------------------------------------- name matching
WORD = re.compile(r"\w+", re.U)


def patterns(name: str):
    toks = WORD.findall(name.lower())
    if not toks:
        return []
    body = r"[\W_]*".join(re.escape(w) for w in toks)
    pats = [re.compile(r"(?<!\w)" + body)]
    last = toks[-1]
    if len(last) >= 6:           # inflected / diminutive forms: Hausrotschwänzchen -> Hausrotschwänz…
        stem = r"[\W_]*".join(re.escape(w) for w in toks[:-1] + [last[:max(4, len(last) - 3)]])
        pats.append(re.compile(r"(?<!\w)" + stem))
    return pats


def find_all(text_low: str, name: str, fuzzy: bool = True) -> list[tuple[int, int]]:
    for pat in patterns(name):
        hits = [(m.start(), m.end()) for m in pat.finditer(text_low)]
        if hits:
            # extend to the end of the word so the highlight covers the inflection
            res = []
            for s, e in hits:
                while e < len(text_low) and text_low[e].isalnum():
                    e += 1
                res.append((s, e))
            return res
    if not fuzzy:
        return []
    # fuzzy: best window of as many tokens as the name
    toks = [(m.start(), m.end(), m.group()) for m in WORD.finditer(text_low)]
    k = max(1, len(WORD.findall(name)))
    target = name.lower()
    best, where = 0.0, None
    for i in range(len(toks) - k + 1):
        s, e = toks[i][0], toks[i + k - 1][1]
        r = difflib.SequenceMatcher(None, target, text_low[s:e]).ratio()
        if r > best:
            best, where = r, (s, e)
    return [where] if where and best >= 0.8 else []


def dp_align(L, M):
    """Monotone alignment of transcription line lengths L to band ink masses M
    (both normalised by their mean): line i -> (band index, matched 1 / carried 0).
    Bands may be skipped (a sketch label, a ruled line), lines may share a band."""
    n, m = len(L), len(M)
    ml = sum(L) / n
    mm = (sum(M) / m) or 1.0
    Ln = [x / ml for x in L]
    Mn = [x / mm for x in M]
    INF = float("inf")
    SKIP, EXTRA = 0.7, 0.7
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for j in range(1, m + 1):
        cost[0][j] = cost[0][j - 1] + SKIP
        back[0][j] = 1
    for i in range(1, n + 1):
        ci, li = cost[i], Ln[i - 1]
        cp = cost[i - 1]
        for j in range(1, m + 1):
            c = abs(li - Mn[j - 1])
            a = cp[j - 1] + c
            b = ci[j - 1] + SKIP
            d = cp[j] + EXTRA + c
            if a <= b and a <= d:
                ci[j], back[i][j] = a, 0
            elif b <= d:
                ci[j], back[i][j] = b, 1
            else:
                ci[j], back[i][j] = d, 2
    i, j, out = n, m, {}
    while i > 0 and j > 0:
        k = back[i][j]
        if k == 0:
            out[i - 1] = (j - 1, 1)
            i -= 1
            j -= 1
        elif k == 1:
            j -= 1
        else:
            out[i - 1] = (j - 1, 0)
            i -= 1
    while i > 0:
        out[i - 1] = (0, 0)
        i -= 1
    return out


ALIGN = {}   # (page index, region id) -> line index -> (band index, matched) or None


def align_region(pidx, rid):
    key = (pidx, rid)
    if key not in ALIGN:
        bands = geo.get(PG[pidx][0], {}).get("l", {}).get(rid)
        res = None
        if bands and len(bands) >= 2 and all(len(b) >= 3 for b in bands):
            lines = region_text[(pidx, rid)].split("\n")
            L = [max(1, len(TAG.sub("", t).strip())) for t in lines]
            res = dp_align(L, [b[2] for b in bands])
        ALIGN[key] = res
    return ALIGN[key]


class Locator:
    """Per entry: find the k-th occurrence of a name in the entry text (for the
    highlight) and on the scan (page, region box, line range)."""

    def __init__(self):
        self.cache = {}

    def entry(self, uid):
        if uid not in self.cache:
            lines = entry_lines(uid)
            low, owner, at = joined(lines)
            self.cache = {uid: (lines, low, owner, at)}   # keep one entry (callers go entry by entry)
        return self.cache[uid]

    def scan(self, uid, name, k=0, fuzzy=True):
        """[page, x0, y0, x1, y1, approximate, word start, word end]: the line box of the
        k-th hit. With the ink profile of the region (line_profiles.py) the i-th
        transcription line maps to a physical line; otherwise the box is divided evenly
        (approximate = 1). Word start/end are fractions of the line width."""
        lines, low, owner, at = self.entry(uid)
        if not lines:
            return None
        hits = find_all(low, name, fuzzy)
        if not hits:
            return None
        s, e = hits[min(k, len(hits) - 1)]
        la, lb = owner[s], owner[max(s, e - 1)]
        pidx, rid, i, n, _ = lines[la]
        j = lines[lb][2] if lines[lb][:2] == (pidx, rid) else i
        g = geo.get(PG[pidx][0], {})
        box = g.get("r", {}).get(rid)
        if not box or n == 0:
            return [pidx]
        x0, y0, x1, y1 = box
        start, length = at.get(la, (s, 1))
        fx0 = max(0.0, min(1.0, (s - start) / length))
        fx1 = max(fx0, min(1.0, (e - start) / length))
        bands = g.get("l", {}).get(rid)
        if bands and len(bands) >= 2:
            m = len(bands)
            al = align_region(pidx, rid)
            if al and i in al:
                bi, hit = al[i]
                bj = max(bi, al.get(j, (bi, 0))[0])
                approx = 0 if hit and abs(m - n) <= 0.25 * n else 1
            else:
                bi = min(m - 1, int((i + 0.5) * m / n))
                bj = min(m - 1, max(bi, int((j + 0.5) * m / n)))
                approx = 0 if abs(m - n) <= max(1, 0.06 * n) else 1
            return [pidx, x0, bands[bi][0], x1, bands[bj][1], approx, round(fx0, 3), round(fx1, 3)]
        lh = (y1 - y0) / n
        return [pidx, x0, round(y0 + i * lh), x1, round(y0 + (j + 1) * lh), 1, round(fx0, 3), round(fx1, 3)]


LOC = Locator()


def text_pos(text: str, name: str, k=0, fuzzy=True):
    if not text or not name:
        return [-1, -1]
    hits = find_all(text.lower(), name, fuzzy)
    if not hits:
        return [-1, -1]
    return list(hits[min(k, len(hits) - 1)])


# ---------------------------------------------------------------- entries
ents = sorted(of_type("DiaryEntry"), key=lambda s: one(s, "identifier"))
eidx = {s: i for i, s in enumerate(ents)}
E = []
for s in ents:
    uid = loc(s).replace("entry_", "")
    page = out[s].get("isPartOf", [None])[0]
    vol = one(page, "isPartOf")[-2:] if page is not None else ""
    ce = corpus_entries.get(uid, {})
    pl = out[s].get("entryPlace", [None])[0]
    pages = []
    for pidx, _, _, _ in spans.get(uid, []):
        if pidx not in pages:
            pages.append(pidx)
    if not pages and ce.get("page_id") in page_idx:
        pages = [page_idx[ce["page_id"]]]
    E.append([one(s, "identifier"), uid, one(s, "eventDate"), one(s, "verbatimEventDate"), one(s, "entryKind"),
              int(vol) if vol.isdigit() else 0, one(pl, "label") if pl is not None else "", one(s, "fieldNotes"),
              pages, ce.get("location_raw") or ""])
print("entries", len(E), "with pages", sum(1 for e in E if e[8]), "multi-page", sum(1 for e in E if len(e[8]) > 1))
uid2e = {e[1]: i for i, e in enumerate(E)}


# ---------------------------------------------------------------- helpers
def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


UM = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def fold(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower().translate(UM)
    return re.sub(r"[^a-z]", "", s).replace("th", "t").replace("ph", "f")


def stem(s: str) -> str:
    f = fold(s)
    for suf in ("chen", "lein", "en", "n", "e", "s"):
        if f.endswith(suf) and len(f) - len(suf) >= 4:
            return f[: -len(suf)]
    return f


class Section:
    """Forms, entities and mentions of one entity type."""

    def __init__(self, fuzzy=True):
        self.fuzzy = fuzzy               # fuzzy matching of misspelt names in the text (taxa only: cheap enough)
        self.ent, self.ent_idx = [], {}
        self.forms, self.form_idx = [], {}
        self.men = []

    def entity(self, node, row):
        if node not in self.ent_idx:
            self.ent_idx[node] = len(self.ent)
            self.ent.append(row)
        return self.ent_idx[node]

    def form(self, name, ent):
        key = (name, ent)
        if key not in self.form_idx:
            self.form_idx[key] = len(self.forms)
            self.forms.append([name, 0, ent])
        return self.form_idx[key]

    def mention(self, form, ei, name, k=0, role=""):
        self.forms[form][1] += 1
        e = E[ei]
        self.men.append([form, ei, *text_pos(e[7], name, k, self.fuzzy), LOC.scan(e[1], name, k, self.fuzzy) or 0, role])


def occurrence_counter():
    return collections.defaultdict(int)


# ---------------------------------------------------------------- taxa
V = json.loads(Path(args.vernaculars).read_text(encoding="utf-8"))
tlink = {r["vernacular_de"].lower(): r for r in read_csv(R / "taxon_link_review.csv")}
TX = Section()
obs_by_entry = collections.defaultdict(list)
for s in of_type("Observation"):
    e = out[s].get("isPartOf", [None])[0]
    if e in eidx:
        obs_by_entry[eidx[e]].append(s)


def taxon_entity(tx):
    key = one(tx, "taxonID").rsplit("/", 1)[-1] if one(tx, "taxonID") else ""
    vern = V.get(key, {}) if key else {}
    names = sorted(set(vern.get("gbif", [])) | set(vern.get("wd", [])))
    return [one(tx, "prefLabel") or one(tx, "label"), one(tx, "scientificName"), key, one(tx, "taxonRank"),
            one(tx, "gbifMatchType"), one(tx, "matchMethod"), one(tx, "family"), one(tx, "order"),
            one(tx, "isBird"), names[:40], vern.get("qid", "")]


def obs_index(s, entry_uid: str, written: str) -> int:
    """The observation's index in its entry: the IRI is sha1("entry_uid|written|index")
    (kg/model.py Observation.uid), so the index is recovered by recomputing it.
    Mention n of a name in the UI is then the pipeline's n-th observation."""
    want = loc(s).replace("obs_", "")
    for i in range(1000):
        if hashlib.sha1(f"{entry_uid}|{written}|{i}".encode("utf-8")).hexdigest()[:12] == want:
            return i
    return 10 ** 6


def written_taxon(s):
    tx = out[s].get("observedTaxon", [None])[0]
    return tx, (one(s, "verbatimIdentification") or one(tx, "prefLabel") or one(tx, "label")) if tx is not None else ""


for ei in range(len(E)):
    seen = occurrence_counter()
    uid = E[ei][1]                       # corpus entry_uid ("e_…"), as in the observation IRI
    for s in sorted(obs_by_entry.get(ei, []), key=lambda o: (obs_index(o, uid, written_taxon(o)[1]), loc(o))):
        tx, written = written_taxon(s)
        if tx is None:
            continue
        ent = TX.entity(tx, taxon_entity(tx))
        f = TX.form(written, ent)
        TX.mention(f, ei, written, seen[written.lower()])
        seen[written.lower()] += 1


def taxon_class(form, ent):
    """A attested German name of the linked taxon (GBIF/Wikidata) or the taxon's
    own label; B spelling or compound variant of such a name; C unattested;
    L not linked to GBIF."""
    label, sci, key = ent[0], ent[1], ent[2]
    if not key:
        return "L", ""
    att = {stem(n): n for n in ent[9] + [label]}
    fs = stem(form)
    if fs in att:
        return "A", att[fs]
    best = max(((difflib.SequenceMatcher(None, fs, a).ratio(), n) for a, n in att.items()), default=(0, ""))
    if best[0] >= 0.85:
        return "B", best[1]
    for a, n in att.items():
        if len(a) >= 4 and len(fs) >= 4 and (fs.endswith(a) or a.endswith(fs)):
            return "B", n
    return "C", best[1] if best[0] >= 0.6 else ""


for f in TX.forms:
    ent = TX.ent[f[2]]
    cls, near = taxon_class(f[0], ent)
    lr = tlink.get(f[0].lower(), {})
    f += [cls, near, lr.get("llm_scientific_name") or lr.get("current_scientific_name") or "", lr.get("status", ""),
          lr.get("gbif_match_type", "")]
print("taxa: entities", len(TX.ent), "forms", len(TX.forms), "mentions", len(TX.men),
      "classes", collections.Counter(f[3] for f in TX.forms))

# ---------------------------------------------------------------- persons
plink = collections.defaultdict(list)
for r in read_csv(R / "person_link_review.csv"):
    plink[r["person_name"].lower()].append(r)
pmerge = {r["variant"]: r for r in read_csv(R / "person_merges.csv")}
ROLE_PRED = {"mentionsCompanion": "Begleiter", "mentionsSource": "Quelle", "mentionsCollector": "Sammler",
             "mentionsCitedAuthor": "zitiert", "mentionsOther": "sonstige"}
PS = Section(fuzzy=False)


LINK_PREDS = ("exactMatch", "closeMatch", "sameAs")    # ontology >= 0.6: skos matches; before: owl:sameAs


def same_as(node, host):
    """The authority id of ``node`` at ``host`` (exact or close match)."""
    return next((str(x).rstrip("/").rsplit("/", 1)[-1] for pr in LINK_PREDS for x in out[node].get(pr, [])
                 if host in str(x)), "")


def person_entity(p):
    return [one(p, "label") or one(p, "name"), same_as(p, "wikidata.org"), same_as(p, "d-nb.info"), labels(p)]


for ei, s in enumerate(ents):
    roles = collections.defaultdict(set)
    for pred, role in ROLE_PRED.items():
        for p in out[s].get(pred, []):
            roles[p].add(role)
    people = list(dict.fromkeys(out[s].get("mentionsPerson", []) + list(roles)))
    for o in obs_by_entry.get(ei, []):
        for p in out[o].get("recordedBy", []):
            if loc(p) != "person_c6b2ff6250e5":      # the diarist himself
                roles[p].add("Beobachter")
                if p not in people:
                    people.append(p)
    text = E[ei][7].lower()
    for p in people:
        names = labels(p)
        found = [n for n in sorted(names, key=len, reverse=True) if find_all(text, n, False)] if names else []
        written = found[0] if found else (names[0] if names else loc(p))
        ent = PS.entity(p, person_entity(p))
        f = PS.form(written, ent)
        PS.mention(f, ei, written, 0, "/".join(sorted(roles.get(p, ()))))


def person_class(form, ent):
    """W linked to Wikidata/GND; V a variant merged into another name (rule in
    the merge table); K canonical name, not linked; E single token, not merged."""
    if form != ent[0]:
        return "V", (pmerge.get(form) or {}).get("rule", "")
    if ent[1] or ent[2]:
        return "W", ""
    return ("E" if len(form.split()) < 2 else "K"), ""


for f in PS.forms:
    ent = PS.ent[f[2]]
    cls, rule = person_class(f[0], ent)
    cands = [[r["qid"], r["wd_label"], r["wd_description"]] for r in plink.get(f[0].lower(), []) if r.get("qid")]
    f += [cls, rule, cands[:8], (plink.get(f[0].lower()) or [{}])[0].get("rule", "")]
print("persons: entities", len(PS.ent), "forms", len(PS.forms), "mentions", len(PS.men),
      "classes", collections.Counter(f[3] for f in PS.forms))

# ---------------------------------------------------------------- places
glink = {r["place_name"].lower(): r for r in read_csv(R / "place_link_review.csv")}
gmerge = {r["variant"]: r for r in read_csv(R / "place_merges.csv")}
PL = Section(fuzzy=False)


def place_entity(p):
    lat, lon = one(p, "lat") or one(p, "decimalLatitude"), one(p, "long") or one(p, "decimalLongitude")
    gn = same_as(p, "geonames")
    return [one(p, "label"), round(float(lat), 5) if lat else None, round(float(lon), 5) if lon else None,
            one(p, "coordinateUncertaintyInMeters"), gn, same_as(p, "wikidata.org"), one(p, "placeKind"),
            one(p, "georeferenceSources")[:80], labels(p)]


legs_by_entry = collections.defaultdict(list)
for s in of_type("TravelEvent"):
    e = out[s].get("isPartOf", [None])[0] or out[s].get("wasDerivedFrom", [None])[0]
    if e in eidx:
        for leg in out[s].get("hasLeg", []):
            for pred in ("departurePlace", "arrivalPlace", "viaPlace"):
                legs_by_entry[eidx[e]] += [(p, "Reise") for p in out[leg].get(pred, [])]
for ei, s in enumerate(ents):
    uses = [(p, "Kopfzeile") for p in out[s].get("entryPlace", [])]
    for o in obs_by_entry.get(ei, []):
        uses += [(p, "Beobachtung:" + one(o, "verbatimLocality")) for p in out[o].get("hasLocality", [])]
    uses += legs_by_entry.get(ei, [])
    text = E[ei][7].lower()
    seen_here = set()
    for p, role in uses:
        names = labels(p)
        written = ""
        if role.startswith("Beobachtung:"):
            written = role.split(":", 1)[1]
            role = "Beobachtung"
            if written not in names:
                written = next((n for n in names if n.lower() in written.lower()), written)
        elif role == "Kopfzeile":
            raw = E[ei][9]
            written = next((n for n in names if raw and fold(n) == fold(raw)), "")
        if not written or written not in names:
            found = [n for n in sorted(names, key=len, reverse=True) if find_all(text, n, False)]
            written = found[0] if found else (names[0] if names else loc(p))
        if (p, written, role) in seen_here:
            continue
        seen_here.add((p, written, role))
        ent = PL.entity(p, place_entity(p))
        f = PL.form(written, ent)
        PL.mention(f, ei, written, 0, role)


def place_class(form, ent):
    """V variant merged into another name; G georeferenced; R georeference to
    check (review status); N no coordinates."""
    lr = glink.get(form.lower(), {})
    if form != ent[0]:
        return "V", (gmerge.get(form) or {}).get("rule", "")
    if lr.get("status") == "review":
        return "R", ""
    if ent[1] is not None:
        return "G", ""
    return "N", ""


for f in PL.forms:
    ent = PL.ent[f[2]]
    cls, rule = place_class(f[0], ent)
    lr = glink.get(f[0].lower(), {})
    f += [cls, rule, [lr.get(k, "") for k in ("status", "source", "confidence", "note", "lat", "lon", "geonames_id",
                                               "geonames_name", "country", "qid", "osm", "feature")]]
print("places: entities", len(PL.ent), "forms", len(PL.forms), "mentions", len(PL.men),
      "classes", collections.Counter(f[3] for f in PL.forms))

# ---------------------------------------------------------------- habitats
hlink = {r["habitat_label"].lower(): r for r in read_csv(R / "habitat_link_review.csv")}
hmerge = {r["variant"]: r for r in read_csv(R / "habitat_merges.csv")}
HB = Section(fuzzy=False)


def habitat_entity(h):
    match, code = "", ""
    for m in ("exactMatch", "closeMatch", "broadMatch"):
        if out[h].get(m):
            match, code = m.replace("Match", ""), loc(out[h][m][0])
            break
    return [one(h, "prefLabel") or one(h, "label"), code, match, labels(h)]


for ei in range(len(E)):
    for o in obs_by_entry.get(ei, []):
        lit = [str(x) for x in out[o].get("habitat", []) if not str(x).startswith("http")]
        for h in [x for x in out[o].get("habitat", []) if str(x).startswith("http")]:
            names = labels(h)
            written = next((l for l in lit if l in names), names[0] if names else loc(h))
            ent = HB.entity(h, habitat_entity(h))
            f = HB.form(written, ent)
            HB.mention(f, ei, written)
for f in HB.forms:
    ent = HB.ent[f[2]]
    lr = hlink.get(ent[0].lower(), {})
    cls = "V" if f[0] != ent[0] else ("R" if lr.get("status") == "review" else "E" if ent[1] else "N")
    f += [cls, (hmerge.get(f[0]) or {}).get("rule", ""),
          [lr.get(k, "") for k in ("status", "confidence", "note", "eunis_code", "eunis_label", "match")]]
print("habitats: entities", len(HB.ent), "forms", len(HB.forms), "mentions", len(HB.men),
      "classes", collections.Counter(f[3] for f in HB.forms))

# ---------------------------------------------------------------- QA flags, evaluation sample
qa_rows = read_csv(R / "qa_flags.csv")
QA = {"head": ["entry_id", "entry_uid", "reason", "action", "value", "detail"],
      "rows": [[r.get(k, "") for k in ("entry_id", "entry_uid", "reason", "action", "value", "detail")] for r in qa_rows],
      "ei": [uid2e.get(r["entry_uid"], -1) for r in qa_rows]}

rng = random.Random(args.seed)
by_vol = collections.defaultdict(list)
for i, m in enumerate(TX.men):
    by_vol[E[m[1]][5]].append(i)
total = len(TX.men)
SAMPLE = []
for vol, idx in sorted(by_vol.items()):
    k = max(1, round(args.sample * len(idx) / total))
    SAMPLE += rng.sample(idx, min(k, len(idx)))
rng.shuffle(SAMPLE)
print("evaluation sample", len(SAMPLE))

eunis = [[r["code"], r["label"], int(r["level"]), r["parent"]] for r in read_csv(Path(args.eunis))]


def pack(sec: Section):
    return {"ent": sec.ent, "forms": sec.forms, "men": sec.men}


# model second reading (second_reading.py): mention index -> suggestion, the
# named species resolved to a taxon of the graph where possible
SUG = {}
by_sci, by_de = {}, {}
for i, ent in enumerate(TX.ent):
    if ent[2]:
        if ent[1]:
            by_sci.setdefault(ent[1].lower(), i)
        for n in [ent[0]] + list(ent[9]):
            by_de.setdefault(n.lower(), i)
if args.second_reading and Path(args.second_reading).exists():
    answers = json.loads(Path(args.second_reading).read_text(encoding="utf-8"))
    occ = collections.Counter()
    for i, m in enumerate(TX.men):
        k = E[m[1]][1] + "|" + TX.forms[m[0]][0].lower()
        key = f"{k}|{occ[k]}"
        occ[k] += 1
        a = answers.get(key)
        if not a or not a.get("reading"):
            continue
        t = None
        if a.get("kind") == "bird":
            t = by_sci.get((a.get("sci") or "").lower().strip())
            if t is None:
                t = by_de.get((a.get("species_de") or "").lower().strip())
        try:
            conf = round(float(a.get("confidence") or 0), 2)
        except (TypeError, ValueError):
            conf = 0.0
        SUG[i] = [a["reading"], 1 if a.get("same") else 0, a.get("kind") or "", a.get("species_de") or "",
                  a.get("sci") or "", conf, (a.get("note") or "")[:300], -1 if t is None else t]
    print("second reading suggestions", len(SUG))

# merge candidates (which other entity could a name belong to; which foreign names could belong here)
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_candidates as MC
CAND = {"taxon": MC.taxa(TX), "person": MC.persons(PS), "place": MC.places(PL), "habitat": MC.habitats(HB)}
for k, v in CAND.items():
    print(k, "candidates: names with suggestions", len(v["nc"]), "entities with suggestions", len(v["ec"]))

# third reading (another model) per mention key, person matches per entity label
SUG3 = {}
if args.third_reading and Path(args.third_reading).exists():
    third = json.loads(Path(args.third_reading).read_text(encoding="utf-8"))
    occ = collections.Counter()
    for i, m in enumerate(TX.men):
        k = E[m[1]][1] + "|" + TX.forms[m[0]][0].lower()
        key = f"{k}|{occ[k]}"
        occ[k] += 1
        a = third.get(key)
        if not a or not a.get("reading"):
            continue
        t = None
        if a.get("kind") == "bird":
            t = by_sci.get((a.get("sci") or "").lower().strip())
            if t is None:
                t = by_de.get((a.get("species_de") or "").lower().strip())
        try:
            conf = round(float(a.get("confidence") or 0), 2)
        except (TypeError, ValueError):
            conf = 0.0
        SUG3[i] = [a["reading"], 1 if a.get("legible", True) else 0, a.get("kind") or "", a.get("species_de") or "",
                   a.get("sci") or "", conf, (a.get("note") or "")[:300], -1 if t is None else t]
    print("third reading answers", len(SUG3))
PM = {}
if args.person_matches and Path(args.person_matches).exists():
    pm = json.loads(Path(args.person_matches).read_text(encoding="utf-8"))
    for i, ent in enumerate(PS.ent):
        a = pm.get(ent[0])
        if a and a.get("decision"):
            try:
                conf = round(float(a.get("confidence") or 0), 2)
            except (TypeError, ValueError):
                conf = 0.0
            PM[i] = [a["decision"], conf, (a.get("reason") or "")[:400]]
    print("person matches", len(PM))


# machine review (tools/validation_ui/machine_review): verdicts per entity / name form, remapped by
# label and name so a rebuilt payload (other index order) still finds them
def _readings_table(path, label):
    out = {}
    if not path or not Path(path).exists():
        return out
    table = json.loads(Path(path).read_text(encoding="utf-8"))
    occ = collections.Counter()
    for i, m in enumerate(TX.men):
        k = E[m[1]][1] + "|" + TX.forms[m[0]][0].lower()
        key = f"{k}|{occ[k]}"
        occ[k] += 1
        a = table.get(key)
        if not a or not a.get("reading"):
            continue
        t = None
        if a.get("kind") == "bird":
            t = by_sci.get((a.get("sci") or "").lower().strip())
            if t is None:
                t = by_de.get((a.get("species_de") or "").lower().strip())
        try:
            conf = round(float(a.get("confidence") or 0), 2)
        except (TypeError, ValueError):
            conf = 0.0
        out[i] = [a["reading"], 1 if a.get("legible", True) else 0, a.get("kind") or "", a.get("species_de") or "",
                  a.get("sci") or "", conf, (a.get("note") or "")[:300], -1 if t is None else t]
    print(label, len(out))
    return out


SUGS = _readings_table(args.machine_readings, "machine readings")
MV = {"model": "", "built": "", "taxon": {"ent": {}, "form": {}}, "person": {"ent": {}}, "place": {"ent": {}}}
if args.machine_review and Path(args.machine_review).exists():
    mr = json.loads(Path(args.machine_review).read_text(encoding="utf-8"))
    MV["model"], MV["built"] = mr.get("model", ""), mr.get("built", "")
    tx_idx = {(e[0], e[2]): i for i, e in enumerate(TX.ent)}
    for k, v in (mr.get("taxon", {}).get("ent") or {}).items():
        i = tx_idx.get((v.get("label"), v.get("cur_key")))
        if i is None and k.isdigit() and int(k) < len(TX.ent) and TX.ent[int(k)][0] == v.get("label"):
            i = int(k)
        if i is not None:
            MV["taxon"]["ent"][i] = v
    tf_idx = {(f[0], TX.ent[f[2]][0]): i for i, f in enumerate(TX.forms)}
    for k, v in (mr.get("taxon", {}).get("form") or {}).items():
        i = tf_idx.get((v.get("name"), v.get("ent_label")))
        if i is None and k.isdigit() and int(k) < len(TX.forms) and TX.forms[int(k)][0] == v.get("name"):
            i = int(k)
        if i is not None:
            MV["taxon"]["form"][i] = v
    for sec, SEC in (("person", PS), ("place", PL)):
        idx = {}
        for i, e in enumerate(SEC.ent):
            idx.setdefault(e[0], i)
        for k, v in (mr.get(sec, {}).get("ent") or {}).items():
            i = idx.get(v.get("label"))
            if i is None and k.isdigit() and int(k) < len(SEC.ent) and SEC.ent[int(k)][0] == v.get("label"):
                i = int(k)
            if i is not None:
                MV[sec]["ent"][i] = v
    print("machine review: taxon entities", len(MV["taxon"]["ent"]), "forms", len(MV["taxon"]["form"]),
          "persons", len(MV["person"]["ent"]), "places", len(MV["place"]["ent"]))

payload = {"v": 4, "built": args.built, "export": args.export_name or R.resolve().parent.name,
           "E": E, "PG": PG, "taxon": pack(TX), "person": pack(PS), "place": pack(PL), "habitat": pack(HB),
           "qa": QA, "sample": SAMPLE, "eunis": eunis, "sug": SUG, "sug3": SUG3, "sugs": SUGS, "pm": PM, "cand": CAND, "mv": MV}
raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
gz = gzip.compress(raw, 9, mtime=0)
Path(args.out).write_text(base64.b64encode(gz).decode())
boxes = [m[4] for m in TX.men if isinstance(m[4], list) and len(m[4]) >= 5]
exact = sum(1 for b in boxes if len(b) > 5 and b[5] == 0)
print(f"taxon mentions with a line box: {len(boxes)}/{len(TX.men)} ({exact} on a profiled line, {len(boxes) - exact} estimated); text position: {sum(1 for m in TX.men if m[2] >= 0)}")
print(f"raw {len(raw) / 1e6:.1f} MB, gz {len(gz) / 1e6:.1f} MB -> {args.out}")
