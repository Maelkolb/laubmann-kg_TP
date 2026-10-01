"""Reviewer corrections of single record fields, and records added by hand.

``review/value_corrections.csv`` fixes WHICH species, place or person a
mention is (and drops mentions that are none); ``review/text_corrections.csv``
and ``review/transcript_decisions.csv`` fix the text, after which the entry is
read again. What neither reaches is a record whose text is right but whose
reading by the extraction model is not: a count taken from the neighbouring
species, the locality of another line, an own count labelled a third-party
report, a record the model skipped. Those are decided per record in
``review/observation_corrections.csv`` and applied here, after the value
corrections and before coverage and QA.

CSV contract (one row per corrected field or added record; extra columns are
ignored)::

    entry_uid     required
    entry_id      informative
    written       the record's bird name as written (empty: the row is about the ENTRY)
    obs_index     the record's extraction index (the number its IRI is built from); preferred key
    occurrence    0-based index among the entry's records with that name; used when obs_index
                  is empty or no longer fits (after a re-extraction)
    action        set (default) | add (a record the text states and the graph misses)
    field         set:  count | locality | date | observer | co_observers | record_type | sex |
                        life_stage | breeding | status
                  set, entry rows (written empty):  entry_date | entry_kind
    new_value     the right value; "-" clears the field
                    count         5 · 3-5 · ca. 20 · mind. 30 · bis 20 · einige (no number)
                    date          YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD
                    observer      a name; "-" = the diarist himself
                    co_observers  names separated by ";"
                  add:  not used; the record comes from the columns below
    species_de, scientific_name, gbif_key, count, locality, date, observer, record_type, text
                  add only: the new record (species_de required; text = the passage)
    old_value, reason, note, reviewed_by, reviewed_at, confidence, sources   audit only

Every applied row and every row that matched nothing is reported as a QA flag
(``record_corrected`` / ``record_added`` / ``correction_unmatched``).
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.model import DiaryEntry, Observation, Person, Place, Taxon
from laubmann_kg.normalization import vocabularies as vocab
from laubmann_kg.normalization.corrections import _known_places, _known_taxa, _remark, _taxon_matches
from laubmann_kg.qa import QAFlag

logger = logging.getLogger(__name__)

FIELDS = ["entry_uid", "entry_id", "written", "obs_index", "occurrence", "action", "field", "new_value", "old_value",
          "species_de", "scientific_name", "gbif_key", "count", "locality", "date", "observer", "record_type", "text",
          "reason", "note", "reviewed_by", "reviewed_at"]
RECORD_FIELDS = ("count", "locality", "date", "observer", "co_observers", "record_type", "sex", "life_stage", "breeding", "status")
ENTRY_FIELDS = ("entry_date", "entry_kind")
CLEAR = {"-", "–", "—"}
_FIELD_DE = {"count": "Anzahl", "locality": "Ort", "date": "Datum", "observer": "Beobachter", "co_observers": "Mitbeobachter",
             "record_type": "Datensatztyp", "sex": "Geschlecht", "life_stage": "Stadium", "breeding": "Brutnachweis",
             "status": "Status", "entry_date": "Datum des Eintrags", "entry_kind": "Art des Eintrags"}
_DIARIST = {"ich", "laubmann", "a. laubmann", "alfred laubmann", "lbm", "verfasser"}
_ISO = r"\d{4}-\d{2}-\d{2}"


@dataclass(frozen=True)
class RecordCorrection:
    entry_uid: str
    entry_id: str = ""
    written: str = ""
    obs_index: Optional[int] = None
    occurrence: Optional[int] = None
    action: str = "set"                # set | add
    field: str = ""
    new: str = ""
    add: tuple[tuple[str, str], ...] = ()    # add: (column, value) pairs of the new record
    reason: str = ""


def load_observation_corrections(path, min_confidence: Optional[float] = None,
                                 min_agreement: Optional[int] = None) -> list[RecordCorrection]:
    """Read one observation_corrections.csv. ``min_confidence`` / ``min_agreement``
    filter rows by their ``confidence`` and ``agreement`` columns (machine files
    write them; rows without a value pass)."""
    if not path or not Path(path).is_file():
        logger.info("no observation corrections at %s", path)
        return []
    out: list[RecordCorrection] = []
    dropped = 0
    with open(path, newline="", encoding="utf-8") as handle:
        for i, row in enumerate(csv.DictReader(handle), 2):
            g = lambda k: (row.get(k) or "").strip()   # noqa: E731
            if min_confidence is not None and g("confidence"):
                try:
                    if float(g("confidence")) < min_confidence:
                        dropped += 1
                        continue
                except ValueError:
                    pass
            if min_agreement is not None and g("agreement").isdigit() and int(g("agreement")) < min_agreement:
                dropped += 1
                continue
            action = g("action").lower() or "set"
            num = lambda k: int(g(k)) if g(k).isdigit() else None   # noqa: E731
            if not g("entry_uid") or action not in ("set", "add"):
                logger.warning("%s:%d skipped (entry_uid/action invalid)", Path(path).name, i)
                continue
            if action == "add":
                if not g("species_de"):
                    logger.warning("%s:%d skipped (add needs species_de)", Path(path).name, i)
                    continue
                cols = ("species_de", "scientific_name", "gbif_key", "count", "locality", "date", "observer", "record_type", "text")
                out.append(RecordCorrection(g("entry_uid"), g("entry_id"), g("species_de"), action="add",
                                            add=tuple((c, g(c)) for c in cols if g(c)), reason=g("reason")))
                continue
            field = g("field").lower()
            if field not in RECORD_FIELDS + ENTRY_FIELDS or g("new_value") == "" or (field in RECORD_FIELDS) != bool(g("written")):
                logger.warning("%s:%d skipped (field/new_value/written invalid)", Path(path).name, i)
                continue
            out.append(RecordCorrection(g("entry_uid"), g("entry_id"), g("written"), num("obs_index"), num("occurrence"),
                                        "set", field, g("new_value"), reason=g("reason")))
    if dropped:
        logger.info("%s: %d corrections below the confidence/agreement thresholds skipped", Path(path).name, dropped)
    return out


# ------------------------------------------------------------------ values
_NUM = r"(\d[\d.' ]*\d|\d)"


def _int(text: str) -> int:
    return int(re.sub(r"[.' ]", "", text))


def parse_count(value: str) -> Optional[dict]:
    """A reviewer's count as the record fields it sets, or None when unreadable:
    ``5`` exact · ``3-5`` range · ``ca. 20`` approximate · ``mind. 30`` / ``über 30``
    / ``>30`` minimum · ``bis 20`` / ``<20`` maximum · words without a number
    (``einige``) plural-unspecified · ``-`` no count."""
    v = value.strip().lower()
    empty = {"individual_count": None, "count_min": None, "count_max": None, "count_qualifier": None}
    if v in CLEAR:
        return empty
    m = re.fullmatch(rf"(?:ca\.?|etwa|ungefähr|rund|gegen)?\s*{_NUM}\s*(?:-|–|bis)\s*{_NUM}", v)
    if m:
        lo, hi = sorted((_int(m.group(1)), _int(m.group(2))))
        if lo == hi:
            return dict(empty, individual_count=lo, count_qualifier="exact")
        return {"individual_count": lo, "count_min": lo, "count_max": hi, "count_qualifier": "approximate"}
    m = re.fullmatch(rf"(ca\.?|etwa|ungefähr|rund|gegen|an die|mind\.?|mindestens|über|ueber|>|>=|bis|bis zu|höchstens|max\.?|<|<=)?\s*{_NUM}\s*(\+)?", v)
    if m:
        cue, n, plus = (m.group(1) or "").rstrip("."), _int(m.group(2)), m.group(3)
        qualifier = ("approximate" if cue in ("ca", "etwa", "ungefähr", "rund", "gegen", "an die")
                     else "minimum" if cue in ("mind", "mindestens", "über", "ueber", ">", ">=") or plus
                     else "maximum" if cue in ("bis", "bis zu", "höchstens", "max", "<", "<=") else "exact")
        return dict(empty, individual_count=n, count_qualifier=qualifier)
    if re.search(r"\d", v):
        return None
    return dict(empty, count_qualifier="plural-unspecified")


def _dates(value: str) -> Optional[tuple[Optional[str], Optional[str]]]:
    v = value.strip()
    if v in CLEAR:
        return None, None
    m = re.fullmatch(rf"({_ISO})(?:\s*/\s*({_ISO}))?", v)
    if not m:
        return None
    end = m.group(2) if m.group(2) and m.group(2) > m.group(1) else None
    return m.group(1), end


def _person(name: str, entry: DiaryEntry, role: str) -> Optional[Person]:
    """The entry's person of that name, or a new one; None for the diarist."""
    name = name.strip()
    if not name or name in CLEAR or name.casefold().rstrip(".") in _DIARIST:
        return None
    for p in entry.persons:
        if p.name.casefold() == name.casefold():
            return p
    person = Person(name=name, role=role)
    entry.persons.append(person)
    return person


