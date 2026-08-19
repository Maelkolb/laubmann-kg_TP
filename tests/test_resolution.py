"""Entity resolution: taxa (GBIF key), persons (name rules), places/habitats."""

from __future__ import annotations

import csv
from pathlib import Path

from rdflib import Literal
from rdflib.namespace import RDF, SKOS

from laubmann_kg.kg.model import DIARIST, DiaryEntry, Habitat, Observation, Person, Place, Taxon, TravelEvent, TravelLeg
from laubmann_kg.kg.rdf import DATA, DWC, LKG, build_graph
from laubmann_kg.pipeline import ExtractionResult
from laubmann_kg.resolution import run_resolution
from laubmann_kg.resolution.common import Decisions, MergeRow, fold
from laubmann_kg.resolution.persons import merge_persons, person_key
from laubmann_kg.resolution.places import merge_habitats, merge_places
from laubmann_kg.resolution.taxa import merge_taxa

NO = Decisions()


def _entry(uid: str, persons=(), observations=(), place=None, travel=()) -> DiaryEntry:
    e = DiaryEntry(entry_uid=uid, entry_id=uid, volume=2, page_uid="p", page_id="doc_0001_L", region_uid=None,
                   scan=None, entry_date="1919-05-01", verbatim_event_date=None, location_raw=None, text_clean="t")
    e.persons = list(persons); e.observations = list(observations); e.place = place; e.travel_events = list(travel)
    for o in e.observations:
        o.entry_uid = uid
    return e


def _obs(taxon, place=None, habitat=None, observer=None, i=0) -> Observation:
    return Observation(entry_uid="", taxon=taxon, verbatim_notes="n", place=place, habitat=habitat,
                       observer=observer, index=i)


# --------------------------------------------------------------------------- taxa

def test_taxa_merge_on_gbif_key_keeps_written_name_and_observation_uid() -> None:
    a = Taxon("Storch", scientific_name="Ciconia ciconia", gbif_key=2480962, gbif_match_type="EXACT")
    b = Taxon("Störche", scientific_name="Ciconia ciconia", gbif_key=2480962, gbif_match_type="EXACT")
    c = Taxon("Weißstorch", scientific_name="Ciconia ciconia", gbif_key=2480962, gbif_match_type="FUZZY")
    broad = Taxon("Bussard", scientific_name="Buteo", gbif_key=2481047, gbif_match_type="HIGHERRANK")
    broad2 = Taxon("Bussarde", scientific_name="Buteo", gbif_key=2481047, gbif_match_type="HIGHERRANK")
    e1 = _entry("e1", observations=[_obs(a, i=0), _obs(a, i=1), _obs(b, i=2), _obs(c, i=3), _obs(broad, i=4), _obs(broad2, i=5)])
    result = ExtractionResult(entries=[e1])
    uid_before = e1.observations[2].uid
    n, rows = merge_taxa(result, {}, NO)
    assert n == 2
    obs_b = e1.observations[2]
    assert obs_b.taxon.vernacular_de == "Storch" and obs_b.taxon_verbatim == "Störche"
    assert obs_b.uid == uid_before                                   # observation IRI is stable
    assert set(obs_b.taxon.alt_names) == {"Störche", "Weißstorch"}
    assert e1.observations[0].taxon.alt_names == obs_b.taxon.alt_names   # canonical carries the altLabels too
    assert e1.observations[4].taxon.vernacular_de == "Bussard" and e1.observations[5].taxon.vernacular_de == "Bussarde"  # HIGHERRANK untouched
    assert {(r.variant, r.canonical, r.rule, r.status) for r in rows} == {
        ("Störche", "Storch", "gbif-key", "auto"), ("Weißstorch", "Storch", "gbif-key", "auto")}
    # RDF: altLabels on the taxon, verbatimIdentification on the merged observation only
    g = build_graph(result)
    tnode = DATA[obs_b.taxon.uid]
    assert set(g.objects(tnode, SKOS.altLabel)) == {Literal("Störche", lang="de"), Literal("Weißstorch", lang="de")}
    assert g.value(DATA[obs_b.uid], DWC.verbatimIdentification) == Literal("Störche", lang="de")
    assert g.value(DATA[e1.observations[0].uid], DWC.verbatimIdentification) is None
    assert len(set(g.subjects(RDF.type, LKG.Taxon))) == 3           # Storch, Bussard, Bussarde


