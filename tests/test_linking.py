"""External linking stage: caches, GBIF/Wikidata rules, review CSVs, RDF."""

import csv
import json
from pathlib import Path

from rdflib import RDF, Literal, URIRef
from rdflib.namespace import OWL, SKOS

import laubmann_kg.linking as linking
import laubmann_kg.linking.taxa as linking_taxa
from laubmann_kg.dwca.occurrence import build_occurrences
from laubmann_kg.kg.model import DiaryEntry, Observation, Person, Taxon
from laubmann_kg.kg.rdf import DWC, LKG, build_graph, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.linking import run_linking
from laubmann_kg.linking.cache import JsonCache
from laubmann_kg.linking.persons import (
    PERSON_REVIEW_FIELDS,
    WIKIDATA_ENTITY_NS,
    link_persons,
    strip_titles,
)
from laubmann_kg.linking.taxa import TAXON_REVIEW_FIELDS, link_taxa
from laubmann_kg.pipeline import ExtractionResult, run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]

GBIF_URL = "https://api.gbif.org/v1/species/match"


def _entry(entry_uid: str = "e_link0001", entry_id: str = "L02-e0100") -> DiaryEntry:
    return DiaryEntry(
        entry_uid=entry_uid, entry_id=entry_id, volume=2, page_uid="p",
        page_id="pid", region_uid="r", scan="1", entry_date="1918-05-01",
        verbatim_event_date="1. Mai 1918", location_raw="München",
        text_clean="Text des Eintrags.",
    )


def _obs(entry_uid: str, vernacular: str, scientific=None, index: int = 0) -> Observation:
    taxon = Taxon(vernacular_de=vernacular, scientific_name=scientific,
                  match_method="gazetteer" if scientific else "unresolved")
    return Observation(entry_uid=entry_uid, taxon=taxon,
                       verbatim_notes=f"{vernacular} beobachtet", index=index)


def _result(*vernaculars_with_names, n_entries: int = 1) -> ExtractionResult:
    entries = []
    for i in range(n_entries):
        entry = _entry(entry_uid=f"e_link{i:04d}", entry_id=f"L02-e01{i:02d}")
        entry.observations = [
            _obs(entry.entry_uid, vern, sci, index=j)
            for j, (vern, sci) in enumerate(vernaculars_with_names)]
        entries.append(entry)
    return ExtractionResult(entries=entries)


def _gbif_response(key=2492462, match_type="EXACT", confidence=99,
                   rank="SPECIES", canonical="Fringilla coelebs", **extra) -> dict:
    return {"usageKey": key, "matchType": match_type, "confidence": confidence,
            "rank": rank, "canonicalName": canonical, "synonym": False, **extra}


def _patch_gbif(monkeypatch, by_name: dict) -> list:
    """get_json fake keyed on the queried name (lowercased); records calls."""
    calls: list = []
    def fake(url, params, timeout=30.0):
        assert url == GBIF_URL
        assert params["kingdom"] == "Animalia" and params["class"] == "Aves"
        calls.append(params["name"])
        return by_name.get(params["name"].lower())
    monkeypatch.setattr("laubmann_kg.linking.http.get_json", fake)
    return calls


def _raise_get_json(monkeypatch) -> None:
    def fail(url, params, timeout=30.0):
        raise AssertionError("network call attempted")
    monkeypatch.setattr("laubmann_kg.linking.http.get_json", fail)


# --- pipeline hook -----------------------------------------------------------

def test_disabled_by_default_no_network(sample_config, monkeypatch) -> None:
    _raise_get_json(monkeypatch)
    result = run_pipeline(sample_config)  # no `linking` section -> hook off
    assert len(result.entries) == 3


# --- JsonCache ---------------------------------------------------------------

