#!/usr/bin/env python3
"""Data of the page "Laubmann-Verknüpfungen" (link check): the validation of the
DATA-LINKING stage only. One record per entity of the graph (taxon, person, place,
habitat concept) with

* the authority link the graph holds now and who set it (pipeline rule, machine
  review, earlier reviewed table),
* the link the pipeline alone had (before the machine review) where the machine
  changed it,
* the machine verdict (applied or only a suggestion) with the votes of its sources,
* other candidate records, the written names with their provenance, up to six
  diary passages with their line on the scan, open merge candidates.

    python tools/validation_ui/link_check/build_data.py            # all defaults
    python tools/validation_ui/link_check/build_data.py --payload payload_checked.b64 \
        --payload-pipeline payload_pipeline.b64 --identities data/review/machine/identities_machine.csv \
        --rounds <r1>/machine_review <r3>/machine_review ... --arbeit <arbeit r1> <arbeit r3> ... \
        --export-review <export>/review --reviewed-merges data/review --out data/exports/link_check/data

--payload            payload (tools/validation_ui/build_payload.py) of the graph under review
--payload-pipeline   payload of the same run before the machine decisions of the last rounds were applied
--payload-r1         payload (or assembled Laubmann_Abgleich.html) of the graph the FIRST machine round judged;
                     used as "before" where --payload-pipeline already carries a machine decision
--identities         the combined machine rows the pipeline reads (applied iff confidence >= 0.9 and agreement >= 2)
--rounds             machine_review folders in the order of combine_rounds.py (column "round" = position)
--arbeit             agent work folders, parallel to --rounds ("-" = none): batches, answers, answers_gemini
--export-review      <export>/review: *_merges.csv (rule-based merges and open candidates), *_link_review.csv
--reviewed-merges    folder with the earlier reviewed *_merges.csv (decision y/n)
--review-layer       review layer of the graph validation page (estimated error probability of every record) -> reliability filter
--triples            pickled triples of the graph under review: ties person / place / habitat mentions to records

Every record is keyed by the casefolded entity label; nothing the page stores refers to an index.
Output: <out>.json (readable) and <out>.b64 (gzip+base64, embedded by assemble.py).
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import gzip
import hashlib
import json
import math
import pickle
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
IN = REPO / "data" / "cache" / "graph_check" / "in"          # payloads of build_payload.py (graph under review, pipeline-only graph)
D1 = Path(r"G:\My Drive\Laubmann_KG_Maschinenpruefung_2026-09-30")
D3 = Path(r"G:\My Drive\Laubmann_KG_Maschinenpruefung_2026-10-01")

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--payload", default=str(IN / "payload_regions.b64"))
ap.add_argument("--payload-pipeline", default=str(IN / "payload_pipeline.b64"))
ap.add_argument("--payload-r1", default=str(D1 / "Laubmann_Abgleich.html"))
ap.add_argument("--identities", default=str(REPO / "data" / "review" / "machine" / "identities_machine.csv"))
ap.add_argument("--rounds", nargs="*", default=[str(D1 / "machine_review"), str(D3 / "machine_review"),
                                                str(D3 / "machine_review_orte_einzelnennungen"), str(D3 / "machine_review_personen_nachsuche")])
ap.add_argument("--round-labels", nargs="*", default=["R1", "R3", "R3 Orte (Einzelnennungen)", "R3 Personen (Nachsuche)"])
ap.add_argument("--arbeit", nargs="*", default=[str(D1 / "arbeit"), str(D3 / "arbeit" / "r3"), str(D3 / "arbeit" / "r3_orte_einzelnennungen"),
                                                str(D3 / "arbeit" / "r3_personen_nachsuche")])
ap.add_argument("--export-review", default=str(REPO / "data" / "exports" / "kg_exports_2026-10-06_regions" / "review"))
ap.add_argument("--reviewed-merges", default=str(REPO / "data" / "review"))
ap.add_argument("--drive", nargs="*", default=[str(HERE.parent / "drive_pages.json"), str(REPO / "configs" / "drive_scan_files.json")])
ap.add_argument("--out", default=str(REPO / "data" / "exports" / "link_check" / "data"))
ap.add_argument("--built", default=None)
ap.add_argument("--review-layer", default=str(REPO / "data" / "cache" / "graph_check" / "review_regions.json"),
                help="review layer of graph_check/build_review.py --quality: q.p (estimated probability that a field is wrong) of every record")
ap.add_argument("--triples", default=str(IN / "triples_regions.pkl"), help="pickled triples of the graph under review (load.py): which record a person, place or habitat mention belongs to")
ap.add_argument("--max-ev", type=int, default=6, help="diary passages per entity")
ap.add_argument("--min-confidence", type=float, default=0.9)
ap.add_argument("--min-agreement", type=int, default=2)
args = ap.parse_args()

TYPES = ("taxon", "person", "place", "habitat")
SECTION = {"taxon": "taxa", "person": "persons", "place": "places", "habitat": "habitats"}
TAG = re.compile(r"<[^>]+>")
lc = str.casefold


def log(*a):
    print(*a, file=sys.stderr)


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def read_csv(path):
    path = Path(path)
    if not path.exists():
        log("missing:", path)
        return []
    with open(path, encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))


def read_json(path, default=None):
    """Tolerant JSON reader (agents sometimes wrote cp1252 or trailing text)."""
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_bytes()
    try:
        txt = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        txt = raw.decode("cp1252").strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        try:
            return json.JSONDecoder().raw_decode(txt)[0]
        except json.JSONDecodeError:
            log("unreadable JSON:", p)
            return default


def load_payload(path):
    p = Path(path)
    raw = p.read_bytes()
    if p.suffix.lower() == ".json":
        return json.loads(raw)
    if p.suffix.lower() in (".html", ".htm"):
        m = re.search(rb'<script id="data" type="application/octet-stream">(.*?)</script>', raw, re.S)
        if not m:
            raise SystemExit(f"{p}: no data block")
        raw = m.group(1)
    return json.loads(gzip.decompress(base64.b64decode(raw.strip())))


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def sources(s):
    out = s if isinstance(s, list) else [x for x in re.split(r"[+,\s]+", s or "") if x]
    seen = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


# ---------------------------------------------------------------- graphs
class Graph:
    """Indexes of one payload (build_payload.py)."""

    def __init__(self, P, tag):
        self.P, self.tag = P, tag
        self.E, self.PG = P["E"], P["PG"]
        self.export = P.get("export") or ""
        self.sec = {t: P[t] for t in TYPES if t in P}
        self.forms_of_ent, self.men_of_form, self.fis_by_name, self.ent_by_label, self.n_of_ent = {}, {}, {}, {}, {}
        for t, s in self.sec.items():
            foe = collections.defaultdict(list)
            byn = collections.defaultdict(list)
            for fi, f in enumerate(s["forms"]):
                foe[f[2]].append(fi)
                byn[lc(f[0])].append(fi)
            mof = collections.defaultdict(list)
            for mi, m in enumerate(s["men"]):
                mof[m[0]].append(mi)
            self.forms_of_ent[t], self.men_of_form[t], self.fis_by_name[t] = foe, mof, byn
            self.n_of_ent[t] = {e: sum(s["forms"][fi][1] for fi in fis) for e, fis in foe.items()}
            lab = {}
            for i, e in enumerate(s["ent"]):
                lab.setdefault(lc(e[0]), i)
            self.ent_by_label[t] = lab

    def ent_of_name(self, t, name):
        """Entity index a written name belongs to (the label itself, else the form with most mentions)."""
        k = lc(name)
        s = self.sec[t]
        fis = self.fis_by_name[t].get(k)
        if fis:
            return s["forms"][max(fis, key=lambda fi: s["forms"][fi][1])][2]
        return self.ent_by_label[t].get(k)

    def form_of_name(self, t, name):
        s = self.sec[t]
        fis = self.fis_by_name[t].get(lc(name))
        return s["forms"][max(fis, key=lambda fi: s["forms"][fi][1])] if fis else None


M = Graph(load_payload(args.payload), "M")
B = Graph(load_payload(args.payload_pipeline), "B") if args.payload_pipeline and Path(args.payload_pipeline).exists() else None
A = Graph(load_payload(args.payload_r1), "A") if args.payload_r1 and Path(args.payload_r1).exists() else None
log("graph under review:", M.export, {t: (len(s["ent"]), len(s["forms"]), len(s["men"])) for t, s in M.sec.items()})
log("pipeline graph:", B.export if B else "-", "| graph of round 1:", A.export if A else "-")
EUNIS = {e[0]: e for e in M.P.get("eunis", [])}
DRIVE = {}
for d in args.drive:
    if Path(d).exists():
        DRIVE.update(json.loads(Path(d).read_text(encoding="utf-8")))

# ---------------------------------------------------------------- machine rows and verdicts
ROWS = read_csv(args.identities)
ROW = {}
for r in ROWS:
    ROW[(r["section"], lc(r["name_form"]))] = r


def applied(r):
    return bool(r) and num(r.get("confidence")) >= args.min_confidence and int(num(r.get("agreement"), 0)) >= args.min_agreement


ROUNDS = []
for i, d in enumerate(args.rounds, 1):
    p = Path(d)
    mr = read_json(p / "machine_review.json", {}) if p.is_dir() else {}
    if not p.is_dir():
        log(f"round {i}: folder {d} missing")
    lab = args.round_labels[i - 1] if i - 1 < len(args.round_labels) else f"R{i}"
    arbeit = Path(args.arbeit[i - 1]) if i - 1 < len(args.arbeit) and args.arbeit[i - 1] not in ("", "-") else None
    ROUNDS.append({"n": i, "label": lab, "dir": str(p), "mr": mr or {}, "arbeit": arbeit, "model": (mr or {}).get("model", ""), "built": (mr or {}).get("built", "")})

# verdicts by label / name, per round (machine_review.json of merge.py)
VERD = {t: {} for t in TYPES}          # type -> lc(label) -> (round, verdict)
VFORM = {}                             # lc(taxon name) -> (round, form verdict)
for R in ROUNDS:
    mr = R["mr"]
    tx = mr.get("taxon") or {}
    if tx.get("ent"):                  # rounds without taxa carry dummy "unsure" forms
        for v in tx["ent"].values():
            if v.get("label"):
                VERD["taxon"][lc(v["label"])] = (R["n"], v)
        for v in (tx.get("form") or {}).values():
            if v.get("name"):
                VFORM[lc(v["name"])] = (R["n"], v)
    for t in ("person", "place", "habitat"):
        for v in ((mr.get(t) or {}).get("ent") or {}).values():
            if v.get("label"):
                VERD[t][lc(v["label"])] = (R["n"], v)
log("machine rows", len(ROWS), "applied", sum(1 for r in ROWS if applied(r)), "| verdicts", {t: len(v) for t, v in VERD.items()}, "taxon forms", len(VFORM))

# raw answers of the agents (votes): type -> lc(label) -> {"text": answer, "gemini": answer}, batches -> lc(label) -> record
KIND = {"taxon": "taxa", "person": "persons", "place": "places", "habitat": "habitats"}
ANS = {t: {} for t in TYPES}
FANS = {}                              # lc(taxon name) -> {"text": form answer, "gemini": form answer}
BATCH = {t: {} for t in TYPES}
for R in ROUNDS:
    a = R["arbeit"]
    if not a or not a.is_dir():
        if a:
            log("arbeit folder missing:", a)
        continue
    for t in TYPES:
        base = a / KIND[t]
        if not base.is_dir():
            continue
        ent_label, form_name = {}, {}
        for f in sorted((base / "batches").glob("batch_*.json")):
            for rec in read_json(f, []) or []:
                if not isinstance(rec, dict) or not rec.get("label"):
                    continue
                BATCH[t][lc(rec["label"])] = rec
                ent_label[rec.get("entity")] = rec["label"]
                if t == "taxon":
                    for fm in rec.get("forms") or []:
                        form_name[fm.get("form")] = fm.get("name")
        for src, sub in (("text", "answers"), ("gemini", "answers_gemini")):
            for f in sorted((base / sub).glob("batch_*.json")):
                data = read_json(f, []) or []
                for rec in data if isinstance(data, list) else []:
                    if not isinstance(rec, dict):
                        continue
                    label = rec.get("label") or ent_label.get(rec.get("entity"))
                    if not label:
                        continue
                    ANS[t].setdefault(lc(label), {})[src] = dict(rec, _r=R["n"])
                    if t == "taxon":
                        for fm in rec.get("forms") or []:
                            name = form_name.get(fm.get("form")) if isinstance(fm, dict) else None
                            if name:
                                FANS.setdefault(lc(name), {})[src] = dict(fm, _r=R["n"])
log("agent answers", {t: len(v) for t, v in ANS.items()}, "taxon form answers", len(FANS), "batches", {t: len(v) for t, v in BATCH.items()})

def occ_clean(v, n=4):
    """Occupation labels of a candidate (the first round stored bare Q-ids for some)."""
    return [o for o in (v or []) if isinstance(o, str) and not re.fullmatch(r"Q\d+", o.strip())][:n] if isinstance(v, list) else []


# Wikidata / GND details of person candidates (collected by the machine review; nothing is fetched here)
WD, GND = {}, {}
for R in ROUNDS:
    a = R["arbeit"]
    if not a or not (a / "persons").is_dir():
        continue
    for name in ("wd_cache.json", "wd_research_cache.json"):
        d = read_json(a / "persons" / name, {}) or {}
        for q, v in d.items():
            if isinstance(v, dict) and q.startswith("Q"):
                WD[q] = {"label": v.get("label") or "", "desc": v.get("desc") or v.get("description") or "", "born": v.get("born") or "", "died": v.get("died") or "",
                         "gnd": v.get("gnd") or "", "occ": occ_clean(v.get("occ") or v.get("occupation"))}
for rec in BATCH["person"].values():
    for c in rec.get("wikidata_candidates") or []:
        if c.get("qid"):
            WD[c["qid"]] = {"label": c.get("label") or "", "desc": c.get("description") or "", "born": c.get("born") or "", "died": c.get("died") or "",
                            "gnd": c.get("gnd") or "", "occ": occ_clean(c.get("occupation"))}
    for c in rec.get("gnd_candidates") or []:
        g = c.get("gnd") or c.get("id")
        if g:
            GND[g] = {"name": c.get("name") or "", "born": c.get("born") or "", "died": c.get("died") or "", "occ": occ_clean(c.get("occupation")),
                      "places": (c.get("places") or [])[:3] if isinstance(c.get("places"), list) else [], "wd": c.get("wikidata") or ""}
for r in read_csv(Path(args.export_review) / "person_link_review.csv"):
    if r.get("qid") and r["qid"] not in WD and r.get("wd_label"):
        WD[r["qid"]] = {"label": r["wd_label"], "desc": r.get("wd_description") or "", "born": "", "died": "", "gnd": "", "occ": []}
log("wikidata details", len(WD), "gnd details", len(GND))

# place link review rows of the export (admin1 is not in the payload)
PLR = {lc(r["place_name"]): r for r in read_csv(Path(args.export_review) / "place_link_review.csv")}

# merges: rule-based merges and open candidates of the export, earlier reviewed decisions
MERGE_OF = {t: {} for t in TYPES}          # lc(variant) -> row (auto / manual: applied)
CANDS_OUT = {t: collections.defaultdict(list) for t in TYPES}   # lc(variant) -> [row] (open candidates)
REVIEWED = {t: {} for t in TYPES}          # (lc variant, lc canonical) -> row with decision y/n
for t in TYPES:
    for r in read_csv(Path(args.reviewed_merges) / f"{t}_merges.csv"):
        if (r.get("decision") or "").strip():
            REVIEWED[t][(lc(r["variant"]), lc(r["canonical"]))] = r
    for r in read_csv(Path(args.export_review) / f"{t}_merges.csv"):
        st = (r.get("status") or "").strip()
        rv = REVIEWED[t].get((lc(r["variant"]), lc(r["canonical"])))
        if st == "candidate":
            if rv is None:
                CANDS_OUT[t][lc(r["variant"])].append(r)
        else:
            MERGE_OF[t][lc(r["variant"])] = dict(r, _reviewed=(rv or {}).get("decision", ""), _reason=(rv or {}).get("reason", ""))
log("merges applied", {t: len(v) for t, v in MERGE_OF.items()}, "open candidate rows", {t: sum(len(x) for x in v.values()) for t, v in CANDS_OUT.items()},
    "earlier decisions", {t: len(v) for t, v in REVIEWED.items()})


# ---------------------------------------------------------------- links
def wd_info(qid):
    return WD.get(qid) or {}


def link_of(G, t, ei):
    """The authority link of entity ``ei`` in graph G, or None."""
    e = G.sec[t]["ent"][ei]
    if t == "taxon":
        if not e[2]:
            return None
        grade = "broad" if e[4] == "HIGHERRANK" else ("close" if e[5] in ("llm+gbif", "machine-review") or e[4] == "FUZZY" else "exact")
        return {"key": str(e[2]), "sci": e[1], "rank": e[3], "family": e[6], "order": e[7], "de": list(e[9] or [])[:10], "qid": e[10] if len(e) > 10 else "",
                "mt": e[4], "mm": e[5], "grade": grade, "label": e[0]}
    if t == "person":
        if not (e[1] or e[2]):
            return None
        w = wd_info(e[1])
        g = GND.get(e[2]) or {}
        return {"qid": e[1] or "", "gnd": e[2] or "", "label": w.get("label") or g.get("name") or "", "desc": w.get("desc") or "", "born": w.get("born") or g.get("born") or "",
                "died": w.get("died") or g.get("died") or "", "occ": w.get("occ") or g.get("occ") or [], "grade": "close"}
    if t == "place":
        if e[1] is None and not e[4] and not e[5]:
            return None
        f = G.form_of_name(t, e[0])
        lr = f[5] if f and len(f) > 5 and isinstance(f[5], list) and len(f[5]) >= 12 else [""] * 12
        src = lr[1] or ""
        grade = "exact" if src in ("osm+geonames", "reviewed") else "close"
        row = PLR.get(lc(e[0]), {}) if G is M else {}
        return {"lat": e[1], "lon": e[2], "unc": int(num(e[3])) if str(e[3] or "").strip() else None, "gn": str(e[4] or ""), "qid": e[5] or "", "osm": lr[10] or "",
                "name": lr[7] or "", "feature": lr[11] or "", "country": lr[8] or "", "admin1": row.get("admin1") or "", "kind": e[6] or "", "src": src, "status": lr[0] or "",
                "conf": lr[2] or "", "note": lr[3] or "", "grade": grade}
    if t == "habitat":
        if not e[1]:
            return None
        return {"code": e[1], "match": e[2] or "close", "grade": e[2] or "close", "label": (EUNIS.get(e[1]) or ["", ""])[1]}
    return None


def same_link(t, a, b):
    if a is None or b is None:
        return a is None and b is None
    if t == "taxon":
        return str(a.get("key")) == str(b.get("key"))
    if t == "person":
        return (a.get("qid") or "") == (b.get("qid") or "") and (a.get("gnd") or "") == (b.get("gnd") or "")
    if t == "habitat":
        return a.get("code") == b.get("code")
    if a.get("lat") is None or b.get("lat") is None:
        return a.get("lat") is None and b.get("lat") is None and (a.get("gn") or "") == (b.get("gn") or "") and (a.get("qid") or "") == (b.get("qid") or "")
    if km((a["lat"], a["lon"]), (b["lat"], b["lon"])) > 0.5:
        return False
    for k in ("gn", "qid"):                       # an id that changed is a change; an id that was only added or dropped is not
        if a.get(k) and b.get(k) and str(a[k]) != str(b[k]):
            return False
    return True


def change_kind(t, before, cur):
    if before is None and cur is None:
        return "same"
    if before is None:
        return "newlink"
    if cur is None:
        return "unlinked"
    if same_link(t, before, cur):
        return "same"
    if t == "person" and (before.get("qid") or "") == (cur.get("qid") or "") and not before.get("gnd") and cur.get("gnd"):
        return "gnd"
    if t == "place" and before.get("lat") is not None and cur.get("lat") is not None:
        return "moved" if km((before["lat"], before["lon"]), (cur["lat"], cur["lon"])) > 0.5 else "relinked"
    return "relinked"


def machine_marked(G, t, name):
    """Does graph G already carry a machine decision for this written name?"""
    f = G.form_of_name(t, name)
    if f is None:
        return False
    if t == "taxon":
        return (f[6] if len(f) > 6 else "") in ("reviewed", "reviewed-unlinked")
    if t == "person":
        ei = f[2]
        return any((G.sec[t]["forms"][fi][6] if len(G.sec[t]["forms"][fi]) > 6 else "") in ("reviewed", "reviewed-nolink") for fi in G.forms_of_ent[t].get(ei, []))
    st = f[5][0] if len(f) > 5 and isinstance(f[5], list) and f[5] else ""
    return st in ("reviewed", "reviewed-nolink")


def baseline(t, names):
    """The link the pipeline alone had for an entity, looked up by its written names (label first):
    (found, source tag, link, entity label). The pipeline graph B where it carries no machine
    decision for the name, else the graph the first machine round judged (A); ``found`` is False
    when no graph without a machine decision has any of the names."""
    names = [names] if isinstance(names, str) else list(names)
    for G in (B, A):
        if G is None or t not in G.sec:
            continue
        for name in names:
            ei = G.ent_of_name(t, name)
            if ei is None:
                continue
            if G is B and machine_marked(G, t, name):
                break                          # B already carries a machine decision: look in A
            return True, G.tag, link_of(G, t, ei), G.sec[t]["ent"][ei][0]
    return False, "", None, ""


# ---------------------------------------------------------------- machine verdict -> proposal
COORD = re.compile(r"(\d{1,2}[.,]\d+)\s*°?\s*N?[,;]?\s*(\d{1,2}[.,]\d+)\s*°?\s*[EO]?")


def row_prop(t, r):
    """What a machine row says the link should be: a link dict, {"nolink": 1}, {"none": 1} or None."""
    if not r:
        return None
    d = r["decision"]
    auth = dict(tok.split(":", 1) for tok in (r.get("authority") or "").split() if ":" in tok)
    if d == "none":
        return {"none": 1}
    if d in ("nolink", "own"):
        return {"nolink": 1}
    if t == "taxon" and d == "same":
        if not auth.get("gbif"):
            return {"nolink": 1}
        return {"key": auth["gbif"], "sci": r.get("scientific_name") or "", "rank": r.get("rank") or "", "label": r.get("target") or ""}
    if t == "person" and d == "link":
        w = wd_info(auth.get("wd", ""))
        g = GND.get(auth.get("gnd", "")) or {}
        return {"qid": auth.get("wd", ""), "gnd": auth.get("gnd", ""), "label": w.get("label") or g.get("name") or "", "desc": w.get("desc") or "", "born": w.get("born") or g.get("born") or "",
                "died": w.get("died") or g.get("died") or "", "occ": w.get("occ") or g.get("occ") or []}
    if t == "place" and d == "link":
        return {"lat": num(r.get("lat"), None), "lon": num(r.get("lon"), None), "unc": int(num(r.get("uncertainty_m"))) if (r.get("uncertainty_m") or "").strip() else None,
                "gn": auth.get("gn", ""), "qid": auth.get("wd", ""), "osm": auth.get("osm", "")}
    if t == "habitat" and d == "link":
        code = auth.get("eunis", "")
        return {"code": code, "match": r.get("eunis_match") or "close", "label": (EUNIS.get(code) or ["", ""])[1]}
    return None


def cand_place(c, origin):
    return {"lat": c.get("lat"), "lon": c.get("lon"), "name": c.get("display_name") or c.get("name") or "", "feature": c.get("type") or "", "qid": c.get("wikidata") or "",
            "osm": c.get("osm") or "", "km": c.get("km_from_main_anchor"), "o": origin}


def votes_for(t, key, verdict):
    """One line per independent source: the text agent, Gemini, deterministic checks, earlier model readings."""
    out = []
    a = ANS[t].get(key, {})
    for src in ("text", "gemini"):
        v = a.get(src)
        if not v:
            continue
        if t == "taxon":
            word, conf, why = v.get("link") or "", v.get("link_confidence"), v.get("link_reason") or ""
            extra = v.get("link_sci") or ""
        elif t == "person":
            wd_, g_ = str(v.get("wikidata") or ""), str(v.get("gnd") or "")
            word = "link" if wd_.startswith("Q") or (g_ and g_ not in ("none", "unclear")) else ("unclear" if "unclear" in (wd_, g_) else "none")
            conf, why = v.get("confidence"), v.get("reason") or ""
            extra = " ".join(x for x in (wd_ if wd_.startswith("Q") else "", "GND " + g_ if g_ and g_ not in ("none", "unclear") else "") if x)
        elif t == "place":
            word, conf, why = v.get("verdict") or "", v.get("confidence"), v.get("reason") or ""
            extra = v.get("location_hint") or ""
        else:
            word, conf, why = v.get("verdict") or "", v.get("confidence"), v.get("reason") or ""
            extra = (v.get("code") or "") + (" (" + v["match"] + ")" if v.get("match") else "")
        out.append({"s": "gemtext" if t == "taxon" and src == "gemini" else src, "v": word, "c": round(num(conf), 2) if conf is not None else None, "why": why[:400], "x": extra[:200], "r": v.get("_r")})
    srcs = sources((verdict or {}).get("sources"))
    if t == "place":
        for s in ("nominatim", "anchor", "generic"):
            if s in srcs:
                out.append({"s": s, "v": "ok", "c": None, "why": "", "x": "", "r": None})
        if (verdict or {}).get("gemini") and not any(v["s"] == "gemini" for v in out):
            out.append({"s": "gemini", "v": verdict["gemini"], "c": None, "why": "", "x": "", "r": None})
    if t == "person":
        if "xref" in srcs:
            out.append({"s": "xref", "v": "ok", "c": None, "why": (verdict or {}).get("note") or "", "x": "", "r": None})
    return out


def machine_info(t, key, row, cur, pm=None):
    """The machine's verdict on an entity (persons, places, habitats): combined row + merged verdict."""
    rv = VERD[t].get(key)
    if not row and not rv:
        return None
    rnd, v = rv if rv else (int(num(row.get("round"), 0)), {})
    if row and (row.get("round") or "").isdigit() and rv and int(row["round"]) != rnd:
        # the combined row comes from another round than the latest verdict: the row is what the pipeline reads
        v = ((ROUNDS[int(row["round"]) - 1]["mr"].get(t) or {}).get("ent") or {})
        v = next((x for x in v.values() if lc(x.get("label") or "") == key), {})
        rnd = int(row["round"])
    word = v.get("verdict") or v.get("decision") or (row or {}).get("decision") or ""
    m = {"word": word, "ap": int(applied(row)), "c": round(num((row or v).get("confidence")), 2), "a": int(num((row or {}).get("agreement"), 0)) if row else None,
         "s": sources((row or {}).get("sources") or v.get("sources")), "r": rnd, "why": (v.get("reason") or (row or {}).get("reason") or "")[:600],
         "note": ((row or {}).get("note") or v.get("note") or "")[:300], "row": int(bool(row))}
    prop = row_prop(t, row)
    if t == "place":
        c = v.get("candidate")
        if prop and prop.get("lat") is not None and c:
            prop.update({"name": c.get("display_name") or c.get("name") or "", "feature": c.get("type") or "", "osm": prop.get("osm") or c.get("osm") or ""})
        elif prop is None and c and word in ("wrong", "unlocated_ok"):
            prop = cand_place(c, "m")
            prop["unc"] = v.get("uncertainty_m")
        if v.get("hint"):
            m["hint"] = v["hint"][:300]
            hc = COORD.search(v["hint"])
            if hc:
                la, lo = float(hc.group(1).replace(",", ".")), float(hc.group(2).replace(",", "."))
                if 35 <= la <= 72 and -12 <= lo <= 35:
                    m["hint_ll"] = [la, lo]
        if word == "unlocatable" and prop is None and cur is None:
            m["nop"] = 1                      # no proposal: the machine found no record either
    if t == "person" and prop is None and word == "unsure":
        wd_ = str(v.get("wikidata") or "")
        if wd_.startswith("Q"):               # named an item but stayed unsure
            w = wd_info(wd_)
            g_ = str(v.get("gnd") or "")
            prop = {"qid": wd_, "gnd": g_ if g_ not in ("none", "unclear") else "", "label": w.get("label") or "", "desc": w.get("desc") or "", "born": w.get("born") or "",
                    "died": w.get("died") or "", "occ": w.get("occ") or [], "weak": 1}
        if v.get("auto_link_ok") is False and cur is not None and prop is None:
            prop = {"nolink": 1, "weak": 1}
    if t == "habitat" and prop is None and word == "other" and v.get("code"):
        prop = {"code": v["code"], "match": v.get("match") or "close", "label": (EUNIS.get(v["code"]) or ["", ""])[1]}
    if t == "habitat" and prop is None and word == "none":
        prop = {"none": 1}
    m["prop"] = prop
    m["votes"] = votes_for(t, key, v)
    if t == "person" and pm:
        word_ = "link" if str(pm[0]).startswith("Q") else ("none" if pm[0] == "none" else "unclear")
        m["votes"].append({"s": "opus", "v": word_, "c": round(num(pm[1]), 2), "why": str(pm[2] or "")[:400], "x": pm[0] if word_ == "link" else ""})
    if t == "person":
        if v.get("auto_link_ok") is not None:
            m["auto_ok"] = bool(v["auto_link_ok"])
    return m