def test_taxa_reviewer_can_reject_an_auto_merge(tmp_path: Path) -> None:
    a = Taxon("Storch", gbif_key=1, gbif_match_type="EXACT"); b = Taxon("Störche", gbif_key=1, gbif_match_type="EXACT")
    result = ExtractionResult(entries=[_entry("e1", observations=[_obs(a), _obs(b, i=1)])])
    csv_path = tmp_path / "taxon_merges.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["merge_id", "section", "variant", "canonical", "decision"]); w.writeheader()
        w.writerow({"merge_id": "taxa: Störche -> Storch", "section": "taxa", "variant": "Störche", "canonical": "Storch", "decision": "n"})
    n, rows = merge_taxa(result, {}, Decisions.load(csv_path))
    assert n == 0 and rows[0].status == "auto"


# --------------------------------------------------------------------------- persons

def test_person_key_strips_titles_folds_umlauts_and_keeps_gendered_forms() -> None:
    assert person_key("Prof. Dr. Walter Wüst") == "walter wuest"
    assert person_key("W. Wuest") == "w wuest" and person_key("W.Wüst") == "w wuest"
    assert person_key("Frau Wüst") == "frau wuest" and person_key("Herr Wüst") == "wuest"


def test_persons_merge_rules() -> None:
    walter = Person("Walter Wüst", role="companion")
    e = [_entry("e1", persons=[walter, Person("Kiefer", role="companion")]),
         _entry("e2", persons=[Person("W. Wüst", role="source"), Person("Dr. Wüst", role="companion")]),
         _entry("e3", persons=[Person("Wuest", role="source"), Person("Frau Wüst", role="companion")]),
         _entry("e4", persons=[Person("Adolf Müller"), Person("Alois Müller"), Person("A. Müller"), Person("Müller")]),
         _entry("e5", persons=[Person("Hans Kiefer"), Person("Kiefer")], observations=[_obs(Taxon("Star"), observer=Person("W. Wüst"))])]
    result = ExtractionResult(entries=e)
    n, rows = merge_persons(result, {}, NO)
    by_rule = {(r.variant, r.rule, r.status) for r in rows}
    assert ("W. Wüst", "initial-unique", "auto") in by_rule
    assert ("Dr. Wüst", "same-key", "auto") in by_rule or ("Dr. Wüst", "surname-unique", "auto") in by_rule
    assert ("Wuest", "same-key", "auto") in by_rule or ("Wuest", "surname-unique", "auto") in by_rule
    assert ("Kiefer", "surname-unique", "auto") in by_rule
    assert not any(r.variant == "Frau Wüst" for r in rows)                                # gendered form kept apart
    assert ("A. Müller", "initial-ambiguous", "candidate") in by_rule                     # Adolf vs Alois
    assert any(r.variant == "Müller" and r.status == "candidate" for r in rows)
    canonical = e[1].persons[0]
    assert canonical.name == "Walter Wüst" and canonical.role == "source"                # role of the mention kept
    assert set(canonical.alt_names) >= {"W. Wüst", "Wuest"}
    assert [p.name for p in e[1].persons] == ["Walter Wüst"]                              # duplicate mention collapsed
    assert e[4].observations[0].observer.name == "Walter Wüst"
    assert [p.name for p in e[3].persons] == ["Adolf Müller", "Alois Müller", "A. Müller", "Müller"]  # ambiguous untouched
    assert n >= 4
    # RDF: altLabels on the person; role edges from the merged mentions
    g = build_graph(result)
    pnode = DATA[canonical.uid]
    assert Literal("W. Wüst") in set(g.objects(pnode, SKOS.altLabel))
    assert (DATA["entry_e2"], LKG.mentionsSource, pnode) in g