def test_jsoncache(tmp_path) -> None:
    path = tmp_path / "cache" / "gbif_cache.json"
    cache = JsonCache(path, flush_every=2)
    cache.put("a", {"x": 1})
    assert "a" in cache and cache.get("a") == {"x": 1}
    assert not path.exists()                      # below flush_every, unflushed
    cache.put("fail", None)                       # failures are never stored
    assert "fail" not in cache and cache.get("fail") is None
    assert not path.exists()                      # None does not tick the counter
    cache.put("none-match", {"matchType": "NONE"})  # empty result IS a valid answer
    assert path.exists()                          # second real put -> auto-flush
    assert not path.with_name(path.name + ".tmp").exists()  # atomic write
    resumed = JsonCache(path)
    assert resumed.get("a") == {"x": 1}
    assert resumed.get("none-match") == {"matchType": "NONE"}
    assert "fail" not in resumed                  # failure retried next run
    resumed.put("b", [1, 2])
    resumed.flush()
    assert json.loads(path.read_text(encoding="utf-8"))["b"] == [1, 2]


# --- GBIF taxa ---------------------------------------------------------------

def test_gbif_exact_applied(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {"fringilla coelebs": _gbif_response()})
    result = _result(("Buchfink", "Fringilla coelebs"), n_entries=2)
    uids_before = [o.taxon.uid for e in result.entries for o in e.observations]
    linked, rows = link_taxa(result, {"sleep": 0, "llm": {"enabled": False}},
                             JsonCache(tmp_path / "gbif.json"), offline=False)
    assert linked == 1
    for entry in result.entries:                  # every obs of the vernacular
        for obs in entry.observations:
            assert obs.taxon.gbif_key == 2492462
            assert obs.taxon.gbif_match_type == "EXACT"
            assert obs.taxon.gbif_canonical_name == "Fringilla coelebs"
            assert obs.taxon.scientific_name == "Fringilla coelebs"  # untouched
    assert [o.taxon.uid for e in result.entries
            for o in e.observations] == uids_before
    assert rows[0]["status"] == "linked"

    graph = build_graph(result)
    taxon_node = URIRef("https://lkg.example.org/data/"
                        + result.entries[0].observations[0].taxon.uid)
    gbif_iri = URIRef("https://www.gbif.org/species/2492462")
    assert (taxon_node, SKOS.exactMatch, gbif_iri) in graph
    assert (taxon_node, DWC.taxonID,
            Literal("https://www.gbif.org/species/2492462")) in graph
    ttl = tmp_path / "linked.ttl"
    serialize_turtle(graph, ttl)
    assert run_shacl_validation(
        data_path=str(ttl),
        ontology_path=str(REPO_ROOT / "ontologies" / "laubmann.ttl"),
        shapes_path=str(REPO_ROOT / "ontologies" / "shacl_shapes.ttl"),
    )


def test_fuzzy_thresholds(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {
        "fringilla coelebs": _gbif_response(match_type="FUZZY", confidence=96),
        "turdus merula": _gbif_response(key=999, match_type="FUZZY", confidence=80,
                                        canonical="Turdus merula"),
    })
    result = _result(("Buchfink", "Fringilla coelebs"), ("Amsel", "Turdus merula"))
    linked, rows = link_taxa(result, {"sleep": 0, "llm": {"enabled": False}},
                             JsonCache(tmp_path / "gbif.json"), offline=False)
    assert linked == 1
    by_vern = {o.taxon.vernacular_de: o.taxon
               for o in result.entries[0].observations}
    assert by_vern["Buchfink"].gbif_key == 2492462
    assert by_vern["Buchfink"].gbif_match_type == "FUZZY"
    assert by_vern["Amsel"].gbif_key is None      # 80 < fuzzy_min 95: review only
    status = {r["vernacular_de"]: r["status"] for r in rows}
    assert status == {"Buchfink": "linked", "Amsel": "review"}
    graph = build_graph(result)
    assert (None, SKOS.closeMatch,
            URIRef("https://www.gbif.org/species/2492462")) in graph


