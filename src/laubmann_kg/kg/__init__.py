"""Export knowledge graph artifacts (RDF/Turtle + JSON-LD), SHACL-validated."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.jsonld import write_jsonld
from laubmann_kg.kg.rdf import build_graph, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation

logger = logging.getLogger(__name__)


def export(config: dict, input_dir: Optional[Path], output_dir: Path,
           validate: bool = True) -> dict:
    from laubmann_kg.pipeline import run_pipeline
    result = run_pipeline(config, input_dir)

    output_dir = Path(output_dir)
    if result.qa_flags:
        from laubmann_kg.qa import write_review_table
        write_review_table(result.qa_flags, output_dir / "review" / "qa_flags.csv")

    graph = build_graph(result)
    ttl_path = output_dir / "rdf" / "laubmann_sample.ttl"
    jsonld_path = output_dir / "jsonld" / "laubmann_sample.jsonld"
    serialize_turtle(graph, ttl_path)
    context = config.get("paths", {}).get("jsonld_context", "schemas/jsonld_context.json")
    write_jsonld(graph, jsonld_path, Path(context))

    conforms = True
    if validate and config.get("validate", True):
        paths = config.get("paths", {})
        conforms = run_shacl_validation(
            data_path=str(ttl_path),
            ontology_path=paths.get("ontology", "ontologies/laubmann.ttl"),
            shapes_path=paths.get("shapes", "ontologies/shacl_shapes.ttl"),
        )
        if not conforms:
            raise SystemExit("SHACL validation failed (violations) – export aborted.")

    return {
        "entries": len(result.entries),
        "observations": len(result.observations),
        "triples": len(graph),
        "ttl": str(ttl_path),
        "jsonld": str(jsonld_path),
        "shacl_conforms": conforms,
    }


def run(config: Path, input_dir: Path, output_dir: Path) -> None:
    """Run the kg export pipeline stage."""
    from laubmann_kg.pipeline import load_config
    logger.info("kg export: config=%s input_dir=%s output_dir=%s", config, input_dir, output_dir)
    summary = export(load_config(config), input_dir, output_dir)
    logger.info("kg export summary: %s", summary)
