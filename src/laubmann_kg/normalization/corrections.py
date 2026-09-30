"""Reviewer value corrections: single mentions fixed by hand.

The transcription sometimes misreads exactly the value that matters
("Rehhenne" for „Birkhenne" -> the model calls it a roe deer and QA drops the
observation; heading "Rauchschwalben" for „Kaufbeuren" -> no entry place), or
the model assigns one mention of a name to the wrong thing ("Tirol" in a list
of birds is a misread Pirol, elsewhere the region). A reviewer records the
decision for ONE entry in ``review/value_corrections.csv`` (a misreading is a
property of one handwritten line, never of every entry with the same reading,
so there is no corpus-wide scope; name-level decisions live in
``review/identities.csv``). This stage applies them right after extraction,
before coverage and QA, so QA, linking, resolution and the export all see the
corrected value. The transcription and the LLM cache stay untouched (misread
TEXT is fixed with ``review/text_corrections.csv``, see review/readings.py).

CSV contract (one row per correction; extra columns are ignored)::

    kind             taxon | place | person | habitat
    entry_uid        required (entry_id alone is accepted as a fallback)
    entry_id         informative
    old_value        the value as extracted (the written name of the mention)
    occurrence       optional: 0-based index among the entry's mentions with that name
                     (taxa; default: all of them)
    action           replace (default) | drop (the mention is not a taxon/place/person/habitat)
    new_value        replace: the right value (taxon/place/person name)
    scientific_name  taxon only, optional: used when the corrected name occurs nowhere else in the run
    gbif_key         taxon only, optional: the reviewed GBIF taxon of the corrected name
    is_bird          taxon only, optional: n/no/0 when the corrected organism is not a bird (default: bird)
    reason, note, reviewed_by, reviewed_at   audit only

Resolution of the corrected value: if the new name already occurs elsewhere in
the run, that Taxon/Place object is reused (it carries the model's scientific
name, rank and bird judgement, or the place kind and coordinates); otherwise a
new object is built from the row. Every applied correction and every row that
matched nothing is reported as a QA flag (``value_corrected`` /
``value_dropped`` / ``correction_unmatched``), so the audit trail ends up in
``review/qa_flags.csv``.
"""

from __future__ import annotations

import csv
import dataclasses
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from laubmann_kg.kg.model import DiaryEntry, Person, Place, Taxon
from laubmann_kg.qa import QAFlag

logger = logging.getLogger(__name__)

FIELDS = ["kind", "entry_uid", "entry_id", "old_value", "occurrence", "action", "new_value",
          "scientific_name", "gbif_key", "is_bird", "reason", "note", "reviewed_by", "reviewed_at"]
KINDS = ("taxon", "place", "person", "habitat")
_NO = {"n", "no", "0", "false", "nein"}
_KIND_DE = {"taxon": "Art", "place": "Ort", "person": "Person", "habitat": "Lebensraum"}


@dataclass(frozen=True)
class Correction:
    kind: str                       # taxon | place | person | habitat
    old: str
    new: str = ""
    entry_uid: str = ""
    entry_id: str = ""
    scientific_name: str = ""
    is_bird: bool = True
    note: str = ""
    action: str = "replace"         # replace | drop
    occurrence: Optional[int] = None
    gbif_key: Optional[int] = None
    reason: str = ""

    def covers(self, entry: DiaryEntry) -> bool:
        if self.entry_uid:
            return entry.entry_uid == self.entry_uid
        return bool(self.entry_id) and entry.entry_id == self.entry_id