def test_higherrank(tmp_path, monkeypatch) -> None:
    higher = _gbif_response(key=2481047, match_type="HIGHERRANK", confidence=94,
                            rank="GENUS", canonical="Buteo")
    _patch_gbif(monkeypatch, {"buteo": higher})
    # resolver-supplied genus name -> broadMatch anchor
    result = _result(("Bussard", "Buteo"))
    linked, rows = link_taxa(result, {"sleep": 0, "llm": {"enabled": False}},
                             JsonCache(tmp_path / "g1.json"), offline=False)
    taxon = result.entries[0].observations[0].taxon
    assert linked == 1 and rows[0]["status"] == "linked-broad"
    assert taxon.gbif_key == 2481047 and taxon.gbif_match_type == "HIGHERRANK"
    assert taxon.scientific_name == "Buteo"       # no backfill on broad anchors
    graph = build_graph(result)
    gbif_iri = URIRef("https://www.gbif.org/species/2481047")
    assert (None, SKOS.broadMatch, gbif_iri) in graph
    assert not list(graph.subjects(DWC.taxonID, None))  # no taxonID for broad

    # LLM-proposed name + HIGHERRANK = double uncertainty -> review only
    monkeypatch.setattr(
        linking_taxa, "build_llm_proposer",
        lambda cfg: lambda vern, ctx: {"scientific_name": "Buteo", "confidence": 0.9})
    result2 = _result(("Bussardartiger", None))
    linked2, rows2 = link_taxa(result2, {"sleep": 0},
                               JsonCache(tmp_path / "g2.json"), offline=False)
    taxon2 = result2.entries[0].observations[0].taxon
    assert linked2 == 0 and rows2[0]["status"] == "review"
    assert taxon2.gbif_key is None and taxon2.scientific_name is None


def test_synonym_accepted_key(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {"parus caeruleus": _gbif_response(
        key=111, canonical="Parus caeruleus", confidence=98,
        synonym=True, acceptedUsageKey=2487879)})
    result = _result(("Blaumeise", "Parus caeruleus"))
    linked, rows = link_taxa(result, {"sleep": 0, "llm": {"enabled": False}},
                             JsonCache(tmp_path / "gbif.json"), offline=False)
    taxon = result.entries[0].observations[0].taxon
    assert linked == 1
    assert taxon.gbif_key == 2487879              # accepted key, not the synonym's
    assert rows[0]["gbif_key"] == 2487879


def test_unresolved_llm_verified(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {"prunella modularis": _gbif_response(
        key=5231437, canonical="Prunella modularis")})
    monkeypatch.setattr(
        linking_taxa, "build_llm_proposer",
        lambda cfg: lambda vern, ctx: {"scientific_name": "Prunella modularis",
                                       "confidence": 0.9})
    result = _result(("Heckenbraunelle", None))
    linked, rows = link_taxa(result, {"sleep": 0},
                             JsonCache(tmp_path / "g1.json"), offline=False)
    taxon = result.entries[0].observations[0].taxon
    assert linked == 1
    assert taxon.scientific_name == "Prunella modularis"  # the VERIFIED form
    assert taxon.match_method == "llm+gbif" and taxon.note is None
    assert rows[0]["llm_scientific_name"] == "Prunella modularis"
    graph = build_graph(result)
    gbif_iri = URIRef("https://www.gbif.org/species/5231437")
    assert (None, SKOS.closeMatch, gbif_iri) in graph     # LLM-mediated: weaker
    assert (None, SKOS.exactMatch, gbif_iri) not in graph

    # below the LLM confidence threshold -> review row only, taxon untouched
    monkeypatch.setattr(
        linking_taxa, "build_llm_proposer",
        lambda cfg: lambda vern, ctx: {"scientific_name": "Prunella modularis",
                                       "confidence": 0.4})
    result2 = _result(("Heckenbraunelle", None))
    linked2, rows2 = link_taxa(result2, {"sleep": 0},
                               JsonCache(tmp_path / "g2.json"), offline=False)
    taxon2 = result2.entries[0].observations[0].taxon
    assert linked2 == 0 and rows2[0]["status"] == "review"
    assert taxon2.gbif_key is None and taxon2.scientific_name is None
    assert rows2[0]["gbif_key"] == 5231437        # still GBIF-checked for review


