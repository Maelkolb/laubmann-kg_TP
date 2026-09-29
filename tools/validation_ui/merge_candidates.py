"""Merge candidates for the validation UI: which other entity might a written
name belong to, and which names of other entities might belong to an entity.

Computed once at build time from the payload sections (build_payload.py):

* taxa: a name equals a German name of another linked taxon (GBIF/Wikidata
  vernaculars), or its base word does ("Hausamsel" -> Amsel), or it is a close
  spelling of one (edit ratio >= 0.86);
* persons: same surname (after titles) and compatible given names/initials;
* places: same folded string, one name contained in the other (>= 6 letters),
  or a close spelling (>= 0.9);
* habitats: close spelling (>= 0.88) or same base word.

Result per section: ``nc`` (form index -> [[entity, score, why], ...]) and
``ec`` (entity -> [[form index, score, why], ...]), each list sorted by score
and cut to a handful, so the UI can offer "gehört zu …" and "gehört das dazu?".
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import defaultdict

UM = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
TITLES = re.compile(r"\b(dr|prof|herr|hr|frau|fr|frl|fraeulein|lehrer|oberlehrer|pfarrer|oberfoerster|foerster|forstmeister|cand|phil|med|rer|nat|stud|ing|hofrat|major|direktor|dir)\b\.?")
GENERIC = {"see", "wald", "garten", "park", "berg", "bach", "moos", "au", "auen", "teich", "weiher", "wiese", "feld", "hof", "damm", "strasse", "str", "brucke", "muhle"}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower().translate(UM)
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", fold(s))


def stem(s: str) -> str:
    k = letters(s)
    for suf in ("chen", "lein", "en", "n", "e", "s"):
        if k.endswith(suf) and len(k) - len(suf) >= 4:
            return k[: -len(suf)]
    return k


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _top(d: dict, k: int) -> dict:
    return {key: sorted(v, key=lambda x: (-x[1], x[0]))[:k] for key, v in d.items()}


def _keep(nc, ec, ok):
    """Drop candidate pairs (form -> entity) the authority records already rule out."""
    nc2 = {fi: [c for c in cs if ok(fi, c[0])] for fi, cs in nc.items()}
    ec2 = {ei: [c for c in cs if ok(c[0], ei)] for ei, cs in ec.items()}
    return {fi: cs for fi, cs in nc2.items() if cs}, {ei: cs for ei, cs in ec2.items() if cs}


def _dist_km(a, b):
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def _add(nc, ec, fi, ent, score, why):
    cur = nc[fi]
    for c in cur:
        if c[0] == ent:
            if score > c[1]:
                c[1], c[2] = score, why
            return
    cur.append([ent, score, why])
    ec[ent].append([fi, score, why])


def taxa(sec) -> dict:
    nc, ec = defaultdict(list), defaultdict(list)
    # index: stem -> entities (linked only), plus label stems for compound matching
    by_stem: dict[str, set] = defaultdict(set)
    label_stem: dict[int, str] = {}
    for ei, e in enumerate(sec.ent):
        if not e[2]:
            continue
        for n in [e[0]] + list(e[9]):
            if len(letters(n)) >= 4:
                by_stem[stem(n)].add(ei)
        label_stem[ei] = stem(e[0])
    stems = list(by_stem)
    for fi, f in enumerate(sec.forms):
        k = stem(f[0])
        if len(k) < 4:
            continue
        for ei in by_stem.get(k, ()):
            if ei != f[2]:
                _add(nc, ec, fi, ei, 3.0, "gleicher deutscher Name")
        # compound: the name ends with another taxon's label stem (Hausamsel -> Amsel)
        for ei, ls in label_stem.items():
            if ei != f[2] and len(ls) >= 5 and k != ls and k.endswith(ls):
                _add(nc, ec, fi, ei, 2.0, "Grundwort „" + sec.ent[ei][0] + "“")
        # spelling
        for s in stems:
            if abs(len(s) - len(k)) > 3 or s[0] != k[0] and s[:2] != k[:2]:
                continue
            r = ratio(k, s)
            if r >= 0.86:
                for ei in by_stem[s]:
                    if ei != f[2]:
                        _add(nc, ec, fi, ei, 1.0 + r / 2, f"ähnliche Schreibung ({r:.2f})")

    # an attested name (class A) of a taxon linked to another GBIF record is that species' name, not a variant
    def ok(fi, ei):
        f = sec.forms[fi]
        own = sec.ent[f[2]][2]
        return not (f[3] == "A" and own and own != sec.ent[ei][2])
    nc, ec = _keep(nc, ec, ok)
    return {"nc": _top(nc, 4), "ec": _top(ec, 12)}


def _parts(name: str):
    w = TITLES.sub(" ", fold(name)).replace("?", " ").split()
    w = [x for x in w if x]
    if not w:
        return "", []
    return w[-1], w[:-1]


def persons(sec) -> dict:
    nc, ec = defaultdict(list), defaultdict(list)
    by_sur: dict[str, list] = defaultdict(list)   # surname -> [(form index, givens, entity)]
    for fi, f in enumerate(sec.forms):
        sur, giv = _parts(f[0])
        if len(sur) >= 3:
            by_sur[sur].append((fi, giv, f[2]))
    for sur, rows in by_sur.items():
        ents = defaultdict(list)
        for fi, giv, ei in rows:
            ents[ei].append(giv)
        if len(ents) < 2:
            continue
        for fi, giv, ei in rows:
            for oe, givs in ents.items():
                if oe == ei:
                    continue
                ogiv = [g for gs in givs for g in gs]
                if not giv or not ogiv:
                    score, why = 1.0, "gleicher Nachname"
                else:
                    ok = any(g[0] == o[0] and (len(g) == 1 or len(o) == 1 or g == o or g.startswith(o) or o.startswith(g)) for g in giv for o in ogiv)
                    if not ok:
                        continue
                    score, why = 2.0, "gleicher Nachname, Vorname/Initiale passt"
                _add(nc, ec, fi, oe, score, why)

    # two persons with different Wikidata items are two persons
    def ok(fi, ei):
        own = sec.ent[sec.forms[fi][2]][1]
        return not (own and sec.ent[ei][1] and own != sec.ent[ei][1])
    nc, ec = _keep(nc, ec, ok)
    return {"nc": _top(nc, 4), "ec": _top(ec, 12)}


def places(sec) -> dict:
    nc, ec = defaultdict(list), defaultdict(list)
    key_of = {fi: letters(f[0]) for fi, f in enumerate(sec.forms)}
    by_key: dict[str, set] = defaultdict(set)
    for fi, k in key_of.items():
        if len(k) >= 4:
            by_key[k].add(sec.forms[fi][2])
    keys = [k for k in by_key if len(k) >= 6 and k not in GENERIC]
    by_first: dict[str, list] = defaultdict(list)
    for k in by_key:
        by_first[k[:3]].append(k)
    for fi, f in enumerate(sec.forms):
        k = key_of[fi]
        if len(k) < 4:
            continue
        for ei in by_key.get(k, ()):
            if ei != f[2]:
                _add(nc, ec, fi, ei, 3.0, "gleiche Schreibung")
        if len(k) >= 6 and k not in GENERIC:
            for o in keys:
                if o == k:
                    continue
                if k in o or o in k:
                    shorter = min(len(k), len(o))
                    if shorter >= 6 and shorter / max(len(k), len(o)) >= 0.45:
                        for ei in by_key[o]:
                            if ei != f[2]:
                                _add(nc, ec, fi, ei, 1.5, "Name enthalten")
        for o in by_first.get(k[:3], ()):
            if o == k or abs(len(o) - len(k)) > 3:
                continue
            r = ratio(k, o)
            if r >= 0.9:
                for ei in by_key[o]:
                    if ei != f[2]:
                        _add(nc, ec, fi, ei, 1.0 + r / 2, f"ähnliche Schreibung ({r:.2f})")

    # two georeferenced places with different GeoNames records, or more than 25 km apart, are two places
    def ok(fi, ei):
        a, b = sec.ent[sec.forms[fi][2]], sec.ent[ei]
        if a[4] and b[4] and a[4] != b[4]:
            return False
        if a[1] is not None and b[1] is not None and _dist_km((a[1], a[2]), (b[1], b[2])) > 25:
            return False
        return True
    nc, ec = _keep(nc, ec, ok)
    return {"nc": _top(nc, 4), "ec": _top(ec, 12)}


def habitats(sec) -> dict:
    nc, ec = defaultdict(list), defaultdict(list)
    st = {fi: stem(f[0]) for fi, f in enumerate(sec.forms)}
    by_stem: dict[str, set] = defaultdict(set)
    for fi, k in st.items():
        if len(k) >= 4:
            by_stem[k].add(sec.forms[fi][2])
    for fi, f in enumerate(sec.forms):
        k = st[fi]
        if len(k) < 4:
            continue
        for ei in by_stem.get(k, ()):
            if ei != f[2]:
                _add(nc, ec, fi, ei, 3.0, "gleiches Grundwort")
        for o, ents in by_stem.items():
            if o == k or abs(len(o) - len(k)) > 3 or o[0] != k[0]:
                continue
            r = ratio(k, o)
            if r >= 0.88:
                for ei in ents:
                    if ei != f[2]:
                        _add(nc, ec, fi, ei, 1.0 + r / 2, f"ähnliche Schreibung ({r:.2f})")
    return {"nc": _top(nc, 4), "ec": _top(ec, 12)}
