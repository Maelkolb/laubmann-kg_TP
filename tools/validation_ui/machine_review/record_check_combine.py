"""Record-level findings of the scan checks as correction rows for the pipeline.

Two checks read the scans against the graph's records: Gemini on every entry
(record_check.py -> record_checks.csv) and Claude subagents on the sample
dossiers (merge.py -> graph_checks.csv). This script writes their findings in
the pipeline's correction contracts with ``confidence``, ``agreement`` (number
of checks that propose the same value for the same field of the same record)
and ``sources``:

    observation_corrections_machine.csv   record fields (count, locality, date, observer, record type,
                                          sex, life stage, breeding, status); contract of
                                          laubmann_kg.normalization.observation_corrections
    value_corrections_machine.csv         another species for one record, record struck; the rows are
                                          ADDED to the file of the earlier rounds (contract of
                                          laubmann_kg.normalization.corrections)

The pipeline (``review.machine``) applies only rows with confidence >= 0.9 AND
agreement >= 2; a single check's finding stays a suggestion for the reviewer.
Where both checks agree their confidences are combined as independent
evidence: 1 - (1 - c1)(1 - c2).

A reviewer who has checked a sample of one class of findings (validation page,
graph_audit.csv) and found it reliable can release the whole class:
``--trust FIELD[:MIN_CONFIDENCE[:quote]]`` counts the reviewed sample as the
second source for every Gemini finding of that field at or above the
confidence (``quote``: only findings whose quoted words stand in the
transcription); FIELD is one of the record fields, ``species`` or ``spurious``.

    python tools/validation_ui/machine_review/record_check_combine.py --gemini <workdir>/record_check \\
        --sonnet <machine_review> --out data/review/machine [--trust record_type:0.95 locality:0.95:quote]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from laubmann_kg.normalization import vocabularies as vocab  # noqa: E402
from laubmann_kg.normalization.observation_corrections import FIELDS as OBS_FIELDS, parse_count  # noqa: E402

csv.field_size_limit(10 ** 9)
NOW = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
SET_FIELDS = ("count", "locality", "date", "observer", "record_type", "sex", "life_stage", "breeding", "status")
ENUMS = {"record_type": vocab.RECORD_TYPES, "sex": vocab.SEXES, "life_stage": vocab.LIFE_STAGES,
         "breeding": vocab.BREEDING_EVIDENCE, "status": vocab.OCCURRENCE_STATUS}


def read(path: Path):
    if not path.exists():
        return [], []
    with open(path, encoding="utf-8-sig", newline="") as h:
        r = csv.DictReader(h)
        return list(r), list(r.fieldnames or [])


def write(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fold(s: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]+", " ", (s or "").casefold()).strip()


def value_of(field: str, fix: dict):
    """(value in the contract's form, comparison key) of a checker's fix for ``field``, or None."""
    raw = fix.get(field)
    if field == "record_type" and raw is None:
        raw = next((t for v in fix.values() if isinstance(v, str) for t in vocab.RECORD_TYPES if t in v), None)   # Claude wrote it under "other"
    if raw in (None, "") or not isinstance(raw, (str, int, float)):
        return None
    raw = str(raw).strip()
    if field == "count":
        parsed = parse_count(raw)
        return (raw, json.dumps(parsed, sort_keys=True)) if parsed is not None else None
    if field == "date":
        m = re.match(r"\d{4}-\d{2}-\d{2}(?:/\d{4}-\d{2}-\d{2})?$", raw)
        return (raw, raw) if m else None
    if field in ENUMS:
        value = "-" if raw.lower() == "none" and field == "breeding" else next(
            (t for t in ENUMS[field] if t == raw.lower() or (field == "record_type" and t in raw.lower())), None)
        return (value, value) if value else None
    if field == "observer":
        names = [n.strip() for n in re.split(r";| und ", raw) if n.strip()]
        return (names[0], fold(names[0]).split(" ")[-1]) if names else None       # compared by surname
    return raw, fold(raw)                                                             # locality


def same(field: str, a, b) -> bool:
    if a[1] == b[1]:
        return True
    return field == "locality" and bool(a[1]) and bool(b[1]) and (a[1] in b[1] or b[1] in a[1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gemini", required=True, help="record_check.py output folder")
    ap.add_argument("--sonnet", default=None, help="merge.py output folder with graph_checks.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trust", nargs="*", default=[], help="classes released by a reviewed sample: FIELD[:MIN_CONFIDENCE[:quote]]")
    args = ap.parse_args()
    out = Path(args.out)
    trust = {}
    for item in args.trust:
        parts = item.split(":")
        trust[parts[0]] = (float(parts[1]) if len(parts) > 1 and parts[1] else 0.0, "quote" in parts[2:])
    checks = {"gemini-scan": read(Path(args.gemini) / "record_checks.csv")[0]}
    if args.sonnet:
        checks["claude-scan"] = read(Path(args.sonnet) / "graph_checks.csv")[0]

    # (entry_uid, written, obs_index) -> {source: row}
    recs: dict = collections.defaultdict(dict)
    for source, rows in checks.items():
        for r in rows:
            if r.get("verdict") in ("wrong", "spurious") and r.get("obs_index") not in ("", None):
                recs[(r["entry_uid"], r["written"], r["obs_index"])][source] = r

    obs_rows, val_rows = [], []
    stats = collections.Counter()
    for (uid, written, index), by_source in sorted(recs.items()):
        any_row = next(iter(by_source.values()))
        base = {"entry_uid": uid, "entry_id": any_row["entry_id"], "written": written, "obs_index": index,
                "occurrence": any_row.get("occurrence", ""), "reviewed_at": NOW}

        def conf(sources):
            miss = 1.0
            for s in sources:
                try:
                    miss *= 1.0 - max(0.0, min(1.0, float(by_source[s].get("confidence") or 0)))
                except ValueError:
                    pass
            return f"{1.0 - miss:.2f}"

        def meta(sources, field=""):
            g = by_source.get("gemini-scan")
            if field in trust and g is not None and list(sources) == ["gemini-scan"]:
                floor, need_quote = trust[field]
                if float(g.get("confidence") or 0) >= floor and (not need_quote or g.get("quote_in_text") == "y"):
                    return {"confidence": g.get("confidence"), "agreement": 2, "sources": "gemini-scan+reviewed-sample",
                            "reviewed_by": "machine:gemini-scan, class released by a reviewed sample",
                            "reason": (g.get("reason") or "")[:240]}
            return {"confidence": conf(sources), "agreement": len(sources), "sources": "+".join(sorted(sources)),
                    "reviewed_by": "machine:" + "+".join(sorted(sources)),
                    "reason": " | ".join((by_source[s].get("reason") or "")[:240] for s in sorted(sources))}

        fixes = {s: (json.loads(r["correction"]) if r.get("correction") else {}) for s, r in by_source.items()}
        fields = {s: {f for f in re.split(r"[;,]\s*", r.get("fields") or "") if f} for s, r in by_source.items()}
        # record struck
        spurious = [s for s, r in by_source.items() if r["verdict"] == "spurious"]
        if spurious:
            val_rows.append({**base, "kind": "taxon", "old_value": written, "action": "drop", "new_value": "", **meta(spurious, "spurious")})
            stats[f"drop agreement {len(spurious)}"] += 1
        # another species
        named = {s: fold(fx.get("sci") or "") for s, fx in fixes.items() if "species" in fields[s] and fx.get("sci")}
        for key in set(named.values()):
            sources = [s for s, k in named.items() if k == key]
            fx = fixes[sources[0]]
            val_rows.append({**base, "kind": "taxon", "old_value": written, "action": "replace",
                             "new_value": fx.get("species_de") or fx["sci"], "scientific_name": fx["sci"], **meta(sources, "species")})
            stats[f"species agreement {len(sources)}"] += 1
        # record fields
        for field in SET_FIELDS:
            vals = {s: value_of(field, fx) for s, fx in fixes.items() if field in fields[s] or (field == "record_type" and "other" in fields[s])}
            vals = {s: v for s, v in vals.items() if v is not None}
            done: set = set()
            for s, v in vals.items():
                if s in done:
                    continue
                sources = [t for t, w in vals.items() if t not in done and same(field, v, w)]
                done.update(sources)
                obs_rows.append({**base, "action": "set", "field": field, "new_value": v[0], **meta(sources, field)})
                stats[f"{field} agreement {len(sources)}"] += 1

    extra = ["confidence", "agreement", "sources"]
    write(out / "observation_corrections_machine.csv", OBS_FIELDS + extra, obs_rows)
    # value corrections: keep the rows of the earlier rounds, replace this script's own
    path = out / "value_corrections_machine.csv"
    old, fields = read(path)
    old = [r for r in old if "-scan" not in (r.get("sources") or "")]
    for f in ["kind", "entry_uid", "entry_id", "old_value", "occurrence", "action", "new_value", "scientific_name", "gbif_key", "is_bird",
              "reason", "note", "reviewed_by", "reviewed_at", "confidence", "agreement", "sources", "round"]:
        if f not in fields:
            fields.append(f)
    for r in val_rows:
        r["round"] = "record-check"
    write(path, fields, old + val_rows)
    applied = sum(1 for r in obs_rows + val_rows if float(r["confidence"]) >= 0.9 and int(r["agreement"]) >= 2)
    print(json.dumps({"records with findings": len(recs), "field corrections": len(obs_rows), "species/drop corrections": len(val_rows),
                      "kept value corrections of earlier rounds": len(old), "rows over the thresholds (applied by the pipeline)": applied,
                      "by kind": dict(sorted(stats.items()))}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