def test_llm_unavailable(tmp_path, monkeypatch) -> None:
    _raise_get_json(monkeypatch)
    monkeypatch.setattr(linking_taxa, "build_llm_proposer", lambda cfg: None)
    result = _result(("Heckenbraunelle", None))
    linked, rows = link_taxa(result, {"sleep": 0},
                             JsonCache(tmp_path / "gbif.json"), offline=False)
    assert linked == 0
    assert rows[0]["status"] == "llm_unavailable"


def test_reviewed_csv_trusted(tmp_path, monkeypatch) -> None:
    _raise_get_json(monkeypatch)

    def _never_called(vern, ctx):
        raise AssertionError("LLM proposer must not run for reviewed names")
    monkeypatch.setattr(linking_taxa, "build_llm_proposer",
                        lambda cfg: _never_called)
    reviewed = tmp_path / "taxon_link_review.csv"
    with reviewed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TAXON_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerow({"vernacular_de": "Buchfink", "gbif_key": "2492462",
                         "gbif_canonical_name": "Fringilla coelebs",
                         "status": "review", "decision": "y"})
    result = _result(("Buchfink", "Fringilla coelebs"))
    linked, rows = link_taxa(result, {"sleep": 0, "reviewed_csv": str(reviewed)},
                             JsonCache(tmp_path / "gbif.json"), offline=False)
    taxon = result.entries[0].observations[0].taxon
    assert linked == 1 and rows[0]["status"] == "reviewed"
    assert taxon.gbif_key == 2492462 and taxon.match_method == "review"
    assert taxon.gbif_match_type == "EXACT"       # legacy blank column -> EXACT


def test_reviewed_csv_match_type_respected(tmp_path, monkeypatch) -> None:
    _raise_get_json(monkeypatch)
    monkeypatch.setattr(linking_taxa, "build_llm_proposer", lambda cfg: None)
    reviewed = tmp_path / "taxon_link_review.csv"
    with reviewed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TAXON_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerow({"vernacular_de": "Bussard", "gbif_key": "2481047",
                         "gbif_match_type": "HIGHERRANK",
                         "gbif_canonical_name": "Buteo",
                         "status": "review", "decision": "y"})
        writer.writerow({"vernacular_de": "Heckenbraunelle", "gbif_key": "5231437",
                         "gbif_match_type": "EXACT",
                         "gbif_canonical_name": "Prunella modularis",
                         "status": "review", "decision": "y"})
    result = _result(("Bussard", None), ("Heckenbraunelle", None))
    linked, rows = link_taxa(result, {"sleep": 0, "reviewed_csv": str(reviewed)},
                             JsonCache(tmp_path / "gbif.json"), offline=False)
    assert linked == 2
    by_vern = {o.taxon.vernacular_de: o.taxon
               for o in result.entries[0].observations}
    assert by_vern["Bussard"].gbif_match_type == "HIGHERRANK"
    assert by_vern["Bussard"].scientific_name is None   # genus: never backfilled
    assert by_vern["Heckenbraunelle"].gbif_match_type == "EXACT"
    assert by_vern["Heckenbraunelle"].scientific_name == "Prunella modularis"
    assert by_vern["Heckenbraunelle"].match_method == "review"

    graph = build_graph(result)
    buteo_iri = URIRef("https://www.gbif.org/species/2481047")
    assert (None, SKOS.broadMatch, buteo_iri) in graph  # not exactMatch
    assert (None, SKOS.exactMatch, buteo_iri) not in graph
    assert (None, DWC.taxonID, Literal(str(buteo_iri))) not in graph
    occ = {r["vernacularName"]: r for r in build_occurrences(result)}
    assert occ["Bussard"]["taxonID"] == ""
    assert occ["Heckenbraunelle"]["taxonID"] == "https://www.gbif.org/species/5231437"


