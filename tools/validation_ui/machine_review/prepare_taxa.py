"""Machine review of the species: batches and contact sheets.

Two inputs for the subagents:

* ``taxa/batches/batch_NNN.json`` - one record per taxon entity of the graph
  (linked to GBIF or not): the GBIF record with its German names, every written
  name form with its evidence class, counts and diary passages, the earlier
  model readings, and the incoming merge candidates. A text-only agent decides
  per name form which taxon it denotes and whether the GBIF link of the entity
  is right.
* ``sheets/sheet_NNN.png|json`` - contact sheets of the doubtful name forms
  (classes B, C, L: variants, unattested and unlinked names), one or two line
  images per form cut from the scans, so a second agent reads the word at the
  image before deciding the species.

    python tools/validation_ui/machine_review/prepare_taxa.py payload.b64 --out <workdir> \
        --pages "<HistOrniGraph_output>" [--second-reading second_reading.json] [--third-reading third_reading.json]
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PageImages, contact_sheet, context, crop_line, instructions, load_payload,  # noqa: E402
                    mention_keys, read_json, write_json, written_of)

BATCH_INSTRUCTIONS = """# Species check (text) — instructions

You are checking the species entities of a knowledge graph built from the ornithological field diaries of Alfred Laubmann (Bavaria, 1917–1965, handwritten German; the transcription is machine-made and contains misreadings). Work carefully but do not over-deliberate: read the batch file, write the answer file, reply. No web lookups are needed; use your knowledge of German bird names, including historical and regional ones (Weidenlaubvogel = Zilpzalp, Dompfaff = Gimpel, Schwarzdrossel = Amsel, Wildente = Stockente, Glanzkopfmeise = Sumpfmeise, Rohrsperling = Rohrammer, Gartenrotschwänzchen = Gartenrotschwanz, Trauerfliegenschnäpper = Trauerschnäpper, Wasserstar = Wasseramsel, Hausschwalbe = Mehlschwalbe, Steinrötel = Steinrötel, Sturmmöwe etc.; taxonomy as in the GBIF backbone).

Files (N = the batch number you were given, three digits):
- Batch: `{root}/taxa/batches/batch_N.json` — an array of entity records. Each has `entity` (id), `label`, `n_mentions`, `gbif` (the taxon the graph links to: key, scientific name, rank, family, the German names GBIF/Wikidata list for it; `null` when the entity is not linked), `llm_proposal` (a scientific name an earlier model proposed for an unlinked entity, unverified), `forms` (every written name assigned to this entity: `name`, `n` mentions, `class` A = attested German name of the linked taxon, B = spelling/compound variant of one, C = not attested for this taxon, L = entity not linked; `nearest_attested`; `contexts` = diary passages with the name; `model_readings` = what two earlier models read at the scan for some of its mentions) and `incoming_candidates` (names currently assigned to OTHER entities that a heuristic thinks might belong here).
- Answer: `{root}/taxa/answers/batch_N.json`

Decide for every entity:
1. `link`: is the GBIF taxon right for the names below it? `ok` / `wrong` (give `link_sci`, the scientific name it should be) / `none` (the names denote no bird taxon at all: another animal, a misreading of a non-bird word, an unspecific word like "Vogel") / `unsure`. For an unlinked entity (`gbif` null): `ok` is impossible — give `link_sci` if the names clearly denote a taxon (species, or genus/family if only that is stated, e.g. "Möwe" → Laridae, "Ente" → Anatidae), else `none` or `unsure`.
2. `forms`: for every written name, which taxon it denotes: `same` = the entity's taxon (after your correction in link_sci, if any); `other` = another taxon (give `sci` and `species_de`); `none` = not a bird / not a taxon (misreading of another word, place, person; say so); `unsure`. Rules: merge = same biological species, not same word; a plumage or age word keeps the species (Schwarzamsel = Amsel), a subspecies/form word denotes that taxon (Trauerbachstelze = Motacilla alba yarrellii); misreadings are never synonyms — if a name is clearly a misread bird name, decide `other`/`same` for the species it stands for and say "Lesefehler für X" in the reason; genus/family names go to the genus/family, not to a species. Use the passages: the context (habitat, behaviour, count, season, companions in the list) often settles a doubtful name. Frequency never decides identity.
3. `incoming`: for every incoming candidate, does the name belong to this entity's taxon (`belongs` true/false/null)?

