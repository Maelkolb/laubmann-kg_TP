"""Export knowledge graph artifacts (RDF/Turtle + JSON-LD), SHACL-validated."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.jsonld import write_jsonld
from laubmann_kg.kg.rdf import build_graph, serialize_turtle
from laubmann_kg.kg.shacl_validate import run_shacl_validation

logger = logging.getLogger(__name__)


def write_transcript_corrections(result, path: Path) -> Optional[Path]:
    """The model's corrections of the transcription (visual reading, prompt v5)
    in the review/text_corrections.csv contract (entry_uid, entry_id, old_text,
    new_text, note, reviewed_by, reviewed_at) plus ``applied``: a reviewer can
    confirm them and feed them back as data/review/text_corrections.csv."""
    import csv
    rows = []
    model = (result.provenance or {}).get("model") or "model"
    for e in result.entries:
        for old, new, applied in (getattr(e, "transcript_corrections", None) or []):
            rows.append({"entry_uid": e.entry_uid, "entry_id": e.entry_id, "old_text": old, "new_text": new,
                         "note": f"visual reading, transcript quality {e.transcript_quality or '?'}",
                         "reviewed_by": f"{model} (scan)", "reviewed_at": "", "applied": "y" if applied else "n"})
    if not rows:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    logger.info("wrote %d transcript corrections to %s", len(rows), path)
    return path


def review_dir_default(config: dict, output_dir: Path) -> dict:
    """The review CSVs a run writes (link and merge reviews) go to
    ``<output_dir>/review`` unless the config names a folder: ``data/review``
    holds the adjudicated decision files the run READS (``reviewed_csv``), and
    writing into it would overwrite them."""
    for section in ("linking", "resolution"):
        cfg = config.get(section)
        if isinstance(cfg, dict) and not cfg.get("review_dir"):
            cfg["review_dir"] = str(Path(output_dir) / "review")
    return config


def export(config: dict, input_dir: Optional[Path], output_dir: Path,
           validate: bool = True, result=None, raise_on_violation: bool = True) -> dict:
    """RDF/Turtle + JSON-LD (+ SHACL) of ``result``; runs the pipeline when no
    result is passed. ``export_all`` shares one pipeline run with the DwC-A."""
    if result is None:
        from laubmann_kg.pipeline import run_pipeline
        result = run_pipeline(review_dir_default(config, output_dir), input_dir)

    output_dir = Path(output_dir)
    if result.qa_flags:
        from laubmann_kg.qa import write_review_table
        write_review_table(result.qa_flags, output_dir / "review" / "qa_flags.csv")
    write_transcript_corrections(result, output_dir / "review" / "transcript_corrections.csv")

    graph = build_graph(result)
    ttl_path = output_dir / "rdf" / "laubmann_sample.ttl"
    jsonld_path = output_dir / "jsonld" / "laubmann_sample.jsonld"
    serialize_turtle(graph, ttl_path)
    context = config.get("paths", {}).get("jsonld_context", "schemas/jsonld_context.json")
    write_jsonld(graph, jsonld_path, Path(context))

    from laubmann_kg.kg.explorer import write_explorer
    explorer_meta = {
        "source": ttl_path.name,
        "ontology": (config.get("paths") or {}).get("ontology", "ontologies/laubmann.ttl"),
        "triples": len(graph),
        "sample": config.get("sample") or {},
        "backend": (result.provenance or {}).get("backend"),
        "model": (result.provenance or {}).get("model"),
        "prompt_sha256": (result.provenance or {}).get("prompt_sha256"),
        "started_at": (result.provenance or {}).get("started_at"),
    }
    explorer = write_explorer(result, output_dir, meta=explorer_meta)
    (output_dir / "run.json").write_text(
        json.dumps({**explorer_meta, "entries": len(result.entries),
                     "observations": len(result.observations),
                     "ttl": str(ttl_path), "explorer": explorer},
                    ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    conforms = True
    if validate and config.get("validate", True):
        paths = config.get("paths", {})
        conforms = run_shacl_validation(
            data_path=str(ttl_path),
            ontology_path=paths.get("ontology", "ontologies/laubmann.ttl"),
            shapes_path=paths.get("shapes", "ontologies/shacl_shapes.ttl"),
        )
        if not conforms and raise_on_violation:
            raise SystemExit("SHACL validation failed (violations) – export aborted.")

    return {
        "entries": len(result.entries),
        "observations": len(result.observations),
        "triples": len(graph),
        "ttl": str(ttl_path),
        "jsonld": str(jsonld_path),
        "shacl_conforms": conforms,
        "explorer": explorer,
    }


def export_all(config: dict, input_dir: Optional[Path], output_dir: Path, validate: bool = True) -> dict:
    """One pipeline run -> RDF/JSON-LD (+ SHACL) and the Darwin Core Archive.
    The two exports are consistent by construction (a live LLM call for an
    uncached entry is made once, not once per export)."""
    from laubmann_kg.dwca import export as export_dwca
    from laubmann_kg.pipeline import run_pipeline
    result = run_pipeline(review_dir_default(config, output_dir), input_dir)
    # SHACL violations are reported after BOTH outputs exist: a failing graph
    # must not cost the archive of a multi-hour run
    summary = export(config, input_dir, output_dir, validate=validate, result=result,
                     raise_on_violation=False)
    summary["dwca"] = export_dwca(config, input_dir, output_dir, validate=validate, result=result)
    if not summary["shacl_conforms"]:
        raise SystemExit("SHACL validation failed (violations) – see the report; "
                         "RDF, JSON-LD and DwC-A were written.")
    return summary


def run(config: Path, input_dir: Path, output_dir: Path) -> None:
    """Run the kg export pipeline stage."""
    from laubmann_kg.pipeline import load_config
    logger.info("kg export: config=%s input_dir=%s output_dir=%s", config, input_dir, output_dir)
    summary = export(load_config(config), input_dir, output_dir)
    logger.info("kg export summary: %s", summary)


def run_all(config: Path, input_dir: Path, output_dir: Path) -> None:
    """Run RDF/JSON-LD + SHACL + DwC-A from one pipeline run."""
    from laubmann_kg.pipeline import load_config
    logger.info("kg+dwca export: config=%s input_dir=%s output_dir=%s", config, input_dir, output_dir)
    summary = export_all(load_config(config), input_dir, output_dir)
    logger.info("kg+dwca export summary: %s", summary)