# --- Wikidata persons --------------------------------------------------------

_HUMAN = {"P31": [{"mainsnak": {"datavalue": {"value": {"numeric-id": 5}}}}]}
_CLUB = {"P31": [{"mainsnak": {"datavalue": {"value": {"numeric-id": 4438121}}}}]}


def _patch_wikidata(monkeypatch, search_by_name: dict, claims_by_qid: dict) -> list:
    calls: list = []
    def fake(url, params, timeout=30.0):
        if params.get("action") == "wbsearchentities":
            calls.append(params["search"])
            return {"search": search_by_name.get(params["search"], [])}
        if params.get("action") == "wbgetentities":
            qid = params["ids"]
            return {"entities": {qid: {"claims": claims_by_qid.get(qid, {})}}}
        raise AssertionError(f"unexpected request {params}")
    monkeypatch.setattr("laubmann_kg.linking.http.get_json", fake)
    return calls


def test_person_auto_link(tmp_path, monkeypatch) -> None:
    assert strip_titles("Dr. Stresemann") == "Stresemann"
    assert strip_titles("Herr Prof. Dr. Erwin Stresemann") == "Erwin Stresemann"

    calls = _patch_wikidata(monkeypatch, {
        "Erwin Stresemann": [{"id": "Q66936", "label": "Erwin Stresemann",
                              "description": "deutscher Ornithologe"}],
        "Walter Wüst": [
            {"id": "Q1", "label": "Walter Wüst", "description": "Politiker"},
            {"id": "Q2", "label": "Walter Wüst", "description": "Ornithologe"}],
        "Hans Verein": [{"id": "Q9", "label": "Hans Verein",
                         "description": "Gesangverein"}],
    }, {"Q66936": _HUMAN, "Q9": _CLUB})

    entry = _entry()
    entry.persons = [Person(name="Dr. Erwin Stresemann", role="companion"),
                     Person(name="Walter Wüst", role="source"),
                     Person(name="Kiel", role="source"),
                     Person(name="Hans Verein", role="source")]
    obs = _obs(entry.entry_uid, "Buchfink", "Fringilla coelebs")
    obs.observer = Person(name="Dr. Erwin Stresemann", role="companion")
    entry.observations = [obs]
    result = ExtractionResult(entries=[entry])

    linked, rows = link_persons(result, {"sleep": 0},
                                JsonCache(tmp_path / "wd.json"), offline=False)
    assert linked == 1
    assert "Erwin Stresemann" in calls            # stripped query hits the API
    iri = WIKIDATA_ENTITY_NS + "Q66936"
    assert iri == "http://www.wikidata.org/entity/Q66936"
    stresemann = [p for p in result.entries[0].persons
                  if p.name == "Dr. Erwin Stresemann"][0]
    assert stresemann.wikidata_iri == iri         # applied on entry.persons ...
    assert result.entries[0].observations[0].observer.wikidata_iri == iri  # and observer
    rules = {(r["person_name"], r["rule"]) for r in rows}
    assert ("Dr. Erwin Stresemann", "linked") in rules
    assert ("Walter Wüst", "multiple-candidates") in rules
    assert ("Kiel", "single-token-name") in rules
    assert ("Hans Verein", "not-human") in rules
    wuest = [p for p in result.entries[0].persons if p.name == "Walter Wüst"][0]
    assert wuest.wikidata_iri is None             # ambiguity never auto-links

    graph = build_graph(result)
    assert (None, OWL.sameAs, URIRef(iri)) in graph


def _person_result(*names: str) -> ExtractionResult:
    entry = _entry()
    entry.persons = [Person(name=name, role="source") for name in names]
    return ExtractionResult(entries=[entry])


