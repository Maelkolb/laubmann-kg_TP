"""Serialize the knowledge graph as JSON-LD using the project context."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from rdflib import Graph

logger = logging.getLogger(__name__)

# Resolved relative to the repository, not the current working directory, so
# notebooks / scripts started elsewhere still find the project context.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTEXT = REPO_ROOT / "schemas" / "jsonld_context.json"


def _load_context(context_path: Optional[Path]) -> dict:
    path = Path(context_path) if context_path else DEFAULT_CONTEXT
    if not path.is_absolute() and not path.exists() and (REPO_ROOT / path).exists():
        path = REPO_ROOT / path          # relative config path, cwd elsewhere
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("@context", {})
    logger.warning("JSON-LD context %s not found; serializing without a context", path)
    return {}


def to_jsonld(graph: Graph, context_path: Optional[Path] = None) -> str:
    context = _load_context(context_path)
    return graph.serialize(format="json-ld", context=context, auto_compact=True)


def write_jsonld(graph: Graph, path: Path, context_path: Optional[Path] = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_jsonld(graph, context_path), encoding="utf-8")
    logger.info("wrote JSON-LD to %s", path)
    return path
