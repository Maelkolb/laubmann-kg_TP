"""Rule-based extraction of ornithological observations from entry text.

Deterministic and network-free: bird mentions are found with the gazetteer
matcher; evidence, counts, and behaviour are inferred from nearby diary phrasing.
Uncertainty is preserved (verbatim name + null scientific name) rather than
invented. An LLM backend can replace this via config without changing callers.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from laubmann_kg.kg.model import Behaviour, DiaryEntry, Evidence, Observation, Place, Taxon
from laubmann_kg.normalization import vocabularies as vocab
from laubmann_kg.normalization.taxa import TaxonResolver, find_taxa

logger = logging.getLogger(__name__)

_SENTENCE_RE = re.compile(r"[^.!?]*[.!?]|[^.!?]+$")
_NUMBER_RE = re.compile(r"\b(\d{1,4})\b")


def _sentence_at(text: str, position: int) -> str:
    for match in _SENTENCE_RE.finditer(text):
        if match.start() <= position < match.end():
            return match.group(0).strip()
    return text.strip()


def _evidence(sentence: str) -> tuple[list[Evidence], list[Behaviour]]:
    low = sentence.lower()
    evidence: list[Evidence] = []
    behaviour: list[Behaviour] = []

    if any(cue in low for cue in vocab.NEST_CUES):
        evidence.append(Evidence("nest", "Nestfund / Brutnachweis"))
        behaviour.append(Behaviour("Brüten / besetztes Nest", reproductive_condition="breeding"))
    if any(cue in low for cue in vocab.SPECIMEN_CUES):
        evidence.append(Evidence("specimen", "Beleg / erlegtes Stück"))
    if any(cue in low for cue in vocab.AUDITORY_CUES):
        call_type = "unknown"
        if any(cue in low for cue in vocab.SONG_CUES):
            call_type = "song"
        elif any(cue in low for cue in vocab.DRUMMING_CUES):
            call_type = "drumming"
        else:
            call_type = "call"
        evidence.append(Evidence("auditory", "Lautäußerung", is_call=True,
                                 call_type=call_type, call_transcription=_call_word(low)))
    if not evidence:
        evidence.append(Evidence("visual", "Sichtbeobachtung"))
    return evidence, behaviour


def _call_word(low: str) -> str:
    for cue in vocab.AUDITORY_CUES:
        if cue.strip() in low:
            return cue.strip()
    return "Ruf"


def _count(sentence: str, mention_start: int) -> tuple[Optional[int], Optional[str]]:
    window = sentence[max(0, mention_start - 40):mention_start].lower()
    if any(cue in window for cue in vocab.PLURAL_CUES):
        return None, "plural-unspecified"
    digits = list(_NUMBER_RE.finditer(window))
    if digits:
        value = int(digits[-1].group(1))
        if 1 <= value <= 9999:
            qualifier = "approximate" if any(c in window for c in vocab.APPROX_CUES) else "exact"
            return value, qualifier
    for word, value in vocab.GERMAN_NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", window):
            return value, "exact"
    return None, None


def extract_observations(
    entry: DiaryEntry,
    resolver: TaxonResolver,
    place: Optional[Place] = None,
) -> list[Observation]:
    text = entry.text_clean or ""
    observations: list[Observation] = []
    for index, mention in enumerate(find_taxa(text)):
        resolution = resolver.resolve(mention.vernacular)
        taxon = Taxon(
            vernacular_de=mention.vernacular,
            scientific_name=resolution.scientific_name,
            taxon_iri=resolution.taxon_iri,
            match_method=resolution.match_method,
            confidence=resolution.confidence,
            note=None if resolution.resolved else resolution.note,
        )
        sentence = _sentence_at(text, mention.start)
        local_start = sentence.find(mention.verbatim)
        evidence, behaviour = _evidence(sentence)
        count, qualifier = _count(sentence, local_start if local_start >= 0 else 0)
        observations.append(Observation(
            entry_uid=entry.entry_uid,
            taxon=taxon,
            verbatim_notes=sentence,
            place=place,
            individual_count=count,
            count_qualifier=qualifier,
            evidence=evidence,
            behaviour=behaviour,
            index=index,
        ))
    return observations
