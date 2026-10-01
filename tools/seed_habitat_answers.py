"""Seed the per-label answer store of the habitat linking from an export's review table.

``linking/habitats.py`` keeps one EUNIS answer per habitat label in
``<linking.habitats.llm.cache_dir>/label_answers.json``, so a re-export links
every known label as before. Exports made before that store existed re-asked
the model whenever the label set changed; this tool writes the answers of one
such export (the one whose links were reviewed) into the store.

    python tools/seed_habitat_answers.py <export>/review/habitat_link_review.csv data/cache/linking/llm_habitats/label_answers.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    store = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {}
    added = 0
    with src.open(newline="", encoding="utf-8") as h:
        for r in csv.DictReader(h):
            label = (r.get("habitat_label") or "").strip()
            if not label or label in store or r.get("status") not in ("linked", "review", "no_match", "rejected"):
                continue                      # reviewed rows come from the decision files, not from the model
            try:
                conf = float(r.get("confidence") or 0)
            except ValueError:
                conf = 0.0
            store[label] = {"code": (r.get("eunis_code") or "").strip() or None, "match": (r.get("match") or "").strip() or None,
                            "confidence": conf, "note": r.get("note") or ""}
            added += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    print(f"{added} labels added, {len(store)} in {dst}")


if __name__ == "__main__":
    main()