def test_persons_accept_candidate_and_never_touch_the_diarist() -> None:
    e = [_entry("e1", persons=[Person("Adolf Müller"), Person("Alois Müller"), Person("A. Müller"), Person("Laubmann"), DIARIST])]
    result = ExtractionResult(entries=e)
    dec = Decisions(); dec.by_id["persons: A. Müller -> Adolf Müller"] = "y"   # accept exactly this pair
    dec.by_id["persons: A. Müller -> Alois Müller"] = "n"                          # (rejecting the other pair changes nothing else)
    n, rows = merge_persons(result, {}, dec)
    cand = [r for r in rows if r.variant == "A. Müller"]
    assert cand and all(r.status == "candidate" for r in cand)
    # accepted: A. Müller merged into Adolf Müller only
    adolf = next(p for p in e[0].persons if p.name == "Adolf Müller")
    assert adolf.alt_names == ("A. Müller",) and "A. Müller" not in [p.name for p in e[0].persons]
    # bare "Laubmann" folds into the diarist; the diarist node keeps its identity (uid) and gains the altLabel
    diarist = next(p for p in e[0].persons if p.name == DIARIST.name)
    assert diarist.uid == DIARIST.uid and diarist.alt_names == ("Laubmann",)
    assert "Laubmann" not in [p.name for p in e[0].persons]


# --------------------------------------------------------------------------- places / habitats

def test_places_orthographic_auto_and_similar_candidates() -> None:
    p1 = Place("Ismaninger Speichersee", canonical="Ismaninger Speichersee", kind="locality", lat=48.2, long=11.7)
    p2 = Place("Ismaninger Speichersee", canonical="Ismaninger  Speichersee.", kind="locality")
    p3 = Place("Woerthsee", canonical="Woerthsee", kind="settlement")
    p4 = Place("Wörthsee", canonical="Wörthsee", kind="settlement")
    p5 = Place("Dechsendorfer Weiher", canonical="Dechsendorfer Weiher", kind="locality")
    p6 = Place("Dechsendorf Weiher", canonical="Dechsendorf Weiher", kind="locality")
    leg = TravelLeg(p3, p4, via_places=(p1,), transport_mode="foot")
    e = [_entry("e1", place=p1, observations=[_obs(Taxon("Star"), place=p2), _obs(Taxon("Star"), place=p4, i=1)]),
         _entry("e2", place=p3, observations=[_obs(Taxon("Star"), place=p5), _obs(Taxon("Star"), place=p6, i=1)],
                travel=[TravelEvent("e2", legs=[leg])])]
    result = ExtractionResult(entries=e)
    n, rows = merge_places(result, {}, NO)
    auto = {(r.variant, r.canonical) for r in rows if r.status == "auto"}
    assert ("Ismaninger  Speichersee.", "Ismaninger Speichersee") in auto
    assert ("Woerthsee", "Wörthsee") in auto or ("Wörthsee", "Woerthsee") in auto
    cand = {(r.variant, r.canonical) for r in rows if r.status == "candidate"}
    assert ("Dechsendorf Weiher", "Dechsendorfer Weiher") in cand or ("Dechsendorfer Weiher", "Dechsendorf Weiher") in cand
    assert n == 2
    obs = e[0].observations[0]
    assert obs.place.name == "Ismaninger Speichersee" and obs.place.lat == 48.2 and "Ismaninger  Speichersee." in obs.place.alt_names
    # travel legs re-pointed too; candidates untouched
    leg2 = e[1].travel_events[0].legs[0]
    assert leg2.via_places[0].name == "Ismaninger Speichersee" and leg2.departure_place.name == leg2.arrival_place.name
    assert e[1].observations[1].place.name == "Dechsendorf Weiher"
    assert set(result.places) == {p.uid for p in (e[0].place, obs.place, e[0].observations[1].place, e[1].place, p5, p6)}


def test_habitats_merge_and_emit_altlabel() -> None:
    e = [_entry("e1", observations=[_obs(Taxon("Star"), habitat=Habitat("Auwald")), _obs(Taxon("Star"), habitat=Habitat("Auwald."), i=1),
                                    _obs(Taxon("Star"), habitat=Habitat("Auwälder"), i=2)])]
    result = ExtractionResult(entries=e)
    n, rows = merge_habitats(result, {"similarity": 0.8}, NO)
    assert n == 1 and {(r.variant, r.status) for r in rows} == {("Auwald.", "auto"), ("Auwälder", "candidate")}
    assert e[0].observations[1].habitat.label == "Auwald" and e[0].observations[1].habitat.alt_labels == ("Auwald.",)
    g = build_graph(result)
    assert Literal("Auwald.", lang="de") in set(g.objects(DATA[Habitat("Auwald").uid], SKOS.altLabel))


