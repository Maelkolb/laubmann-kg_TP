"""Feed exported review files through the pipeline's loaders (run with the repo's Python).

    python tests/loaders_check.py <folder with identities.csv, value_corrections.csv, ...>

Prints one JSON line: rows read / rows kept per file and the warnings of the loaders."""
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from laubmann_kg.review.identities import Identities              # noqa: E402
from laubmann_kg.normalization.corrections import load_corrections  # noqa: E402
from laubmann_kg.extraction.reading import load_transcript_decisions  # noqa: E402
from laubmann_kg.qa import load_qa_decisions                        # noqa: E402

warnings = []


class Catch(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            warnings.append(record.getMessage())


logging.getLogger().addHandler(Catch())
logging.getLogger().setLevel(logging.INFO)
d = Path(sys.argv[1])
ids = Identities.load(d / "identities.csv")
corr = load_corrections(d / "value_corrections.csv")
td = load_transcript_decisions(d / "transcript_decisions.csv")
qd = load_qa_decisions(d / "qa_decisions.csv")
tc_rows = sum(1 for _ in open(d / "text_corrections.csv", encoding="utf-8")) - 1 if (d / "text_corrections.csv").exists() else 0
print(json.dumps({
    "forms": {s: len(v) for s, v in ids.forms.items()}, "links": {s: len(v) for s, v in ids.links.items()},
    "form_decisions": sorted({i.decision for v in ids.forms.values() for i in v.values()}),
    "link_authorities": sorted({p for v in ids.links.values() for i in v.values() for p, _ in i.authority}),
    "corrections": len(corr), "corrections_actions": sorted({c.action for c in corr}),
    "transcript": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in td.items()}, "qa": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in qd.items()},
    "text_corrections": tc_rows, "warnings": warnings}, ensure_ascii=False))