# ---------------------------------------------------------------- passages
PAGES, PAGE_IDX = [], {}


def page_ref(G, pidx):
    if pidx is None or pidx < 0 or pidx >= len(G.PG):
        return -1
    g = G.PG[pidx]
    if g[0] not in PAGE_IDX:
        PAGE_IDX[g[0]] = len(PAGES)
        PAGES.append([g[0], g[1], g[2], g[3], g[4], g[5], g[6], DRIVE.get(g[0], "")])
    return PAGE_IDX[g[0]]


def snippet(text, s, e, name, width=150):
    """(clean snippet, highlight start, highlight end): the passage around a mention, markup removed."""
    if s is None or s < 0:
        i = lc(text).find(lc(name)) if name else -1
        if i >= 0 and lc(text[i:i + len(name)]) == lc(name):
            s, e = i, i + len(name)
    if s is None or s < 0:
        t0 = TAG.sub("", text[:2 * width])
        return t0 + ("…" if len(text) > 2 * width else ""), -1, -1
    a, b = max(0, s - width), min(len(text), e + width)
    while a > 0 and text[a] not in " \n" and s - a < width + 25:      # start at a word boundary
        a -= 1
    while b < len(text) and text[b - 1] not in " \n" and b - e < width + 25:
        b += 1
    raw = text[a:s] + "\x01" + text[s:e] + "\x02" + text[e:b]
    raw = re.sub(r"<[^>\x01\x02]*>", "", raw)
    raw = re.sub(r"<[^>]*$", "", raw)
    raw = re.sub(r"^[^<]*>", "", raw) if ">" in raw[:12] and "<" not in raw[:raw.find(">")] else raw
    hs = raw.find("\x01")
    raw = raw.replace("\x01", "")
    he = raw.find("\x02")
    raw = raw.replace("\x02", "")
    pre = "…" if a > 0 else ""
    return pre + raw + ("…" if b < len(text) else ""), hs + len(pre), he + len(pre)


