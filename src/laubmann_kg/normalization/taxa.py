"""German bird-name gazetteer, matcher, and taxon resolvers.

The gazetteer maps historical German vernacular names to scientific names. The
matcher finds vernacular mentions in entry text. Resolution to a scientific name
and taxon IRI is delegated to a ``TaxonResolver``; see the interface below.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Protocol

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIXES = ("", "s", "e", "n", "en", "er")
_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")

# Historical German vernacular → scientific name. Curated from the Laubmann
# vocabulary; deliberately conservative (only confident mappings). Multi-word
# names are matched via their head noun (e.g. "Rotrückiger Würger" → "Würger").
BIRD_GAZETTEER: dict[str, str] = {
    "Mauersegler": "Apus apus",
    "Rabenkrähe": "Corvus corone",
    "Saatkrähe": "Corvus frugilegus",
    "Dohle": "Coloeus monedula",
    "Elster": "Pica pica",
    "Eichelhäher": "Garrulus glandarius",
    "Weidenlaubvogel": "Phylloscopus collybita",
    "Fitislaubvogel": "Phylloscopus trochilus",
    "Waldlaubvogel": "Phylloscopus sibilatrix",
    "Berglaubvogel": "Phylloscopus bonelli",
    "Berglaubsänger": "Phylloscopus bonelli",
    "Fichtenlaubvogel": "Phylloscopus collybita",
    "Hausrotschwanz": "Phoenicurus ochruros",
    "Hausrotschwänzchen": "Phoenicurus ochruros",
    "Gartenrotschwanz": "Phoenicurus phoenicurus",
    "Baumpieper": "Anthus trivialis",
    "Wiesenpieper": "Anthus pratensis",
    "Rauchschwalbe": "Hirundo rustica",
    "Mehlschwalbe": "Delichon urbicum",
    "Uferschwalbe": "Riparia riparia",
    "Gartenbaumläufer": "Certhia brachydactyla",
    "Waldbaumläufer": "Certhia familiaris",
    "Buchfink": "Fringilla coelebs",
    "Bergfink": "Fringilla montifringilla",
    "Grünfink": "Chloris chloris",
    "Bluthänfling": "Linaria cannabina",
    "Stieglitz": "Carduelis carduelis",
    "Zaunkönig": "Troglodytes troglodytes",
    "Gimpel": "Pyrrhula pyrrhula",
    "Rotkehlchen": "Erithacus rubecula",
    "Kleiber": "Sitta europaea",
    "Wildente": "Anas platyrhynchos",
    "Heidelerche": "Lullula arborea",
    "Feldlerche": "Alauda arvensis",
    "Haubenlerche": "Galerida cristata",
    "Goldammer": "Emberiza citrinella",
    "Amsel": "Turdus merula",
    "Singdrossel": "Turdus philomelos",
    "Misteldrossel": "Turdus viscivorus",
    "Wacholderdrossel": "Turdus pilaris",
    "Ringeltaube": "Columba palumbus",
    "Hohltaube": "Columba oenas",
    "Turteltaube": "Streptopelia turtur",
    "Kuckuck": "Cuculus canorus",
    "Grünspecht": "Picus viridis",
    "Schwarzspecht": "Dryocopus martius",
    "Buntspecht": "Dendrocopos major",
    "Star": "Sturnus vulgaris",
    "Flußuferläufer": "Actitis hypoleucos",
    "Zaungrasmücke": "Sylvia communis",
    "Dorngrasmücke": "Sylvia communis",
    "Gartengrasmücke": "Sylvia borin",
    "Mönchsgrasmücke": "Sylvia atricapilla",
    "Turmfalke": "Falco tinnunculus",
    "Kohlmeise": "Parus major",
    "Blaumeise": "Cyanistes caeruleus",
    "Haubenmeise": "Lophophanes cristatus",
    "Sumpfmeise": "Poecile palustris",
    "Tannenmeise": "Periparus ater",
    "Wachtel": "Coturnix coturnix",
    "Wachtelkönig": "Crex crex",
    "Lachmöwe": "Chroicocephalus ridibundus",
    "Lachmöve": "Chroicocephalus ridibundus",
    "Feldsperling": "Passer montanus",
    "Haussperling": "Passer domesticus",
    "Bekassine": "Gallinago gallinago",
    "Wasseramsel": "Cinclus cinclus",
    "Eisvogel": "Alcedo atthis",
    "Gartenspötter": "Hippolais icterina",
    "Bachstelze": "Motacilla alba",
    "Gebirgsbachstelze": "Motacilla cinerea",
    "Sperber": "Accipiter nisus",
    "Waldkauz": "Strix aluco",
    "Mäusebussard": "Buteo buteo",
    "Bussard": "Buteo buteo",
    "Würger": "Lanius collurio",
    "Neuntöter": "Lanius collurio",
    "Zwergtaucher": "Tachybaptus ruficollis",
    "Bläßhuhn": "Fulica atra",
    "Storch": "Ciconia ciconia",
    "Kiebitz": "Vanellus vanellus",
    "Waldohreule": "Asio otus",
    "Heuschreckensänger": "Locustella naevia",
}


def _norm(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("v", "w")):
        text = text.replace(a, b)
    return text


@dataclass(frozen=True)
class _Stem:
    stem: str
    vernacular: str


def _build_stems(gazetteer: Iterable[str]) -> list[_Stem]:
    stems = [_Stem(_norm(name), name) for name in gazetteer]
    stems.sort(key=lambda s: len(s.stem), reverse=True)
    return stems


_STEMS = _build_stems(BIRD_GAZETTEER)


@dataclass
class TaxonMention:
    vernacular: str
    verbatim: str
    start: int


def find_taxa(text: str, stems: Optional[list[_Stem]] = None) -> list[TaxonMention]:
    """Return vernacular bird mentions found in ``text``, de-duplicated by name,
    ordered by first appearance."""
    stems = stems if stems is not None else _STEMS
    seen: dict[str, TaxonMention] = {}
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        norm = _norm(token)
        for stem in stems:
            if norm.startswith(stem.stem) and norm[len(stem.stem):] in _ALLOWED_SUFFIXES:
                if stem.vernacular not in seen:
                    seen[stem.vernacular] = TaxonMention(stem.vernacular, token, match.start())
                break
    return sorted(seen.values(), key=lambda m: m.start)


@dataclass
class TaxonResolution:
    scientific_name: Optional[str]
    taxon_iri: Optional[str]
    match_method: str
    confidence: Optional[float]
    note: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.scientific_name is not None


UNRESOLVED = TaxonResolution(None, None, "unresolved", None, "kein Nomenklatur-Treffer")


class TaxonResolver(Protocol):
    def resolve(self, vernacular_de: str) -> TaxonResolution: ...


class SeedTaxonResolver:
    """Offline resolver backed by the bundled gazetteer. Never fabricates an IRI."""

    def __init__(self, gazetteer: Optional[dict[str, str]] = None) -> None:
        self.gazetteer = gazetteer if gazetteer is not None else BIRD_GAZETTEER

    def resolve(self, vernacular_de: str) -> TaxonResolution:
        sci = self.gazetteer.get(vernacular_de)
        if sci is None:
            return UNRESOLVED
        return TaxonResolution(sci, None, "gazetteer", 0.9)


class LinksLongTaxonResolver:
    """Resolver backed by the index-linker ``links_long`` table.

    Reads the documented column contract; only rows whose ``reference_source``
    is trusted yield a scientific name / taxon IRI. Falls back to the seed
    gazetteer when a name is absent from the table.
    """

    _TRUSTED = {"index_validated", "index_resolved_unvalidated"}

    def __init__(self, links_long_path: Path, fallback: Optional[TaxonResolver] = None) -> None:
        self.fallback = fallback or SeedTaxonResolver()
        self._by_name: dict[str, dict] = {}
        path = Path(links_long_path)
        if not path.exists():
            logger.warning("links_long not found at %s; using fallback only", path)
            return
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("species") or "").strip()
                if name:
                    self._by_name.setdefault(name, row)

    def resolve(self, vernacular_de: str) -> TaxonResolution:
        row = self._by_name.get(vernacular_de)
        if row is None:
            return self.fallback.resolve(vernacular_de)
        sci = (row.get("scientific_name") or "").strip() or None
        source = (row.get("reference_source") or "").strip()
        if sci is None or source not in self._TRUSTED:
            res = self.fallback.resolve(vernacular_de)
            note = f"links_long source={source or 'none'}; unbestätigt"
            return TaxonResolution(res.scientific_name, res.taxon_iri, res.match_method, res.confidence, note)
        conf = _to_float(row.get("resolve_confidence")) or _to_float(row.get("nom_score"))
        return TaxonResolution(sci, (row.get("taxon_iri") or "").strip() or None,
                               f"links_long:{source}", conf)


def _to_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def build_resolver(config: Optional[dict] = None) -> TaxonResolver:
    config = config or {}
    links_long = config.get("links_long_path")
    if links_long:
        return LinksLongTaxonResolver(Path(links_long))
    return SeedTaxonResolver()
