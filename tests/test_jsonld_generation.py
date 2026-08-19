import json
from pathlib import Path

from laubmann_kg.kg import export


def test_jsonld_export_is_shacl_valid(sample_config, tmp_path: Path) -> None:
    summary = export(sample_config, None, tmp_path, validate=True)
    assert summary["shacl_conforms"] is True
    assert summary["observations"] >= 4  # Lachmöwe, Buchfink, Wildente, Grünspecht, Storch

    jsonld = Path(summary["jsonld"])
    assert jsonld.exists()
    doc = json.loads(jsonld.read_text(encoding="utf-8"))
    assert "@context" in doc or "@graph" in doc


def test_turtle_graph_has_expected_classes(sample_config, tmp_path: Path) -> None:
    from rdflib import Graph, Namespace, RDF

    export(sample_config, None, tmp_path, validate=False)
    graph = Graph()
    graph.parse(tmp_path / "rdf" / "laubmann_sample.ttl", format="turtle")
    lkg = Namespace("https://w3id.org/laubmann-kg/ontology#")
    assert (None, RDF.type, lkg.Observation) in graph
    assert (None, RDF.type, lkg.DiaryEntry) in graph
    assert (None, RDF.type, lkg.Taxon) in graph
    # 0.4.0: renamed / flattened classes are gone from the data
    for old in ("ObservationEvent", "BirdCall", "ObservationEvidence", "BehaviourNote", "Habitat"):
        assert (None, RDF.type, lkg[old]) not in graph, old
    # grouping superclasses are not materialised
    for abstract in ("ArchivalUnit", "EntryRecord", "RecordDetail"):
        assert (None, RDF.type, lkg[abstract]) not in graph, abstract


def test_export_all_runs_the_pipeline_once_for_rdf_and_dwca(sample_config, tmp_path: Path, monkeypatch) -> None:
    import laubmann_kg.kg as kg
    import laubmann_kg.pipeline as pipeline
    calls = []
    real = pipeline.run_pipeline
    monkeypatch.setattr(pipeline, "run_pipeline", lambda cfg, inp: (calls.append(1), real(cfg, inp))[1])
    summary = kg.export_all(sample_config, None, tmp_path, validate=True)
    assert calls == [1]                                    # one pipeline run feeds both exports
    assert summary["shacl_conforms"] is True and summary["dwca"]["valid"] is True
    assert summary["dwca"]["counts"]["occurrence.txt"] == summary["observations"]
    assert (tmp_path / "rdf" / "laubmann_sample.ttl").exists() and Path(summary["dwca"]["zip"]).exists()
