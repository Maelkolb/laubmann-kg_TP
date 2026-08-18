"""RDF emission of the full kg/model.py contract (ontology v0.3.0).

Builds one entry with every new field populated, emits the graph, checks the
predicates/datatypes, and validates the Turtle against the SHACL shapes with
inference="none" (superclasses materialised at emit time).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from laubmann_kg.kg.jsonld import DEFAULT_CONTEXT, write_jsonld
from laubmann_kg.kg.model import (
    Behaviour,
    DiaryEntry,
    Evidence,
    Habitat,
    Observation,
    Person,
    Place,
    Taxon,
    TravelEvent,
    TravelLeg,
    WeatherReport,
)
from laubmann_kg.kg.rdf import DATA, DWC, DWCIRI, GEO, LKG, SCHEMA, build_graph, run_uid, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation
from laubmann_kg.kg.sparql import QUERIES, run_all
from laubmann_kg.pipeline import ExtractionResult

REPO_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = REPO_ROOT / "ontologies" / "laubmann.ttl"
SHAPES = REPO_ROOT / "ontologies" / "shacl_shapes.ttl"

PROVENANCE = {
    "backend": "google", "provider": "google", "model": "gemini-2.5-flash",
    "prompt": "observation_extraction", "prompt_sha256": "ab" * 32,
    "temperature": 0.0, "thinking_level": None,
    "started_at": "2026-08-17T10:00:00+00:00",
    "method": "LLM extraction from diary text (gemini-2.5-flash)",
}


def _full_entry() -> DiaryEntry:
    entry_place = Place("Erlangen", canonical="Erlangen", lat=49.5897, long=11.0039,
                        kind="settlement")
    own = Place("Dechsendorfer Weiher", canonical="Dechsendorfer Weiher", kind="locality")
    stork = Taxon("Storch", scientific_name="Ciconia ciconia", match_method="gazetteer",
                  confidence=0.98, rank="species", is_bird=True,
                  gbif_key=2480962, gbif_match_type="EXACT")
    warblers = Taxon("Rohrsänger", rank="group", is_bird=True)
    entry = DiaryEntry(
        entry_uid="e_rdf1", entry_id="L03-e0001", volume=3, page_uid="p_rdf1",
        page_id="L03-p012", region_uid="r_rdf1", scan="0012",
        entry_date="1919-04-12", verbatim_event_date="12. IV. 1919",
        location_raw="Erlangen", text_clean="Text.",
        place=entry_place, entry_kind="field-day", entry_date_end="1919-04-13",
        date_plausible=True, date_note="Datum aus Kontext korrigiert",
        header_date="1919-04-11",
    )
    absence = Observation(
        entry_uid="e_rdf1", taxon=stork, verbatim_notes="Keine Störche mehr am Weiher",
        place=own, locality=own, individual_count=0, occurrence_status="absent",
        index=0, event_date="1919-04-13", event_time="07:30",
        sex="mixed", life_stage="adult", breeding_evidence="probable",
        vitality="alive", movement_kind="departing", flight_direction="NO→SW",
        identification_qualifier="wohl", count_min=3, count_max=4,
        evidence=[Evidence("auditory", "Lautäußerung", is_call=True, call_type="call"),
                  Evidence("visual", "Sichtbeobachtung")],
        behaviour=[Behaviour("balzend")],
        habitat=Habitat("Weiher / Schilf"),
    )
    plain = Observation(entry_uid="e_rdf1", taxon=warblers, verbatim_notes="Rohrsänger singen",
                        place=entry_place, index=1)   # no evidence, inherits entry place
    entry.observations = [absence, plain]
    entry.persons = [Person("Kiefer", role="companion")]
    entry.weather = WeatherReport("trüb", temperature_value=8.0, temperature_unit="C")
    entry.travel_events = [TravelEvent("e_rdf1", legs=[
        TravelLeg(entry_place, own, transport_mode="foot")])]
    return entry


def _graph(provenance=PROVENANCE) -> tuple[Graph, DiaryEntry]:
    entry = _full_entry()
    return build_graph(ExtractionResult(entries=[entry], provenance=provenance)), entry


def test_observation_detail_predicates() -> None:
    graph, entry = _graph()
    absence, plain = entry.observations
    node = DATA[absence.uid]

    # status/counts on the OBSERVATION (no longer on the evidence)
    assert graph.value(node, DWC.occurrenceStatus) == Literal("absent")
    count = graph.value(node, LKG.individualCount)
    assert count == Literal(0, datatype=XSD.integer)      # 0 allowed for absences
    assert graph.value(node, DWC.individualCount) == count
    assert graph.value(node, LKG.individualCountMin) == Literal(3, datatype=XSD.integer)
    assert graph.value(node, LKG.individualCountMax) == Literal(4, datatype=XSD.integer)
    for evidence in graph.objects(node, LKG.hasEvidence):
        assert graph.value(evidence, DWC.occurrenceStatus) is None

    # demography / hedge / movement
    assert graph.value(node, DWC.sex) == Literal("mixed")
    assert graph.value(node, DWC.lifeStage) == Literal("adult")
    assert graph.value(node, DWC.vitality) == Literal("alive")
    assert graph.value(node, DWC.identificationQualifier) == Literal("wohl")
    assert graph.value(node, LKG.breedingEvidence) == Literal("probable")
    assert graph.value(node, DWC.reproductiveCondition) == Literal("breeding")
    assert graph.value(node, LKG.movementKind) == Literal("departing")
    assert graph.value(node, LKG.flightDirection) == Literal("NO→SW", lang="de")

    # own date/time vs. inherited entry date
    assert graph.value(node, DWC.eventDate) == Literal("1919-04-13", datatype=XSD.date)
    assert graph.value(node, DWC.eventTime) == Literal("07:30")
    assert graph.value(DATA[plain.uid], DWC.eventDate) == Literal("1919-04-12", datatype=XSD.date)
    assert graph.value(DATA[plain.uid], DWC.eventTime) is None

    # own locality vs. inherited entry place
    own = DATA[absence.locality.uid]
    assert graph.value(node, LKG.hasLocality) == own
    assert graph.value(node, LKG.observedAt) == own
    assert graph.value(node, DWC.verbatimLocality) == Literal("Dechsendorfer Weiher")
    assert graph.value(DATA[plain.uid], LKG.hasLocality) is None
    assert graph.value(DATA[plain.uid], LKG.observedAt) == DATA[entry.place.uid]

    # attribution co-emitted for DwC consumers
    diarist = graph.value(node, LKG.observedBy)
    assert graph.value(node, DWCIRI.recordedBy) == diarist
    assert graph.value(diarist, SCHEMA.name) == Literal("Alfred Laubmann")

    # behaviour: node + dwc:behavior literal
    assert graph.value(node, DWC.behavior) == Literal("balzend", lang="de")
    assert list(graph.objects(node, LKG.hasBehaviour))

    # no evidence stated -> no hasEvidence at all
    assert list(graph.objects(DATA[plain.uid], LKG.hasEvidence)) == []


def test_evidence_and_habitat() -> None:
    graph, entry = _graph()
    absence = entry.observations[0]
    node = DATA[absence.uid]
    evidence = {graph.value(e, LKG.evidenceKind): e for e in graph.objects(node, LKG.hasEvidence)}
    assert set(evidence) == {LKG.evidence_auditory, LKG.evidence_visual}
    call = evidence[LKG.evidence_auditory]
    assert (call, RDF.type, LKG.BirdCall) in graph
    assert (call, RDF.type, LKG.ObservationEvidence) in graph      # materialised superclass
    assert graph.value(call, LKG.callType) == Literal("call")
    assert graph.value(call, LKG.callTranscription) is None       # no "Ruf" placeholder
    assert Literal("Ruf") not in set(graph.objects(None, None))

    habitat = graph.value(node, LKG.hasHabitat)
    assert (habitat, RDF.type, LKG.Habitat) in graph
    assert (habitat, RDF.type, SKOS.Concept) in graph
    assert (habitat, RDF.type, LKG.Place) not in graph             # Habitat is NOT a Place
    assert graph.value(habitat, SKOS.prefLabel) == Literal("Weiher / Schilf", lang="de")
    assert graph.value(habitat, SKOS.inScheme) == LKG.habitatScheme
    assert graph.value(habitat, DWC.habitat) == Literal("Weiher / Schilf", lang="de")
    assert graph.value(node, DWCIRI.habitat) == habitat
    assert graph.value(node, DWC.habitat) == Literal("Weiher / Schilf", lang="de")


def test_taxon_place_entry_page_predicates() -> None:
    graph, entry = _graph()
    stork = DATA[entry.observations[0].taxon.uid]
    assert graph.value(stork, RDFS.label) == Literal("Storch", lang="de")
    assert graph.value(stork, DWC.vernacularName) == Literal("Storch", lang="de")
    assert graph.value(stork, DWC.taxonRank) == Literal("species")
    assert graph.value(stork, LKG.isBird) == Literal(True, datatype=XSD.boolean)
    assert graph.value(stork, LKG.matchMethod) == Literal("gazetteer")
    conf = graph.value(stork, LKG.matchConfidence)
    assert conf.datatype == XSD.decimal and conf.toPython() == Decimal("0.98")
    assert graph.value(stork, LKG.gbifMatchType) == Literal("EXACT")
    assert (stork, SKOS.exactMatch, URIRef("https://www.gbif.org/species/2480962")) in graph
    unresolved = DATA[entry.observations[1].taxon.uid]
    assert graph.value(unresolved, DWC.taxonRank) == Literal("group")
    assert graph.value(unresolved, SKOS.note) is not None          # still flags uncertainty

    place = DATA[entry.place.uid]
    assert graph.value(place, LKG.placeKind) == Literal("settlement")
    lat = graph.value(place, GEO.lat)
    assert lat.datatype == XSD.decimal and lat.toPython() == Decimal("49.5897")
    assert graph.value(place, DWC.decimalLatitude) == lat
    assert graph.value(place, DWC.decimalLongitude) == graph.value(place, GEO.long)
    assert graph.value(place, DWC.geodeticDatum) == Literal("WGS84")

    node = DATA[entry.uid]
    assert graph.value(node, DCTERMS.identifier) == Literal("L03-e0001")
    assert graph.value(node, LKG.entryPlace) == place
    assert graph.value(node, LKG.entryKind) == Literal("field-day")
    assert graph.value(node, LKG.entryDate) == Literal("1919-04-12", datatype=XSD.date)
    assert graph.value(node, LKG.entryDateEnd) == Literal("1919-04-13", datatype=XSD.date)
    assert graph.value(node, DWC.eventDate) == Literal("1919-04-12/1919-04-13")  # interval
    assert graph.value(node, DWC.verbatimEventDate) == Literal("12. IV. 1919")
    assert graph.value(node, LKG.datePlausible) == Literal(True, datatype=XSD.boolean)
    assert graph.value(node, LKG.dateNote) == Literal("Datum aus Kontext korrigiert", lang="de")
    assert graph.value(node, SKOS.note) == Literal("Datum aus Kontext korrigiert", lang="de")

    page = graph.value(node, LKG.hasPage)
    volume = graph.value(node, LKG.hasVolume)
    assert graph.value(page, DCTERMS.identifier) == Literal("L03-p012")
    assert graph.value(page, DCTERMS.isPartOf) == volume
    region = graph.value(node, LKG.hasSourceRegion)
    assert region == DATA["region_r_rdf1"]
    assert (region, RDF.type, LKG.SourceRegion) in graph
    assert (region, RDF.type, URIRef("http://www.w3.org/ns/oa#Annotation")) in graph
    assert graph.value(region, RDFS.label) is not None

    person = graph.value(node, LKG.mentionsPerson)
    assert graph.value(person, SCHEMA.name) == Literal("Kiefer")
    assert graph.value(person, SKOS.note) == Literal("companion")


def test_prov_run_skeleton() -> None:
    graph, entry = _graph()
    run = DATA[run_uid(PROVENANCE)]
    assert (run, RDF.type, PROV.Activity) in graph
    assert graph.value(run, RDFS.label) is not None
    started = graph.value(run, PROV.startedAtTime)
    assert started.datatype == XSD.dateTime and str(started) == "2026-08-17T10:00:00+00:00"
    agent = graph.value(run, PROV.wasAssociatedWith)
    assert agent == DATA["agent_gemini-2.5-flash"]
    assert (agent, RDF.type, PROV.SoftwareAgent) in graph
    assert graph.value(agent, RDFS.label) == Literal("gemini-2.5-flash")
    assert graph.value(agent, LKG.backend) == Literal("google")
    prompt = graph.value(run, PROV.used)
    assert prompt == DATA["prompt_" + "ab" * 6]
    assert (prompt, RDF.type, PROV.Entity) in graph
    assert graph.value(prompt, RDFS.label) == Literal("observation_extraction")
    assert graph.value(prompt, DCTERMS.identifier) == Literal("ab" * 32)
    # every observation, travel event and weather report points at the run
    for obs in entry.observations:
        assert graph.value(DATA[obs.uid], PROV.wasGeneratedBy) == run
    for event in entry.travel_events:
        assert graph.value(DATA[event.uid], PROV.wasGeneratedBy) == run
    assert graph.value(DATA[entry.weather.uid(entry.entry_uid)], PROV.wasGeneratedBy) == run
    # stable id: same provenance -> same run IRI
    assert run_uid(dict(PROVENANCE)) == run_uid(PROVENANCE)


def test_empty_provenance_emits_no_run() -> None:
    graph, entry = _graph(provenance={})
    assert list(graph.subjects(RDF.type, PROV.Activity)) == []
    assert list(graph.subjects(PROV.wasGeneratedBy, None)) == []
    assert run_uid({}) is None
    # also when built without the keyword at all (hand-built test results)
    graph2 = build_graph(ExtractionResult(entries=[_full_entry()]))
    assert list(graph2.subjects(RDF.type, PROV.Activity)) == []


def test_offline_pipeline_provenance_without_prompt(sample_config, tmp_path) -> None:
    from laubmann_kg.pipeline import run_pipeline
    result = run_pipeline(sample_config, None)
    assert result.provenance.get("backend") == "offline"
    graph = build_graph(result)
    runs = list(graph.subjects(RDF.type, PROV.Activity))
    assert len(runs) == 1
    assert graph.value(runs[0], PROV.used) is None            # no prompt hash offline
    agent = graph.value(runs[0], PROV.wasAssociatedWith)
    assert graph.value(agent, LKG.backend) == Literal("offline")


def test_turtle_prefixes_and_shacl_conformance(tmp_path) -> None:
    graph, _ = _graph()
    ttl = tmp_path / "full.ttl"
    serialize_turtle(graph, ttl)
    text = ttl.read_text(encoding="utf-8")
    assert "@prefix geo: <http://www.w3.org/2003/01/geo/wgs84_pos#> ." in text
    assert "geo1:" not in text
    for prefix in ("dwciri:", "prov:", "dcterms:", "schema:", "rdfs:"):
        assert f"@prefix {prefix}" in text
    assert run_shacl_validation(data_path=str(ttl), ontology_path=str(ONTOLOGY),
                                shapes_path=str(SHAPES))
    # round-trip: the Turtle re-parses to the same triple count
    reparsed = Graph().parse(str(ttl), format="turtle")
    assert len(reparsed) == len(graph)


def test_jsonld_default_context_is_repo_relative(tmp_path, monkeypatch) -> None:
    assert DEFAULT_CONTEXT.is_absolute() and DEFAULT_CONTEXT.exists()
    monkeypatch.chdir(tmp_path)                        # cwd elsewhere must not matter
    graph, entry = _graph()
    out = write_jsonld(graph, tmp_path / "g.jsonld")
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["@context"]["@version"] == 1.1
    nodes = {n["@id"]: n for n in doc["@graph"]}
    obs = nodes["data:" + entry.observations[0].uid]
    assert obs["occurrenceStatus"] == "absent"
    assert obs["hasLocality"] == "data:" + entry.observations[0].locality.uid
    assert obs["wasGeneratedBy"].startswith("data:run_")


def test_competency_queries_run() -> None:
    graph, _ = _graph()
    rows = run_all(graph)
    assert set(rows) == set(QUERIES)
    own = [r for r in rows["CQ7_own_locality_vs_entry_place"] if r["ownLocality"]]
    inherited = [r for r in rows["CQ7_own_locality_vs_entry_place"] if not r["ownLocality"]]
    assert len(own) == 1 and len(inherited) == 1
    assert own[0]["entryPlace"] == "Erlangen" and own[0]["ownLocality"] == "Dechsendorfer Weiher"
    absent = rows["CQ8_absence_records"]
    assert len(absent) == 1 and absent[0]["vernacular"] == "Storch"
    assert rows["CQ4_auditory_observations"][0]["transcription"] is None   # optional now


def test_ontology_axioms_and_vocabularies_parse() -> None:
    onto = Graph().parse(str(ONTOLOGY), format="turtle")
    assert (LKG.ObservationEvent, RDFS.subClassOf, DWC.Occurrence) in onto
    assert (LKG.Habitat, RDFS.subClassOf, SKOS.Concept) in onto
    assert (LKG.Habitat, RDFS.subClassOf, LKG.Place) not in onto
    assert (LKG.observedTaxon, RDFS.subPropertyOf, DWCIRI.toTaxon) in onto
    assert (LKG.observedAt, RDFS.subPropertyOf, DWCIRI.inDescribedPlace) not in onto
    assert (LKG.containsObservation, OWL.inverseOf, LKG.derivedFromEntry) in onto
    assert (LKG.routeOrder, RDFS.domain, LKG.Route) in onto
    # the habitat scheme is declared in controlled_vocabularies.ttl (see below), not in the ontology
    assert (LKG.habitatScheme, RDF.type, SKOS.ConceptScheme) not in onto
    onto_iri = URIRef("https://w3id.org/laubmann-kg/ontology")
    assert onto.value(onto_iri, OWL.versionInfo) == Literal("0.3.0")
    for prop in ("entryPlace", "hasLocality", "entryKind", "entryDateEnd", "dateNote",
                 "datePlausible", "individualCountMin", "individualCountMax",
                 "breedingEvidence", "movementKind", "flightDirection", "evidenceKind",
                 "matchMethod", "matchConfidence", "gbifMatchType", "isBird", "placeKind",
                 "backend"):
        assert (LKG[prop], RDFS.label, None) in onto, prop

    from laubmann_kg.normalization import vocabularies as vocab
    vocabs = Graph().parse(str(REPO_ROOT / "ontologies" / "controlled_vocabularies.ttl"),
                           format="turtle")

    def _values(scheme: URIRef) -> set[str]:
        return {str(label) for concept in vocabs.subjects(SKOS.inScheme, scheme)
                for label in vocabs.objects(concept, SKOS.prefLabel) if label.language == "en"}

    assert _values(LKG.occurrenceStatusScheme) == set(vocab.OCCURRENCE_STATUS)
    assert _values(LKG.sexScheme) == set(vocab.SEXES)
    assert _values(LKG.lifeStageScheme) == set(vocab.LIFE_STAGES)
    assert _values(LKG.breedingEvidenceScheme) == set(vocab.BREEDING_EVIDENCE)
    assert _values(LKG.vitalityScheme) == set(vocab.VITALITY)
    assert _values(LKG.movementKindScheme) == set(vocab.MOVEMENT_KINDS)
    assert _values(LKG.taxonRankScheme) == set(vocab.TAXON_RANKS)
    assert _values(LKG.placeKindScheme) == set(vocab.PLACE_KINDS)
    assert _values(LKG.entryKindScheme) == set(vocab.ENTRY_KINDS)
    assert _values(LKG.evidenceKindScheme) == set(vocab.EVIDENCE_KINDS)
    assert (LKG.habitatScheme, RDF.type, SKOS.ConceptScheme) in vocabs


def test_shapes_encode_relaxed_constraints() -> None:
    # Warning-severity regressions would not fail run_shacl_validation, so pin
    # the load-bearing shape changes on the shapes graph itself.
    from rdflib.namespace import SH
    shapes = Graph().parse(str(SHAPES), format="turtle")
    call = next(shapes.subjects(SH.path, LKG.callTranscription))
    assert shapes.value(call, SH.minCount) is None                # optional transcription
    assert shapes.value(call, SH.maxCount).toPython() == 1
    count = next(p for p in shapes.subjects(SH.path, LKG.individualCount)
                 if shapes.value(p, SH.minInclusive) is not None)
    assert shapes.value(count, SH.minInclusive).toPython() == 0    # absences may carry 0
    evidence = next(shapes.subjects(SH.path, LKG.hasEvidence))
    assert shapes.value(evidence, SH.maxCount).toPython() == 4
    assert shapes.value(evidence, SH.minCount) is None
    # dwc:occurrenceStatus is constrained on the ObservationEvent shape
    obs_paths = {shapes.value(p, SH.path)
                 for p in shapes.objects(LKG.ObservationEventShape, SH.property)}
    assert {DWC.occurrenceStatus, DWC.sex, DWC.lifeStage, DWC.vitality, LKG.breedingEvidence,
            LKG.movementKind, LKG.hasLocality, LKG.individualCountMin, DWC.eventDate,
            DWC.eventTime, LKG.countQualifier, LKG.hasHabitat} <= obs_paths
    # HabitatShape stands on its own (no PlaceShape inheritance)
    assert (LKG.HabitatShape, SH.targetClass, LKG.Habitat) in shapes