def test_wikidata_error_body_is_failure_not_cached(tmp_path, monkeypatch) -> None:
    cache = JsonCache(tmp_path / "wd.json")

    def ratelimited(url, params, timeout=30.0):
        # HTTP 200 carrying an API error; the empty payload keys must NOT be
        # mistaken for a valid empty result
        return {"error": {"code": "ratelimited"}, "search": [], "entities": {}}
    monkeypatch.setattr("laubmann_kg.linking.http.get_json", ratelimited)
    linked, rows = link_persons(_person_result("Erwin Stresemann"),
                                {"sleep": 0}, cache, offline=False)
    assert linked == 0 and rows[0]["rule"] == "error"
    assert "search:de:erwin stresemann" not in cache
    assert "search:en:erwin stresemann" not in cache

    def claims_error(url, params, timeout=30.0):
        if params.get("action") == "wbsearchentities":
            return {"search": [{"id": "Q66936", "label": "Erwin Stresemann"}]}
        return {"error": {"code": "ratelimited"}, "entities": {}}
    monkeypatch.setattr("laubmann_kg.linking.http.get_json", claims_error)
    linked, rows = link_persons(_person_result("Erwin Stresemann"),
                                {"sleep": 0}, cache, offline=False)
    assert linked == 0 and rows[0]["rule"] == "error"
    assert "claims:Q66936" not in cache

    # once the API recovers, the same cache resolves the person
    _patch_wikidata(monkeypatch, {"Erwin Stresemann": [
        {"id": "Q66936", "label": "Erwin Stresemann"}]}, {"Q66936": _HUMAN})
    linked, rows = link_persons(_person_result("Erwin Stresemann"),
                                {"sleep": 0}, cache, offline=False)
    assert linked == 1 and rows[0]["rule"] == "linked"


def test_person_limit_budget_is_cache_aware(tmp_path, monkeypatch) -> None:
    calls = _patch_wikidata(monkeypatch, {
        "Erwin Stresemann": [{"id": "Q66936", "label": "Erwin Stresemann"}],
        "Walter Wüst": [{"id": "Q77", "label": "Walter Wüst"}],
    }, {"Q66936": _HUMAN, "Q77": _HUMAN})
    cache = JsonCache(tmp_path / "wd.json")
    cfg = {"sleep": 0, "limit": 1}

    linked1, rows1 = link_persons(
        _person_result("Erwin Stresemann", "Walter Wüst"), cfg, cache,
        offline=False)
    assert linked1 == 1                           # budget spent on person1
    assert [r["person_name"] for r in rows1] == ["Erwin Stresemann"]

    linked2, rows2 = link_persons(
        _person_result("Erwin Stresemann", "Walter Wüst"), cfg, cache,
        offline=False)
    assert linked2 == 2                           # cached person1 is budget-free
    assert [r["person_name"] for r in rows2] == ["Erwin Stresemann", "Walter Wüst"]
    assert calls == ["Erwin Stresemann", "Walter Wüst"]  # one search each


def test_sharp_s_names_link_independently(tmp_path, monkeypatch) -> None:
    _patch_wikidata(monkeypatch, {
        "Hans Weiß": [{"id": "Q100", "label": "Hans Weiß"}],
        "Hans Weiss": [{"id": "Q200", "label": "Hans Weiss"}],
    }, {"Q100": _HUMAN, "Q200": _HUMAN})
    result = _person_result("Hans Weiß", "Hans Weiss")
    linked, rows = link_persons(result, {"sleep": 0},
                                JsonCache(tmp_path / "wd.json"), offline=False)
    assert linked == 2                            # no casefold ß/ss collision
    by_name = {p.name: p.wikidata_iri for p in result.entries[0].persons}
    assert by_name["Hans Weiß"] == WIKIDATA_ENTITY_NS + "Q100"
    assert by_name["Hans Weiss"] == WIKIDATA_ENTITY_NS + "Q200"


# --- cache resumability ------------------------------------------------------