def load_corrections(path, min_confidence: Optional[float] = None) -> list[Correction]:
    """Read one value_corrections.csv. ``min_confidence`` filters rows by their
    ``confidence`` column (the machine review writes one; rows without the
    column pass), so machine corrections can be taken above a threshold only."""
    path = Path(path)
    if not path.exists():
        logger.info("no value corrections at %s", path)
        return []
    out: list[Correction] = []
    dropped = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for i, row in enumerate(csv.DictReader(handle), 2):
            g = lambda k: (row.get(k) or "").strip()   # noqa: E731
            if min_confidence is not None and g("confidence"):
                try:
                    if float(g("confidence")) < min_confidence:
                        dropped += 1
                        continue
                except ValueError:
                    pass
            kind, action = g("kind").lower(), (g("action").lower() or "replace")
            if kind not in KINDS or action not in ("replace", "drop") or not g("old_value") \
                    or (action == "replace" and not g("new_value")):
                logger.warning("%s:%d skipped (kind/action/old_value/new_value invalid)", path.name, i)
                continue
            if action == "replace" and kind == "habitat":
                logger.warning("%s:%d skipped (a habitat mention can only be dropped; EUNIS classes are name-level)", path.name, i)
                continue
            if not (g("entry_uid") or g("entry_id")) or g("scope").lower() not in ("", "entry"):
                logger.warning("%s:%d skipped (corrections apply to one entry: entry_uid required)", path.name, i)
                continue
            occ = g("occurrence")
            key = g("gbif_key")
            out.append(Correction(kind, g("old_value"), g("new_value"), g("entry_uid"), g("entry_id"),
                                  g("scientific_name"), g("is_bird").lower() not in _NO, g("note"), action,
                                  int(occ) if occ.isdigit() else None, int(key) if key.isdigit() else None, g("reason")))
    if dropped:
        logger.info("%s: %d corrections below the confidence threshold %.2f skipped", path.name, dropped, min_confidence)
    return out


def _same(a: Optional[str], b: str) -> bool:
    return a is not None and a.strip().casefold() == b.strip().casefold()


def _taxon_matches(taxon: Taxon, verbatim: Optional[str], old: str) -> bool:
    return _same(taxon.vernacular_de, old) or _same(verbatim, old)


def _place_matches(place: Optional[Place], old: str) -> bool:
    return place is not None and (_same(place.verbatim, old) or _same(place.canonical, old) or _same(place.name, old))


def _known_taxa(entries: Iterable[DiaryEntry]) -> dict[str, Taxon]:
    """Best Taxon object per vernacular name (casefolded): the most frequent
    variant that carries a scientific name, else the most frequent."""
    seen: dict[str, Counter] = {}
    for e in entries:
        for o in e.observations:
            seen.setdefault(o.taxon.vernacular_de.casefold(), Counter())[o.taxon] += 1
    best = {}
    for key, cnt in seen.items():
        ranked = sorted(cnt.items(), key=lambda kv: (kv[0].scientific_name is None, kv[0].is_bird is False, -kv[1]))
        best[key] = ranked[0][0]
    return best


def _known_places(entries: Iterable[DiaryEntry]) -> dict[str, Place]:
    seen: dict[str, Counter] = {}
    for e in entries:
        places = [e.place] + [o.place for o in e.observations] + [o.locality for o in e.observations]
        for p in places:
            if p is not None:
                seen.setdefault(p.name.casefold(), Counter())[p] += 1
    return {k: sorted(c.items(), key=lambda kv: (kv[0].lat is None, kv[0].kind is None, -kv[1]))[0][0]
            for k, c in seen.items()}


def _new_taxon(c: Correction, known: dict[str, Taxon]) -> Taxon:
    t = known.get(c.new.casefold())
    if t is not None and not (c.scientific_name and t.scientific_name != c.scientific_name) \
            and not (c.gbif_key and t.gbif_key and t.gbif_key != c.gbif_key):
        return t
    sci = c.scientific_name or None
    rank = ("species" if len(sci.split()) == 2 else "subspecies" if len(sci.split()) == 3 else None) if sci else None
    return Taxon(vernacular_de=c.new, scientific_name=sci, match_method="review", confidence=1.0,
                 rank=rank, is_bird=c.is_bird, note="Name bei der Durchsicht korrigiert",
                 gbif_key=c.gbif_key, gbif_match_type="EXACT" if c.gbif_key else None,
                 gbif_canonical_name=sci if c.gbif_key else None)


def _new_place(c: Correction, known: dict[str, Place]) -> Place:
    return known.get(c.new.casefold()) or Place(verbatim=c.new)


def _remark(obs, text: str) -> None:
    obs.occurrence_remarks = f"{obs.occurrence_remarks}; {text}" if obs.occurrence_remarks else text


