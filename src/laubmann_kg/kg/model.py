"""Knowledge graph domain model mirroring ontologies/laubmann.ttl (0.7.0).

The dataclasses are the contract between extraction and emission. Not every
dataclass is a node in the graph: ``Evidence``, ``Behaviour`` and ``Habitat``
are emitter inputs — the RDF emitter turns evidence into ``lkg:evidenceKind``
concept links (calls into ``lkg:callType`` / ``lkg:callTranscription`` on the
observation itself), behaviour into ``dwc:behavior`` literals and habitat into
a shared ``skos:Concept`` node. External links (GBIF, EUNIS, GeoNames,
Wikidata, GND) are read off the fields below by ``kg/authority.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal, Optional

DATA_NS = "https://w3id.org/laubmann-kg/data/"
ONTO_NS = "https://w3id.org/laubmann-kg/ontology#"


def data_iri(uid: str) -> str:
    """The global identifier of a node: its IRI in the data namespace. The
    Darwin Core Archive uses the same strings as eventID / occurrenceID."""
    return DATA_NS + uid


# Place.georef_source -> dwc:georeferenceSources (one wording for RDF and DwC-A)
GEOREF_SOURCES = {
    "gazetteer": "built-in gazetteer of the project (normalization/places.py)",
    "osm+geonames": "OpenStreetMap/Nominatim name match confirmed by GeoNames (point = GeoNames feature)",
    "osm": "OpenStreetMap/Nominatim name match",
    "geonames": "GeoNames name match (unique in the home region)",
    "reviewed": "reviewer decision (validation UI)",
    "machine-review": "machine review of the place link (LLM subagents with gazetteer checks)",
}

TimeOfDay = Literal["dawn", "morning", "forenoon", "noon", "afternoon", "evening", "dusk", "night"]

# GBIF backbone ranks carried on a linked Taxon (dwc:kingdom … dwc:genus), in
# hierarchy order. Mirrors the field names of the GBIF species/match response.
HIGHER_RANKS = ("kingdom", "phylum", "class", "order", "family", "genus")


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
    # GBIF backbone classification of the linked taxon: ((rank, name), ...) in
    # HIGHER_RANKS order, only ranks GBIF returned. Empty when unlinked.
    higher_taxonomy: tuple[tuple[str, str], ...] = ()
    # vernacular spellings merged into this taxon by entity resolution (same
    # GBIF accepted key); emitted as skos:altLabel. The canonical name stays
    # vernacular_de, so the uid does not move.
    alt_names: tuple[str, ...] = ()

    @property
    def uid(self) -> str:
        return f"taxon_{_slug(self.vernacular_de.lower())}"

    def higher_rank(self, rank: str) -> Optional[str]:
        """Name at ``rank`` (e.g. "family") from the GBIF classification, or None."""
        for r, name in self.higher_taxonomy:
            if r == rank:
                return name
        return None


@dataclass(frozen=True)
class Place:
    verbatim: str
    canonical: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None
    kind: Optional[str] = None                # vocab.PLACE_KINDS (settlement|locality|region)
    alt_names: tuple[str, ...] = ()           # merged spellings (entity resolution) -> skos:altLabel
    elevation_m: Optional[float] = None       # stated elevation ("Oberstdorf 843 m") -> dwc:minimum/maximumElevationInMeters
    # linking/places.py: gazetteer identity of the georeference
    geonames_id: Optional[int] = None         # -> skos:exactMatch|closeMatch https://sws.geonames.org/<id>/
    wikidata_iri: Optional[str] = None        # -> skos:exactMatch|closeMatch (same grade as the georeference)
    coordinate_uncertainty_m: Optional[int] = None   # -> dwc:coordinateUncertaintyInMeters (centroid radius)
    georef_source: Optional[str] = None       # gazetteer | osm | osm+geonames | geonames | reviewed -> dwc:georeferenceSources

    @property
    def name(self) -> str:
        return self.canonical or self.verbatim

    @property
    def uid(self) -> str:
        return f"place_{_slug((self.canonical or self.verbatim).lower())}"


@dataclass(frozen=True)
class Habitat:
    """A habitat label; emitted as a shared skos:Concept in lkg:habitatScheme
    (one node per label, reached from observations via dwciri:habitat)."""
    label: str
    alt_labels: tuple[str, ...] = ()          # merged spellings (entity resolution) -> skos:altLabel
    # linking/habitats.py: EUNIS class (2012) the label maps to
    eunis_code: Optional[str] = None          # "G1.2"
    eunis_label: Optional[str] = None         # "Mixed riparian floodplain and gallery woodland"
    eunis_match: Optional[str] = None         # exact | close | broad -> skos:exactMatch/closeMatch/broadMatch
    eunis_uri: Optional[str] = None           # http://eunis.eea.europa.eu/eunishabitats/G1.2
    eunis_parents: tuple[tuple[str, str, str], ...] = ()   # ((code, label, uri), ...) up to the level-1 group

    @property
    def uid(self) -> str:
        return f"habitat_{_slug(self.label.lower())}"


@dataclass(frozen=True)
class Person:
    name: str
    role: Optional[str] = None  # companion | source | collector | cited-author | other
    wikidata_iri: Optional[str] = None  # http://www.wikidata.org/entity/Q... (verified)
    alt_names: tuple[str, ...] = ()     # merged name variants (entity resolution) -> skos:altLabel
    gnd_iri: Optional[str] = None       # https://d-nb.info/gnd/<id> (reviewer-added, person_link_review.csv gnd)
    wikidata_match: Optional[str] = None  # exact (reviewed) | close (automatic unique-label match); None = close
    gnd_match: Optional[str] = None     # exact (human review) | close (machine review); None = exact

    @property
    def uid(self) -> str:
        return f"person_{_slug(self.name.lower())}"


@dataclass(frozen=True)
class TravelLeg:
    departure_place: Optional[Place]          # None: the text does not say where the leg began
    arrival_place: Place
    via_places: tuple[Place, ...] = ()
    transport_mode: Optional[str] = None      # vocab.TRANSPORT_MODES; None = not stated
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
    call_type: Optional[str] = None           # song | call | alarm | drumming; None/"unknown" = not stated
    call_transcription: Optional[str] = None  # the diarist's phonetic rendering, as written


@dataclass(frozen=True)
class Behaviour:
    """A noted behaviour; emitted as a dwc:behavior literal (no node)."""
    label: str
    reproductive_condition: Optional[str] = None


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
    co_observers: list[Person] = field(default_factory=list)   # companions observing WITH the diarist
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
    event_date_end: Optional[str] = None      # last day when the record's own date is a range
    event_time: Optional[str] = None          # "HH:MM" when the record states a clock time
    # --- spatial / temporal qualification (0.5.0, tightened 0.7.0: only what the text states) ---
    spatial_context: Optional[str] = None     # the observer's vantage as written ("vom Fenster")
    microhabitat: Optional[str] = None        # where on/in the habitat ("Teichufer", "Baumkrone")
    relative_elevation: Optional[str] = None  # flight height as written ("in mäßiger Höhe")
    altitude_m: Optional[float] = None        # metres above sea level stated for the record's own site
    time_of_day: Optional[TimeOfDay] = None   # vocab.TIME_OF_DAY (dawn … night)
    flags: tuple[str, ...] = ()               # mapper notes for QA (e.g. "record_type_conflict")
    taxon_verbatim: Optional[str] = None      # the taxon name as written, when resolution merged it
                                              # into a canonical taxon (-> dwc:verbatimIdentification)

    @property
    def uid(self) -> str:
        base = f"{self.entry_uid}|{self.taxon_verbatim or self.taxon.vernacular_de}|{self.index}"
        return f"obs_{_slug(base)}"

    @property
    def recorders(self) -> list[Person]:
        """Everyone who recorded the occurrence (dwciri:recordedBy): the
        diarist and his companions for his own records; the observer for a
        third-party record; nobody for an unattributed report or citation."""
        if self.record_type == "field-observation":
            lead = [self.observer] if self.observer is not None else [DIARIST]
        else:
            lead = [self.observer] if self.observer is not None else []
        return lead + [p for p in self.co_observers if p not in lead]


@dataclass(frozen=True)
class SourceRegionRef:
    """A body-text layout region an entry's text was read from (the first is
    the header region; an entry continuing over pages has one per page)."""
    region_uid: str
    page_uid: str
    page_id: str
    scan: Optional[str] = None


@dataclass
class MultimodalRegion:
    """A drawing, map, photograph, mounted object or inserted text placed with
    an entry (multimodal catalogue v2 / text-inserts catalogue), relinked to the
    entry that precedes it in reading order."""
    region_uid: str
    page_uid: str
    page_id: str
    volume: int
    scan: Optional[str]
    entry_uid: Optional[str]
    kind: str                                 # vocab.REGION_KINDS
    description: Optional[str] = None         # layout model's description (English)
    visible_text: Optional[str] = None        # text on the region as transcribed
    crop: Optional[str] = None                # regions/<page_id>/<file>.png
    region_type: Optional[str] = None         # layout type (ImageRegion, ObjectRegion, ParagraphRegion …)

    @property
    def uid(self) -> str:
        return f"region_{self.region_uid}"


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
    # every body-text region the entry's text runs through (corpus span); empty
    # = only the header region (region_uid) is known
    source_regions: list[SourceRegionRef] = field(default_factory=list)
    # patched corpus: tail of the text before an entry split off at a boundary
    # (pasted report, digest); shown to the model for attribution only
    context_before: Optional[str] = None
    # patched corpus: kind of the reviewed boundary the entry starts at
    # (correspondence | species-digest | field-day | …) and its source
    boundary_kind: Optional[str] = None
    boundary_source: Optional[str] = None
    multimodal: list[MultimodalRegion] = field(default_factory=list)
    # extraction notes for QA (e.g. "truncated_output": the model hit its token cap)
    flags: list[str] = field(default_factory=list)
    # visual reading (prompt v5): the model compared the transcription with the
    # page scans; text_clean holds the corrected reading, text_transcribed the
    # transcription as it came from the corpus
    transcript_quality: Optional[str] = None          # good | minor | poor | illegible
    transcript_corrections: list[tuple[str, str, bool]] = field(default_factory=list)  # (old, new, applied)
    text_transcribed: Optional[str] = None
    # the end of the entry before and the beginning of the entry after this one
    # in the volume (reading pass only: their text is not this entry's)
    neighbour_before: Optional[str] = None
    neighbour_after: Optional[str] = None
    reading_notes: list[str] = field(default_factory=list)   # reviewer corrections of the transcription (skos:note)

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
