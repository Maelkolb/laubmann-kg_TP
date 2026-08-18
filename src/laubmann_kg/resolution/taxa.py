"""Taxon resolution: vernacular spellings that resolve to the same taxon become
one node.

Two rules, both authority-backed (no string guessing):

* ``gbif-key``        – same accepted GBIF usage key with an EXACT or FUZZY match
                        at species/subspecies level. HIGHERRANK anchors and
                        names the model ranked genus/family/group are NOT merged:
                        two vernaculars that share a genus or family may still be
                        different concepts.
* ``scientific-name`` – same scientific name from the resolver/gazetteer when no
                        GBIF key is available (optional, on by default).

The canonical spelling is the most-used variant; the others become
``skos:altLabel`` and every merged observation keeps its written name in
``dwc:verbatimIdentification`` (``Observation.taxon_verbatim``), so the
observation IRI does not change.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import replace

from laubmann_kg.resolution.common import Decisions, MergeRow, choose_canonical

logger = logging.getLogger(__name__)

_MERGEABLE_MATCH = ("EXACT", "FUZZY")
_SUPRASPECIFIC = ("genus", "family", "group")   # model rank: names above species level are not merged


def merge_taxa(result, cfg: dict, decisions: Decisions) -> tuple[int, list[MergeRow]]:
    cfg = cfg or {}
    on_sci = bool(cfg.get("merge_on_scientific_name", True))
    # vernacular (lower) -> (representative Taxon, n observations)
    seen: dict[str, tuple] = {}
    for entry in result.entries:
        for obs in entry.observations:
            key = obs.taxon.vernacular_de.lower()
            t, n = seen.get(key, (obs.taxon, 0))
            seen[key] = (t if t.gbif_key or not obs.taxon.gbif_key else obs.taxon, n + 1)

    groups: dict[str, list[str]] = defaultdict(list)
    for key, (taxon, _) in seen.items():
        if taxon.rank in _SUPRASPECIFIC:
            continue        # "Ente" (family) and "Raubmöwe" (genus) stay separate concepts
        if taxon.gbif_key and taxon.gbif_match_type in _MERGEABLE_MATCH:
            groups[f"gbif:{taxon.gbif_key}"].append(key)
        elif on_sci and taxon.scientific_name and not taxon.gbif_key:
            groups[f"sci:{taxon.scientific_name.strip().lower()}"].append(key)

    rows: list[MergeRow] = []
    mapping: dict[str, str] = {}          # variant key -> canonical key
    for gkey, members in groups.items():
        if len(members) < 2:
            continue
        canonical = choose_canonical([(seen[m][0].vernacular_de, seen[m][1]) for m in members]).lower()
        rule = "gbif-key" if gkey.startswith("gbif:") else "scientific-name"
        for m in members:
            if m == canonical:
                continue
            row = MergeRow("taxa", seen[m][0].vernacular_de, seen[canonical][0].vernacular_de, rule, "auto",
                           seen[m][1], seen[canonical][1],
                           gkey + (f" · {seen[canonical][0].scientific_name}" if seen[canonical][0].scientific_name else ""))
            rows.append(row)
            if decisions.applies(row):
                mapping[m] = canonical

    if not mapping:
        return 0, rows
    # canonical taxon objects with their alt names
    alts: dict[str, list[str]] = defaultdict(list)
    for m, c in mapping.items():
        alts[c].append(seen[m][0].vernacular_de)
    canon: dict[str, object] = {c: replace(seen[c][0], alt_names=tuple(sorted(set(v)))) for c, v in alts.items()}

    merged = 0
    for entry in result.entries:
        for obs in entry.observations:
            key = obs.taxon.vernacular_de.lower()
            if key in mapping:
                written = obs.taxon.vernacular_de
                obs.taxon = canon[mapping[key]]
                obs.taxon_verbatim = written
                merged += 1
            elif key in canon:
                obs.taxon = canon[key]        # canonical spelling gains its altLabels
    logger.info("taxa: %d spellings merged into %d taxa (%d observations re-pointed)",
                len(mapping), len(canon), merged)
    return len(mapping), rows
