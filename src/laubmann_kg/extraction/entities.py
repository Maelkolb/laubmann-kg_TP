"""Extract named entities (taxa, persons, places) from an entry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from laubmann_kg.kg.model import DiaryEntry, Place
from laubmann_kg.normalization.persons import PersonMention, extract_persons
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import TaxonMention, find_taxa

logger = logging.getLogger(__name__)


@dataclass
class EntitySet:
    taxa: list[TaxonMention] = field(default_factory=list)
    persons: list[PersonMention] = field(default_factory=list)
    place: Optional[Place] = None


def extract_entities(entry: DiaryEntry) -> EntitySet:
    text = entry.text_clean or ""
    return EntitySet(
        taxa=find_taxa(text),
        persons=extract_persons(text),
        place=normalize_place(entry.location_raw),
    )
