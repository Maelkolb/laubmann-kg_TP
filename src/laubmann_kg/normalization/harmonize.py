"""One reading per shared node (taxa by vernacular name, places by name).

The model reads every record on its own, so the same written name can come
back with different details: "Brachvogel" as ``Numenius``/genus in 481 records
and as ``Numenius arquata``/species in 22; "Isar" as a locality here and a
region there. Taxon and Place nodes are keyed by the name alone, so the RDF
emitter would keep whichever instance it met first while the Darwin Core
Archive published every variant. This stage, run after QA and before linking,
gives every record of a name the same node: the most frequent reading of each
field (ties: the first in corpus order), and reports the names whose readings
disagreed. Linking and entity resolution then enrich that single node.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import replace

logger = logging.getLogger(__name__)

# Taxon fields the model reads per record; everything else on the Taxon is
# either the name itself or filled later by linking/resolution.
_TAXON_FIELDS = ("scientific_name", "rank", "is_bird", "match_method", "taxon_iri", "note")
_PLACE_FIELDS = ("kind", "elevation_m", "lat", "long")


def _majority(values: list):
    """Most frequent non-None value (first seen wins a tie), else None."""
    counts = Counter(v for v in values if v is not None)
    if not counts:
        return None
    best = max(counts.values())
    return next(v for v in values if v is not None and counts[v] == best)


def harmonize_taxa(entries) -> dict[str, dict]:
    """Give all records of a vernacular name one Taxon. The scientific name
    and rank are chosen together (the most frequent pair) so a genus name
    never ends up with rank species. Returns {name: {field: Counter}} for the
    names whose readings disagreed."""
    by_name: dict[str, list] = defaultdict(list)
    for entry in entries:
        for obs in entry.observations:
            by_name[obs.taxon.vernacular_de.lower()].append(obs)
    disagreements: dict[str, dict] = {}
    for name, records in by_name.items():
        taxa = [o.taxon for o in records]
        if len({(t.scientific_name, t.rank, t.is_bird) for t in taxa}) == 1:
            continue
        pair = _majority([(t.scientific_name, t.rank) for t in taxa if t.scientific_name] or
                         [(t.scientific_name, t.rank) for t in taxa])
        template = next(t for t in taxa if (t.scientific_name, t.rank) == pair)
        chosen = replace(template, is_bird=_majority([t.is_bird for t in taxa]))
        disagreements[name] = {
            "readings": Counter((t.scientific_name, t.rank) for t in taxa),
            "chosen": (chosen.scientific_name, chosen.rank),
        }
        for obs in records:
            # the record keeps its own confidence (QA reads it per record)
            obs.taxon = replace(chosen, confidence=obs.taxon.confidence)
    if disagreements:
        logger.info("harmonize: %d taxon names had differing readings, e.g. %s", len(disagreements),
                    "; ".join(f"{n}: {dict(d['readings'])} -> {d['chosen']}"
                              for n, d in list(disagreements.items())[:5]))
    return disagreements


def harmonize_places(entries) -> int:
    """Give all uses of a place name (entry places, record localities,
    effective places, travel places) one Place: kind, stated elevation and
    gazetteer coordinates by majority. Returns the number of names changed."""
    uses: dict[str, list] = defaultdict(list)

    def collect(place):
        if place is not None:
            uses[place.uid].append(place)

    for entry in entries:
        collect(entry.place)
        for obs in entry.observations:
            collect(obs.place)
            collect(obs.locality)
        for event in entry.travel_events:
            for leg in event.legs:
                collect(leg.departure_place)
                collect(leg.arrival_place)
                for via in leg.via_places:
                    collect(via)
    canonical = {}
    changed = 0
    for uid, places in uses.items():
        if len(set(places)) == 1:
            canonical[uid] = places[0]
            continue
        kwargs = {f: _majority([getattr(p, f) for p in places]) for f in ("kind", "elevation_m")}
        coords = _majority([(p.lat, p.long) for p in places if p.lat is not None])
        kwargs["lat"], kwargs["long"] = coords if coords else (None, None)
        canonical[uid] = replace(places[0], **kwargs)
        changed += 1

    def canon(place):
        return None if place is None else canonical.get(place.uid, place)

    for entry in entries:
        entry.place = canon(entry.place)
        for obs in entry.observations:
            obs.place = canon(obs.place)
            obs.locality = canon(obs.locality)
        for event in entry.travel_events:
            event.legs = [replace(leg, departure_place=canon(leg.departure_place),
                                  arrival_place=canon(leg.arrival_place),
                                  via_places=tuple(canon(v) for v in leg.via_places))
                          for leg in event.legs]
    if changed:
        logger.info("harmonize: %d place names had differing readings (kind/elevation/coordinates)", changed)
    return changed


def harmonize(result) -> dict:
    taxa = harmonize_taxa(result.entries)
    places = harmonize_places(result.entries)
    return {"taxa": len(taxa), "places": places}