Confidence is your own certainty (1.0 = beyond doubt). Be conservative with `same` on class C names: a name that is not a known German name of the species needs support from the passages or from a known historical/regional name.

Write the answers as JSON, an array with one object per entity in input order:
`{"entity": <id>, "link": "ok|wrong|none|unsure", "link_sci": "scientific name or null", "link_species_de": "German name or null", "link_rank": "species|subspecies|genus|family|order|null", "link_confidence": 0.0-1.0, "link_reason": "one short sentence, German", "forms": [{"form": <id>, "decision": "same|other|none|unsure", "sci": "scientific name or null", "species_de": "German name or null", "rank": "species|subspecies|genus|family|order|null", "confidence": 0.0-1.0, "reason": "one short sentence, German"}], "incoming": [{"form": <id>, "belongs": true|false|null, "reason": "short, German"}]}`

Then reply with only the answer file path and one line per entity `label → link (n forms same / other / none / unsure)`.
"""

SHEET_INSTRUCTIONS = """# Species check (scan) — instructions

You are reading handwritten German ornithological diary lines (Alfred Laubmann, Bavaria, 1917–1965; Latin cursive with some Kurrent elements, bird names often underlined) to check doubtful species names of a knowledge graph. Work carefully but do not over-deliberate. Read each sheet image ONCE with the Read tool, then its manifest, then write the answer file; no other tools are needed.

Files (N = a sheet number you were given, three digits; you may have been given two sheets — answer both, one file each):
- Image: `{root}/sheets/sheet_N.png` — up to 8 numbered crops; the orange rectangle marks the line (sometimes two lines) the word stands on. Crops of the same written name follow each other and say so in the manifest.
- Manifest: `{root}/sheets/sheet_N.json` — per number: `written` (the machine transcription's word at that position), `context` (transcribed text around it), `current` (the taxon the graph assigns: label, scientific name, GBIF key; empty when unlinked), `class` (B = spelling variant of a known name of that taxon, C = name not attested for that taxon, L = not linked), and earlier model readings of the same crop where they exist (`gemini`, `opus`: reading and species; they can be wrong).
- Answer: `{root}/sheets/answers/sheet_N.json`

For each numbered crop, FIRST read the marked line yourself without looking at the transcription: find the word that corresponds to `written` (use `context` only to locate it) and transcribe exactly what is written, in the diary's spelling and inflection. THEN decide what it denotes: a bird (today's German species name and the scientific name; genus or family if only that is stated), another animal, a place, a person, or something else. Historical names are common: Weidenlaubvogel = Zilpzalp (Phylloscopus collybita), Fitislaubvogel = Fitis, Waldlaubvogel = Waldlaubsänger, Wildente = Stockente, Dompfaff = Gimpel, Schwarzdrossel = Amsel, Glanzkopfmeise = Sumpfmeise, Hausschwalbe = Mehlschwalbe, Rohrsperling = Rohrammer. Only after that compare with the transcription and the earlier readings. If the marked line does not contain the word (the crop shows another line — two-column lists, rotated pages) or is illegible, set `legible` false and confidence 0 and say what you see.

Write the answers as JSON (array of one object per number, in order) with exactly these fields:
`{"n": 1, "reading": "the word(s) as written", "legible": true, "kind": "bird|other_animal|place|person|other", "species_de": "German species name or null", "sci": "scientific name or null", "rank": "species|subspecies|genus|family|null", "confidence": 0.0-1.0, "agrees_with_transcription": true|false, "agrees_with_current": true|false, "note": "one short sentence, German"}`

