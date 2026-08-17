"""Knowledge graph domain model mirroring ontologies/laubmann.ttl."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

DATA_NS = "https://lkg.example.org/data/"
ONTO_NS = "https://lkg.example.org/ontology#"


def _slug(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


@dataclass(frozen=True)
class DiaryVolume:
    number: int

    @property
    def uid(self) -> str:
        return f"volume_{self.number:02d}"

    @property
    def label(self) -> str:
        return f"Laubmann · Band {self.number:02d}"


@dataclass(frozen=True)
class DiaryPage:
    page_uid: str
    volume: int
    page_id: str
    scan: Optional[str] = None

    @property
    def uid(self) -> str:
        return f"page_{self.page_uid}"

    @property
    def label(self) -> str:
        scan = f" · scan {self.scan}" if self.scan else ""
        return f"Vol. {self.volume:02d}{scan} ({self.page_id})"


@dataclass(frozen=True)
class Taxon:
    vernacular_de: str
    scientific_name: Optional[str] = None
    taxon_iri: Optional[str] = None
    match_method: str = "unresolved"
    confidence: Optional[float] = None
    note: Optional[str] = None
    gbif_key: Optional[int] = None            # GBIF backbone usage key (accepted taxon)
    gbif_match_type: Optional[str] = None     # EXACT | FUZZY | HIGHERRANK
    gbif_canonical_name: Optional[str] = None
    rank: Optional[str] = None                # vocab.TAXON_RANKS — rank at which the diarist named it
    is_bird: Optional[bool] = None            # model's judgement; None = not stated

    @property
    def uid(self) -> str:
        return f"taxon_{_slug(self.vernacular_de.lower())}"


@dataclass(frozen=True)
class Place:
    verbatim: str
    canonical: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None
    kind: Optional[str] = None                # vocab.PLACE_KINDS (settlement|locality|region|route|unknown)

    @property
    def name(self) -> str:
        return self.canonical or self.verbatim

    @property
    def uid(self) -> str:
        return f"place_{_slug((self.canonical or self.verbatim).lower())}"


@dataclass(frozen=True)
class Habitat:
    label: str

    @property
    def uid(self) -> str:
        return f"habitat_{_slug(self.label.lower())}"


@dataclass(frozen=True)
class Person:
    name: str
    role: Optional[str] = None  # companion | source | collector | cited-author | other
    wikidata_iri: Optional[str] = None  # http://www.wikidata.org/entity/Q... (verified)

    @property
    def uid(self) -> str:
        return f"person_{_slug(self.name.lower())}"


@dataclass(frozen=True)
class TravelLeg:
    departure_place: Place
    arrival_place: Place
    via_places: tuple[Place, ...] = ()
    transport_mode: str = "unknown"
    departure_time: Optional[str] = None  # xsd:dateTime (entry date + stated clock time)
    arrival_time: Optional[str] = None
    verbatim: Optional[str] = None

    def uid(self, event_uid: str, index: int) -> str:
        return f"leg_{event_uid}_{index}"


@dataclass
class TravelEvent:
    entry_uid: str
    legs: list[TravelLeg] = field(default_factory=list)
    index: int = 0

    @property
    def uid(self) -> str:
        return f"travel_{self.entry_uid}_{self.index}"


@dataclass(frozen=True)
class Evidence:
    kind: str  # visual | auditory | nest | specimen
    label: str
    occurrence_status: str = "present"
    is_call: bool = False
    call_type: Optional[str] = None
    call_transcription: Optional[str] = None

    def uid(self, obs_uid: str, index: int = 0) -> str:
        # index keeps evidences of the same kind on one observation distinct, so
        # e.g. two bird calls do not collapse onto one node (SHACL callTranscription
        # requires exactly one value per BirdCall).
        return f"evidence_{obs_uid}_{self.kind}_{index}"


@dataclass(frozen=True)
class Behaviour:
    label: str
    reproductive_condition: Optional[str] = None

    def uid(self, obs_uid: str) -> str:
        return f"behaviour_{obs_uid}_{_slug(self.label.lower(), 8)}"


@dataclass(frozen=True)
class WeatherReport:
    verbatim: str                            # primary; mapper guarantees non-empty
    temperature_value: Optional[float] = None
    temperature_unit: Optional[str] = None   # C | R | F — never unit-converted
    precipitation: Optional[str] = None      # vocab.PRECIPITATION_TYPES
    wind: Optional[str] = None               # free German text
    sky: Optional[str] = None                # vocab.SKY_CONDITIONS

    def uid(self, entry_uid: str) -> str:
        return f"weather_{entry_uid}"


@dataclass
class Observation:
    entry_uid: str
    taxon: Taxon
    verbatim_notes: str
    place: Optional[Place] = None             # EFFECTIVE place: own locality, else the entry place
    individual_count: Optional[int] = None    # >= 0; 0 only with occurrence_status == "absent"
    count_qualifier: Optional[str] = None
    evidence: list[Evidence] = field(default_factory=list)   # empty = the text does not say how
    behaviour: list[Behaviour] = field(default_factory=list)
    habitat: Optional[Habitat] = None
    occurrence_remarks: Optional[str] = None
    index: int = 0
    record_type: str = "field-observation"    # vocab.RECORD_TYPES
    observer: Optional[Person] = None         # None = the diarist
    literature_citation: Optional[str] = None
    # --- model-provided detail (all optional; None = not stated in the text) ---
    locality: Optional[Place] = None          # the record's OWN place when it differs from the entry place
    occurrence_status: str = "present"        # vocab.OCCURRENCE_STATUS (present|absent)
    count_min: Optional[int] = None           # range lower bound ("3-4" -> 3)
    count_max: Optional[int] = None           # range upper bound ("3-4" -> 4)
    sex: Optional[str] = None                 # vocab.SEXES
    life_stage: Optional[str] = None          # vocab.LIFE_STAGES
    breeding_evidence: Optional[str] = None   # vocab.BREEDING_EVIDENCE (atlas-style)
    vitality: Optional[str] = None            # vocab.VITALITY (dead when stated; None = alive/not stated)
    movement_kind: Optional[str] = None       # vocab.MOVEMENT_KINDS
    flight_direction: Optional[str] = None    # as written ("NO→SW")
    identification_qualifier: Optional[str] = None  # the diarist's own hedge as written ("?", "wohl", "cf.")
    event_date: Optional[str] = None          # ISO date of THIS record when it differs from the entry date
    event_time: Optional[str] = None          # "HH:MM" when the record states a clock time
    flags: tuple[str, ...] = ()               # mapper notes for QA (e.g. "record_type_conflict")

    @property
    def uid(self) -> str:
        base = f"{self.entry_uid}|{self.taxon.vernacular_de}|{self.index}"
        return f"obs_{_slug(base)}"


@dataclass
class DiaryEntry:
    entry_uid: str
    entry_id: str
    volume: int
    page_uid: str
    page_id: str
    region_uid: Optional[str]
    scan: Optional[str]
    entry_date: Optional[str]  # ISO YYYY-MM-DD (header date, possibly corrected by the model)
    verbatim_event_date: Optional[str]
    location_raw: Optional[str]
    text_clean: str
    observations: list[Observation] = field(default_factory=list)
    travel_events: list[TravelEvent] = field(default_factory=list)
    persons: list[Person] = field(default_factory=list)
    weather: Optional[WeatherReport] = None
    # --- entry-level reading (model-provided for the LLM backend) ---
    place: Optional[Place] = None             # the entry's main locality (cleaned; kind in vocab.PLACE_KINDS)
    entry_kind: Optional[str] = None          # vocab.ENTRY_KINDS
    entry_date_end: Optional[str] = None      # ISO date; multi-day entries only
    date_plausible: Optional[bool] = None     # model: False = header date contradicted and not repairable
    date_note: Optional[str] = None           # model's German note on a corrected/doubted date
    header_date: Optional[str] = None         # upstream ISO date before any model correction

    @property
    def uid(self) -> str:
        return f"entry_{self.entry_uid}"

    @property
    def label(self) -> str:
        loc = self.place.name if self.place is not None else self.location_raw
        loc = f" · {loc}" if loc else ""
        date = self.verbatim_event_date or self.entry_date or "o. D."
        return f"Tagebucheintrag {date}{loc}"


DIARIST = Person(name="Alfred Laubmann")
# DIARIST.uid == "person_c6b2ff6250e5" — byte-identical to the URI hardcoded in
# HistOrniGraph_addons/kg_enrich/attribute_observers.py, which this supersedes.