def pick_mentions(G, t, fis, limit):
    """Up to ``limit`` mentions of the forms: located on the scan first, spread over the forms and the years."""
    s = G.sec[t]
    cand = []
    tiers = MT.get(t) if G is M and CORPUS else None
    for rank, fi in enumerate(fis):
        for mi in G.men_of_form[t].get(fi, []):
            m = s["men"][mi]
            box = m[4]
            has_box = isinstance(box, list) and len(box) >= 5
            q = (2 if has_box and len(box) > 5 and box[5] == 0 else 1 if has_box else 0) + (1 if m[2] >= 0 else 0)
            y = (G.E[m[1]][2] or "")[:4]
            cand.append((mi, fi, rank, q, int(y) if y.isdigit() else 0, tiers[mi] if tiers else 0))
    if not cand:
        return []
    top = max(c[5] for c in cand)
    if len(cand) > 4000:                       # frequent names: a deterministic thinning keeps the greedy pick cheap
        step = len(cand) / 4000.0
        thin = [cand[int(i * step)] for i in range(4000)]
        if max(c[5] for c in thin) < top:
            thin.append(next(c for c in cand if c[5] == top))
        cand = thin
    out, used_e, forms_seen, years = [], set(), collections.Counter(), []
    while len(out) < limit and cand:
        best, bi = None, -1
        for i, (mi, fi, rank, q, y, tr) in enumerate(cand):
            ei = s["men"][mi][1]
            if ei in used_e or (not out and tr < top):      # the first passage is one of the most reliable level
                continue
            spread = min((abs(y - y0) for y0 in years), default=20) if y else 0
            sc = q * 3 + min(spread, 20) * 0.5 - forms_seen[fi] * 4 - (rank * 0.2 if forms_seen[fi] else 0) + (6 if not forms_seen[fi] and rank < limit else 0) + tr * 4
            if best is None or sc > best:
                best, bi = sc, i
        if bi < 0:
            break
        mi, fi, rank, q, y, tr = cand.pop(bi)
        out.append(mi)
        used_e.add(s["men"][mi][1])
        forms_seen[fi] += 1
        if y:
            years.append(y)
    out.sort(key=lambda mi: (G.E[s["men"][mi][1]][2] or "9999", mi))
    return out