def _fix_legs(entry: DiaryEntry, old: str, new: Place) -> int:
    n = 0
    for ev in entry.travel_events:
        legs = []
        for leg in ev.legs:
            changes = {}
            if _place_matches(leg.departure_place, old):
                changes["departure_place"] = new
            if _place_matches(leg.arrival_place, old):
                changes["arrival_place"] = new
            via = tuple(new if _place_matches(p, old) else p for p in leg.via_places)
            if via != leg.via_places:
                changes["via_places"] = via
            n += bool(changes)
            legs.append(dataclasses.replace(leg, **changes) if changes else leg)
        ev.legs = legs
    return n


def _taxon_hits(e: DiaryEntry, c: Correction) -> list:
    hits = [o for o in e.observations if _taxon_matches(o.taxon, o.taxon_verbatim, c.old)]
    if c.occurrence is not None:
        return hits[c.occurrence:c.occurrence + 1]
    return hits


def _apply_taxon(e: DiaryEntry, c: Correction, known_taxa) -> int:
    hits = _taxon_hits(e, c)
    if c.action == "drop":
        e.observations = [o for o in e.observations if not any(o is h for h in hits)]
        return len(hits)
    new = _new_taxon(c, known_taxa)
    for o in hits:
        o.taxon, o.taxon_verbatim = new, None
        _remark(o, f"Artname bei der Durchsicht korrigiert: „{c.old}“ → „{c.new}“")
    return len(hits)


def _drop_place(e: DiaryEntry, old: str) -> int:
    """The name is no place: remove it as entry place and as record locality;
    the records' effective place falls back to their locality or the entry place."""
    n = 0
    old_entry = e.place
    if _place_matches(e.place, old):
        e.place = None
        n += 1
    for o in e.observations:
        if _place_matches(o.locality, old):
            o.locality = None
            n += 1
        if _place_matches(o.place, old) or (old_entry is not e.place and o.place is old_entry):
            o.place = o.locality if o.locality is not None else e.place
            n += 1
    return n


def _apply_place(e: DiaryEntry, c: Correction, known_places) -> int:
    if c.action == "drop":
        return _drop_place(e, c.old)
    n = 0
    new = _new_place(c, known_places)
    # the entry place, or a heading the model could not use as a place (QA "nonplace")
    old_entry_place = e.place
    header_only = e.place is None and _same(e.location_raw, c.old)
    if _place_matches(e.place, c.old) or header_only:
        e.place = new
        n += 1
    entry_changed = e.place is not old_entry_place
    for o in e.observations:
        if _place_matches(o.locality, c.old):
            o.locality = new
            n += 1
        # effective place: the record's own locality, else the entry place
        if o.locality is not None:
            target = o.locality
        elif _place_matches(o.place, c.old):
            target = new
        elif (o.place is None and header_only) or (entry_changed and o.place is old_entry_place):
            target = e.place
        else:
            continue
        if o.place is not target:
            o.place = target
            n += 1
    return n + _fix_legs(e, c.old, new)


def _apply_person(e: DiaryEntry, c: Correction) -> int:
    n = 0
    if c.action == "drop":
        before = len(e.persons)
        e.persons = [p for p in e.persons if not _same(p.name, c.old)]
        n = before - len(e.persons)
        for o in e.observations:
            if o.observer is not None and _same(o.observer.name, c.old):
                o.observer = None              # not a person: the record is the diarist's
                n += 1
            kept = [p for p in o.co_observers if not _same(p.name, c.old)]
            n += len(o.co_observers) - len(kept)
            o.co_observers = kept
        return n
    persons = []
    for p in e.persons:
        if _same(p.name, c.old):
            p = dataclasses.replace(p, name=c.new, wikidata_iri=None, gnd_iri=None, alt_names=())
            n += 1
        persons.append(p)
    e.persons = persons
    for o in e.observations:
        if o.observer is not None and _same(o.observer.name, c.old):
            o.observer = dataclasses.replace(o.observer, name=c.new, wikidata_iri=None, gnd_iri=None, alt_names=())
            n += 1
        renamed = []
        for p in o.co_observers:
            if _same(p.name, c.old):
                p = dataclasses.replace(p, name=c.new, wikidata_iri=None, gnd_iri=None, alt_names=())
                n += 1
            renamed.append(p)
        o.co_observers = renamed
    return n