`agrees_with_current` = your species is the taxon in `current` (false when unlinked). Then reply with only the answer file path(s) and one line per crop `n: reading → species`.
"""


def readings_summary(form_mentions, keys, second, third) -> str:
    parts = []
    for name, src in (("Gemini 3.5", second), ("Opus 5.5", third)):
        if not src:
            continue
        cnt = collections.Counter()
        for mi in form_mentions:
            a = src.get(keys[mi])
            if a and a.get("reading"):
                what = a.get("species_de") or a.get("kind") or "?"
                cnt[(a["reading"], what)] += 1
        if cnt:
            parts.append(name + ": " + "; ".join(f"„{r}“ → {w} ×{n}" for (r, w), n in cnt.most_common(3)))
    return " · ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--second-reading", default=None)
    ap.add_argument("--third-reading", default=None)
    ap.add_argument("--per-batch", type=int, default=15)
    ap.add_argument("--per-sheet", type=int, default=8)
    ap.add_argument("--sheet-width", type=int, default=1200)
    ap.add_argument("--no-sheets", action="store_true")
    args = ap.parse_args()

    P = load_payload(args.payload)
    root = Path(args.out).resolve()
    T, E = P["taxon"], P["E"]
    keys = mention_keys(P, "taxon")
    second = read_json(args.second_reading, {}) if args.second_reading else {}
    third = read_json(args.third_reading, {}) if args.third_reading else {}
    forms_of = collections.defaultdict(list)
    for fi, f in enumerate(T["forms"]):
        forms_of[f[2]].append(fi)
    men_of = collections.defaultdict(list)
    for mi, m in enumerate(T["men"]):
        men_of[m[0]].append(mi)
    ent_n = {ei: sum(T["forms"][fi][1] for fi in fis) for ei, fis in forms_of.items()}
    ec = P["cand"]["taxon"]["ec"]

    def contexts(fi, k, width=150):
        out, seen = [], set()
        ms = sorted(men_of[fi], key=lambda mi: (T["men"][mi][2] < 0, mi))
        for mi in ms:
            m = T["men"][mi]
            e = E[m[1]]
            if e[0] in seen:
                continue
            seen.add(e[0])
            out.append({"entry": e[0], "date": e[2], "text": context(e[7], m[2], m[3], width)})
            if len(out) >= k:
                break
        return out

    # ------------------------------------------------------------ text batches
    order = sorted(forms_of, key=lambda ei: -ent_n[ei])
    batches = []
    for ei in order:
        ent = T["ent"][ei]
        rec = {"entity": ei, "label": ent[0], "n_mentions": ent_n[ei],
               "gbif": {"key": ent[2], "sci": ent[1], "rank": ent[3], "match_type": ent[4], "family": ent[6], "order": ent[7],
                        "german_names": ent[9]} if ent[2] else None,
               "llm_proposal": next((T["forms"][fi][5] for fi in forms_of[ei] if T["forms"][fi][5]), "") or None,
               "forms": [], "incoming_candidates": []}
        for fi in sorted(forms_of[ei], key=lambda fi: -T["forms"][fi][1]):
            f = T["forms"][fi]
            rec["forms"].append({"form": fi, "name": f[0], "n": f[1], "class": f[3], "nearest_attested": f[4] or None,
                                 "contexts": contexts(fi, 2 if f[3] == "A" else 3),
                                 "model_readings": readings_summary(men_of[fi], keys, second, third) or None})
        for c in ec.get(str(ei), []):
            fi = c[0]
            f = T["forms"][fi]
            home = T["ent"][f[2]]
            rec["incoming_candidates"].append({"form": fi, "name": f[0], "n": f[1], "why": c[2],
                                               "now_at": home[0] + (f" ({home[1]})" if home[1] else " (nicht verknüpft)"),
                                               "contexts": contexts(fi, 1)})
        batches.append(rec)
    bdir = root / "taxa" / "batches"
    bdir.mkdir(parents=True, exist_ok=True)
    (root / "taxa" / "answers").mkdir(parents=True, exist_ok=True)
    for i in range(0, len(batches), args.per_batch):
        write_json(bdir / f"batch_{i // args.per_batch + 1:03d}.json", batches[i:i + args.per_batch])
    instructions(root / "taxa" / "INSTRUCTIONS.md", BATCH_INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"taxa: {len(batches)} entities in {(len(batches) + args.per_batch - 1) // args.per_batch} batches")
    if args.no_sheets:
        return

    # ------------------------------------------------------------ contact sheets of doubtful forms
    pages = PageImages(Path(args.pages))
    items = []
    for fi, f in enumerate(T["forms"]):
        if f[3] not in ("B", "C", "L"):
            continue
        cands = [mi for mi in men_of[fi] if isinstance(T["men"][mi][4], list) and len(T["men"][mi][4]) >= 5]
        cands.sort(key=lambda mi: (T["men"][mi][4][5] if len(T["men"][mi][4]) > 5 else 1, mi))
        want = 2 if f[1] >= 3 else 1
        chosen, seen = [], set()
        for mi in cands:
            ei = T["men"][mi][1]
            if ei in seen:
                continue
            seen.add(ei)
            chosen.append(mi)
            if len(chosen) >= want:
                break
        for mi in chosen:
            items.append((fi, mi, len(chosen)))
    print(f"sheets: {len(items)} crops for {len({fi for fi, _, _ in items})} doubtful forms")
    sdir = root / "sheets"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "answers").mkdir(exist_ok=True)
    k = 0
    for s in range(0, len(items), args.per_sheet):
        chunk = items[s:s + args.per_sheet]
        crops, manifest = [], []
        for n, (fi, mi, n_of_form) in enumerate(chunk, 1):
            m = T["men"][mi]
            pidx, x0, y0, x1, y1 = m[4][:5]
            pg = P["PG"][pidx]
            png = pages.path(pg[0])
            if not png or not pg[5]:
                continue
            try:
                c = crop_line(png, pg[5], pg[6], (x0, y0, x1, y1), args.sheet_width - 90)
            except Exception as exc:  # noqa: BLE001
                print("crop failed", pg[0], exc)
                continue
            crops.append((n, c))
            f = T["forms"][fi]
            ent = T["ent"][f[2]]
            e = E[m[1]]
            g, o = second.get(keys[mi]) or {}, third.get(keys[mi]) or {}
            manifest.append({"n": n, "form": fi, "mention": mi, "key": keys[mi], "entry_id": e[0], "date": e[2],
                             "written": written_of(P, "taxon", m), "form_name": f[0], "form_mentions": f[1], "crops_of_this_form": n_of_form,
                             "context": context(e[7], m[2], m[3], 110), "class": f[3],
                             "current": {"label": ent[0], "sci": ent[1], "gbif_key": ent[2]} if ent[2] else {},
                             "nearest_attested": f[4] or None, "approximate_line": bool(len(m[4]) > 5 and m[4][5]),
                             "gemini": {"reading": g.get("reading"), "species_de": g.get("species_de"), "sci": g.get("sci"), "confidence": g.get("confidence")} if g else None,
                             "opus": {"reading": o.get("reading"), "species_de": o.get("species_de"), "sci": o.get("sci"), "confidence": o.get("confidence")} if o else None})
        if not crops:
            continue
        k += 1
        contact_sheet(crops, args.sheet_width).save(sdir / f"sheet_{k:03d}.png", "PNG", optimize=True)
        write_json(sdir / f"sheet_{k:03d}.json", manifest)
    instructions(sdir / "INSTRUCTIONS.md", SHEET_INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"{k} sheets in {sdir}")


if __name__ == "__main__":
    main()
