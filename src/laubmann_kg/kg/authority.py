"""External authority links in one shape (ontology 0.6.0).

Every link of a project node — Taxon → GBIF, habitat concept → EUNIS, Place →
GeoNames / Wikidata, Person → Wikidata / GND — becomes an ``AuthorityLink``:
the authority, the record's IRI and id, the match grade and, when known, the
record's label. The RDF emitter writes all of them the same way
(``skos:exactMatch | closeMatch | broadMatch`` to the IRI; the IRI a
``skos:Concept`` with ``skos:inScheme lkg:authority_<name>``, ``skos:notation``,
``skos:prefLabel``), so a consumer queries one pattern for all five
authorities. The grades are derived here from the evidence the linking stage
already records on the node; nothing is looked up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from laubmann_kg.kg.model import Habitat, Person, Place, Taxon

EXACT, CLOSE, BROAD = "exact", "close", "broad"
MATCH_GRADES = (EXACT, CLOSE, BROAD)

# authority key -> (IRI prefix, lkg scheme local name)
AUTHORITIES: dict[str, tuple[str, str]] = {
    "gbif": ("https://www.gbif.org/species/", "authority_gbif"),
    "eunis": ("http://eunis.eea.europa.eu/eunishabitats/", "authority_eunis"),
    "geonames": ("https://sws.geonames.org/", "authority_geonames"),
    "wikidata": ("http://www.wikidata.org/entity/", "authority_wikidata"),
    "gnd": ("https://d-nb.info/gnd/", "authority_gnd"),
}

# Place.georef_source -> grade: two independent sources agreeing (OSM hit and
# GeoNames record) or a reviewer decision is an identity claim; a
# single-source name match is a close match.
_PLACE_GRADES = {"osm+geonames": EXACT, "reviewed": EXACT}


@dataclass(frozen=True)
class AuthorityLink:
    authority: str            # key of AUTHORITIES
    iri: str
    notation: str             # the authority's own id ("2481139", "G1.2", "Q11850829", "1012394506")
    match: str                # exact | close | broad
    label: Optional[str] = None
    label_lang: Optional[str] = None

    @property
    def scheme(self) -> str:
        return AUTHORITIES[self.authority][1]


def authority_of(iri: str) -> Optional[str]:
    """Authority key for an IRI, or None when it belongs to none of the five
    (http/https and a trailing slash are tolerated)."""
    norm = re.sub(r"^https?://", "", iri or "")
    for key, (prefix, _) in AUTHORITIES.items():
        if norm.startswith(re.sub(r"^https?://", "", prefix)):
            return key
    return None


def notation_of(iri: str) -> str:
    return (iri or "").rstrip("/").rsplit("/", 1)[-1]


def _link(authority: str, iri: str, match: str, label: Optional[str] = None,
          label_lang: Optional[str] = None) -> AuthorityLink:
    return AuthorityLink(authority, iri, notation_of(iri), match, label or None, label_lang)


def taxon_links(taxon: Taxon) -> list[AuthorityLink]:
    out: list[AuthorityLink] = []
    if taxon.gbif_key:
        if taxon.gbif_match_type == "HIGHERRANK":
            grade = BROAD                       # genus anchor is broader, not equal
        elif taxon.match_method == "llm+gbif" or taxon.gbif_match_type == "FUZZY":
            grade = CLOSE                       # LLM-mediated or fuzzy: weaker claim
        else:
            grade = EXACT
        out.append(_link("gbif", f"{AUTHORITIES['gbif'][0]}{int(taxon.gbif_key)}", grade,
                         taxon.gbif_canonical_name))
    # curated index-linker IRI (taxa.links_long_path): an identity the project
    # asserted by hand; only the five authorities are emitted
    if taxon.taxon_iri:
        key = authority_of(taxon.taxon_iri)
        if key is not None and not any(l.iri == taxon.taxon_iri for l in out):
            out.append(_link(key, taxon.taxon_iri, EXACT))
    return out


def habitat_links(habitat: Habitat) -> list[AuthorityLink]:
    if not (habitat.eunis_uri and habitat.eunis_code):
        return []
    grade = habitat.eunis_match if habitat.eunis_match in MATCH_GRADES else CLOSE
    return [AuthorityLink("eunis", habitat.eunis_uri, habitat.eunis_code, grade,
                          habitat.eunis_label or None, "en")]


def place_links(place: Place) -> list[AuthorityLink]:
    grade = _PLACE_GRADES.get(place.georef_source or "", CLOSE)
    out: list[AuthorityLink] = []
    if place.geonames_id:
        out.append(_link("geonames", f"{AUTHORITIES['geonames'][0]}{int(place.geonames_id)}/", grade))
    if place.wikidata_iri:
        out.append(_link("wikidata", place.wikidata_iri, grade))
    return out


def person_links(person: Person) -> list[AuthorityLink]:
    out: list[AuthorityLink] = []
    if person.wikidata_iri:
        grade = person.wikidata_match if person.wikidata_match in MATCH_GRADES else CLOSE
        out.append(_link("wikidata", person.wikidata_iri, grade))
    if person.gnd_iri:
        out.append(_link("gnd", person.gnd_iri, EXACT))     # reviewer-researched
    return out