def _drop_habitat(e: DiaryEntry, old: str) -> int:
    n = 0
    for o in e.observations:
        if o.habitat is not None and (_same(o.habitat.label, old) or any(_same(a, old) for a in o.habitat.alt_labels)):
            o.habitat = None
            n += 1
    return n


def apply_corrections(entries: list[DiaryEntry], corrections: list[Correction]) -> tuple[int, list[QAFlag]]:
    """Apply ``corrections`` in place. Returns (number of changed values, flags)."""
    if not corrections:
        return 0, []
    known_taxa, known_places = _known_taxa(entries), _known_places(entries)
    flags: list[QAFlag] = []
    total = 0
    for c in corrections:
        hits = 0
        for e in entries:
            if not c.covers(e):
                continue
            if c.kind == "taxon":
                n = _apply_taxon(e, c, known_taxa)
            elif c.kind == "place":
                n = _apply_place(e, c, known_places)
            elif c.kind == "person":
                n = _apply_person(e, c)
            else:
                n = _drop_habitat(e, c.old)
            if n:
                hits += 1
                total += n
                what = _KIND_DE[c.kind]
                if c.action == "drop":
                    flags.append(QAFlag(e.entry_id, e.entry_uid, "value_dropped",
                        f"{what} „{c.old}“ bei der Durchsicht entfernt ({n}×)" + (f"; {c.reason}" if c.reason else "")
                        + (f"; {c.note}" if c.note else ""), "excluded", c.old))
                else:
                    flags.append(QAFlag(e.entry_id, e.entry_uid, "value_corrected",
                        f"{what} korrigiert: „{c.old}“ → „{c.new}“ ({n}×)" + (f"; {c.note}" if c.note else ""),
                        "flagged", f"{c.old} -> {c.new}"))
        if not hits:
            flags.append(QAFlag(c.entry_id or "", c.entry_uid or "", "correction_unmatched",
                f"{c.kind}-Korrektur „{c.old}“ → „{c.new or '(entfernen)'}“ passt auf keinen Wert dieses Eintrags",
                "flagged", f"{c.old} -> {c.new}"))
            logger.warning("value correction matched nothing: %s %r -> %r (%s)", c.kind, c.old, c.new, c.entry_uid or c.entry_id)
    logger.info("value corrections: %d rows, %d values changed, %d unmatched", len(corrections), total,
                sum(f.reason == "correction_unmatched" for f in flags))
    return total, flags


def apply_identity_removals(entries: list[DiaryEntry], ids) -> list[QAFlag]:
    """Name-level ``none`` decisions of review/identities.csv: the reviewer saw
    the mentions of a name and decided it is no taxon / person / place /
    habitat at all (a misreading, another organism). Every mention of the name
    is removed; one QA flag per entry."""
    if not ids:
        return []
    flags: list[QAFlag] = []
    kinds = (("taxa", "taxon"), ("persons", "person"), ("places", "place"), ("habitats", "habitat"))
    for e in entries:
        for section, kind in kinds:
            for ident in ids.forms[section].values():
                if ident.decision != "none":
                    continue
                c = Correction(kind, ident.name, action="drop", entry_uid=e.entry_uid, reason=ident.reason)
                n = (_apply_taxon(e, c, {}) if kind == "taxon" else _drop_place(e, ident.name) if kind == "place"
                     else _apply_person(e, c) if kind == "person" else _drop_habitat(e, ident.name))
                if n:
                    flags.append(QAFlag(e.entry_id, e.entry_uid, "review_not_" + kind,
                                        f"„{ident.name}“ ist laut Durchsicht kein(e) {_KIND_DE[kind]}"
                                        + (f" ({ident.reason})" if ident.reason else "") + f" ({n}×)", "excluded", ident.name))
    if flags:
        logger.info("reviewed identities: %d name-level removals", len(flags))
    return flags
