"""Place and habitat resolution.

Places (``lkg:Place``, keyed by the model's cleaned name):

* ``orthographic``  – identical after folding (umlauts, ß, case, punctuation,
                      "St."/"Sankt", whitespace): auto.
* ``similar``       – folded keys with a high string similarity (default ≥ 0.9)
                      of the same place kind, or one of them without a kind:
                      ``candidate`` rows for review (a reviewer or an LLM
                      adjudicator decides; nothing is merged automatically).

Habitats (``skos:Concept`` labels): ``orthographic`` auto; ``similar`` (≥ 0.85)
candidates. Coordinates: when a merged variant carries coordinates and the
canonical does not, the canonical inherits them (same place). Canonical
spelling = most-used variant; merged spellings become ``skos:altLabel``.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import replace

from laubmann_kg.kg.model import Habitat, Place, TravelLeg
from laubmann_kg.resolution.common import Decisions, MergeRow, choose_canonical, fold, similarity

logger = logging.getLogger(__name__)


def _candidate_pairs(keys: list[str], threshold: float, max_bucket: int = 400) -> list[tuple[str, str, float]]:
    """Similar-key pairs; bucketed on the first three characters to stay cheap."""
    buckets: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        buckets[k[:3]].append(k)
    pairs = []
    for members in buckets.values():
        if len(members) > max_bucket:
            members = members[:max_bucket]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if abs(len(a) - len(b)) > max(3, int(0.3 * min(len(a), len(b)))):
                    continue
                r = similarity(a, b)
                if r >= threshold:
                    pairs.append((a, b, r))
    return pairs


# --------------------------------------------------------------------------
# places
# --------------------------------------------------------------------------

def _all_places(result):
    """Every Place object in the result with its usage count (entry places,
    observation places/localities, travel legs)."""
    usage: Counter = Counter()
    objs: dict[str, Place] = {}
    def see(p: Place, w: int = 1):
        if p is None:
            return
        usage[p.name] += w
        old = objs.get(p.name)
        # keep the richest instance (coordinates, kind)
        if old is None or (old.lat is None and p.lat is not None) or (not old.kind and p.kind):
            objs[p.name] = p
    for entry in result.entries:
        see(entry.place)
        for obs in entry.observations:
            see(obs.place); see(obs.locality)
        for ev in entry.travel_events:
            for leg in ev.legs:
                see(leg.departure_place); see(leg.arrival_place)
                for v in leg.via_places:
                    see(v)
    return usage, objs


def merge_places(result, cfg: dict, decisions: Decisions) -> tuple[int, list[MergeRow]]:
    cfg = cfg or {}
    threshold = float(cfg.get("similarity", 0.9))
    usage, objs = _all_places(result)
    if not objs:
        return 0, []
    by_key: dict[str, list[str]] = defaultdict(list)
    for name in objs:
        by_key[fold(name)].append(name)

    rows: list[MergeRow] = []
    mapping: dict[str, str] = {}
    # 1. orthographic
    for key, members in by_key.items():
        if len(members) < 2:
            continue
        canonical = choose_canonical([(m, usage[m]) for m in members])
        for m in members:
            if m == canonical:
                continue
            row = MergeRow("places", m, canonical, "orthographic", "auto", usage[m], usage[canonical],
                           f"kind {objs[m].kind or '-'} / {objs[canonical].kind or '-'}")
            rows.append(row)
            if decisions.applies(row):
                mapping[m] = canonical
    # 2. similar keys -> candidates (only across different key groups)
    rep_of_key = {k: choose_canonical([(m, usage[m]) for m in members]) for k, members in by_key.items()}
    for a, b, r in _candidate_pairs(sorted(by_key), threshold):
        na, nb = rep_of_key[a], rep_of_key[b]
        ka, kb = objs[na].kind, objs[nb].kind
        if ka and kb and ka != kb:
            continue
        canonical = choose_canonical([(na, usage[na]), (nb, usage[nb])]); variant = nb if canonical == na else na
        row = MergeRow("places", variant, canonical, "similar", "candidate", usage[variant], usage[canonical],
                       f"similarity {r:.2f}; kind {objs[variant].kind or '-'} / {objs[canonical].kind or '-'}")
        rows.append(row)
        if decisions.applies(row):
            mapping[variant] = mapping.get(canonical, canonical)

    if not mapping:
        return 0, rows
    # resolve chains and build canonical objects
    def root(n):
        seen = set()
        while n in mapping and n not in seen:
            seen.add(n); n = mapping[n]
        return n
    alts: dict[str, list[str]] = defaultdict(list)
    for m in list(mapping):
        c = root(m)
        mapping[m] = c
        alts[c].append(m)
    canon: dict[str, Place] = {}
    for c, variants in alts.items():
        base = objs[c]
        lat, long = base.lat, base.long
        if lat is None:
            for v in variants:
                if objs[v].lat is not None:
                    lat, long = objs[v].lat, objs[v].long
                    break
        kind = base.kind or next((objs[v].kind for v in variants if objs[v].kind), None)
        canon[c] = replace(base, lat=lat, long=long, kind=kind, alt_names=tuple(sorted(set(variants))))

    def fix(p):
        if p is None:
            return None
        if p.name in mapping:
            return canon[mapping[p.name]]
        if p.name in canon:
            return canon[p.name]
        return p
    n = 0
    for entry in result.entries:
        if entry.place is not None and entry.place.name in mapping: n += 1
        entry.place = fix(entry.place)
        for obs in entry.observations:
            if obs.place is not None and obs.place.name in mapping: n += 1
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
    logger.info("places: %d spellings merged into %d places (%d references re-pointed)", len(mapping), len(canon), n)
    return len(mapping), rows


# --------------------------------------------------------------------------
# habitats
# --------------------------------------------------------------------------

def merge_habitats(result, cfg: dict, decisions: Decisions) -> tuple[int, list[MergeRow]]:
    cfg = cfg or {}
    threshold = float(cfg.get("similarity", 0.85))
    usage: Counter = Counter()
    for entry in result.entries:
        for obs in entry.observations:
            if obs.habitat is not None:
                usage[obs.habitat.label] += 1
    if not usage:
        return 0, []
    by_key: dict[str, list[str]] = defaultdict(list)
    for label in usage:
        by_key[fold(label)].append(label)
    rows: list[MergeRow] = []
    mapping: dict[str, str] = {}
    for key, members in by_key.items():
        if len(members) < 2:
            continue
        canonical = choose_canonical([(m, usage[m]) for m in members])
        for m in members:
            if m == canonical:
                continue
            row = MergeRow("habitats", m, canonical, "orthographic", "auto", usage[m], usage[canonical])
            rows.append(row)
            if decisions.applies(row):
                mapping[m] = canonical
    rep_of_key = {k: choose_canonical([(m, usage[m]) for m in members]) for k, members in by_key.items()}
    for a, b, r in _candidate_pairs(sorted(by_key), threshold):
        na, nb = rep_of_key[a], rep_of_key[b]
        canonical = choose_canonical([(na, usage[na]), (nb, usage[nb])]); variant = nb if canonical == na else na
        row = MergeRow("habitats", variant, canonical, "similar", "candidate", usage[variant], usage[canonical],
                       f"similarity {r:.2f}")
        rows.append(row)
        if decisions.applies(row):
            mapping[variant] = mapping.get(canonical, canonical)
    if not mapping:
        return 0, rows
    def root(n):
        seen = set()
        while n in mapping and n not in seen:
            seen.add(n); n = mapping[n]
        return n
    alts: dict[str, list[str]] = defaultdict(list)
    for m in list(mapping):
        c = root(m); mapping[m] = c; alts[c].append(m)
    canon = {c: Habitat(c, alt_labels=tuple(sorted(set(v)))) for c, v in alts.items()}
    n = 0
    for entry in result.entries:
        for obs in entry.observations:
            h = obs.habitat
            if h is None:
                continue
            if h.label in mapping:
                obs.habitat = canon[mapping[h.label]]; n += 1
            elif h.label in canon:
                obs.habitat = canon[h.label]
    logger.info("habitats: %d labels merged into %d concepts (%d observations re-pointed)", len(mapping), len(canon), n)
    return len(mapping), rows