def _place(name: str, known: dict[str, Place]) -> Place:
    return known.get(name.casefold()) or Place(verbatim=name, kind="locality")


# ------------------------------------------------------------------ apply
def _find(entry: DiaryEntry, c: RecordCorrection) -> Optional[Observation]:
    named = [o for o in entry.observations if _taxon_matches(o.taxon, o.taxon_verbatim, c.written)]
    if c.obs_index is not None:
        hit = next((o for o in named if o.index == c.obs_index), None)
        if hit is not None:
            return hit
    if c.occurrence is not None:
        return named[c.occurrence] if c.occurrence < len(named) else None
    return named[0] if len(named) == 1 else None


def _set(entry: DiaryEntry, o: Observation, c: RecordCorrection, known_places: dict[str, Place]) -> Optional[str]:
    """Apply one field; returns the old value as text, or None when the new value is unusable."""
    v, clear = c.new.strip(), c.new.strip() in CLEAR
    if c.field == "count":
        fields = parse_count(v)
        if fields is None:
            return None
        old = (f"{o.count_min}-{o.count_max}" if o.count_min is not None and o.count_max is not None
               else "" if o.individual_count is None else str(o.individual_count))
        for k, x in fields.items():
            setattr(o, k, x)
        return old
    if c.field == "locality":
        old = o.locality.name if o.locality is not None else ""
        o.locality = None if clear else _place(v, known_places)
        o.place = o.locality if o.locality is not None else entry.place
        return old
    if c.field == "date":
        dates = _dates(v)
        if dates is None:
            return None
        old = o.event_date or ""
        o.event_date, o.event_date_end = dates
        return old
    if c.field == "observer":
        old = o.observer.name if o.observer is not None else ""
        o.observer = _person(v, entry, "source")
        return old
    if c.field == "co_observers":
        old = "; ".join(p.name for p in o.co_observers)
        people = [] if clear else [_person(n, entry, "companion") for n in v.split(";")]
        o.co_observers = [p for p in people if p is not None and p != o.observer]
        return old
    enums = {"record_type": ("record_type", vocab.RECORD_TYPES, False), "sex": ("sex", vocab.SEXES, True),
             "life_stage": ("life_stage", vocab.LIFE_STAGES, True), "breeding": ("breeding_evidence", vocab.BREEDING_EVIDENCE, True),
             "status": ("occurrence_status", vocab.OCCURRENCE_STATUS, False)}
    attr, vocabulary, clearable = enums[c.field]
    value = None if clear and clearable else vocab.normalize_enum(v, vocabulary)
    if value is None and not (clear and clearable):
        return None
    old = getattr(o, attr) or ""
    setattr(o, attr, value)
    if c.field == "status" and value == "absent":
        o.individual_count = o.count_min = o.count_max = o.count_qualifier = None
    return old


