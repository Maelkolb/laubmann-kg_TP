from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def sample_config() -> dict:
    return {
        "corpus": {"entries": str(FIXTURES / "sample_entries.csv")},
        "sample": {"volume": 2},
        "extraction": {"backend": "offline"},
        "taxa": {"links_long_path": None},
        "paths": {
            "ontology": str(REPO_ROOT / "ontologies" / "laubmann.ttl"),
            "shapes": str(REPO_ROOT / "ontologies" / "shacl_shapes.ttl"),
            "jsonld_context": str(REPO_ROOT / "schemas" / "jsonld_context.json"),
        },
        "validate": True,
    }
