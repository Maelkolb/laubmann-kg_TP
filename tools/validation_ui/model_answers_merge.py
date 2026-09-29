"""Join the model answers of the third reading (sheets) and the person matching
(batches) into two JSON files keyed for build_payload.py.

    python tools/validation_ui/model_answers_merge.py --sheets third/sheets --sheet-answers third/answers \
        --batches persons/batches --batch-answers persons/answers --out-third third_reading.json --out-persons person_matches.json

third_reading.json: mention key -> {reading, legible, kind, species_de, sci, confidence, note, model}
person_matches.json: entity label -> {decision, confidence, reason, model}
Answers that do not parse are reported and skipped; a sheet or batch without an
answer file is listed as missing (re-run those).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load_json(path: Path):
    txt = path.read_text(encoding="utf-8").strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
    return json.loads(txt)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--sheet-answers", required=True)
    ap.add_argument("--batches", required=True)
    ap.add_argument("--batch-answers", required=True)
    ap.add_argument("--out-third", default="third_reading.json")
    ap.add_argument("--out-persons", default="person_matches.json")
    ap.add_argument("--model", default="claude-opus-5-5")
    args = ap.parse_args()

    third, missing, bad = {}, [], []
    for man in sorted(Path(args.sheets).glob("sheet_*.json")):
        ans = Path(args.sheet_answers) / man.name
        if not ans.exists():
            missing.append(man.stem)
            continue
        try:
            rows = load_json(ans)
            by_n = {int(r["n"]): r for r in rows}
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{man.stem}: {exc}")
            continue
        for item in load_json(man):
            r = by_n.get(int(item["n"]))
            if not r:
                continue
            third[item["key"]] = {"reading": r.get("reading"), "legible": r.get("legible", True), "kind": r.get("kind"),
                                  "species_de": r.get("species_de"), "sci": r.get("sci"), "confidence": r.get("confidence"),
                                  "agrees_t": r.get("agrees_with_transcription"), "agrees_g": r.get("agrees_with_gemini"),
                                  "note": r.get("note"), "model": args.model}
    Path(args.out_third).write_text(json.dumps(third, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"third reading: {len(third)} mentions; missing sheets: {missing or 'none'}; unparseable: {bad or 'none'}")

    persons, pmissing, pbad = {}, [], []
    for bat in sorted(Path(args.batches).glob("batch_*.json")):
        ans = Path(args.batch_answers) / bat.name
        if not ans.exists():
            pmissing.append(bat.stem)
            continue
        try:
            rows = load_json(ans)
        except Exception as exc:  # noqa: BLE001
            pbad.append(f"{bat.stem}: {exc}")
            continue
        labels = {r["entity"]: r["label"] for r in load_json(bat)}
        for r in rows:
            lab = labels.get(r.get("entity"), r.get("label"))
            if lab:
                persons[lab] = {"decision": r.get("decision"), "confidence": r.get("confidence"), "reason": r.get("reason"), "model": args.model}
    Path(args.out_persons).write_text(json.dumps(persons, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"person matches: {len(persons)}; missing batches: {pmissing or 'none'}; unparseable: {pbad or 'none'}")


if __name__ == "__main__":
    main()
