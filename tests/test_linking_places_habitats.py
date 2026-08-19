"""Place linking (Nominatim cache + GeoNames index + Wikidata) and habitat
linking (EUNIS classes): matching rules, review CSVs, RDF/SHACL, DwC-A."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, SKOS

import laubmann_kg.linking.habitats as habitats_mod
from laubmann_kg.dwca.event import build_events
from laubmann_kg.dwca.measurement_or_fact import build_measurements
from laubmann_kg.kg.model import DiaryEntry, Habitat, Observation, Place, Taxon
from laubmann_kg.kg.rdf import DATA, DWC, LKG, build_graph, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.linking.cache import JsonCache
from laubmann_kg.linking.habitats import EunisVocabulary, link_habitats
from laubmann_kg.linking.places import GeoNamesIndex, GeoRecord, geocodable, link_places, resolve_label
from laubmann_kg.pipeline import ExtractionResult

REPO = Path(__file__).resolve().parents[1]


def _entry(uid: str, place: Place | None = None) -> DiaryEntry:
    e = DiaryEntry(entry_uid=uid, entry_id=f"L02-{uid}", volume=2, page_uid="p1", page_id="doc_0001_L", region_uid=None,
                   scan=None, entry_date="1918-05-01", verbatim_event_date="1. Mai 1918", location_raw=None,
                   text_clean="Text " + "x" * 90)
    e.place = place
    return e


def _obs(uid: str, place: Place | None = None, habitat: Habitat | None = None, index: int = 0) -> Observation:
    o = Observation(entry_uid=uid, taxon=Taxon(vernacular_de="Buchfink", scientific_name="Fringilla coelebs", rank="species", is_bird=True),
                    verbatim_notes="Buchfink", index=index)
    o.place = place
    o.habitat = habitat
    return o


def _shacl_ok(graph, tmp_path) -> bool:
    ttl = tmp_path / "g.ttl"
    serialize_turtle(graph, ttl)
    return run_shacl_validation(data_path=str(ttl), ontology_path=str(REPO / "ontologies" / "laubmann.ttl"),
                                shapes_path=str(REPO / "ontologies" / "shacl_shapes.ttl"))


# --------------------------------------------------------------------------- places

def test_geocodable_filters_fragments_and_generic_nouns() -> None:
    assert geocodable("Ismaning") and geocodable("Maisinger See") and geocodable("Hagnau am Bodensee")
    for bad in ("an der Halde bei Hirschzell", "Wald", "See", "Speichersee", "Garten", "Ecke Sälmanstraße", "K2 Areal", "vor dem Fenster", "123"):
        assert not geocodable(bad), bad


GN_ISMANING = [GeoRecord(2895643, "Ismaning", "P", "PPLA4", "DE", "02", 48.2333, 11.6833, 16000),
               GeoRecord(6556317, "Ismaning", "A", "ADM4", "DE", "02", 48.2333, 11.6833, 0)]
OSM_ISMANING = [{"osm_type": "relation", "osm_id": 2168245, "lat": "48.2242434", "lon": "11.6715263", "category": "boundary",
                 "type": "administrative", "name": "Ismaning", "name_de": "Ismaning", "display_name": "Ismaning, Landkreis München, Bayern, Deutschland",
                 "wikidata": "Q262560"}]


def test_resolve_label_osm_confirmed_by_geonames_and_fallbacks() -> None:
    l = resolve_label("Ismaning", "settlement", OSM_ISMANING, GN_ISMANING)
    assert l.status == "linked" and l.source == "osm+geonames" and l.geonames.id == 2895643 and l.qid == "Q262560"
    assert (l.lat, l.lon) == (48.2333, 11.6833) and l.uncertainty_m == 2000       # GeoNames point + PPLA4 radius
    # OSM only (a moor GeoNames lacks): coordinates from OSM, uncertainty from the OSM type
    l = resolve_label("Ampermoos", "locality", [{"osm_type": "way", "osm_id": 1, "lat": "48.1", "lon": "11.1", "category": "natural",
                                                   "type": "wetland", "name": "Ampermoos", "display_name": "Ampermoos, Bayern"}], [])
    assert l.status == "linked" and l.source == "osm" and l.geonames is None and l.uncertainty_m == 1000
    # a street/house hit is not a place
    l = resolve_label("Ismaning", None, [{"osm_type": "way", "osm_id": 2, "lat": "48", "lon": "11", "category": "highway", "type": "residential",
                                           "name": "Ismaning", "display_name": "Ismaning, Straße"}], [])
    assert l.status == "no_match"
    # GeoNames alone: unique in Bavaria -> linked (0.8); ambiguous -> review
    l = resolve_label("Ismaning", None, None, GN_ISMANING)
    assert l.status == "linked" and l.source == "geonames" and l.confidence == 0.8
    l = resolve_label("Neukirchen", None, None, [GeoRecord(1, "Neukirchen", "P", "PPL", "DE", "02", 48.0, 12.0, 100),
                                                 GeoRecord(2, "Neukirchen", "P", "PPL", "DE", "02", 49.5, 10.0, 300)])
    assert l.status == "review" and "candidates" in l.note
    # nothing at all
    assert resolve_label("Nirgendwo", None, [], []).status == "no_match"


def test_link_places_applies_links_writes_review_and_emits_rdf(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "cache"; cache_dir.mkdir()
    (cache_dir / "nominatim_cache.json").write_text(json.dumps({"Ismaning": OSM_ISMANING, "Nirgendwo": []}), encoding="utf-8")
    # GeoNames index without dumps: inject records
    monkeypatch.setattr(GeoNamesIndex, "_load", lambda self, download: None)
    def fake_init(self, directory, countries=(), download=True):
        self.dir = Path(directory); self.countries = tuple(countries); self.loaded = ["DE"]
        self.index = {"ismaning": GN_ISMANING}; self.primary = {"ismaning": {r.id for r in GN_ISMANING}}
    monkeypatch.setattr(GeoNamesIndex, "__init__", fake_init)
    ismaning = Place("Ismaning", canonical="Ismaning", kind="settlement")
    nowhere = Place("Nirgendwo", canonical="Nirgendwo", kind="locality")
    e1 = _entry("e1", ismaning); e1.observations = [_obs("e1", ismaning), _obs("e1", nowhere, index=1)]
    result = ExtractionResult(entries=[e1])
    n, rows = link_places(result, {"cache_dir": str(cache_dir), "geonames": {"download": False}}, JsonCache(tmp_path / "wd.json"), offline=True)
    assert n == 1
    by = {r["place_name"]: r for r in rows}
    assert by["Ismaning"]["status"] == "linked" and by["Ismaning"]["geonames_id"] == 2895643 and by["Ismaning"]["qid"] == "Q262560"
    assert by["Nirgendwo"]["status"] == "no_match"
    p = e1.place
    assert p.geonames_id == 2895643 and p.wikidata_iri.endswith("Q262560") and p.coordinate_uncertainty_m == 2000 and p.lat == 48.2333
    assert e1.observations[0].place is p                    # references re-pointed to the one linked object
    graph = build_graph(result)
    node = DATA[p.uid]
    assert (node, OWL.sameAs, URIRef("https://sws.geonames.org/2895643/")) in graph
    assert (node, OWL.sameAs, URIRef("http://www.wikidata.org/entity/Q262560")) in graph
    assert graph.value(node, DWC.coordinateUncertaintyInMeters).toPython() == 2000
    assert graph.value(node, DWC.georeferenceSources) is not None
    assert _shacl_ok(graph, tmp_path)
    ev = build_events(result)[0]
    assert ev["coordinateUncertaintyInMeters"] == "2000" and ev["locationID"] == "https://sws.geonames.org/2895643/" and ev["georeferenceProtocol"]


# --------------------------------------------------------------------------- habitats

def test_eunis_vocabulary_loads_codes_hierarchy_and_prompt_list() -> None:
    v = EunisVocabulary(REPO / "data" / "eunis_habitats.csv")
    g12 = v.get("g1.2")
    assert g12 and g12["label"].startswith("Mixed riparian") and g12["uri"] == "http://eunis.eea.europa.eu/eunishabitats/G1.2"
    assert [a["code"] for a in v.ancestors("G1.21")] == ["G1.2", "G1", "G"]
    lines = v.prompt_list().splitlines()
    assert "G1.2\tMixed riparian floodplain and gallery woodland" in lines and not any(l.startswith("A1.1\t") for l in lines)
    assert 300 < len(lines) < 450


def test_link_habitats_with_fake_proposer_emits_skos_matches_and_emof(tmp_path, monkeypatch) -> None:
    answers = {"Auwald": {"code": "G1.2", "match": "exact", "confidence": 0.95, "note": ""},
               "Schilf": {"code": "C3.21", "match": "exact", "confidence": 0.9, "note": ""},
               "Hangwald": {"code": "G1", "match": "close", "confidence": 0.6, "note": "slope forest, type unknown"},
               "Rauchschwalbe": {"code": None, "match": "none", "confidence": 0.9, "note": "a bird, not a habitat"},
               "Fantasiecode": {"code": "Z9.9", "match": "exact", "confidence": 0.9, "note": ""}}
    monkeypatch.setattr(habitats_mod, "build_habitat_proposer", lambda cfg, vocab: (lambda labels: {l: answers[l] for l in labels if l in answers}))
    e = _entry("e1")
    e.observations = [_obs("e1", habitat=Habitat("Auwald"), index=0), _obs("e1", habitat=Habitat("Auwald"), index=1),
                      _obs("e1", habitat=Habitat("Schilf"), index=2), _obs("e1", habitat=Habitat("Hangwald"), index=3),
                      _obs("e1", habitat=Habitat("Rauchschwalbe"), index=4), _obs("e1", habitat=Habitat("Fantasiecode"), index=5)]
    result = ExtractionResult(entries=[e])
    n, rows = link_habitats(result, {"vocabulary": str(REPO / "data" / "eunis_habitats.csv"), "min_confidence": 0.8}, offline=False)
    assert n == 2
    st = {r["habitat_label"]: r["status"] for r in rows}
    assert st == {"Auwald": "linked", "Schilf": "linked", "Hangwald": "review", "Rauchschwalbe": "no_match", "Fantasiecode": "no_match"}
    h = e.observations[0].habitat
    assert h.eunis_code == "G1.2" and h.eunis_match == "exact" and [c for c, _, _ in h.eunis_parents] == ["G1", "G"]
    assert e.observations[1].habitat is h                    # shared per label
    assert e.observations[3].habitat.eunis_code is None       # review: not applied
    graph = build_graph(result)
    hab = DATA[h.uid]; eunis = URIRef("http://eunis.eea.europa.eu/eunishabitats/G1.2")
    assert (hab, SKOS.exactMatch, eunis) in graph
    assert (eunis, SKOS.notation, Literal("G1.2")) in graph and (eunis, SKOS.broader, URIRef("http://eunis.eea.europa.eu/eunishabitats/G1")) in graph
    assert (URIRef("http://eunis.eea.europa.eu/eunishabitats/G1"), SKOS.broader, URIRef("http://eunis.eea.europa.eu/eunishabitats/G")) in graph
    assert _shacl_ok(graph, tmp_path)
    mof = [r for r in build_measurements(result) if r["measurementType"].startswith("habitat type")]
    assert len(mof) == 3 and mof[0]["measurementValueID"] == str(eunis) and mof[0]["measurementValue"].startswith("G1.2 ")


def test_link_habitats_reviewed_csv_overrides(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(habitats_mod, "build_habitat_proposer", lambda cfg, vocab: (lambda labels: {}))
    reviewed = tmp_path / "habitat_link_review.csv"
    with reviewed.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["habitat_label", "eunis_code", "match", "decision"]); w.writeheader()
        w.writerow({"habitat_label": "Hangwald", "eunis_code": "G1", "match": "broad", "decision": "y"})
    e = _entry("e1"); e.observations = [_obs("e1", habitat=Habitat("Hangwald"))]
    result = ExtractionResult(entries=[e])
    n, rows = link_habitats(result, {"vocabulary": str(REPO / "data" / "eunis_habitats.csv"), "reviewed_csv": str(reviewed)}, offline=False)
    assert n == 1 and rows[0]["status"] == "reviewed" and e.observations[0].habitat.eunis_match == "broad"
    graph = build_graph(result)
    assert (DATA[e.observations[0].habitat.uid], SKOS.broadMatch, URIRef("http://eunis.eea.europa.eu/eunishabitats/G1")) in graph


def test_entry_context_disambiguates_and_demotes() -> None:
    from laubmann_kg.linking.places import _context_points
    # two Bernrieds in Bavaria; the entries also mention Tutzing (anchor) -> the Starnberg one
    recs = [GeoRecord(1, "Bernried", "P", "PPL", "DE", "02", 48.92, 12.88, 5000), GeoRecord(2, "Bernried", "P", "PPLA4", "DE", "02", 47.87, 11.30, 2000)]
    osm = [{"osm_type": "r", "osm_id": 1, "lat": "48.9187", "lon": "12.884", "category": "boundary", "type": "administrative", "name": "Bernried", "display_name": "Bernried, Landkreis Deggendorf"},
           {"osm_type": "r", "osm_id": 2, "lat": "47.8705", "lon": "11.2996", "category": "place", "type": "village", "name": "Bernried", "display_name": "Bernried am Starnberger See"}]
    no_ctx = resolve_label("Bernried", "settlement", osm, recs, primary_ids={1, 2})
    assert no_ctx.geonames.id == 1                         # first (most important) OSM hit wins without context
    ctx = _context_points({"Bernried": {0, 1}, "Tutzing": {0, 1, 2}}, {"Tutzing": (47.91, 11.28)})
    assert ctx["Bernried"] == [[(47.91, 11.28)], [(47.91, 11.28)]] and "Tutzing" not in ctx
    with_ctx = resolve_label("Bernried", "settlement", osm, recs, context=ctx["Bernried"], primary_ids={1, 2})
    assert with_ctx.geonames.id == 2 and with_ctx.status == "linked"
    # a weak hit (track named after the gorge) is confirmed by the context, a far hit demoted
    track = [{"osm_type": "w", "osm_id": 3, "lat": "47.99", "lon": "11.30", "category": "highway", "type": "track", "name": "Maisinger Schlucht", "display_name": "Maisinger Schlucht, Pöcking"}]
    assert resolve_label("Maisinger Schlucht", "locality", track, []).status == "review"
    assert resolve_label("Maisinger Schlucht", "locality", track, [], context=(47.95, 11.3)).status == "linked"
    far = [{"osm_type": "n", "osm_id": 4, "lat": "50.76", "lon": "13.76", "category": "place", "type": "hamlet", "name": "Schirm", "display_name": "Schirm, Sachsen"}]
    assert resolve_label("Schirm", "locality", far, []).status == "linked"
    assert resolve_label("Schirm", "locality", far, [], context=(48.1, 11.6)).status == "review"
    # a pub in Munich named "Korfu" is not confirmed by the Munich context when GeoNames knows Corfu as a town
    pub = [{"osm_type": "n", "osm_id": 5, "lat": "48.17", "lon": "11.56", "category": "amenity", "type": "restaurant", "name": "Korfu", "display_name": "Korfu, München"}]
    corfu = [GeoRecord(2463679, "Corfu", "P", "PPLA", "GR", "ESYE22", 39.62, 19.92, 28000)]
    l = resolve_label("Korfu", "settlement", pub, corfu, context=(48.14, 11.58), primary_ids=set())
    assert l.status != "linked" and (l.geonames is not None or l.confidence < 0.8)
    # one stray entry must not pull a locality away: 1 of 10 entries near the candidate -> no bonus
    ctx10 = [[(48.2, 11.68)]] * 9 + [[(49.48, 11.78)]]
    stray = [{"osm_type": "n", "osm_id": 6, "lat": "49.484", "lon": "11.782", "category": "place", "type": "neighbourhood", "name": "Tafelberg", "display_name": "Tafelberg, Sulzbach-Rosenberg"}]
    assert resolve_label("Tafelberg", "locality", stray, [], context=ctx10).status == "review"