def _set_entry(entry: DiaryEntry, c: RecordCorrection) -> Optional[str]:
    if c.field == "entry_kind":
        kind = vocab.normalize_enum(c.new, vocab.ENTRY_KINDS)
        if kind is None:
            return None
        old, entry.entry_kind = entry.entry_kind or "", kind
        return old
    dates = _dates(c.new)
    if dates is None or dates[0] is None:
        return None
    old = entry.entry_date or ""
    entry.entry_date, entry.entry_date_end = dates
    entry.date_plausible = True
    entry.date_note = f"Datum bei der Durchsicht korrigiert (vorher: {old or 'ohne'})"
    return old


def _add(entry: DiaryEntry, c: RecordCorrection, known_taxa: dict[str, Taxon], known_places: dict[str, Place]) -> Optional[Observation]:
    row = dict(c.add)
    text = row.get("text") or row["species_de"]
    if any(o.verbatim_notes == text and _taxon_matches(o.taxon, o.taxon_verbatim, row["species_de"]) for o in entry.observations):
        return None                                      # the record exists (re-run, or the re-extraction found it)
    taxon = known_taxa.get(row["species_de"].casefold())
    sci = row.get("scientific_name") or None
    if taxon is None or (sci and taxon.scientific_name and taxon.scientific_name != sci):
        key = int(row["gbif_key"]) if row.get("gbif_key", "").isdigit() else None
        rank = ("species" if len(sci.split()) == 2 else "subspecies" if len(sci.split()) == 3 else None) if sci else None
        taxon = Taxon(vernacular_de=row["species_de"], scientific_name=sci, match_method="review", confidence=1.0, rank=rank,
                      is_bird=True, gbif_key=key, gbif_match_type="EXACT" if key else None, gbif_canonical_name=sci if key else None)
    o = Observation(entry_uid=entry.entry_uid, taxon=taxon, verbatim_notes=text, place=entry.place,
                    index=max((x.index for x in entry.observations), default=-1) + 1,
                    occurrence_remarks="Datensatz bei der Durchsicht ergänzt")
    for field in ("count", "locality", "date", "observer", "record_type"):
        if row.get(field):
            _set(entry, o, RecordCorrection(entry.entry_uid, written=row["species_de"], field=field, new=row[field]), known_places)
    if o.observer is not None and "record_type" not in row:
        o.record_type = "third-party-report"
    entry.observations.append(o)
    return o