def mention_rec(G, t, mi):
    s = G.sec[t]
    m = s["men"][mi]
    e = G.E[m[1]]
    name = s["forms"][m[0]][0]
    snip, hs, he = snippet(e[7], m[2], m[3], name)
    box = m[4]
    p, bx = -1, None
    if isinstance(box, list) and box:
        p = page_ref(G, box[0])
        if len(box) >= 5:
            bx = [box[1], box[2], box[3], box[4], int(box[5]) if len(box) > 5 else 1] + ([box[6], box[7]] if len(box) > 7 else [])
    pages = [page_ref(G, x) for x in (e[8] or [])]
    if p < 0 and pages:
        p = pages[0]
    rec = {"d": e[2] or "", "vd": e[3] or "", "id": e[0], "vol": e[5], "tx": snip, "hs": hs, "he": he, "p": p, "b": bx, "pp": pages, "f": name, "ro": m[5] if len(m) > 5 else "",
           "hp": e[6] or ""}
    if G is M and CORPUS:                       # level index of the passage's record, its error estimates in %, 1/2 = tied to the entry
        rec["k"] = MT[t][mi]
        p, po, pc, tie = MW[t][mi]
        for key_, v in (("kp", p), ("ko", po), ("kc", pc)):
            if v is not None:
                rec[key_] = int(v * 100)            # floor: the shown percentage agrees with the thresholds
        if tie:
            rec["ke"] = tie
    return rec


def year_hist(G, t, fis):
    c = collections.Counter()
    s = G.sec[t]
    for fi in fis:
        for mi in G.men_of_form[t].get(fi, []):
            y = (G.E[s["men"][mi][1]][2] or "")[:4]
            if y.isdigit():
                c[int(y)] += 1
    return sorted(c.items())


PLACE_PT = {}
for e in M.sec["place"]["ent"]:
    if e[1] is not None:
        PLACE_PT.setdefault(lc(e[0]), (e[0], e[1], e[2]))


def anchors_of(G, fis, own_label, cur):
    c = collections.Counter()
    s = G.sec["place"]
    for fi in fis:
        for mi in G.men_of_form["place"].get(fi, []):
            h = lc(G.E[s["men"][mi][1]][6] or "")
            if h and h != lc(own_label) and h in PLACE_PT:
                c[h] += 1
    out = []
    for h, n in c.most_common(5):
        lab, la, lo = PLACE_PT[h]
        out.append({"place": lab, "n": n, "lat": la, "lon": lo, "km": round(km((cur["lat"], cur["lon"]), (la, lo)), 1) if cur and cur.get("lat") is not None else None})
    return out


# ---------------------------------------------------------------- who set the link
def who_of(t, G, ei, cur, rows):
    """Provenance of the current link: pipeline rule, machine review, or none."""
    s = G.sec[t]
    e = s["ent"][ei]
    f = G.form_of_name(t, e[0]) or s["forms"][G.forms_of_ent[t][ei][0]]
    ap = [r for r in rows if applied(r)]
    if t == "taxon":
        if e[5] == "machine-review" or any(r["decision"] == "same" for r in ap):
            return {"by": "machine"}
        if not cur:
            return {"by": "none", "status": f[6] if len(f) > 6 else "", "llm": f[5] if len(f) > 5 else ""}
        return {"by": "pipeline", "rule": e[5], "mt": e[4], "status": f[6] if len(f) > 6 else "", "llm": f[5] if len(f) > 5 else ""}
    if t == "person":
        rules = [s["forms"][fi][6] if len(s["forms"][fi]) > 6 else "" for fi in G.forms_of_ent[t][ei]]
        rule = f[6] if len(f) > 6 else ""
        if "reviewed" in rules or "reviewed-nolink" in rules or ap:
            return {"by": "machine", "rule": "reviewed" if "reviewed" in rules else "reviewed-nolink" if "reviewed-nolink" in rules else rule}
        if cur:
            return {"by": "pipeline", "rule": "linked" if "linked" in rules else rule}
        return {"by": "none", "rule": rule}
    lr = f[5] if len(f) > 5 and isinstance(f[5], list) else []
    st = lr[0] if lr else ""
    if t == "place":
        if st in ("reviewed", "reviewed-nolink") or (lr and lr[1] == "machine-review"):
            return {"by": "machine", "status": st}
        if cur:
            return {"by": "pipeline", "rule": lr[1] if lr else "", "status": st, "conf": lr[2] if lr else "", "note": lr[3] if lr else "", "src": e[7]}
        return {"by": "none", "status": st, "note": lr[3] if lr else ""}
    if st == "reviewed":
        return {"by": "machine", "status": st}
    if cur:
        return {"by": "pipeline", "rule": "llm", "status": st, "conf": lr[1] if len(lr) > 1 else "", "note": lr[2] if len(lr) > 2 else ""}
    return {"by": "none", "status": st, "note": lr[2] if len(lr) > 2 else ""}


# ---------------------------------------------------------------- how a link is backed
# two   applied machine review row: >= 2 independent sources agreed and confidence >= the threshold
# one   linked by the pipeline alone (GBIF exact name, Wikidata exact label, one Gemini answer per habitat label)
# name  places: coordinates from a gazetteer name match only (OpenStreetMap/Nominatim or GeoNames), not confirmed by the place review
# mno   the machine review holds the link wrong or the name for no entity: no link in the graph
# none  no link and no applied machine decision
BASIS = ("two", "one", "name", "mno", "none")


def link_basis(t, e, cur, who, m, gone):
    if gone:
        return "mno"
    by = who.get("by")
    if by == "machine" and cur is not None and (m or {}).get("ineff"):
        by = "pipeline"                           # the applied row has no effect: the link in the graph is the pipeline's
    if cur is None:
        return "mno" if by == "machine" else "none"
    if by == "machine":
        return "two"
    if t == "place" and "name match" in str(e[7] if len(e) > 7 else ""):
        return "name"
    return "one"


