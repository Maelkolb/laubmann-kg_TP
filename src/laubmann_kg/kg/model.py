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

    @property
    def uid(self) -> str:
        return f"taxon_{_slug(self.vernacular_de.lower())}"


@dataclass(frozen=True)
class Place:
    verbatim: str
    canonical: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None

    @property
    def name(self) -> str:
        return self.canonical or self.verbatim

    @property
    def uid(self) -> str:
        return f"place_{_slug((self.canonical or self.verbatim).lower())}"


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


@dataclass
class Observation:
    entry_uid: str
    taxon: Taxon
    verbatim_notes: str
    place: Optional[Place] = None
    individual_count: Optional[int] = None
    count_qualifier: Optional[str] = None
    evidence: list[Evidence] = field(default_factory=list)
    behaviour: list[Behaviour] = field(default_factory=list)
    occurrence_remarks: Optional[str] = None
    index: int = 0

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
    entry_date: Optional[str]  # ISO YYYY-MM-DD
    verbatim_event_date: Optional[str]
    location_raw: Optional[str]
    text_clean: str
    observations: list[Observation] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return f"entry_{self.entry_uid}"

    @property
    def label(self) -> str:
        loc = f" · {self.location_raw}" if self.location_raw else ""
        date = self.verbatim_event_date or self.entry_date or "o. D."
        return f"Tagebucheintrag {date}{loc}"
