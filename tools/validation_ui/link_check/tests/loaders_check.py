"""Feed an exported review/identities.csv through the pipeline's own loader (run with the repo's Python).

    python tests/loaders_check.py <folder with identities.csv>

Prints one JSON line: every decision the loader kept (forms and links per section, keyed as the
pipeline keys them) and the loader's warnings."""
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from laubmann_kg.review.identities import Identities, apply_mappings   # noqa: E402

warnings = []


class Catch(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            warnings.append(record.getMessage())


logging.getLogger().addHandler(Catch())
logging.getLogger().setLevel(logging.INFO)
path = Path(sys.argv[1]) / "identities.csv"
ids = Identities.load(path)
rows = sum(1 for _ in open(path, encoding="utf-8", newline="")) - 1


def dump(table):
    return {sec: {key: {"name": i.name, "decision": i.decision, "target": i.target, "authority": dict(i.authority), "gbif_key": i.gbif_key, "geonames_id": i.geonames_id,
                        "scientific_name": i.scientific_name, "rank": i.rank, "lat": i.lat, "lon": i.lon, "uncertainty_m": i.uncertainty_m, "eunis_match": i.eunis_match,
                        "origin": i.origin, "note": i.note} for key, i in d.items()} for sec, d in table.items()}


# the resolution stage applies same/own with apply_mappings: a reviewed "same" must move the form to its target
mapped = {}
for sec in ("persons", "places", "habitats"):
    names = [i.name for i in ids.forms[sec].values()] + [i.target for i in ids.forms[sec].values() if i.target]
    mapping = {i.name: "RULE-TARGET" for i in ids.forms[sec].values() if i.decision == "own"}
    n = apply_mappings(mapping, list(dict.fromkeys(names)), sec, ids)
    mapped[sec] = {"applied": n, "mapping": mapping}
print(json.dumps({"rows": rows, "forms": dump(ids.forms), "links": dump(ids.links), "mapped": mapped, "warnings": warnings}, ensure_ascii=False))