def form_basis(fr, ent_basis):
    """Species: a written name is machine-verified (status reviewed) or linked by its own GBIF exact match."""
    if ent_basis in ("mno", "none"):
        return ent_basis
    return "two" if fr.get("st") == "reviewed" else "one"


# ---------------------------------------------------------------- candidates
def dedupe(t, cands, cur):
    out = []
    for c in cands:
        if not c:
            continue
        if t == "taxon":
            k = str(c.get("key") or "")
        elif t == "person":
            k = (c.get("qid") or "") + "|" + (c.get("gnd") or "")
        elif t == "habitat":
            k = c.get("code") or ""
        else:
            k = f"{c.get('lat')},{c.get('lon')}" if c.get("lat") is not None else ""
        if not k or k == "|":
            continue
        if any(x[0] == k for x in out):
            continue
        if cur and ((t == "place" and cur.get("lat") is not None and c.get("lat") is not None and km((cur["lat"], cur["lon"]), (c["lat"], c["lon"])) < 0.05)
                    or (t != "place" and same_link(t, cur, c))):
            continue
        out.append((k, c))
    return [c for _, c in out][:9]


TAXON_BY_KEY = {}
for G in (A, B, M):                      # details of taxa by GBIF key (the graph under review wins)
    if G is None:
        continue
    for i, e in enumerate(G.sec["taxon"]["ent"]):
        if e[2]:
            TAXON_BY_KEY[str(e[2])] = link_of(G, "taxon", i)


def taxon_cand(key, sci="", rank="", label="", origin=""):
    d = TAXON_BY_KEY.get(str(key))
    c = {"key": str(key), "sci": sci or (d or {}).get("sci", ""), "rank": rank or (d or {}).get("rank", ""), "label": (d or {}).get("label") or label or "",
         "family": (d or {}).get("family", ""), "de": (d or {}).get("de", []), "o": origin}
    return c


def candidates(t, G, ei, cur, before, m, fis):
    s = G.sec[t]
    e = s["ent"][ei]
    key = lc(e[0])
    out = []
    if m and m.get("prop") and not m["prop"].get("none") and not m["prop"].get("nolink"):
        out.append(dict(m["prop"], o="m"))
    if before:
        out.append(dict(before, o="b"))
    if t == "taxon":
        p = row_prop(t, ROW.get(("taxa", key)))
        if p and p.get("key"):
            out.append(taxon_cand(p["key"], p.get("sci"), p.get("rank"), p.get("label"), "m"))
        rv = VERD[t].get(key)
        if rv and rv[1].get("new_key"):
            out.append(taxon_cand(rv[1]["new_key"], rv[1].get("new_sci"), rv[1].get("new_rank"), rv[1].get("species_de"), "m"))
    elif t == "person":
        b = BATCH[t].get(key, {})
        for c in b.get("wikidata_candidates") or []:
            out.append({"qid": c.get("qid") or "", "gnd": c.get("gnd") or "", "label": c.get("label") or "", "desc": c.get("description") or "", "born": c.get("born") or "",
                        "died": c.get("died") or "", "occ": occ_clean(c.get("occupation"), 3), "o": "wd"})
        for fi in fis:
            f = s["forms"][fi]
            for c in (f[5] if len(f) > 5 and isinstance(f[5], list) else []):
                if c and c[0]:
                    w = wd_info(c[0])
                    out.append({"qid": c[0], "gnd": w.get("gnd") or "", "label": c[1] or w.get("label") or "", "desc": c[2] or w.get("desc") or "", "born": w.get("born") or "",
                                "died": w.get("died") or "", "occ": w.get("occ") or [], "o": "p"})
        for c in (b.get("gnd_candidates") or [])[:6]:
            g = c.get("gnd") or c.get("id") or ""
            if g and not any(x.get("gnd") == g for x in out):
                out.append({"qid": c.get("wikidata") or "", "gnd": g, "label": c.get("name") or "", "desc": ", ".join(occ_clean(c.get("occupation"), 3)),
                            "born": c.get("born") or "", "died": c.get("died") or "", "occ": [], "o": "gnd"})
        pm = G.P.get("pm", {}).get(str(ei))
        if pm and str(pm[0]).startswith("Q"):
            w = wd_info(pm[0])
            out.append({"qid": pm[0], "gnd": w.get("gnd") or "", "label": w.get("label") or "", "desc": w.get("desc") or "", "born": w.get("born") or "", "died": w.get("died") or "",
                        "occ": w.get("occ") or [], "o": "opus"})
    elif t == "place":
        f = G.form_of_name(t, e[0])
        lr = f[5] if f and len(f) > 5 and isinstance(f[5], list) and len(f[5]) >= 12 else None
        if lr and lr[0] in ("review", "no_match") and lr[4] and lr[5]:
            out.append({"lat": num(lr[4]), "lon": num(lr[5]), "name": lr[7] or e[0], "feature": lr[11] or "", "gn": lr[6] or "", "qid": lr[9] or "", "osm": lr[10] or "",
                        "note": lr[3] or "", "o": "p"})
        for c in (BATCH[t].get(key, {}).get("candidates") or []):
            if c.get("lat") is not None:
                out.append(cand_place(c, "nom"))
        if m and m.get("hint_ll"):
            out.append({"lat": m["hint_ll"][0], "lon": m["hint_ll"][1], "name": m.get("hint") or "", "feature": "", "qid": "", "osm": "", "o": "hint"})
    else:
        f = G.form_of_name(t, e[0])
        lr = f[5] if f and len(f) > 5 and isinstance(f[5], list) and len(f[5]) >= 6 else None
        if lr and lr[3] and lr[0] in ("review", "no_match"):
            out.append({"code": lr[3], "match": lr[5] or "close", "label": lr[4] or (EUNIS.get(lr[3]) or ["", ""])[1], "note": lr[2] or "", "o": "p"})
        for src in ("text", "gemini"):
            v = ANS[t].get(key, {}).get(src)
            if v and v.get("code") and (v.get("verdict") or "") in ("ok", "other") and v["code"] in EUNIS:
                out.append({"code": v["code"], "match": v.get("match") or "close", "label": EUNIS[v["code"]][1], "o": "m" if src == "text" else "gem"})
        if cur and cur.get("code") in EUNIS and EUNIS[cur["code"]][3] in EUNIS:
            par = EUNIS[EUNIS[cur["code"]][3]]
            out.append({"code": par[0], "match": "broad", "label": par[1], "o": "parent"})
    return dedupe(t, out, cur)


READINGS = collections.defaultdict(list)       # taxon form index (graph under review) -> votes from the line images
for src, pkey in (("gemini", "sug"), ("opus", "sug3"), ("scan", "sugs")):
    for mi, a in (M.P.get(pkey) or {}).items():
        if not str(mi).isdigit() or int(mi) >= len(M.sec["taxon"]["men"]) or not isinstance(a, list) or len(a) < 7:
            continue
        fi = M.sec["taxon"]["men"][int(mi)][0]
        legible = src == "gemini" or bool(a[1])
        READINGS[fi].append({"s": src, "v": ((a[3] or a[4]) if a[2] == "bird" else (a[2] or "")) if legible else "illegible", "x": "„" + str(a[0]) + "“", "c": round(num(a[5]), 2),
                             "why": str(a[6] or "")[:180], "id": M.E[M.sec["taxon"]["men"][int(mi)][1]][0]})


def readings_of(fi):
    out = []
    for src in ("scan", "gemini", "opus"):
        out += sorted((r for r in READINGS.get(fi, []) if r["s"] == src), key=lambda r: -r["c"])[:3]
    return out


# ---------------------------------------------------------------- entities
STATS = {t: collections.Counter() for t in TYPES}
ANOM = collections.Counter()
ANOM_EX = collections.defaultdict(list)


def anom(kind, example=None):
    ANOM[kind] += 1
    if example is not None and len(ANOM_EX[kind]) < 12:
        ANOM_EX[kind].append(example)

ENTS = {t: [] for t in TYPES}
KEYS = {t: set() for t in TYPES}
USED_ROWS = set()

# ---------------------------------------------------------------- reliability (the filter of the graph validation page)
# graph_check/build_review.py --quality gives every record q.p, the estimated probability that at least one of its
# fields is wrong (record_quality.py), and po / pc for the occurrence and the coordinates. The filter keeps the records
# below a threshold: all | < 50 % | < 25 % | < 10 %, index c = 0-3; a record passes c when its level index k >= c.
# A mention of an entity passes when the record it is tied to does (the taxon of a record, a place as its locality /
# observedAt, a person as its recordedBy, a habitat of a record); a mention tied to the entry (header place, persons
# mentioned in the entry, places of travel legs) when the best record of the entry does.
THRESH = (None, 0.50, 0.25, 0.10)
MT, MW = {}, {}                 # type -> [level index per mention], [(p, po, pc, tie)]; tie 0 record, 1 entry, 2 entry without records
CORPUS = None
UNKNOWN = (0, None, None, None)


def level_of(p):
    return 3 if p < THRESH[3] else 2 if p < THRESH[2] else 1 if p < THRESH[1] else 0


def rank(x):
    return (x[0], -(x[1] if x[1] is not None else 9))


