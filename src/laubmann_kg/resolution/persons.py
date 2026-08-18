"""Person resolution: name variants of one person become one node.

Rules (deterministic, conservative — every merge lands in ``person_merges.csv``
where a reviewer can reject it):

* ``same-key``        – identical after title stripping / umlaut folding /
                        punctuation ("Dr. Wüst" = "Wuest" = "Wüst.").
* ``wikidata``        – same Wikidata item (linking stage verified it).
* ``initial-unique``  – "W. Wüst" → "Walter Wüst": initial(s) match and there
                        is exactly one full-name person with that surname.
* ``surname-unique``  – bare "Wüst" → "Walter Wüst": exactly one person with
                        that surname exists (no other full names, initials or
                        gendered forms). Family members are kept apart because
                        "Frau …" / "Frl. …" / "Fräulein …" / "Fr. …" stay in the key.
* ``dominant``        – an initial or bare surname that fits several persons is
                        merged into the one that carries ≥ ``dominant_min`` (5)
                        uses and ≥ ``dominant_ratio`` (5) × the runner-up
                        ("A. Müller" → Adolf Müller 3093 vs. Arno Müller 30).

Remaining ambiguous cases (initial matches several full names, bare surname
with several comparable candidates) are written as ``candidate`` rows and
applied only after a reviewer accepts them. The canonical name is the most complete spelling
(most name tokens, then most observations, diacritics preferred); the
diarist (``model.DIARIST``) is never merged into anything else.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import replace

from laubmann_kg.kg.model import DIARIST, Person
from laubmann_kg.resolution.common import Decisions, MergeRow, fold

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(
    r"^(?:(?:prof|dr|dipl|ing|med|phil|jur|rer|nat|h\.?c|geheimrat|oberst|major|pfarrer|baron|graf|"
    r"freiherr|frhr|forstmeister|oberfoerster|oberförster|foerster|förster|revierfoerster|revierförster|"
    r"hofrat|sanitaetsrat|sanitätsrat|studienrat|oberstudienrat|oberlehrer|hauptlehrer|lehrer|rektor|"
    r"direktor|inspektor|oberinspektor|oberpostmeister|postmeister|apotheker|kaplan|dekan|pater|"
    r"praeparator|präparator|kustos|konservator|assessor|referendar|herr|hr|cand|stud)\.?\s+)+", re.IGNORECASE)
# words that mark a "name" as a description rather than a person ("Freunden mit Gattin aus Bonn")
_NON_NAME = ("mit", "aus", "und", "von", "der", "die", "des", "dem", "freund", "freunde", "freunden",
             "gattin", "familie", "sohn", "tochter", "frau", "bruder", "schwester", "kollege")
# "Fr." is ambiguous in the diaries (Frau / Fräulein / Freund) -> kept as a distinguishing token like Frau/Frl.
_GENDERED = ("frau", "frl", "fraeulein", "fräulein", "fr")


def person_key(name: str) -> str:
    """Comparison key: titles stripped (gendered forms kept), folded, punctuation
    turned into spaces so initials survive as single-letter tokens."""
    n = _TITLE_RE.sub("", (name or "").strip())
    n = re.sub(r"\.", ". ", n)          # "W.Wüst" -> "W. Wüst"
    return fold(n)


def _parts(key: str) -> tuple[list[str], list[str], str]:
    """(initials, first names, surname) from a folded key."""
    toks = key.split()
    if not toks:
        return [], [], ""
    surname = toks[-1]
    initials = [t for t in toks[:-1] if len(t) == 1]
    firsts = [t for t in toks[:-1] if len(t) > 1 and t not in _GENDERED]   # "Frl." is a marker, not a first name
    return initials, firsts, surname


def _is_gendered(key: str) -> bool:
    return bool(key) and key.split()[0] in _GENDERED


def _dominant(clusters, usage, min_uses: int, ratio: float):
    """The cluster root that clearly dominates the others by (cluster) usage, or None."""
    ranked = sorted(clusters, key=lambda c: -usage(c))
    top = usage(ranked[0])
    second = usage(ranked[1]) if len(ranked) > 1 else 0
    if top >= min_uses and top >= ratio * max(second, 1):
        return ranked[0]
    return None


def merge_persons(result, cfg: dict, decisions: Decisions) -> tuple[int, list[MergeRow]]:
    cfg = cfg or {}
    allow_surname = bool(cfg.get("merge_bare_surname", True))
    dominant_min = int(cfg.get("dominant_min", 5))
    dominant_ratio = float(cfg.get("dominant_ratio", 5.0))
    # collect names with usage counts (mentions + observer attributions)
    usage: Counter = Counter()
    wikidata: dict[str, str] = {}
    for entry in result.entries:
        for p in entry.persons:
            usage[p.name] += 1
            if p.wikidata_iri:
                wikidata[p.name] = p.wikidata_iri
        for obs in entry.observations:
            if obs.observer is not None:
                usage[obs.observer.name] += 1
                if obs.observer.wikidata_iri:
                    wikidata[obs.observer.name] = obs.observer.wikidata_iri
    usage.pop(DIARIST.name, None)
    names = sorted(usage)
    if not names:
        return 0, []

    # union-find over names; has_full[root] = the cluster contains a full name
    parent = {n: n for n in names}
    keys = {n: person_key(n) for n in names}
    has_full = {n: bool(_parts(keys[n])[1]) for n in names}
    rule_of: dict[str, str] = {}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b, rule):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            has_full[ra] = has_full[ra] or has_full[rb]
            rule_of[b] = rule

    # 1. same key
    by_key: dict[str, list[str]] = defaultdict(list)
    for n in names:
        by_key[person_key(n)].append(n)
    for key, members in by_key.items():
        for m in members[1:]:
            union(members[0], m, "same-key")
    # 2. same Wikidata item
    by_qid: dict[str, list[str]] = defaultdict(list)
    for n, q in wikidata.items():
        if n in usage:
            by_qid[q].append(n)
    for q, members in by_qid.items():
        for m in members[1:]:
            union(members[0], m, "wikidata")

    # 3./4. initials and bare surnames against full names (per surname);
    # initials first so a bare surname sees the already-joined clusters; a name
    # whose cluster already holds a full name is resolved and skipped
    def cluster_usage(root):
        return sum(usage[m] for m in names if find(m) == find(root))
    by_surname: dict[str, list[str]] = defaultdict(list)
    for n, k in keys.items():
        _, _, s = _parts(k)
        if s:
            by_surname[s].append(n)
    candidates: list[MergeRow] = []
    for surname, members in by_surname.items():
        full = [n for n in members if _parts(keys[n])[1] and not _is_gendered(keys[n])]
        for n in members:
            initials, firsts, _ = _parts(keys[n])
            if firsts or _is_gendered(keys[n]) or len(surname) < 4 or not initials or has_full[find(n)]:
                continue
            full_clusters = {find(m) for m in full}
            fits = [c for c in full_clusters
                    if any(all(any(f.startswith(i) for f in _parts(keys[m])[1]) for i in initials)
                           for m in full if find(m) == c)]
            if len(fits) == 1:
                union(next(iter(fits)), n, "initial-unique")
            elif len(fits) > 1:
                dom = _dominant(fits, cluster_usage, dominant_min, dominant_ratio)
                if dom is not None:
                    union(dom, n, "dominant")
                else:
                    for c in fits:
                        candidates.append(MergeRow("persons", n, c, "initial-ambiguous", "candidate",
                                                   usage[n], cluster_usage(c), f"initials {''.join(initials)} match several full names"))
    if allow_surname:
        for surname, members in by_surname.items():
            for n in members:
                initials, firsts, _ = _parts(keys[n])
                if firsts or initials or _is_gendered(keys[n]) or len(surname) < 4 or has_full[find(n)]:
                    continue
                # gendered forms ("Frau Wüst") never absorb a bare surname
                others = {find(m) for m in members if find(m) != find(n) and not _is_gendered(keys[m])}
                if len(others) == 1:
                    union(next(iter(others)), n, "surname-unique")
                elif others:
                    dom = _dominant(others, cluster_usage, dominant_min, dominant_ratio)
                    if dom is not None:
                        union(dom, n, "dominant")
                    else:
                        for c in others:
                            candidates.append(MergeRow("persons", n, c, "surname-ambiguous", "candidate",
                                                       usage[n], cluster_usage(c), f"bare surname; {len(others)} persons share it"))

    # canonical per cluster
    clusters: dict[str, list[str]] = defaultdict(list)
    for n in names:
        clusters[find(n)].append(n)
    rows: list[MergeRow] = []
    mapping: dict[str, str] = {}
    def completeness(n):
        k = keys[n]; init, firsts, _ = _parts(k)
        toks = k.split()
        return (not _is_gendered(k), not any(w in _NON_NAME for w in toks), len(firsts),
                sum(len(f) for f in firsts) + len(init), usage[n],
                sum(1 for ch in n if ch in "äöüÄÖÜß"), -len(n))
    for root, members in clusters.items():
        if len(members) < 2:
            continue
        canonical = max(members, key=completeness)
        for m in members:
            if m == canonical:
                continue
            row = MergeRow("persons", m, canonical, rule_of.get(m) or rule_of.get(canonical) or "same-key",
                           "auto", usage[m], usage[canonical], "")
            rows.append(row)
            if decisions.applies(row):
                mapping[m] = canonical
    # accepted candidates
    for row in candidates:
        rows.append(row)
        if decisions.applies(row) and row.variant not in mapping:
            mapping[row.variant] = mapping.get(row.canonical, row.canonical)

    if not mapping:
        return 0, rows
    alts: dict[str, list[str]] = defaultdict(list)
    for m, c in mapping.items():
        alts[c].append(m)
    canon_person: dict[str, Person] = {}
    def canonical_person(name: str, template: Person) -> Person:
        c = mapping.get(name, name)
        if c not in canon_person:
            qid = wikidata.get(c) or next((wikidata[v] for v in alts.get(c, []) if v in wikidata), None)
            canon_person[c] = Person(name=c, role=None, wikidata_iri=qid, alt_names=tuple(sorted(set(alts.get(c, [])))))
        base = canon_person[c]
        return replace(base, role=template.role) if template.role else base

    merged = 0
    for entry in result.entries:
        new_persons: list[Person] = []
        seen_names: set[str] = set()
        for p in entry.persons:
            q = canonical_person(p.name, p) if (p.name in mapping or p.name in alts) else p
            if q.name != p.name:
                merged += 1
            if q.name in seen_names:
                # keep the first mention's role edge; a second variant of the same
                # person in one entry adds no information
                continue
            seen_names.add(q.name)
            new_persons.append(q)
        entry.persons = new_persons
        for obs in entry.observations:
            if obs.observer is not None and (obs.observer.name in mapping or obs.observer.name in alts):
                if obs.observer.name in mapping:
                    merged += 1
                obs.observer = canonical_person(obs.observer.name, obs.observer)
    logger.info("persons: %d names merged into %d persons (%d references re-pointed)",
                len(mapping), len(alts), merged)
    return len(mapping), rows