def test_run_resolution_writes_review_files_and_reads_decisions(tmp_path: Path) -> None:
    a = Taxon("Storch", gbif_key=1, gbif_match_type="EXACT"); b = Taxon("Störche", gbif_key=1, gbif_match_type="EXACT")
    result = ExtractionResult(entries=[_entry("e1", observations=[_obs(a), _obs(b, i=1)], persons=[Person("Walter Wüst"), Person("W. Wüst")])])
    summary = run_resolution(result, {"review_dir": str(tmp_path)})
    assert summary["taxa_merged"] == 1 and summary["persons_merged"] == 1
    for name in ("taxon_merges.csv", "person_merges.csv", "place_merges.csv", "habitat_merges.csv"):
        assert (tmp_path / name).exists()
    rows = list(csv.DictReader((tmp_path / "taxon_merges.csv").open(encoding="utf-8")))
    assert rows[0]["merge_id"] == "taxa: Störche -> Storch" and rows[0]["decision"] == ""
    # a decision written into the file is picked up on the next run
    rows[0]["decision"] = "n"
    with (tmp_path / "taxon_merges.csv").open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    result2 = ExtractionResult(entries=[_entry("e1", observations=[_obs(a), _obs(b, i=1)])])
    assert run_resolution(result2, {"review_dir": str(tmp_path)})["taxa_merged"] == 0
    assert list(csv.DictReader((tmp_path / "taxon_merges.csv").open(encoding="utf-8")))[0]["decision"] == "n"  # decision survives


def test_fold() -> None:
    assert fold("St. Heinrich") == fold("Sankt Heinrich") == "sankt heinrich"
    assert fold("Wörthsee") == fold("Woerthsee") == "woerthsee"
    assert fold("Ismaninger  Speichersee.") == "ismaninger speichersee"


def test_decisions_are_per_pair_not_per_variant() -> None:
    dec = Decisions(); dec.by_id["persons: Müller -> Arno Müller"] = "n"
    auto = MergeRow("persons", "Müller", "Adolf Müller", "dominant", "auto", 20, 3000)
    rejected = MergeRow("persons", "Müller", "Arno Müller", "surname-ambiguous", "candidate", 20, 30)
    assert dec.applies(auto)                # the rejection of another pair does not veto the automatic merge
    assert not dec.applies(rejected)
    dec.by_id["persons: Müller -> Adolf Müller"] = "n"
    assert not dec.applies(auto)            # rejecting the exact pair does


def test_person_candidates_are_cluster_level_and_accepted_chains_follow() -> None:
    e = [_entry("e1", persons=[Person("Wüst"), Person("Dr Wüst"), Person("Herr Wüst"), Person("Walter Wüst"),
                                 Person("Dr. Walter Wüst"), Person("Karl Wüst")])]
    result = ExtractionResult(entries=e)
    # the decision was recorded in an earlier run under the then-canonical label "Dr. Walter Wüst"
    dec = Decisions(); dec.by_id["persons: Wüst -> Dr. Walter Wüst"] = "y"
    n, rows = merge_persons(result, {}, dec)
    cand = [(r.variant, r.canonical) for r in rows if r.status == "candidate"]
    # one row per pair of clusters, named by the cluster canonicals (not "Dr Wüst -> …" three times)
    assert sorted(cand) == [("Wüst", "Karl Wüst"), ("Wüst", "Walter Wüst")]
    walter = next(p for p in e[0].persons if p.name == "Walter Wüst")
    assert set(walter.alt_names) == {"Wüst", "Dr Wüst", "Herr Wüst", "Dr. Walter Wüst"}   # the whole cluster followed
    assert [p.name for p in e[0].persons] == ["Walter Wüst", "Karl Wüst"]
