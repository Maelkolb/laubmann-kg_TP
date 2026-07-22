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
    lkg = Namespace("https://lkg.example.org/ontology#")
    assert (None, RDF.type, lkg.ObservationEvent) in graph
    assert (None, RDF.type, lkg.DiaryEntry) in graph
    assert (None, RDF.type, lkg.Taxon) in graph