def apply_observation_corrections(entries: list[DiaryEntry], corrections: list[RecordCorrection]) -> tuple[int, list[QAFlag]]:
    """Apply ``corrections`` in place. Returns (number of applied rows, flags)."""
    if not corrections:
        return 0, []
    by_uid = {e.entry_uid: e for e in entries}
    known_taxa, known_places = _known_taxa(entries), _known_places(entries)
    flags: list[QAFlag] = []
    applied = 0

    absent = 0

    def unmatched(c: RecordCorrection, why: str, warn: bool = True) -> None:
        what = f"{c.written or 'Eintrag'} · {_FIELD_DE.get(c.field, c.action)} → {c.new or '(neu)'}"
        flags.append(QAFlag(c.entry_id, c.entry_uid, "correction_unmatched", f"Korrektur „{what}“: {why}", "flagged", what))
        if warn:
            logger.warning("observation correction not applied (%s): %s %s", why, c.entry_uid, what)

    for c in corrections:
        entry = by_uid.get(c.entry_uid)
        if entry is None:
            absent += 1                 # a run over part of the corpus, or an entry QA excluded: flagged, one log line
            unmatched(c, "Eintrag nicht in diesem Lauf", warn=False)
            continue
        if c.action == "add":
            o = _add(entry, c, known_taxa, known_places)
            if o is not None:
                applied += 1
                flags.append(QAFlag(entry.entry_id, entry.entry_uid, "record_added",
                                    f"Datensatz „{c.written}“ bei der Durchsicht ergänzt" + (f"; {c.reason}" if c.reason else ""),
                                    "flagged", c.written))
            continue
        if c.field in ENTRY_FIELDS:
            old, target = _set_entry(entry, c), None
        else:
            target = _find(entry, c)
            if target is None:
                unmatched(c, "kein solcher Datensatz in diesem Eintrag")
                continue
            old = _set(entry, target, c, known_places)
        if old is None:
            unmatched(c, "Wert nicht lesbar")
            continue
        applied += 1
        label = _FIELD_DE[c.field]
        if target is not None:
            _remark(target, f"{label} bei der Durchsicht korrigiert: „{old or '—'}“ → „{c.new}“")
        flags.append(QAFlag(entry.entry_id, entry.entry_uid, "record_corrected",
                            f"{c.written + ': ' if c.written else ''}{label} „{old or '—'}“ → „{c.new}“"
                            + (f"; {c.reason}" if c.reason else ""), "flagged",
                            f"{c.written}|{c.field}|{c.new}" if c.written else f"{c.field}|{c.new}"))
    if absent:
        logger.warning("observation corrections: %d rows concern entries that are not in this run", absent)
    logger.info("observation corrections: %d rows, %d applied, %d unmatched", len(corrections), applied,
                sum(f.reason == "correction_unmatched" for f in flags))
    return applied, flags
