"""Machine review of the habitats: batches for the EUNIS links.

Every habitat concept of the graph (a habitat phrase of the diary, shared by
all observations that use it) with its written forms, a few diary passages and
its current EUNIS class (exact / close / broad match). The agent decides
whether the class is right, names a better one from the EUNIS list (levels
1–3 of the terrestrial, freshwater and coastal groups, written next to the
batches), or says that the phrase is no habitat (a place name, a behaviour,
too vague). Decisions are keyed by the habitat label, like the reviewer UI's.

    python tools/validation_ui/machine_review/prepare_habitats.py payload.b64 --out <workdir> \\
        [--eunis data/eunis_habitats.csv] [--min-mentions 1] [--per-batch 40] [--known machine_review.json …]
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import context, instructions, load_payload, read_json, write_json  # noqa: E402

INSTRUCTIONS = """# Habitats → EUNIS — instructions

The knowledge graph of Alfred Laubmann's ornithological field diaries (Bavaria and his travels, 1917–1965, German) records the habitat phrases the diarist wrote next to his bird observations ("Schilf", "Auwald", "an der Isar", "Kiesbank") as shared habitat concepts, each linked to a class of the EUNIS habitat classification (European Environment Agency). You check these links. Work carefully but do not over-deliberate: read the batch and the EUNIS list, write the answer file; no other tools are needed. Write nothing else anywhere.

Files (N = the batch number you were given, three digits):
- Batch: `{root}/habitats/batches/batch_N.json` — an array of habitats: `entity` (id), `label` (the concept's German label), `forms` (written forms with counts), `n_mentions`, `current` (EUNIS `code`, `label`, `match` = exact | close | broad, or null when not linked), `passages` (diary text around a use).
- EUNIS list: `{root}/habitats/eunis_levels_1-3.txt` (code — English label; level 1–3 of groups B coastal, C inland waters, D mires/bogs/fens, E grasslands, F heath/scrub, G woodland, H inland sparsely vegetated, I arable/gardens/parks, J buildings/artificial, X complexes). Use a level-4 code only when you are sure of it.
- Answer: `{root}/habitats/answers/batch_N.json`

For each habitat:
- `verdict`: `ok` (the current class fits the phrase), `other` (a better class: give `code` and `match`), `none` (not a habitat: a place name, a behaviour, a direction, weather, or too vague to classify, e.g. "Gelände", "dort"), `unsure`.
- `match`: `exact` (the class is the same kind of place: "Fichtenwald" → G3.1 Fir and spruce woodland), `close` (the class fits but the phrase is narrower/wider in a way that matters), `broad` (the class is a broader parent: "Waldrand" → G, "Ufer" → C3).
- Prefer the most specific class you can justify from the phrase alone; the passages only disambiguate (e.g. "Moos" = bog in Bavaria, "Au" = floodplain woodland).

Answer JSON: `[{"entity": <id>, "label": "...", "verdict": "ok|other|none|unsure", "code": "EUNIS code or null", "match": "exact|close|broad|null", "confidence": 0.0-1.0, "reason": "one short sentence, German"}]`

Then reply with only the answer file path and one line `habitats: n ok / other / none / unsure`.
"""

GROUPS = ("B", "C", "D", "E", "F", "G", "H", "I", "J", "X")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("--out", required=True)
    ap.add_argument("--eunis", default=str(Path(__file__).resolve().parents[3] / "data" / "eunis_habitats.csv"))
    ap.add_argument("--min-mentions", type=int, default=1)
    ap.add_argument("--per-batch", type=int, default=40)
    ap.add_argument("--known", nargs="*", default=None, help="machine_review.json of earlier rounds (habitat labels judged there are skipped)")
    args = ap.parse_args()
    P = load_payload(args.payload)
    root = Path(args.out).resolve()
    H, E = P["habitat"], P["E"]
    known = set()
    for path in args.known or []:
        for v in ((read_json(path, {}) or {}).get("habitat") or {}).get("ent", {}).values():
            if v.get("label"):
                known.add(v["label"].lower())

    eunis = {}
    with open(args.eunis, encoding="utf-8", newline="") as h:
        for r in csv.DictReader(h):
            eunis[r["code"]] = r
    hdir = root / "habitats"
    (hdir / "batches").mkdir(parents=True, exist_ok=True)
    (hdir / "answers").mkdir(parents=True, exist_ok=True)
    lines = [f"{c} — {r['label']}" for c, r in sorted(eunis.items())
             if c[:1] in GROUPS and r["level"].isdigit() and int(r["level"]) <= 3]
    (hdir / "eunis_levels_1-3.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    forms_of = collections.defaultdict(list)
    for fi, f in enumerate(H["forms"]):
        forms_of[f[2]].append(fi)
    men_of = collections.defaultdict(list)
    for mi, m in enumerate(H["men"]):
        men_of[m[0]].append(mi)
    n_of = {ei: sum(H["forms"][fi][1] for fi in fis) for ei, fis in forms_of.items()}
    selected = [ei for ei in sorted(forms_of, key=lambda ei: -n_of[ei])
                if n_of[ei] >= args.min_mentions and H["ent"][ei][0].lower() not in known]
    recs = []
    for ei in selected:
        ent = H["ent"][ei]
        code = ent[1]
        passages, seen = [], set()
        for fi in forms_of[ei]:
            for mi in men_of[fi]:
                m = H["men"][mi]
                e = E[m[1]]
                if e[0] in seen:
                    continue
                seen.add(e[0])
                text = e[7] or ""
                s = text.lower().find(H["forms"][fi][0].lower())
                passages.append(context(text, s, s + len(H["forms"][fi][0]), 110) if s >= 0 else "")
                if len(passages) >= 3:
                    break
            if len(passages) >= 3:
                break
        recs.append({"entity": ei, "label": ent[0], "n_mentions": n_of[ei],
                     "forms": [[H["forms"][fi][0], H["forms"][fi][1]] for fi in forms_of[ei]],
                     "current": {"code": code, "label": (eunis.get(code) or {}).get("label", ""), "match": ent[2]} if code else None,
                     "passages": [p for p in passages if p]})
    for i in range(0, len(recs), args.per_batch):
        write_json(hdir / "batches" / f"batch_{i // args.per_batch + 1:03d}.json", recs[i:i + args.per_batch])
    instructions(hdir / "INSTRUCTIONS.md", INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"habitats: {len(recs)} of {len(H['ent'])} in {(len(recs) + args.per_batch - 1) // args.per_batch} batches "
          f"(skipped as known: {sum(1 for e in H['ent'] if e[0].lower() in known)})")


if __name__ == "__main__":
    main()