def test_cache_resumable_and_failures_uncached(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "gbif.json"
    _patch_gbif(monkeypatch, {"fringilla coelebs": _gbif_response(),
                              "buteo buteo": None})  # simulated network failure
    cache = JsonCache(cache_path)
    result = _result(("Buchfink", "Fringilla coelebs"), ("Bussard", "Buteo buteo"))
    linked, rows = link_taxa(result, {"sleep": 0, "llm": {"enabled": False}},
                             cache, offline=False)
    cache.flush()
    assert linked == 1
    assert {r["vernacular_de"]: r["status"] for r in rows} == {
        "Buchfink": "linked", "Bussard": "error"}
    stored = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "match:fringilla coelebs" in stored
    assert "match:buteo buteo" not in stored      # failure NOT cached

    _raise_get_json(monkeypatch)                  # run 2: cache-only for Buchfink
    result2 = _result(("Buchfink", "Fringilla coelebs"), ("Bussard", "Buteo buteo"))
    linked2, _ = link_taxa(result2, {"sleep": 0, "llm": {"enabled": False}},
                           JsonCache(cache_path), offline=False)
    assert linked2 == 1
    assert result2.entries[0].observations[0].taxon.gbif_key == 2492462
    assert "match:buteo buteo" not in JsonCache(cache_path)  # still retryable


def test_taxa_limit_budget_is_cache_aware(tmp_path, monkeypatch) -> None:
    llm_calls: list[str] = []

    class _Inner:
        model = "fake-llm"

        def complete(self, prompt: str) -> str:
            for vern, sci in (("Heckenbraunelle", "Prunella modularis"),
                              ("Zaunkönig", "Troglodytes troglodytes")):
                if vern in prompt:
                    llm_calls.append(vern)
                    return json.dumps({"scientific_name": sci,
                                       "confidence": 0.9})
            raise AssertionError(f"unexpected prompt: {prompt[:80]}")

    monkeypatch.setattr("laubmann_kg.llm.clients._build_provider",
                        lambda backend, config: _Inner())
    gbif_calls = _patch_gbif(monkeypatch, {
        "prunella modularis": _gbif_response(key=5231437,
                                             canonical="Prunella modularis"),
        "troglodytes troglodytes": _gbif_response(
            key=2493179, canonical="Troglodytes troglodytes")})
    cfg = {"sleep": 0, "limit": 1, "llm": {"cache_dir": str(tmp_path / "llm")}}
    cache = JsonCache(tmp_path / "gbif.json")

    linked1, rows1 = link_taxa(_result(("Heckenbraunelle", None),
                                       ("Zaunkönig", None)),
                               cfg, cache, offline=False)
    assert linked1 == 1                           # budget spent on name1
    assert [r["vernacular_de"] for r in rows1] == ["Heckenbraunelle"]

    linked2, rows2 = link_taxa(_result(("Heckenbraunelle", None),
                                       ("Zaunkönig", None)),
                               cfg, cache, offline=False)
    assert linked2 == 2                           # cached name1 is budget-free
    assert [r["vernacular_de"] for r in rows2] == ["Heckenbraunelle", "Zaunkönig"]
    assert llm_calls == ["Heckenbraunelle", "Zaunkönig"]  # one real call each
    assert gbif_calls == ["Prunella modularis", "Troglodytes troglodytes"]


# --- orchestrator ------------------------------------------------------------

def test_review_csv_columns_exact(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {"fringilla coelebs": _gbif_response(),
                              "turdus merula": _gbif_response(
                                  key=999, canonical="Turdus merula")})

    def _boom(result, cfg, cache, offline):
        raise RuntimeError("persons section exploded")
    monkeypatch.setattr(linking, "link_persons", _boom)

    entries = []
    for i in range(3):
        entry = _entry(entry_uid=f"e_l{i:04d}", entry_id=f"L02-e02{i:02d}")
        entry.observations = [_obs(entry.entry_uid, "Buchfink", "Fringilla coelebs")]
        if i == 0:  # Amsel appears once, Buchfink three times -> usage order
            entry.observations.append(
                _obs(entry.entry_uid, "Amsel", "Turdus merula", index=1))
        entries.append(entry)
    result = ExtractionResult(entries=entries)

    summary = run_linking(result, {
        "cache_dir": str(tmp_path / "cache"), "review_dir": str(tmp_path / "review"),
        "taxa": {"sleep": 0, "llm": {"enabled": False}}, "persons": {"sleep": 0}})
    assert summary["taxa_linked"] == 2 and summary["persons_linked"] == 0

    taxon_csv = tmp_path / "review" / "taxon_link_review.csv"
    person_csv = tmp_path / "review" / "person_link_review.csv"
    assert taxon_csv.exists() and person_csv.exists()  # finally block wrote both
    with taxon_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        data = list(reader)
    assert header == TAXON_REVIEW_FIELDS
    assert header[-1] == "decision"
    assert [row[0] for row in data] == ["Buchfink", "Amsel"]  # usage-desc order
    assert all(row[-1] == "" for row in data)                 # decision blank
    with person_csv.open(newline="", encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == PERSON_REVIEW_FIELDS


def test_run_linking_never_raises(tmp_path, monkeypatch) -> None:
    _raise_get_json(monkeypatch)

    def _boom(result, cfg, cache, offline):
        raise RuntimeError("boom")
    monkeypatch.setattr(linking, "link_taxa", _boom)
    monkeypatch.setattr(linking, "link_persons", _boom)
    result = _result(("Buchfink", "Fringilla coelebs"))
    summary = run_linking(result, {"cache_dir": str(tmp_path / "cache"),
                                   "review_dir": str(tmp_path / "review")})
    assert summary == {"taxa_linked": 0, "taxa_review": 0,
                       "persons_linked": 0, "persons_review": 0}
    assert (tmp_path / "review" / "taxon_link_review.csv").exists()


def test_review_decisions_survive_rerun_and_failure(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {"fringilla coelebs": _gbif_response(
        match_type="FUZZY", confidence=80)})  # below fuzzy_min -> review row
    cfg = {"cache_dir": str(tmp_path / "cache"),
           "review_dir": str(tmp_path / "review"),
           "taxa": {"sleep": 0, "llm": {"enabled": False}},
           "persons": {"enabled": False}}
    csv_path = tmp_path / "review" / "taxon_link_review.csv"

    run_linking(_result(("Buchfink", "Fringilla coelebs")), cfg)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["decision"] for r in rows] == [""]
    rows[0]["decision"] = "y"                     # human adjudication
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TAXON_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    run_linking(_result(("Buchfink", "Fringilla coelebs")), cfg)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rerun = list(csv.DictReader(handle))
    assert [r["vernacular_de"] for r in rerun] == ["Buchfink"]
    assert [r["decision"] for r in rerun] == ["y"]  # adjudication survives rerun

    def _boom(result, cfg, cache, offline):
        raise RuntimeError("taxa section exploded")
    monkeypatch.setattr(linking, "link_taxa", _boom)
    run_linking(_result(("Buchfink", "Fringilla coelebs")), cfg)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        after_failure = list(csv.DictReader(handle))
    assert [r["decision"] for r in after_failure] == ["y"]  # not truncated


def test_determinism(tmp_path, monkeypatch) -> None:
    _patch_gbif(monkeypatch, {
        "fringilla coelebs": _gbif_response(),
        "turdus merula": _gbif_response(key=999, canonical="Turdus merula"),
    })
    cache = JsonCache(tmp_path / "gbif.json")

    def _run():
        result = _result(("Buchfink", "Fringilla coelebs"),
                         ("Amsel", "Turdus merula"), n_entries=2)
        linked, rows = link_taxa(result, {"sleep": 0, "llm": {"enabled": False}},
                                 cache, offline=False)
        taxa = [(o.taxon.vernacular_de, o.taxon.gbif_key, o.taxon.scientific_name)
                for e in result.entries for o in e.observations]
        return linked, rows, taxa

    first = _run()
    second = _run()  # second run rides the shared cache
    assert first == second