def build_corpus():
    rl = Path(args.review_layer)
    if not rl.exists():
        log("no review layer at", rl, "- the page is built without the reliability filter")
        return None
    RV = json.loads(rl.read_text(encoding="utf-8")).get("entries", {})
    by_name, by_idx, best = {}, {}, {}
    totals, levels = [0, 0, 0, 0], collections.Counter()
    for eid, e in RV.items():
        a, b = {}, {}
        for k, r in (e.get("rec") or {}).items():
            q = r.get("q") or {}
            if q.get("p") is None:
                anom("reliability: record without an error estimate in the review layer", f"{eid} {k}")
                x = UNKNOWN
            else:
                p = num(q["p"])
                x = (level_of(p), p, num(q["po"]) if q.get("po") is not None else None, num(q["pc"]) if q.get("pc") is not None else None)
                if q.get("lv") is not None and int(q["lv"]) != 4 - x[0]:
                    anom("reliability: level of the review layer differs from its p", f"{eid} {k} p={p} lv={q['lv']}")
            a[(lc(r.get("w") or ""), int(r.get("occ") or 0))] = x      # occ counts the casefolded name (build_review.py)
            b[int(k)] = x
            for c in range(x[0] + 1):
                totals[c] += 1
            levels[x[0]] += 1
        by_name[eid], by_idx[eid] = a, b
        best[eid] = max(b.values(), key=rank) if b else None

    def entry_tier(eid):
        x = best.get(eid)
        return (x[0], x[1], x[2], x[3], 1) if x else (0, None, None, None, 2)

    # taxa: one mention per record, the k-th mention of a written name in an entry = its k-th record of that name
    s = M.sec["taxon"]
    occ, mt, mw = collections.Counter(), [], []
    for m in s["men"]:
        eid, name = M.E[m[1]][0], lc(s["forms"][m[0]][0])
        r = by_name.get(eid, {}).get((name, occ[(eid, name)]))
        occ[(eid, name)] += 1
        if r is None:
            anom("reliability: taxon mention without a record in the review layer", f"{eid} {name}")
            r = UNKNOWN
        mt.append(r[0])
        mw.append((r[1], r[2], r[3], 0))
    MT["taxon"], MW["taxon"] = mt, mw
    got = [sum(1 for x in mt if x >= c) for c in range(4)]
    if got != totals:
        anom("reliability: taxon mentions per threshold differ from the records of the review layer", f"{got} vs {totals}")

    # persons, places, habitats: the graph says which record a mention belongs to
    rec_person, rec_place, rec_hab, ent_person = {}, {}, collections.defaultdict(list), set()
    tp = Path(args.triples)
    if tp.exists():
        want = {"identifier", "containsObservation", "recordedBy", "hasLocality", "observedAt", "habitat", "observedTaxon", "verbatimIdentification", "label", "name", "prefLabel",
                "mentionsPerson", "mentionsCompanion", "mentionsSource", "mentionsCollector", "mentionsCitedAuthor", "mentionsOther"}

        def loc(u):
            u = str(u)
            return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

        entries, out = [], collections.defaultdict(dict)
        with open(tp, "rb") as h:
            triples = pickle.load(h)
        for s_, p_, o_ in triples:
            pn = loc(p_)
            if pn == "type":
                if loc(o_) == "DiaryEntry":
                    entries.append(s_)
            elif pn in want:
                out[s_].setdefault(pn, []).append(o_)
        del triples

        def lab(n, keys):
            d = out.get(n) or {}
            return next((str(d[k][0]) for k in keys if d.get(k)), "")

        def better(table, key, r):
            if key not in table or rank(r) > rank(table[key]):
                table[key] = r

        lost = 0
        for s_ in entries:
            d = out.get(s_) or {}
            eid, uid = lab(s_, ("identifier",)), loc(s_).replace("entry_", "")
            idx = by_idx.get(eid, {})
            for pred in ("mentionsPerson", "mentionsCompanion", "mentionsSource", "mentionsCollector", "mentionsCitedAuthor", "mentionsOther"):
                for p in d.get(pred, []):
                    ent_person.add((eid, lc(lab(p, ("label", "name")))))
            for o in d.get("containsObservation", []):
                od = out.get(o) or {}
                tx = (od.get("observedTaxon") or [None])[0]
                written = lab(o, ("verbatimIdentification",)) or (lab(tx, ("prefLabel", "label", "name")) if tx is not None else "")
                h_ = loc(o).replace("obs_", "")
                i_ = next((i for i in range(1000) if hashlib.sha1(f"{uid}|{written}|{i}".encode("utf-8")).hexdigest()[:12] == h_), None)
                r = idx.get(i_)
                if r is None:
                    lost += 1
                    r = UNKNOWN
                for p in od.get("recordedBy", []):
                    better(rec_person, (eid, lc(lab(p, ("label", "name")))), r)
                for p in set(od.get("hasLocality", []) + od.get("observedAt", [])):
                    better(rec_place, (eid, lc(lab(p, ("label",)))), r)
                for hb in od.get("habitat", []):
                    if str(hb).startswith("http"):
                        rec_hab[(eid, lc(lab(hb, ("prefLabel", "label"))))].append(r)
        if lost:
            anom("reliability: records of the graph without an estimate in the review layer", lost)
        for v in rec_hab.values():
            v.sort(key=rank, reverse=True)
    else:
        log("no triples at", tp, "- person / place / habitat mentions follow their entry (at least one record in the corpus)")
        anom("reliability: triples missing, person / place / habitat mentions counted by their entry")
    for t in ("person", "place", "habitat"):
        s = M.sec[t]
        mt, mw, used = [], [], collections.Counter()
        for m in s["men"]:
            eid, label = M.E[m[1]][0], lc(s["ent"][s["forms"][m[0]][2]][0])
            role = m[5] if len(m) > 5 else ""
            x = entry_tier(eid)
            if tp.exists():
                if t == "person":
                    r = rec_person.get((eid, label))
                    if r is not None and (eid, label) not in ent_person:     # observer of single records only
                        x = r + (0,)
                elif t == "place" and role == "Beobachtung":
                    r = rec_place.get((eid, label))
                    if r is None:
                        anom("reliability: locality mention without a record in the graph (counted by its entry)", f"{eid} {label}")
                    else:
                        x = r + (0,)
                elif t == "habitat":
                    lst = rec_hab.get((eid, label))
                    if not lst:
                        anom("reliability: habitat mention without a record in the graph (counted by its entry)", f"{eid} {label}")
                    else:
                        r = lst[min(used[(eid, label)], len(lst) - 1)]
                        used[(eid, label)] += 1
                        x = r + (0,)
            mt.append(x[0])
            mw.append(x[1:])
        MT[t], MW[t] = mt, mw
    log("reliability: records per threshold", totals, "| mentions per threshold", {t: [sum(1 for x in MT[t] if x >= c) for c in range(4)] for t in TYPES})
    return {"rec": totals, "thr": [round(x * 100) if x else 0 for x in THRESH], "levels": [levels[k] for k in range(4)]}


CORPUS = build_corpus()


def nc_of(t, mis):
    """Mentions per threshold [all, < 50 %, < 25 %, < 10 %]."""
    c = [0, 0, 0, 0]
    for mi in mis:
        for k in range(MT[t][mi] + 1):
            c[k] += 1
    return c


def form_how(t, G, name, label):
    """How a written name came to its entity."""
    if lc(name) == lc(label):
        return {"k": "label"}
    r = MERGE_OF[t].get(lc(name))
    if r:
        how = {"k": "reviewed" if r.get("status") == "manual" or r.get("_reviewed") == "y" else "rule", "rule": r.get("rule") or "", "to": r.get("canonical") or ""}
        if r.get("_reason"):
            how["why"] = r["_reason"][:200]
        if r.get("detail"):
            how["detail"] = r["detail"][:120]
        return how
    f = G.form_of_name(t, name)
    rule = f[4] if f and t != "taxon" and len(f) > 4 else ""
    return {"k": "rule", "rule": rule or ("gbif-key" if t == "taxon" else "")}


def build_entity(t, G, ei, gone=False):
    s = G.sec[t]
    e = s["ent"][ei]
    label = e[0]
    key = lc(label)
    fis = sorted(G.forms_of_ent[t].get(ei, []), key=lambda fi: (-s["forms"][fi][1], s["forms"][fi][0]))
    if not fis:
        return None
    n = sum(s["forms"][fi][1] for fi in fis)
    cur = None if gone else link_of(G, t, ei)
    sect = SECTION[t]
    rows = []
    li = {"person": 3, "place": 8, "habitat": 3}.get(t)
    seen_names = {lc(s["forms"][fi][0]) for fi in fis}
    extra = [x for x in dict.fromkeys(e[li] if li is not None and len(e) > li and isinstance(e[li], list) else []) if lc(x) not in seen_names]
    for name in dict.fromkeys([label] + [s["forms"][fi][0] for fi in fis] + extra):
        r = ROW.get((sect, lc(name)))
        if r:
            rows.append(r)
            USED_ROWS.add((sect, lc(name)))
    main_row = ROW.get((sect, key)) or (rows[0] if rows and t != "taxon" else None)

    # ---- before (pipeline alone) and category
    forms = []
    changed_forms, confirmed_forms, suggest_forms = [], [], []
    if t == "taxon":
        for fi in fis:
            f = s["forms"][fi]
            r = ROW.get((sect, lc(f[0])))
            fr = {"f": f[0], "n": f[1], "how": form_how(t, G, f[0], label), "cls": f[3] if len(f) > 3 else "", "st": f[6] if len(f) > 6 else ""}
            fv = VFORM.get(lc(f[0]))
            if G is M and READINGS.get(fi):
                fr["rd"] = readings_of(fi)
            if r or (fv and fv[1].get("decision") and (fv[1].get("sources") or fv[1].get("confidence"))):
                src_ = r or fv[1]
                fm = {"d": src_["decision"], "ap": int(applied(r)), "c": round(num(src_.get("confidence")), 2), "a": int(num(src_.get("agreement"), 0)), "s": sources(src_.get("sources")),
                      "r": int(num(r.get("round"), 0)) if r else fv[0], "why": (src_.get("reason") or src_.get("note") or "")[:300]}
                p = row_prop(t, r) if r else None
                if p and p.get("key"):
                    fm["key"], fm["sci"] = p["key"], p.get("sci") or ""
                    if cur is None or str(p["key"]) != str(cur["key"]):
                        fm["diff"] = 1
                elif p:
                    fm["none" if p.get("none") else "nolink"] = 1
                    if cur is not None or p.get("none"):
                        fm["diff"] = 1
                fa = FANS.get(lc(f[0]), {})
                fm["votes"] = [{"s": "gemtext" if src == "gemini" else src, "v": v.get("decision") or "", "c": round(num(v.get("confidence")), 2), "why": (v.get("reason") or "")[:200],
                                "x": v.get("sci") or v.get("species_de") or ""} for src, v in fa.items()]
                fr["m"] = fm
                if fm["ap"]:
                    found, tag, bl, bl_label = baseline(t, f[0])
                    ck = change_kind(t, bl, cur) if found else ("same" if not (fv and fv[1].get("changed")) else "relinked")
                    if not found:
                        anom("taxon form: no pipeline state before the machine", f[0])
                    if ck == "same":
                        confirmed_forms.append(f[0])
                    else:
                        fr["was"] = {"src": tag, "label": bl_label, "key": (bl or {}).get("key", ""), "sci": (bl or {}).get("sci", ""), "ck": ck, "known": int(found)}
                        changed_forms.append(f[0])
                elif fm["d"] != "unsure" or fm.get("diff"):
                    suggest_forms.append(f[0])
            forms.append(fr)
    else:
        for fi in fis:
            f = s["forms"][fi]
            forms.append({"f": f[0], "n": f[1], "how": form_how(t, G, f[0], label)})
        for name in extra:                     # names of the cluster no passage was assigned to
            forms.append({"f": name, "n": 0, "how": form_how(t, G, name, label)})

    m = None
    before, before_src, before_label, ck = None, "", "", ""
    if t == "taxon":
        rv = VERD[t].get(key)
        if rv or rows:
            v = rv[1] if rv else {}
            ap_rows = [r for r in rows if applied(r)]
            best = max(rows, key=lambda r: (applied(r), num(r.get("confidence")))) if rows else None
            m = {"word": v.get("link") or (best or {}).get("decision") or "", "ap": int(bool(ap_rows)), "c": round(num(v.get("confidence") if v else (best or {}).get("confidence")), 2),
                 "a": max([int(num(r.get("agreement"), 0)) for r in rows] + [0]) if rows else None, "s": sorted({x for r in rows for x in sources(r.get("sources"))}),
                 "r": rv[0] if rv else int(num((best or {}).get("round"), 0)), "why": (v.get("reason") or "")[:600], "note": (v.get("note") or "")[:300], "row": int(bool(rows)),
                 "votes": votes_for(t, key, v), "nrows": len(rows), "nap": len(ap_rows)}
            prop = None
            if v.get("new_key") and (cur is None or str(v["new_key"]) != str(cur["key"])):
                prop = taxon_cand(v["new_key"], v.get("new_sci"), v.get("new_rank"), v.get("species_de"), "m")
            elif v.get("link") == "none" and not ap_rows:
                prop = {"none": 1}
            m["prop"] = prop
        found, tag, bl, bl_label = baseline(t, label)
        before, before_src, before_label = bl, tag, bl_label
        if changed_forms:
            cat = "changed"
            lab_form = next((fr for fr in forms if lc(fr["f"]) == key), None)
            ck = (lab_form or {}).get("was", {}).get("ck") or "forms"
        elif confirmed_forms:
            cat = "confirmed"
        elif suggest_forms or (m and (m.get("prop") or m["word"] in ("wrong", "none"))):
            cat = "suggest"
        elif m and m["word"] == "unsure":
            cat = "suggest"
        else:
            cat = "pipeline" if cur else "unlinked"
    else:
        m = machine_info(t, key, main_row, cur, G.P.get("pm", {}).get(str(ei)) if t == "person" and G is M else None)
        found, tag, bl, bl_label = baseline(t, [label] + [fr["f"] for fr in forms if lc(fr["f"]) != key])
        before, before_src, before_label = bl, tag, bl_label
        p_ = (m or {}).get("prop") or {}
        ineff = bool(m and m["ap"] and not gone and ((p_.get("none")) or (p_.get("nolink") and cur is not None)
                                                      or (p_ and not p_.get("nolink") and not p_.get("none") and not same_link(t, p_, cur))))
        if ineff:
            # the row clears the thresholds but the graph does not show its effect (a variant name carries
            # its own automatic link, or the name survives in a role the removal does not cover)
            m["ineff"] = 1
            anom(f"{t}: applied machine row not effective in the graph ({'none' if p_.get('none') else 'nolink' if p_.get('nolink') else 'link'})", label)
            cat = "suggest"
        elif m and m["ap"]:
            if gone:
                cat, ck = "changed", "none"
            else:
                word = m["word"]
                if found:
                    ck = change_kind(t, bl, cur)
                else:
                    anom(f"{t}: no pipeline state before the machine", label)
                    ck = "same" if word in ("ok", "nolink") or (t == "person" and m.get("auto_ok")) else "relinked"
                cat = "confirmed" if ck == "same" else "changed"
        elif m and not m.get("nop") and (m["row"] or m.get("prop") or m["word"] in ("unsure", "wrong", "unlocated_ok", "unlocatable", "other", "none", "not_a_place")):
            cat = "suggest"
        else:
            cat = "pipeline" if cur else "unlinked"

    sq = ""
    if cat == "suggest":
        p = (m or {}).get("prop")
        if t == "taxon":
            diff = any((fr.get("m") or {}).get("diff") and not fr["m"]["ap"] for fr in forms) or bool(p)
            agree = any((fr.get("m") or {}).get("d") == "same" and not fr["m"].get("diff") for fr in forms)
            sq = "change" if diff else ("agree" if agree else "unsure")
        elif m and m.get("ineff"):
            sq = "change"
        elif p and p.get("weak"):
            sq = "unsure"
        elif p and (p.get("none") or p.get("nolink")):
            sq = "change" if (cur is not None or p.get("none")) else "agree"
        elif p:
            sq = "agree" if same_link(t, p, cur) else "change"
            if sq == "change" and found and bl is not None and same_link(t, p, bl) and (m or {}).get("word") in ("ok", "link"):
                sq = "stale"                 # the machine confirmed the link of the pipeline run; this graph has another one
        else:
            sq = "unsure"
    if m and t != "taxon" and not m["ap"] and m.get("votes"):
        words = {v["v"] for v in m["votes"] if v["s"] in ("text", "gemini") and v["v"]}
        if len(words) > 1:
            m["split"] = 1                   # the two models disagree
    if t == "place" and cur and not cur.get("name"):
        srcs = [(m or {}).get("prop"), before, (BATCH[t].get(key, {}).get("graph") or {})]
        for x in srcs:
            if not x:
                continue
            if x.get("geonames_name") and str(x.get("geonames_id") or "") == str(cur.get("gn") or "-"):
                cur.update(name=x["geonames_name"], feature=cur.get("feature") or x.get("feature") or "", country=cur.get("country") or x.get("country") or "", admin1=cur.get("admin1") or x.get("admin1") or "")
                break
            if x.get("name") and x.get("lat") is not None and same_link(t, x, cur):
                cur.update(name=x["name"], feature=cur.get("feature") or x.get("feature") or "", osm=cur.get("osm") or x.get("osm") or "", country=cur.get("country") or x.get("country") or "")
                break
    who = who_of(t, G, ei, cur, rows) if not gone else {"by": "machine", "status": "removed"}
    lb = link_basis(t, e, cur, who, m, gone)
    if t == "taxon":
        w = collections.Counter()
        for fr in forms:
            fr["lb"] = form_basis(fr, lb)
            w[fr["lb"]] += fr["n"]
        if sum(w.values()):                       # the class that covers most of the species' mentions
            lb = max(BASIS, key=lambda b: (w[b], -BASIS.index(b)))
    rec = {"k": key, "l": label, "n": n, "q": cat, "cur": cur, "who": who, "lb": lb, "forms": forms}
    if CORPUS:
        nc_by = {s["forms"][fi][0]: nc_of(t, G.men_of_form[t].get(fi, [])) for fi in fis} if G is M and not gone else {}
        for fr in forms:
            fr["nc"] = nc_by.get(fr["f"]) or [fr["n"], 0, 0, 0]
        rec["nc"] = [sum(fr["nc"][c] for fr in forms) for c in range(4)]
    if sq:
        rec["sq"] = sq
    if gone:
        rec["gone"] = 1
    if cat == "changed":
        rec["ck"] = ck
        rec["before"] = before
        rec["bsrc"] = before_src
        if before_label and lc(before_label) != key:
            rec["blabel"] = before_label
        if t == "taxon":
            rec["nchg"] = sum(fr["n"] for fr in forms if fr.get("was"))
    elif before is not None and not same_link(t, before, cur) and before_src:
        # the pipeline graph differs although no machine decision is applied: a run-to-run difference
        # of the pipeline itself (LLM proposer, harmonisation); shown as information only
        rec["drift"] = {"link": before, "src": before_src}
        anom(f"{t}: pipeline graph differs without an applied machine row", label)
    if m:
        rec["m"] = m
    cands = candidates(t, G, ei, cur, before if cat == "changed" else None, m, fis)
    if cands:
        rec["cands"] = cands
    rec["ev"] = [mention_rec(G, t, mi) for mi in pick_mentions(G, t, fis, args.max_ev)]
    if t == "person":
        rec["yrs"] = year_hist(G, t, fis)
        b = BATCH[t].get(key, {})
        if b.get("roles"):
            rec["roles"] = b["roles"]
    if t == "place":
        rec["anc"] = anchors_of(G, fis, label, cur)
        rec["kind"] = e[6] or ""
        roles = collections.Counter(s["men"][mi][5] or "" for fi in fis for mi in G.men_of_form[t].get(fi, []))
        rec["roles"] = {k_: v for k_, v in roles.most_common(4) if k_}
    # merge candidates: this entity (variant) could be the same as another one (canonical)
    out_c = []
    for fr in forms:
        for r in CANDS_OUT[t].get(lc(fr["f"]), []):
            tgt = M.ent_of_name(t, r["canonical"])
            if tgt is None or (G is M and tgt == ei):
                continue
            te = M.sec[t]["ent"][tgt]
            out_c.append({"v": fr["f"], "to": te[0], "rule": r.get("rule") or "", "detail": (r.get("detail") or "")[:120], "n": M.n_of_ent[t].get(tgt, 0)})
    if out_c and not gone:
        out_c.sort(key=lambda c: (-c["n"], c["to"]))        # the most frequent candidate first (J takes the first)
        seen = set()
        rec["mg"] = [c for c in out_c if not (lc(c["to"]) in seen or seen.add(lc(c["to"])))][:9]
    return rec


for t in TYPES:
    s = M.sec[t]
    for ei in range(len(s["ent"])):
        rec = build_entity(t, M, ei)
        if rec is None:
            continue
        if rec["k"] in KEYS[t]:
            anom(f"{t}: two entities with the same casefolded label", rec["l"])
            n_ = 2
            while f"{rec['k']}#{n_}" in KEYS[t]:
                n_ += 1
            rec["k"] = f"{rec['k']}#{n_}"
        KEYS[t].add(rec["k"])
        ENTS[t].append(rec)

# names the machine removed from the graph (applied "none"): shown from the last graph that still has them
GONE = collections.Counter()
for r in ROWS:
    if r["decision"] != "none" or not applied(r):
        continue
    t = next(k for k, v in SECTION.items() if v == r["section"])
    name = r["name_form"]
    if lc(name) in M.fis_by_name[t]:
        continue                               # still in the graph: reported with its entity (not effective)
    USED_ROWS.add((r["section"], lc(name)))
    src = next((G for G in (B, A) if G is not None and t in G.sec and lc(name) in G.fis_by_name[t]), None)
    if src is None:
        GONE[(t, "not in any earlier graph")] += 1
        continue
    s = src.sec[t]
    fi = max(src.fis_by_name[t][lc(name)], key=lambda x: s["forms"][x][1])
    f = s["forms"][fi]
    ei = f[2]
    key = lc(name)
    if key in KEYS[t]:
        key += "#entfernt"
    bl = link_of(src, t, ei)
    rv = VFORM.get(lc(name)) if t == "taxon" else VERD[t].get(lc(name))
    v = rv[1] if rv else {}
    m = {"word": "none", "ap": 1, "c": round(num(r.get("confidence")), 2), "a": int(num(r.get("agreement"), 0)), "s": sources(r.get("sources")), "r": int(num(r.get("round"), 0)),
         "why": (v.get("reason") or r.get("reason") or v.get("note") or "")[:600], "note": (r.get("note") or "")[:300], "row": 1, "prop": {"none": 1},
         "votes": votes_for(t, lc(src.sec[t]["ent"][ei][0]) if t == "taxon" else lc(name), v)}
    if t == "taxon":
        fa = FANS.get(lc(name), {})
        m["votes"] = [{"s": "gemtext" if s_ == "gemini" else s_, "v": x.get("decision") or "", "c": round(num(x.get("confidence")), 2), "why": (x.get("reason") or "")[:300],
                       "x": x.get("sci") or x.get("species_de") or ""} for s_, x in fa.items()] or m["votes"]
    rec = {"k": key, "l": name, "n": f[1], "q": "changed", "ck": "none", "gone": 1, "cur": None, "who": {"by": "machine", "status": "removed"}, "lb": "mno",
           "before": bl, "bsrc": src.tag, "forms": [{"f": name, "n": f[1], "how": {"k": "label"}} | ({"lb": "mno"} if t == "taxon" else {})], "m": m,
           "ev": [mention_rec(src, t, mi) for mi in pick_mentions(src, t, [fi], args.max_ev)]}
    if CORPUS:                                  # not in the graph any more: no record of any corpus
        rec["nc"] = [f[1], 0, 0, 0]
        rec["forms"][0]["nc"] = [f[1], 0, 0, 0]
    if lc(s["ent"][ei][0]) != lc(name):
        rec["blabel"] = s["ent"][ei][0]
    if bl:
        rec["cands"] = [dict(bl, o="b")]
    if t == "person":
        rec["yrs"] = year_hist(src, t, [fi])
    if t == "place":
        rec["anc"] = anchors_of(src, [fi], name, bl)
    KEYS[t].add(key)
    ENTS[t].append(rec)
    GONE[(t, src.tag)] += 1
log("removed by the machine (applied none):", dict(GONE))

# incoming merge candidates (who could belong here) from the outgoing ones
for t in TYPES:
    by_key = {e["k"]: e for e in ENTS[t]}
    for e in ENTS[t]:
        for c in e.get("mg", []):
            tgt = by_key.get(lc(c["to"]))
            if tgt is not None and tgt is not e:
                tgt.setdefault("mgin", []).append({"v": c["v"], "from": e["l"], "rule": c["rule"], "n": e["n"]})
    for e in ENTS[t]:
        if "mgin" in e:
            e["mgin"] = sorted(e["mgin"], key=lambda c: -c["n"])[:12]
    ENTS[t].sort(key=lambda e: (-e["n"], e["l"]))

# machine rows that match no name of the graph
unused = [r for r in ROWS if (r["section"], lc(r["name_form"])) not in USED_ROWS]
ANOM["machine rows without a name in the graph"] = len(unused)
ANOM["... of them applied"] = sum(1 for r in unused if applied(r))
UNUSED_BY = collections.Counter((r["section"], r["decision"], "applied" if applied(r) else "suggestion") for r in unused)

# ---------------------------------------------------------------- output
def compact(x):
    """Drop empty strings, None, empty lists and dicts inside nested records (the page reads them as falsy)."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            v = compact(v)
            if v is None or v == "" or v == [] or v == {}:
                continue
            out[k] = v
        return out
    if isinstance(x, list):
        return [compact(v) for v in x]
    return x


def js_fold(s):
    """The page's key function (toLowerCase + ß -> ss); must agree with str.casefold for every name."""
    return s.lower().replace("ß", "ss").replace("ſ", "s")


for t in TYPES:
    for e in ENTS[t]:
        for name in [e["l"]] + [f["f"] for f in e["forms"]]:
            if js_fold(name) != lc(name):
                anom("name whose casefold differs from the page's key function", name)
        cur, ev = e.get("cur"), e.get("ev")
        keep = {k: compact(v) for k, v in e.items() if k not in ("cur", "ev")}
        for k in [k for k, v in keep.items() if v in ("", None, [], {}) and k not in ("n",)]:
            del keep[k]
        e.clear()
        e.update(keep)
        e["cur"] = compact(cur) if cur else None
        e["ev"] = [{k: v for k, v in m.items() if v not in ("", None) or k in ("d", "tx")} for m in (ev or [])]
for t in TYPES:
    for e in ENTS[t]:
        STATS[t][e["q"]] += 1
        STATS[t]["n:" + e["q"]] += e["n"]
        if e.get("mg"):
            STATS[t]["merge"] += 1
            STATS[t]["n:merge"] += e["n"]
        if e["q"] == "changed":
            STATS[t]["ck:" + e.get("ck", "")] += 1
        if e["q"] == "suggest":
            STATS[t]["sq:" + e.get("sq", "")] += 1
        STATS[t]["all"] += 1
        STATS[t]["n:all"] += e["n"]
stats = {t: dict(sorted(c.items())) for t, c in STATS.items()}
# link basis per type: entities by their class, mentions by class (species: per written name)
LB = {}
for t in TYPES:
    ent_c, men_c = collections.Counter(), collections.Counter()
    for e in ENTS[t]:
        ent_c[e["lb"]] += 1
        for f in e["forms"]:
            men_c[f.get("lb", e["lb"])] += f["n"]
    LB[t] = {"ent": {b: ent_c[b] for b in BASIS}, "men": {b: men_c[b] for b in BASIS}}
# machine rows on which >= 2 sources agreed but the confidence stayed below the threshold (not applied)
BELOW = {}
for t in TYPES:
    rs = [r for r in ROWS if r["section"] == SECTION[t] and int(num(r.get("agreement"), 0)) >= args.min_agreement and num(r.get("confidence")) < args.min_confidence]
    conf = collections.Counter(round(num(r.get("confidence")), 2) for r in rs)
    top = conf.most_common(1)[0] if conf else (None, 0)
    BELOW[t] = {"rows": len(rs), "conf": top[0], "nconf": top[1]}       # the most frequent confidence among them
if CORPUS:
    CORPUS["ent"] = {t: [sum(1 for e in ENTS[t] if e["nc"][c] > 0) for c in range(4)] for t in TYPES}
    CORPUS["men"] = {t: [sum(e["nc"][c] for e in ENTS[t]) for c in range(4)] for t in TYPES}
TAXA = [[e[0], e[1], str(e[2]), e[3]] for e in M.sec["taxon"]["ent"] if e[2]]
payload = {"app": "laubmann-link-check", "v": 1, "built": args.built or date.today().isoformat(), "export": M.export, "base_export": B.export if B else "",
           "r1_export": A.export if A else "", "thresholds": {"conf": args.min_confidence, "agree": args.min_agreement},
           "rounds": [{"n": R["n"], "label": R["label"], "model": R["model"], "built": R["built"], "dir": Path(R["dir"]).name} for R in ROUNDS],
           "PAGES": PAGES, "EUNIS": M.P.get("eunis", []), "TAXA": TAXA, "ents": ENTS, "stats": stats,
           "anomalies": dict(ANOM), "anomaly_examples": dict(ANOM_EX), "unused_rows": {"|".join(k): v for k, v in sorted(UNUSED_BY.items())},
           "basis": LB, "below": BELOW}
if CORPUS:
    payload["corpus"] = CORPUS
raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
Path(str(out) + ".json").write_bytes(raw)
gz = gzip.compress(raw, 9, mtime=0)
Path(str(out) + ".b64").write_text(base64.b64encode(gz).decode("ascii"), encoding="ascii")
print(json.dumps({"stats": stats, "basis": LB, "below": BELOW, "corpus": CORPUS, "anomalies": dict(ANOM), "anomaly_examples": dict(ANOM_EX), "unused_rows": payload["unused_rows"], "pages": len(PAGES)}, ensure_ascii=False, indent=1))
print(f"raw {len(raw) / 1e6:.1f} MB, gz+b64 {len(gz) * 4 / 3 / 1e6:.1f} MB -> {out}.json / .b64")
