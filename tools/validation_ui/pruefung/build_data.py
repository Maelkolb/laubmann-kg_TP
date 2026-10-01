#!/usr/bin/env python3
"""Data of the page "Laubmann-Validierung": human sign-off of the machine review
(rounds r1, r2, r3 ...) plus the name-level review of everything the machine did
not see, habitats, QA flags and the transcript corrections of the visual reading.

    python build_data.py --payload payload.b64 \
        --machine <r1 dir>@<graph of r1> <r2 dir>@<graph of r2> <r3 dir> \
        --arbeit <arbeit> <arbeit2> <arbeit3> --review <export>/review --dwca <export>/dwca \
        --legacy-pruefung Laubmann_Pruefung.html --out data

--payload        payload of tools/validation_ui/build_payload.py (the graph under review; .b64, .json, or
                 an assembled Laubmann_Abgleich.html)
--machine        one folder per machine round, in order (r1 r2 r3); a later round's verdict on the same key
                 supersedes an earlier one. ``DIR@GRAPH``: the round was run on another graph (payload file);
                 its verdicts are read against that graph (the state "before" = that graph) and shown with the
                 evidence of --payload. Files used when present: machine_review.json, identities_machine.csv,
                 value_corrections_machine.csv, text_corrections*.csv, graph_checks*[_entries|_missing|
                 _misreadings].csv, place_readings.json, taxa_a_readings.json, transcript_checks.csv.
--arbeit         agent work folders (persons/batches, places/batches, entries/dossier_*/dossier.json)
--review         <export>/review (transcript_corrections.csv, qa_flags.csv)
--dwca           <export>/dwca (occurrence.txt: records per entry)
--legacy-pruefung  Laubmann_Pruefung.html of 2026-09-30 (or its decoded data.json): translates progress files
                 of that page (decisions keyed by its item numbers) to the stable keys of this page

Every decision of the page is keyed by a stable key (type:written name / entry_uid|name|occurrence /
entry_uid|old|new ...), never by a graph index, so it survives a rebuild on another export.
Output: <out>.json (readable) and <out>.b64 (gzip+base64, embedded by assemble.py).
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import difflib
import gzip
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--payload", required=True)
ap.add_argument("--machine", nargs="*", default=[], help="machine round folders in order, DIR or DIR@GRAPH")
ap.add_argument("--arbeit", nargs="*", default=[], help="agent work folders (batches, dossiers)")
ap.add_argument("--review", default=None, help="<export>/review")
ap.add_argument("--dwca", default=None, help="<export>/dwca")
ap.add_argument("--drive", default=str(HERE.parent / "drive_pages.json"))
ap.add_argument("--legacy-pruefung", default=None, help="Laubmann_Pruefung.html (2026-09-30) or its data.json")
ap.add_argument("--out", default=str(HERE / "data"))
ap.add_argument("--built", default=None)
ap.add_argument("--sample-per-stratum", type=int, default=40)
ap.add_argument("--tc-sample-per-stratum", type=int, default=25)
ap.add_argument("--seed", type=int, default=20260930)
ap.add_argument("--max-ev", type=int, default=8, help="evidence passages per machine item")
ap.add_argument("--max-ev-unchecked", type=int, default=4, help="evidence passages per unchecked entity / habitat")
args = ap.parse_args()
MIN_CONF, MIN_AGREE = 0.9, 2                  # review.machine thresholds of configs/full_llm.yaml
TYPES = ("taxon", "person", "place", "habitat")
SECTION = {"taxon": "taxa", "person": "persons", "place": "places", "habitat": "habitats"}
lc = str.lower
TAG = re.compile(r"<[^>]+>")


def log(*a):
    print(*a, file=sys.stderr)


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


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


def hkey(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- graphs
class Graph:
    """Indexes of one payload (build_payload.py)."""

    def __init__(self, P, name):
        self.P, self.name = P, name
        self.E, self.PG = P["E"], P["PG"]
        self.sec = {t: P[t] for t in TYPES if t in P}
        self.uid2e = {e[1]: i for i, e in enumerate(self.E)}
        self.forms_of_ent, self.men_of_form, self.n_of_ent, self.fis_by_name, self.mkey, self.mkey2mi = {}, {}, {}, {}, {}, {}
        self.men_of_entry = collections.defaultdict(list)
        for t, s in self.sec.items():
            foe = collections.defaultdict(list)
            for fi, f in enumerate(s["forms"]):
                foe[f[2]].append(fi)
            mof = collections.defaultdict(list)
            for mi, m in enumerate(s["men"]):
                mof[m[0]].append(mi)
            byn = collections.defaultdict(list)
            for fi, f in enumerate(s["forms"]):
                byn[lc(f[0])].append(fi)
            occ, keys = collections.Counter(), []
            for mi, m in enumerate(s["men"]):
                k = self.E[m[1]][1] + "|" + lc(s["forms"][m[0]][0])
                keys.append(f"{k}|{occ[k]}")
                occ[k] += 1
                if t != "habitat":
                    self.men_of_entry[m[1]].append((t, mi))
            self.forms_of_ent[t], self.men_of_form[t], self.fis_by_name[t] = foe, mof, byn
            self.n_of_ent[t] = {e: sum(s["forms"][fi][1] for fi in fis) for e, fis in foe.items()}
            self.mkey[t] = keys
            self.mkey2mi[t] = {k: i for i, k in enumerate(keys)}
        self.ent_by_label = {t: {} for t in self.sec}
        for t, s in self.sec.items():
            for i, e in enumerate(s["ent"]):
                self.ent_by_label[t].setdefault(lc(e[0]), i)

    def names_of(self, t, ei):
        s = self.sec[t]
        return [[s["forms"][fi][0], s["forms"][fi][1]] for fi in sorted(self.forms_of_ent[t].get(ei, []), key=lambda x: -s["forms"][x][1])]


P = load_payload(args.payload)
C = Graph(P, str(args.payload))
E, PG = C.E, C.PG
TX, PS, PL, HB = (C.sec.get(t, {"ent": [], "forms": [], "men": []}) for t in TYPES)
SEC = C.sec
DRIVE = json.loads(Path(args.drive).read_text(encoding="utf-8")) if Path(args.drive).exists() else {}
for _m in HB["men"]:                 # build_payload does not locate habitat mentions in the text
    if _m[2] < 0:
        _w = HB["forms"][_m[0]][0]
        _i = lc(E[_m[1]][7]).find(lc(_w))
        if _i >= 0:
            _m[2], _m[3] = _i, _i + len(_w)
log("graph", P.get("export"), "entries", len(E), {t: (len(s["ent"]), len(s["forms"]), len(s["men"])) for t, s in SEC.items()})

_graphs = {}


def graph_at(path):
    if not path:
        return C
    p = str(Path(path).resolve())
    if p == str(Path(args.payload).resolve()):
        return C
    if p not in _graphs:
        _graphs[p] = Graph(load_payload(p), p)
        log("round graph", _graphs[p].P.get("export"), p)
    return _graphs[p]


# ---------------------------------------------------------------- machine rounds
class Round:
    def __init__(self, n, spec):
        d, _, g = spec.partition("@") if "@" in spec else (spec, "", "")
        self.n, self.dir = n, Path(d)
        self.G = graph_at(g) if g else C
        self.ok = self.dir.is_dir()
        if not self.ok:
            log(f"round {n}: folder {d} missing — skipped")
        f = lambda name: self.dir / name   # noqa: E731
        self.mr = json.loads(f("machine_review.json").read_text(encoding="utf-8")) if self.ok and f("machine_review.json").exists() else None
        self.rows = read_csv(f("identities_machine.csv")) if self.ok else []
        self.vcm = read_csv(f("value_corrections_machine.csv")) if self.ok else []
        self.tcm = []
        self.checks = {"entries": [], "obs": [], "missing": [], "misread": []}
        self.place_readings, self.taxa_a, self.tchecks = {}, {}, []
        if self.ok:
            for p in sorted(self.dir.glob("text_corrections*.csv")):
                self.tcm += read_csv(p)
            for p in sorted(self.dir.glob("graph_checks*_entries.csv")):
                pre = p.name[: -len("_entries.csv")]
                self.checks["entries"] += read_csv(p)
                self.checks["obs"] += read_csv(self.dir / f"{pre}.csv")
                self.checks["missing"] += read_csv(self.dir / f"{pre}_missing.csv")
                self.checks["misread"] += read_csv(self.dir / f"{pre}_misreadings.csv")
            if f("place_readings.json").exists():
                self.place_readings = json.loads(f("place_readings.json").read_text(encoding="utf-8"))
            if f("taxa_a_readings.json").exists():
                self.taxa_a = json.loads(f("taxa_a_readings.json").read_text(encoding="utf-8"))
            self.tchecks = read_csv(f("transcript_checks.csv"))
        stamps = [r.get("reviewed_at") or "" for r in self.rows + self.vcm + self.tcm if r.get("reviewed_at")]
        self.model = (self.mr or {}).get("model") or next((r.get("reviewed_by", "").replace("machine:", "") for r in self.rows + self.tcm if r.get("reviewed_by")), "")
        if not self.model:
            for v in list(self.place_readings.values())[:1] + list(self.taxa_a.values())[:1]:
                v = v[0] if isinstance(v, list) and v else v
                self.model = (v or {}).get("model", "") if isinstance(v, dict) else ""
        self.built = (self.mr or {}).get("built") or (max(stamps) if stamps else "")
        self.info = {"n": n, "model": self.model, "built": self.built, "graph": self.G.P.get("export") or "", "same": self.G is C,
                     "files": sorted(x.name for x in self.dir.iterdir()) if self.ok else [], "dir": str(self.dir)}
        if self.ok:
            log(f"round {n}: {d} graph={self.info['graph']} mr={'y' if self.mr else 'n'} rows={len(self.rows)} vcm={len(self.vcm)} tcm={len(self.tcm)} "
                f"entries={len(self.checks['entries'])} place_readings={len(self.place_readings)} taxa_a={len(self.taxa_a)} tchecks={len(self.tchecks)}")


ROUNDS = [R for R in (Round(i + 1, s) for i, s in enumerate(args.machine)) if R.ok]   # numbering stays positional (r3 = third folder)

# identities rows: per (section, name) the rows of the latest round that has any
ALLROWS, ROWIDX = [], {}
for R in ROUNDS:
    mine = collections.defaultdict(list)
    for r in R.rows:
        r = dict(r)
        r["_rnd"] = R.n
        mine[(r["section"], lc(r["name_form"]))].append(len(ALLROWS))
        ALLROWS.append(r)
    ROWIDX.update(mine)


def rows_for(t, name):
    return ROWIDX.get((SECTION[t], lc(name)), [])


def row_auto(r):
    return num(r.get("confidence")) >= MIN_CONF and int(num(r.get("agreement"), 0)) >= MIN_AGREE


def sources(s):
    out = s if isinstance(s, list) else [x for x in re.split(r"[+,\s]+", s or "") if x]
    seen = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


# agent work folders: batches by label, dossiers by entry uid (later folders win)
PBATCH, LBATCH, DOSS = {}, {}, {}
for a in args.arbeit:
    A = Path(a)
    if not A.is_dir():
        log("arbeit folder missing:", a)
        continue
    for kind, store in (("persons", PBATCH), ("places", LBATCH)):
        for f in sorted((A / kind / "batches").glob("batch_*.json")):
            for rec in json.loads(f.read_text(encoding="utf-8")):
                store[lc(rec.get("label") or "")] = rec
    for d in sorted((A / "entries").glob("dossier_*/dossier.json")):
        j = json.loads(d.read_text(encoding="utf-8"))
        DOSS[j["entry"]["uid"]] = j
log("batches: persons", len(PBATCH), "places", len(LBATCH), "dossiers", len(DOSS))


# ---------------------------------------------------------------- machine verdicts per round -> proto items (keyed)
def map_verdicts(G, mr):
    """machine_review.json -> {type: {graph index: verdict}} for graph G (by label/name, index as check)."""
    out = {"taxon": {}, "form": {}, "person": {}, "place": {}, "habitat": {}}
    TXg = G.sec["taxon"]
    tx_idx = {(e[0], e[2]): i for i, e in enumerate(TXg["ent"])}
    for k, v in (mr.get("taxon", {}).get("ent") or {}).items():
        i = tx_idx.get((v.get("label"), v.get("cur_key")))
        if i is None and k.isdigit() and int(k) < len(TXg["ent"]) and TXg["ent"][int(k)][0] == v.get("label"):
            i = int(k)
        if i is None:
            i = G.ent_by_label["taxon"].get(lc(v.get("label") or ""))
        if i is not None:
            out["taxon"][i] = v
    tf_idx = {(f[0], TXg["ent"][f[2]][0]): i for i, f in enumerate(TXg["forms"])}
    for k, v in (mr.get("taxon", {}).get("form") or {}).items():
        i = tf_idx.get((v.get("name"), v.get("ent_label")))
        if i is None and k.isdigit() and int(k) < len(TXg["forms"]) and TXg["forms"][int(k)][0] == v.get("name"):
            i = int(k)
        if i is None:
            fis = G.fis_by_name["taxon"].get(lc(v.get("name") or ""), [])
            i = fis[0] if fis else None
        if i is not None:
            out["form"][i] = v
    for sec in ("person", "place", "habitat"):
        S_ = G.sec.get(sec)
        if not S_:
            continue
        for k, v in (mr.get(sec, {}).get("ent") or {}).items():
            i = G.ent_by_label[sec].get(lc(v.get("label") or ""))
            if i is None and k.isdigit() and int(k) < len(S_["ent"]) and S_["ent"][int(k)][0] == v.get("label"):
                i = int(k)
            if i is not None:
                out[sec][i] = v
    return out


def is_lift(cur_sci, new_sci):
    return bool(cur_sci and new_sci and cur_sci != new_sci and cur_sci.startswith(new_sci + " "))


PROTO = []          # proto items of all rounds, in round order


def text_gemini(src):
    """persons/places/habitats: "gemini" is Gemini's text second opinion (gemini_verify.py), not a scan reading"""
    return ["gemtext" if s == "gemini" else s for s in src]


def form_badge(v):
    return {"d": v["decision"], "c": round(num(v.get("confidence")), 2), "a": int(num(v.get("agreement"), 0)),
            "s": sources(v.get("sources")), "n": v.get("note") or "", "key": v.get("key"), "sci": v.get("sci"),
            "de": v.get("species_de"), "rank": v.get("rank"), "changed": bool(v.get("changed"))}


def taxon_protos(R, mv):
    G = R.G
    TXg = G.sec["taxon"]
    badge_of_fi = {fi: form_badge(v) for fi, v in mv["form"].items()}
    for ei, v in mv["taxon"].items():
        ent = TXg["ent"][ei]
        cur_key, cur_sci, link = ent[2], ent[1], v["link"]
        fis = G.forms_of_ent["taxon"].get(ei, [])
        badges = {fi: badge_of_fi[fi] for fi in fis if fi in badge_of_fi}
        if link == "ok":
            lifted = [b for b in badges.values() if b["d"] == "same" and b.get("key") and b["key"] != cur_key and is_lift(cur_sci, b.get("sci"))]
            cat, new = ("lift", {"key": lifted[0]["key"], "sci": lifted[0]["sci"], "rank": lifted[0]["rank"], "de": lifted[0]["de"]}) if lifted else ("ok", None)
        elif link == "none":
            cat, new = "none", None
        elif link == "unsure":
            cat, new = "unsure", None
        else:
            nk = v.get("new_key")
            prop = {"key": nk, "sci": v.get("new_sci"), "rank": v.get("new_rank"), "de": v.get("species_de")}
            if not nk:
                cat, new = "unsure", None
            elif nk == cur_key:
                cat, new = "ok", None
            elif not cur_key:
                cat, new = "newlink", prop
            elif is_lift(cur_sci, v.get("new_sci")):
                cat, new = "lift", prop
            else:
                cat, new = "relink", prop
        target_key = (new or {}).get("key") or cur_key
        moved, doubt = [], []
        for fi in fis:
            b = badges.get(fi)
            if not b:
                continue
            if b["d"] == "same" and b.get("key") and target_key and b["key"] != target_key and b["changed"] \
                    and (b.get("sci") or "") != (cur_sci or "") and not is_lift(cur_sci, b.get("sci")) \
                    and not (new and ((b.get("sci") or "") == (new.get("sci") or "") or is_lift(new.get("sci"), b.get("sci")))):
                moved.append(fi)
            elif b["d"] == "none" and cat != "none":
                moved.append(fi)
            elif b["d"] == "unsure":
                doubt.append(fi)
        name = lambda fi: TXg["forms"][fi][0]   # noqa: E731
        rows = [ri for fi in fis if fi not in moved for ri in rows_for("taxon", name(fi))]
        auto = any(row_auto(ALLROWS[ri]) for ri in rows if ALLROWS[ri]["decision"] != "same" or ALLROWS[ri].get("authority") != ("gbif:" + cur_key if cur_key else ""))
        q = {"ok": "confirm", "lift": "change", "newlink": "change", "relink": "change", "none": "change", "unsure": "open"}[cat]
        srcs = {"text"}
        for b in badges.values():
            srcs.update(b["s"])
        base = {"t": "taxon", "key": "taxon:" + lc(ent[0]), "q": q, "k": cat, "label": ent[0], "sci": cur_sci, "rnd": R.n,
                "conf": round(num(v.get("confidence")), 2), "reason": v.get("reason") or "", "auto": int(auto),
                "names": [[name(fi), TXg["forms"][fi][1]] for fi in fis], "bn": {lc(name(fi)): b for fi, b in badges.items()},
                "cur": {"key": cur_key, "sci": cur_sci, "rank": ent[3], "family": ent[6], "de": ent[9]} if cur_key else None,
                "prop": new, "rows": rows, "doubt": [lc(name(fi)) for fi in doubt], "moved": [lc(name(fi)) for fi in moved],
                "llm": ent[5] if not cur_key else "", "G": G,
                "src": [s for s in ["text", "scan", "gemini", "opus", "gbif", "incoming"] if s in srcs],
                "agree": max([b["a"] for b in badges.values()] + [1])}
        if cat == "ok" and doubt:
            PROTO.append(dict(base, q="open", k="name-unsure", focus=[lc(name(fi)) for fi in doubt]))
        else:
            PROTO.append(base)
        for fi in moved:
            b = badges[fi]
            f = TXg["forms"][fi]
            PROTO.append({"t": "form", "key": "form:" + lc(f[0]), "q": "change", "k": "moved" if b["d"] == "same" else "name-none", "rnd": R.n,
                          "label": f[0], "sci": cur_sci, "cls": f[3], "conf": b["c"], "agree": b["a"], "src": b["s"] or ["text"],
                          "reason": b["n"], "auto": int(any(row_auto(ALLROWS[ri]) for ri in rows_for("taxon", f[0]))),
                          "cur": {"label": ent[0], "key": cur_key, "sci": cur_sci},
                          "prop": {"key": b.get("key"), "sci": b.get("sci"), "de": b.get("de"), "rank": b.get("rank")} if b["d"] == "same" else None,
                          "rows": rows_for("taxon", f[0]), "names": [[f[0], f[1]]], "bn": {lc(f[0]): b}, "G": G})


def person_protos(R, mv):
    G = R.G
    PSg = G.sec["person"]
    pm = G.P.get("pm", {})
    for ei, v in mv["person"].items():
        ent = PSg["ent"][ei]
        had_qid, had_gnd = ent[1], ent[2]
        d, wd, gnd = v["decision"], v.get("wikidata"), v.get("gnd")
        wd = wd if wd and str(wd).startswith("Q") else None
        gnd = gnd if gnd and gnd not in ("none", "unclear") else None
        if d == "link":
            cat = "link-confirm" if had_qid and wd == had_qid else ("link-new" if not had_qid else "link-change")
        elif d == "nolink":
            cat = "nolink-remove" if had_qid else "nolink-confirm"
        else:
            cat = "unsure-remove" if had_qid and v.get("auto_link_ok") is False else ("unsure-haslink" if had_qid else "unsure")
        q = {"link-confirm": "confirm", "nolink-confirm": "confirm", "link-new": "change", "link-change": "change",
             "nolink-remove": "change", "unsure-remove": "change", "unsure-haslink": "open", "unsure": "open"}[cat]
        b = PBATCH.get(lc(ent[0]), {})
        cands = [{"qid": c["qid"], "label": c.get("label") or "", "desc": c.get("description") or "", "born": c.get("born") or "",
                  "died": c.get("died") or "", "gnd": c.get("gnd") or "", "human": c.get("human")} for c in b.get("wikidata_candidates", [])]
        gcands = []
        for c in b.get("gnd_candidates", []):
            gcands.append({"gnd": c.get("gnd") or c.get("id") or "", "name": c.get("name") or "", "born": c.get("born") or "",
                           "died": c.get("died") or "", "occ": ", ".join(c.get("occupation") or []) if isinstance(c.get("occupation"), list) else (c.get("occupation") or ""),
                           "places": ", ".join(c.get("places") or []) if isinstance(c.get("places"), list) else (c.get("places") or ""),
                           "wd": c.get("wikidata") or ""})
        names = G.names_of("person", ei)
        rows = rows_for("person", ent[0]) + [ri for n_, _ in names for ri in rows_for("person", n_) if lc(n_) != lc(ent[0])]
        it = {"t": "person", "key": "person:" + lc(ent[0]), "q": q, "k": cat, "label": ent[0], "rnd": R.n, "conf": round(num(v.get("confidence")), 2),
              "agree": int(num(v.get("agreement"), 1)), "src": text_gemini(sources(v.get("sources"))) or ["text"], "reason": v.get("reason") or "",
              "note": v.get("note") or "", "auto": int(any(row_auto(ALLROWS[ri]) for ri in rows)) if q == "change" else 0,
              "cur": {"qid": had_qid, "gnd": had_gnd}, "prop": {"qid": wd, "gnd": gnd} if d == "link" else ({"qid": None, "gnd": None} if d == "nolink" else None),
              "cands": cands, "gcands": gcands, "years": b.get("years") or "", "roles": b.get("roles") or {}, "names": names,
              "opus": pm.get(str(ei)), "rows": rows, "G": G}
        if cat == "unsure-remove":
            it["prop"] = {"qid": None, "gnd": None}
        PROTO.append(it)


COORD = re.compile(r"(\d{1,2}[.,]\d+)\s*°?\s*N[,;]?\s*(\d{1,2}[.,]\d+)\s*°?\s*[EO]")


def place_protos(R, mv):
    G = R.G
    PLg = G.sec["place"]
    for ei, v in mv["place"].items():
        ent = PLg["ent"][ei]
        vd, cand, had = v["verdict"], v.get("candidate"), ent[1] is not None
        if vd == "ok":
            cat, q = "ok", "confirm"
        elif vd == "wrong":
            cat, q = ("wrong", "change") if cand else ("wrong-nocand", "open")
        elif vd == "unlocated_ok":
            cat, q = ("unlocated_ok", "change") if cand else ("unlocated-nocand", "open")
        elif vd == "not_a_place":
            cat, q = "not_a_place", "change"
        elif vd == "unlocatable":
            cat, q = "unlocatable", "open"
        else:
            cat, q = "unsure", "open"
        b = LBATCH.get(lc(ent[0]), {})
        hint = v.get("hint") or ""
        hc = COORD.search(hint)
        names = G.names_of("place", ei)
        rows = rows_for("place", ent[0]) + [ri for n_, _ in names for ri in rows_for("place", n_) if lc(n_) != lc(ent[0])]
        PROTO.append({"t": "place", "key": "place:" + lc(ent[0]), "q": q, "k": cat, "label": ent[0], "rnd": R.n, "conf": round(num(v.get("confidence")), 2),
                      "agree": 1 + int(any(s != "text" for s in (v.get("sources") or []))), "src": text_gemini(sources(v.get("sources"))) or ["text"],
                      "reason": v.get("reason") or "", "hint": hint, "hint_ll": [float(hc.group(1).replace(",", ".")), float(hc.group(2).replace(",", "."))] if hc else None,
                      "unc": v.get("uncertainty_m"), "auto": int(any(row_auto(ALLROWS[ri]) for ri in rows)) if q == "change" else 0,
                      "cur": {"lat": ent[1], "lon": ent[2], "unc": ent[3], "gn": ent[4], "qid": ent[5], "kind": ent[6], "src": ent[7]} if had else {"kind": ent[6]},
                      "prop": ({"lat": cand["lat"], "lon": cand["lon"], "name": cand.get("display_name") or cand.get("name"), "type": cand.get("type"),
                                "qid": cand.get("wikidata") or "", "osm": cand.get("osm") or "", "km": cand.get("km_from_main_anchor")} if cand and cat in ("wrong", "unlocated_ok") else
                               ({"none": True} if cat == "not_a_place" else None)),
                      "cands": [{"id": c["id"], "name": c.get("display_name") or c.get("name"), "type": c.get("type"), "lat": c["lat"], "lon": c["lon"],
                                 "km": c.get("km_from_main_anchor"), "qid": c.get("wikidata") or "", "osm": c.get("osm") or ""} for c in b.get("candidates", [])],
                      "anchors": [{"place": a["place"], "n": a["entries"], "lat": a["lat"], "lon": a["lon"], "km": a.get("km_from_graph_point")} for a in b.get("anchors", [])[:4]],
                      "roles": b.get("roles") or {}, "graph": b.get("graph") or None, "names": names, "rows": rows, "G": G})


def habitat_protos(R, mv):
    G = R.G
    H = G.sec.get("habitat")
    if not H:
        return
    eun = {e[0]: e for e in (G.P.get("eunis") or P.get("eunis") or [])}
    for ei, v in mv["habitat"].items():
        ent = H["ent"][ei]
        cur_code, cur_match = ent[1], ent[2]
        vd, code = (v.get("verdict") or "unsure").lower(), (v.get("code") or "").strip()
        if vd == "ok" or (vd == "other" and code and code == cur_code):
            cat, q, prop = "h-ok", "confirm", None
        elif vd == "other" and code:
            cat, q, prop = ("h-other" if cur_code else "h-new"), "change", {"code": code, "match": (v.get("match") or "close").lower(), "label": (eun.get(code) or ["", ""])[1]}
        elif vd == "none":
            cat, q, prop = "h-none", "change", {"none": True}
        else:
            cat, q, prop = "h-unsure", "open", None
        names = G.names_of("habitat", ei)
        rows = rows_for("habitat", ent[0]) + [ri for n_, _ in names for ri in rows_for("habitat", n_) if lc(n_) != lc(ent[0])]
        PROTO.append({"t": "habitat", "key": "habitat:" + lc(ent[0]), "q": q, "k": cat, "label": ent[0], "rnd": R.n, "conf": round(num(v.get("confidence")), 2),
                      "agree": int(num(v.get("agreement"), 1)), "src": text_gemini(sources(v.get("sources"))) or ["text"], "reason": v.get("reason") or "",
                      "auto": int(any(row_auto(ALLROWS[ri]) for ri in rows)) if q == "change" else 0,
                      "cur": {"code": cur_code, "match": cur_match, "label": (eun.get(cur_code) or ["", ""])[1]} if cur_code else None, "prop": prop,
                      "sug": None, "names": names, "rows": rows, "G": G})


def mention_protos(R):
    G = R.G
    for r in R.vcm:
        key = f"men:{r['entry_uid']}|{lc(r['old_value'])}|{r.get('occurrence') or 0}"
        PROTO.append({"t": "mention", "key": key, "q": "change", "k": "value-" + r["action"], "label": r["old_value"], "n": 1, "rnd": R.n,
                      "conf": round(num(r.get("confidence")), 2), "agree": 1, "src": sources(r.get("sources")) or ["scan"], "reason": r.get("reason") or "",
                      "note": r.get("note") or "", "auto": int(num(r.get("confidence")) >= MIN_CONF), "uid": r["entry_uid"],
                      "mkey": f"{r['entry_uid']}|{lc(r['old_value'])}|{r.get('occurrence') or 0}",
                      "cur": {"value": r["old_value"]}, "prop": {"action": r["action"], "value": r.get("new_value") or "", "sci": r.get("scientific_name") or "", "key": r.get("gbif_key") or ""},
                      "vrow": {k: v for k, v in r.items() if k not in ("confidence", "sources")}})
    stats = collections.Counter()
    for mi_s, r in R.taxa_a.items():
        stats["n"] += 1
        if not r.get("legible"):
            stats["illegible"] += 1
            continue
        stats["legible"] += 1
        if r.get("agrees") is True:
            stats["agree"] += 1
            continue
        stats["disagree"] += 1
        mi = int(mi_s)
        TXg = G.sec["taxon"]
        if mi >= len(TXg["men"]):
            continue
        m = TXg["men"][mi]
        f = TXg["forms"][m[0]]
        uid, eid = G.E[m[1]][1], G.E[m[1]][0]
        occ = int(G.mkey["taxon"][mi].rsplit("|", 1)[1])
        isbird = (r.get("kind") or "") == "bird"
        PROTO.append({"t": "mention", "key": f"men:{uid}|{lc(f[0])}|{occ}", "q": "change", "k": "value-replace" if isbird else "value-drop", "label": f[0], "n": 1, "rnd": R.n,
                      "conf": round(num(r.get("conf")), 2), "agree": 1, "src": ["scan"], "uid": uid, "mkey": f"{uid}|{lc(f[0])}|{occ}",
                      "reason": "Bildlesung (Klasse-A-Stichprobe): „" + (r.get("reading") or "") + "“ → " + ((r.get("species_de") or r.get("sci") or "") if isbird else (r.get("kind") or "kein Vogel")) + ". " + (r.get("note") or ""),
                      "note": "", "auto": 0, "cur": {"value": f[0]},
                      "prop": {"action": "replace" if isbird else "drop", "value": r.get("species_de") or r.get("sci") or "", "sci": r.get("sci") or "", "key": ""},
                      "vrow": {"kind": "taxon", "entry_uid": uid, "entry_id": eid, "old_value": f[0], "occurrence": occ, "action": "replace" if isbird else "drop",
                               "new_value": (r.get("species_de") or r.get("sci") or "") if isbird else "", "scientific_name": (r.get("sci") or "") if isbird else "", "gbif_key": "",
                               "is_bird": "y" if isbird else "n", "reason": r.get("note") or "", "note": "Lesung: " + (r.get("reading") or ""),
                               "reviewed_by": "machine:" + (r.get("model") or R.model or "claude"), "reviewed_at": R.built}})
    return stats


def entry_protos(R):
    checks, missing, misread = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for r in R.checks["obs"]:
        checks[r["entry_uid"]].append(r)
    for r in R.checks["missing"]:
        missing[r["entry_uid"]].append(r)
    for r in R.checks["misread"]:
        misread[r["entry_uid"]].append(r)
    for r in R.checks["entries"]:
        uid = r["entry_uid"]
        g = DOSS.get(uid, {}).get("graph", {})
        obs = []
        for c in checks[uid]:
            corr = None
            if c.get("correction"):
                try:
                    corr = json.loads(c["correction"])
                except ValueError:
                    corr = {"other": c["correction"]}
            obs.append({"i": int(num(c["obs_index"])), "occ": int(num(c.get("occurrence"), 0)), "written": c["written"], "taxon": c["taxon"], "sci": c["sci"], "count": c["count"],
                        "v": c["verdict"], "fields": [x for x in (c.get("fields") or "").split(";") if x], "corr": corr, "conf": round(num(c.get("confidence")), 2), "reason": c.get("reason") or ""})
        gobs = {o["index"]: o for o in g.get("observations", [])}
        for o in obs:
            go = gobs.get(o["i"])
            if go:
                o["locality"], o["date"], o["cq"] = go.get("locality") or "", go.get("event_date") or "", go.get("count_qualifier") or ""
                o["observer"] = go.get("observer") or ", ".join(go.get("observers") or [])
                gr = go.get("georef")
                if isinstance(gr, list) and len(gr) >= 3 and gr[1] not in (None, ""):
                    o["locality"] = (o["locality"] + " " if o["locality"] else "") + f"({gr[1]}, {gr[2]})"
        PROTO.append({"t": "entry", "key": "entry:" + uid, "q": "extract", "k": "entry", "uid": uid, "id": r["entry_id"], "vol": int(num(r.get("volume"))), "date": r.get("date") or "", "rnd": R.n,
                      "n_obs": int(num(r["n_obs"])), "ok": int(num(r["ok"])), "wrong": int(num(r["wrong"])), "spurious": int(num(r["spurious"])), "unsure": int(num(r["unsure"])),
                      "missing": int(num(r["missing"])), "date_ok": r.get("date_ok") == "True", "place_ok": r.get("place_ok") == "True", "kind_ok": r.get("kind_ok") == "True",
                      "legible": r.get("scan_legible") == "True", "summary": r.get("summary") or "", "obs": obs,
                      "miss": [{"kind": m["kind"], "text": m["text"], "de": m.get("species_de") or "", "sci": m.get("sci") or "", "count": m.get("count") or "", "note": m.get("note") or ""} for m in missing[uid]],
                      "misread": [{"old": m["transcribed"], "new": m["correct"], "for": m.get("matters_for") or ""} for m in misread[uid]],
                      "persons": [[p.get("name"), ", ".join(p.get("roles") or []) if isinstance(p.get("roles"), list) else (p.get("roles") or "")] for p in g.get("persons", [])],
                      "n": 1})


def text_protos(R):
    seen = set()
    for r in R.tcm:
        k = (r["entry_uid"], r["old_text"])
        if k in seen:
            continue
        seen.add(k)
        PROTO.append({"t": "text", "key": f"text:{r['entry_uid']}|{r['old_text']}", "q": "text", "k": "text", "label": r["old_text"], "n": 1, "rnd": R.n, "uid": r["entry_uid"],
                      "conf": round(num(r.get("confidence")), 2) if r.get("confidence") else None, "agree": 1, "src": ["entry-check"], "reason": r.get("note") or "",
                      "for": r.get("matters_for") or "", "auto": 0, "cur": {"value": r["old_text"]}, "prop": {"value": r["new_text"]}})


TAXA_A_STATS = collections.Counter()
PLACE_READ = collections.defaultdict(list)       # lc written place name -> [(round, reading)]
for R in ROUNDS:
    if R.mr:
        mv = map_verdicts(R.G, R.mr)
        log(f"round {R.n}: verdicts mapped", {k: len(v) for k, v in mv.items()})
        taxon_protos(R, mv)
        person_protos(R, mv)
        place_protos(R, mv)
        habitat_protos(R, mv)
    TAXA_A_STATS.update(mention_protos(R))
    entry_protos(R)
    text_protos(R)
    for k, rs in R.place_readings.items():
        for r in (rs if isinstance(rs, list) else [rs]):
            if r.get("written"):
                PLACE_READ[lc(r["written"])].append((R.n, r))

# ---------------------------------------------------------------- supersede: a later round's verdict on the same key (or on all names) wins
BYKEY, ORDER_K = {}, []
for it in PROTO:
    k = it["key"]
    if k in BYKEY:
        old = BYKEY[k]
        it["prev"] = old.get("prev", []) + [{"r": old["rnd"], "k": old["k"], "conf": old.get("conf"), "q": old["q"]}]
    else:
        ORDER_K.append(k)
    BYKEY[k] = it
later_names = collections.defaultdict(dict)       # type -> lc name -> latest round with a verdict covering it
for it in BYKEY.values():
    if it["t"] in ("taxon", "form", "person", "place", "habitat"):
        tt = "taxon" if it["t"] == "form" else it["t"]
        for n_, _ in it.get("names", []):
            later_names[tt][lc(n_)] = max(later_names[tt].get(lc(n_), 0), it["rnd"])
SUPERSEDED = 0
for k in list(ORDER_K):
    it = BYKEY[k]
    if it["t"] not in ("taxon", "form", "person", "place", "habitat"):
        continue
    tt = "taxon" if it["t"] == "form" else it["t"]
    ns = [lc(n_) for n_, _ in it.get("names", [])]
    if ns and all(later_names[tt].get(n_, 0) > it["rnd"] for n_ in ns):
        del BYKEY[k]
        ORDER_K.remove(k)
        SUPERSEDED += 1
log("proto items", len(PROTO), "after supersede", len(BYKEY), "superseded by names", SUPERSEDED)

# ---------------------------------------------------------------- resolve against the graph under review
USED_E, USED_MEN, USED_FORMS, USED_ENTS = set(), {t: set() for t in TYPES}, {t: set() for t in TYPES}, {t: set() for t in TYPES}
ITEMS = []
DROP = collections.Counter()
KEYS = set()


def add(item):
    k = item["key"]
    if k in KEYS:
        n_ = 2
        while f"{k}#{n_}" in KEYS:
            n_ += 1
        item["key"] = f"{k}#{n_}"
    KEYS.add(item["key"])
    item.pop("G", None)
    item["i"] = len(ITEMS)
    ITEMS.append(item)
    return item


def pick_mentions(t, fis, limit):
    """Up to `limit` mentions over the given forms: prefer mentions with a line box and a
    model reading, spread over forms and entries."""
    sec = SEC[t]
    if not fis or limit <= 0:
        return []
    per_form = max(2, (limit + len(fis) - 1) // max(1, len(fis)))
    out, seen_e = [], set()
    sug = P.get("sug", {}), P.get("sug3", {}), P.get("sugs", {})
    for fi in fis:
        cand = C.men_of_form[t].get(fi, [])

        def score(mi):
            m = sec["men"][mi]
            has_box = isinstance(m[4], list) and len(m[4]) >= 5
            exact = has_box and len(m[4]) > 5 and m[4][5] == 0
            rd = t == "taxon" and any(str(mi) in s for s in sug)
            return (-int(rd), -int(exact), -int(has_box), -int(m[2] >= 0), m[1])
        take = 0
        for mi in sorted(cand, key=score):
            if take >= per_form or len(out) >= limit:
                break
            if sec["men"][mi][1] in seen_e and take > 0:
                continue
            out.append(mi)
            seen_e.add(sec["men"][mi][1])
            take += 1
    for mi in out:
        USED_MEN[t].add(mi)
        USED_E.add(sec["men"][mi][1])
    return out


def use_forms(t, fis):
    for fi in fis:
        USED_FORMS[t].add(fi)
        USED_ENTS[t].add(SEC[t]["forms"][fi][2])


def resolve_names(t, names):
    """-> (display fis: one per written name, all fis of those names in the graph under review)"""
    disp, allf = [], []
    for n_, _ in names:
        fis = C.fis_by_name[t].get(lc(n_), [])
        if not fis:
            continue
        allf += [fi for fi in fis if fi not in allf]
        best = max(fis, key=lambda fi: SEC[t]["forms"][fi][1])
        if best not in disp:
            disp.append(best)
    return disp, allf


def now_state(t, allf):
    """State of the names in the graph under review (shown when the round ran on another graph)."""
    s = SEC[t]
    cnt = collections.Counter()
    for fi in allf:
        cnt[s["forms"][fi][2]] += s["forms"][fi][1]
    if not cnt:
        return None
    ei, _ = cnt.most_common(1)[0]
    e = s["ent"][ei]
    out = {"label": e[0], "mixed": len(cnt) > 1}
    if t == "taxon":
        out.update({"key": e[2], "sci": e[1]})
    elif t == "person":
        out.update({"qid": e[1], "gnd": e[2]})
    elif t == "place":
        out.update({"lat": e[1], "lon": e[2]})
    elif t == "habitat":
        out.update({"code": e[1]})
    return out


def disp_badges(bn, disp):
    return {str(fi): bn[lc(SEC["taxon"]["forms"][fi][0])] for fi in disp if lc(SEC["taxon"]["forms"][fi][0]) in bn}


for k in ORDER_K:
    it = BYKEY[k]
    t = it["t"]
    G = it.get("G")
    if t in ("taxon", "form", "person", "place", "habitat"):
        tt = "taxon" if t == "form" else t
        disp, allf = resolve_names(tt, it["names"])
        if not allf:
            DROP[t + " not in graph"] += 1
            continue
        s = SEC[tt]
        it["n"] = sum(s["forms"][fi][1] for fi in allf)
        it["forms"] = disp
        it["names"] = [[s["forms"][fi][0], sum(s["forms"][x][1] for x in allf if lc(s["forms"][x][0]) == lc(s["forms"][fi][0]))] for fi in disp]
        if G is not C:
            it["now"] = now_state(tt, allf)
        if tt == "taxon":
            it["badges"] = disp_badges(it.pop("bn", {}), disp)
            name_fi = {lc(s["forms"][fi][0]): fi for fi in disp}
            for f_ in ("doubt", "moved", "focus"):
                if f_ in it:
                    it[f_] = [name_fi[n_] for n_ in it[f_] if n_ in name_fi]
            evf = [fi for fi in allf if lc(s["forms"][fi][0]) not in {lc(s["forms"][x][0]) for x in it.get("moved", [])}] if it.get("moved") else allf
            if it.get("k") == "name-unsure" and it.get("focus"):
                evf = [fi for fi in allf if lc(s["forms"][fi][0]) in {lc(s["forms"][x][0]) for x in it["focus"]}]
                it["n"] = sum(s["forms"][fi][1] for fi in evf)
            elif it.get("k") == "name-unsure":          # the doubtful names are not in this graph: a plain confirmation
                it["q"], it["k"] = "confirm", "ok"
                it.pop("focus", None)
            it["ev"] = pick_mentions("taxon", evf or allf, args.max_ev)
        else:
            it.pop("bn", None)
            if t == "person":
                ce = C.ent_by_label["person"].get(lc(it["label"]))
                if ce is not None and P.get("pm", {}).get(str(ce)):
                    it["opus"] = P["pm"][str(ce)]
            it["ev"] = pick_mentions(tt, sorted(allf, key=lambda x: -s["forms"][x][1]), args.max_ev)
        use_forms(tt, allf)
        add(it)
    elif t == "mention":
        ei = C.uid2e.get(it["uid"])
        if ei is None:
            DROP["mention entry not in graph"] += 1
            continue
        it["ei"] = ei
        mi = C.mkey2mi["taxon"].get(it.pop("mkey"))
        it["ev"] = [mi] if mi is not None else []
        if mi is None:
            it["stale"] = 1
        else:
            USED_MEN["taxon"].add(mi)
            use_forms("taxon", [TX["men"][mi][0]])
        USED_E.add(ei)
        it.pop("uid", None)
        add(it)
    elif t == "text":
        ei = C.uid2e.get(it["uid"])
        if ei is None:
            DROP["text entry not in graph"] += 1
            continue
        it["ei"] = ei
        it.pop("uid", None)
        it["found"] = int(it["label"] in E[ei][7])
        USED_E.add(ei)
        add(it)
    elif t == "entry":
        ei = C.uid2e.get(it["uid"])
        if ei is None:
            DROP["checked entry not in graph"] += 1
            continue
        it["ei"] = ei
        it.pop("uid", None)
        now = sorted(lc(TX["forms"][m[0]][0]) for tt_, mi in C.men_of_entry.get(ei, []) if tt_ == "taxon" for m in [TX["men"][mi]])
        chk = sorted(lc(o["written"]) for o in it["obs"])
        if now != chk:
            it["stale"] = 1
            it["now_obs"] = [TX["forms"][TX["men"][mi][0]][0] + " → " + TX["ent"][TX["forms"][TX["men"][mi][0]][2]][0] for tt_, mi in C.men_of_entry.get(ei, []) if tt_ == "taxon"][:80]
        USED_E.add(ei)
        add(it)
log("dropped", dict(DROP))

# second visual round: place-name readings on the place items (by written name)
place_scan_stats = collections.Counter()
for it in ITEMS:
    if it["t"] != "place":
        continue
    rs = []
    for fi in it["forms"]:
        rs += PLACE_READ.get(lc(PL["forms"][fi][0]), [])
    if not rs:
        continue
    rnd = max(r for r, _ in rs)
    rs = [r for _, r in rs]
    it["scan"] = rs
    if "scan" not in it["src"]:
        it["src"] = it["src"] + ["scan"]

    def _mismarked(r):
        n_ = (r.get("note") or "").lower()
        return (r.get("is_place") is False and (num(r.get("conf")) < 0.7 or any(x in n_ for x in (
            "nicht im kasten", "nicht auf der zeile", "nicht in der zeile", "nicht enthalten", "falsche zeile", "eine zeile", "außerhalb", "one line",
            "not on the marked", "not in the box", "doesn't contain", "does not contain", "nicht das gesuchte", "nicht die gesuchte"))))
    legible = [r for r in rs if r.get("legible") and not _mismarked(r)]
    place_scan_stats["items"] += 1
    if not legible:
        place_scan_stats["illegible"] += 1
        continue
    if rnd < it["rnd"]:
        place_scan_stats["older_than_verdict"] += 1
        continue
    located = [r for r in legible if r.get("is_place") is True and r.get("lat") is not None and r.get("lon") is not None and num(r.get("conf")) >= 0.6]
    notplace = [r for r in legible if r.get("is_place") is False and num(r.get("conf")) >= 0.7]
    if it["q"] == "open" and located and not any(r.get("is_place") is False for r in legible):
        best = max(located, key=lambda r: num(r.get("conf")))
        it.update(q="change", k="scan-located", rnd=rnd, prev=it.get("prev", []) + [{"r": it["rnd"], "k": it["k"], "conf": it["conf"], "q": "open"}])
        it["prop"] = {"lat": float(best["lat"]), "lon": float(best["lon"]), "name": (best.get("place") or it["label"]) + (", " + best["region"] if best.get("region") else ""),
                      "type": "Bildlesung", "qid": "", "osm": "", "km": None}
        it["unc"] = best.get("unc") or it.get("unc") or 1000
        it["conf"] = round(num(best.get("conf")), 2)
        it["agree"] = 1 + (1 if len(located) > 1 else 0)
        it["reason"] = "Bildlesung: „" + (best.get("reading") or "") + "“ → " + (best.get("place") or "") + (" (" + best["region"] + ")" if best.get("region") else "") + ". " + (best.get("note") or "")
        place_scan_stats["located"] += 1
    elif it["q"] == "open" and notplace and len(notplace) == len(legible):
        best = max(notplace, key=lambda r: num(r.get("conf")))
        it.update(q="change", k="not_a_place", rnd=rnd, prev=it.get("prev", []) + [{"r": it["rnd"], "k": it["k"], "conf": it["conf"], "q": "open"}])
        it["prop"] = {"none": True}
        it["conf"] = round(num(best.get("conf")), 2)
        it["reason"] = "Bildlesung: „" + (best.get("reading") or "") + "“ — " + (best.get("note") or "kein Ortsname")
        place_scan_stats["not_a_place"] += 1
    else:
        place_scan_stats["still_open"] += 1

# ---------------------------------------------------------------- the audit sample of confirmations (hash order: stable over rebuilds)
confirms = [it for it in ITEMS if it["q"] == "confirm"]
STRATA = [
    ("taxon-text", lambda it: it["t"] == "taxon" and it["k"] == "ok" and not ({"scan", "gemini", "opus"} & set(it["src"]))),
    ("taxon-scan", lambda it: it["t"] == "taxon" and it["k"] == "ok" and bool({"scan", "gemini", "opus"} & set(it["src"]))),
    ("person", lambda it: it["t"] == "person" and it["k"] == "link-confirm"),
    ("place-text", lambda it: it["t"] == "place" and it["k"] == "ok" and it["agree"] < 2),
    ("place-corr", lambda it: it["t"] == "place" and it["k"] == "ok" and it["agree"] >= 2),
    ("habitat", lambda it: it["t"] == "habitat" and it["k"] == "h-ok"),
]
sample_info = []
for sid, pred in STRATA:
    pool = sorted([it for it in confirms if pred(it)], key=lambda it: hkey(args.seed, it["key"]))
    if not pool:
        continue
    take = pool[:args.sample_per_stratum]
    for rank, it in enumerate(take):
        it["q"], it["stratum"], it["rank"] = "sample", sid, rank
    sample_info.append({"id": sid, "pool": len(pool), "n": len(take)})
for it in ITEMS:
    if it["q"] == "confirm":
        it["q"] = "rest"
MACHINE_KEYS = {it["key"] for it in ITEMS}
CHECKED_FORMS = {t: set(USED_FORMS[t]) for t in TYPES}

# ---------------------------------------------------------------- not checked: every entity of the graph no machine round saw
# header places of the entries -> anchor points for places
place_pt = {}
for i, e in enumerate(PL["ent"]):
    if e[1] is not None:
        place_pt.setdefault(lc(e[0]), (e[0], e[1], e[2]))


def km(a, b):
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(12742 * math.asin(math.sqrt(h)), 1)


UNCHECKED = collections.Counter()
for t in ("taxon", "person", "place"):
    s = SEC[t]
    order = sorted(range(len(s["ent"])), key=lambda ei: -C.n_of_ent[t].get(ei, 0))
    for ei in order:
        fis = C.forms_of_ent[t].get(ei, [])
        if not fis:
            continue
        ent = s["ent"][ei]
        key = t + ":" + lc(ent[0])
        if key in MACHINE_KEYS or any(fi in CHECKED_FORMS[t] for fi in fis):
            continue
        fis = sorted(fis, key=lambda x: -s["forms"][x][1])
        n_ = C.n_of_ent[t].get(ei, 0)
        it = {"t": t, "key": key, "q": "unchecked", "label": ent[0], "n": n_, "forms": fis, "names": [[s["forms"][fi][0], s["forms"][fi][1]] for fi in fis], "src": [], "rnd": 0}
        if t == "taxon":
            linked = bool(ent[2])
            it.update(sci=ent[1], cur={"key": ent[2], "sci": ent[1], "rank": ent[3], "family": ent[6], "de": ent[9]} if linked else None,
                      llm=ent[5] if not linked else "", badges={})
        elif t == "person":
            linked = bool(ent[1] or ent[2])
            cands, seen = [], set()
            for fi in fis:
                for c in (s["forms"][fi][5] if len(s["forms"][fi]) > 5 and isinstance(s["forms"][fi][5], list) else []):
                    if c and c[0] not in seen:
                        seen.add(c[0])
                        cands.append({"qid": c[0], "label": c[1], "desc": c[2], "born": "", "died": "", "gnd": ""})
            it.update(cur={"qid": ent[1], "gnd": ent[2]}, cands=cands[:8], gcands=[], roles={}, years="", opus=P.get("pm", {}).get(str(ei)))
            roles = collections.Counter()
            for fi in fis:
                for mi in C.men_of_form[t].get(fi, []):
                    for r in (s["men"][mi][5] or "").split("/"):
                        if r:
                            roles[r] += 1
            it["roles"] = dict(roles.most_common(5))
        else:
            linked = ent[1] is not None
            lr = s["forms"][fis[0]][5] if len(s["forms"][fis[0]]) > 5 and isinstance(s["forms"][fis[0]][5], list) else []
            it.update(cur={"lat": ent[1], "lon": ent[2], "unc": ent[3], "gn": ent[4], "qid": ent[5], "kind": ent[6], "src": ent[7]} if linked else {"kind": ent[6]},
                      cands=[], unc=None, hint="", hint_ll=None)
            if lr and len(lr) >= 12:
                it["graph"] = {"source": lr[1], "linking_note": lr[3], "geonames_name": lr[7], "country": lr[8], "feature": lr[11], "confidence": lr[2], "status": lr[0]}
            anc = collections.Counter()
            for fi in fis:
                for mi in C.men_of_form[t].get(fi, []):
                    h = lc(E[s["men"][mi][1]][6] or "")
                    if h and h != lc(ent[0]) and h in place_pt:
                        anc[h] += 1
            it["anchors"] = [{"place": place_pt[h][0], "n": c, "lat": place_pt[h][1], "lon": place_pt[h][2], "km": km((ent[1], ent[2]), place_pt[h][1:]) if linked else None}
                             for h, c in anc.most_common(4)]
            roles = collections.Counter(s["men"][mi][5] or "" for fi in fis for mi in C.men_of_form[t].get(fi, []))
            it["roles"] = {k_: v for k_, v in roles.most_common(4) if k_}
        it["k"] = "linked" if linked else "unlinked"
        it["ev"] = pick_mentions(t, fis, args.max_ev_unchecked)
        use_forms(t, fis)
        UNCHECKED[(t, it["k"])] += 1
        add(it)
log("unchecked", dict(UNCHECKED))

# ---------------------------------------------------------------- habitats (EUNIS)
EUNIS = {e[0]: e for e in P.get("eunis", [])}
HB_N = collections.Counter()
for ei in sorted(range(len(HB["ent"])), key=lambda x: -C.n_of_ent["habitat"].get(x, 0)):
    fis = C.forms_of_ent["habitat"].get(ei, [])
    if not fis:
        continue
    ent = HB["ent"][ei]
    if "habitat:" + lc(ent[0]) in MACHINE_KEYS or any(fi in CHECKED_FORMS["habitat"] for fi in fis):
        continue
    fis = sorted(fis, key=lambda x: -HB["forms"][x][1])
    lr = next((HB["forms"][fi][5] for fi in fis if len(HB["forms"][fi]) > 5 and isinstance(HB["forms"][fi][5], list) and any(HB["forms"][fi][5])), [])
    code = ent[1]
    sug = {"code": lr[3], "label": lr[4], "match": lr[5], "conf": lr[1], "note": lr[2], "status": lr[0]} if len(lr) >= 6 else None
    it = {"t": "habitat", "key": "habitat:" + lc(ent[0]), "q": "habitat", "k": "linked" if code else "unlinked", "label": ent[0], "rnd": 0, "src": [],
          "n": C.n_of_ent["habitat"].get(ei, 0), "forms": fis, "names": [[HB["forms"][fi][0], HB["forms"][fi][1]] for fi in fis],
          "cur": {"code": code, "match": ent[2], "label": (EUNIS.get(code) or ["", ""])[1], "level": (EUNIS.get(code) or ["", "", ""])[2], "parent": (EUNIS.get(code) or ["", "", "", ""])[3]} if code else None,
          "sug": sug}
    it["ev"] = pick_mentions("habitat", fis, args.max_ev_unchecked)
    use_forms("habitat", fis)
    HB_N[it["k"]] += 1
    add(it)
log("habitats", dict(HB_N))

# ---------------------------------------------------------------- QA flags
qa_rows = read_csv(Path(args.review) / "qa_flags.csv") if args.review else []
if not qa_rows and P.get("qa"):
    qa_rows = [dict(zip(P["qa"]["head"], r)) for r in P["qa"]["rows"]]
QA_N = collections.Counter(r["reason"] for r in qa_rows)
qa_order = {r: i for i, (r, _) in enumerate(QA_N.most_common())}
for r in sorted(qa_rows, key=lambda r: (qa_order[r["reason"]], r.get("entry_id") or "", r.get("value") or "")):
    ei = C.uid2e.get(r.get("entry_uid") or "")
    it = {"t": "qa", "key": f"qa:{r.get('entry_uid') or r.get('entry_id')}|{r['reason']}|{r.get('value') or ''}", "q": "qa", "k": r["reason"], "label": r.get("value") or "",
          "id": r.get("entry_id") or "", "uid": r.get("entry_uid") or "", "action": r.get("action") or "", "detail": r.get("detail") or "", "n": 1, "rnd": 0, "src": []}
    if ei is not None:
        it["ei"] = ei
        USED_E.add(ei)
    add(it)
log("qa flags", len(qa_rows), dict(QA_N.most_common(8)))

# ---------------------------------------------------------------- transcript corrections of the visual reading (before extraction)
WORD = re.compile(r"\w+", re.U)
BIRD, PLACE = set(), set()
for f in TX["forms"]:
    BIRD.update(w for w in WORD.findall(lc(f[0])) if len(w) >= 4)
for e in TX["ent"]:
    for n_ in [e[0]] + list(e[9] if len(e) > 9 and isinstance(e[9], list) else []):
        w = lc(n_)
        if len(w) >= 4 and " " not in w:
            BIRD.add(w)
for e in PL["ent"]:                 # geolocated place names (single words, or capitalised words of longer names)
    if e[1] is None:
        continue
    for n_ in [e[0]] + list(e[8] if len(e) > 8 and isinstance(e[8], list) else []):
        ws = WORD.findall(n_)
        if len(ws) == 1 and len(ws[0]) >= 4 and ws[0][:1].isupper():
            PLACE.add(lc(ws[0]))
        else:
            PLACE.update(lc(w) for w in ws if len(w) >= 5 and w[:1].isupper())
STOP = {"der", "die", "das", "und", "ein", "eine", "einer", "einen", "dem", "den", "des", "mit", "von", "vom", "auf", "aus", "bei", "nach", "sich", "nicht", "noch", "auch", "wie"}
BIRD -= STOP
PLACE -= STOP | BIRD


def stems(w):
    out = {w}
    for suf in ("chen", "lein", "en", "n", "e", "s", "es", "er"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            out.add(w[: -len(suf)])
    return out


HEADS = ("meise", "fink", "finken", "ente", "enten", "taube", "specht", "möwe", "lerche", "schwalbe", "drossel", "reiher", "falke", "sänger",
         "ammer", "läufer", "taucher", "gans", "gänse", "huhn", "hühner", "eule", "adler", "weihe", "bussard", "rabe", "krähe", "würger", "pieper",
         "stelze", "schnäpper", "kauz", "häher", "sperling", "spatz", "zeisig", "gimpel", "kleiber", "rotschwanz", "kehlchen", "schwirl", "rohrsänger",
         "grasmücke", "laubsänger", "säger", "schnepfe", "regenpfeifer", "seeschwalbe", "kormoran", "storch", "milan", "sperber", "habicht", "wachtel")


def is_bird(w):
    return any(x in BIRD for x in stems(w)) or any(w.endswith(h) and len(w) > len(h) + 1 for h in HEADS)


def change_kind(old, new):
    o, n_ = TAG.sub("", old or ""), TAG.sub("", new or "")
    if o.startswith("location_header:") or n_.startswith("location_header:"):
        return "place"
    if o.startswith("date:") or n_.startswith("date:"):
        return "num"
    ot, nt = WORD.findall(o), WORD.findall(n_)
    sm = difflib.SequenceMatcher(None, [lc(x) for x in ot], [lc(x) for x in nt], autojunk=False)
    rem, addd = [], []
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op in ("replace", "delete"):
            rem += ot[a0:a1]
        if op in ("replace", "insert"):
            addd += nt[b0:b1]
    if not rem and not addd:
        # only punctuation / markup / case changed
        return "word"
    if not rem:
        return "ins"
    if not addd:
        return "del"
    ch = rem + addd
    if any(re.search(r"\d", w) for w in ch) or any(re.fullmatch(r"[IVX]{1,4}", w) for w in ch):
        return "num"
    if any(is_bird(lc(w)) for w in ch):
        return "bird"
    if any(lc(w) in PLACE for w in ch if w[:1].isupper()):
        return "place"
    return "word"


def find_pos(text, s):
    if not s:
        return -1, -1
    i = text.find(s)
    if i < 0:
        s2 = TAG.sub("", s)
        i = text.find(s2)
        s = s2
    if i < 0:
        for pre in ("location_header:", "date:"):
            if s.startswith(pre):
                s = s[len(pre):].strip()
                i = text.find(s)
                break
    if i < 0:
        i = lc(text).find(lc(s))
    return (i, i + len(s)) if i >= 0 else (-1, -1)


def records_per_entry():
    occ = Path(args.dwca) / "occurrence.txt" if args.dwca else None
    if occ and occ.exists():
        cnt = collections.Counter()
        with open(occ, encoding="utf-8", newline="") as h:
            head = h.readline().rstrip("\n").split("\t")
            ev = head.index("eventID")
            for line in h:
                cols = line.split("\t")
                if len(cols) > ev:
                    cnt[cols[ev].rsplit("entry_", 1)[-1]] += 1
        log("dwca records per entry:", len(cnt), "entries,", sum(cnt.values()), "records")
        return cnt, "dwca"
    cnt = collections.Counter()
    for m in TX["men"]:
        cnt[E[m[1]][1]] += 1
    return cnt, "graph"


NREC, NREC_SRC = records_per_entry()
TCHECK = {}
for R in ROUNDS:
    for r in R.tchecks:
        TCHECK[(r["entry_uid"], r["old_text"], r["new_text"])] = dict(r, _rnd=R.n)
tc_rows = read_csv(Path(args.review) / "transcript_corrections.csv") if args.review else []
TC = {"total": len(tc_rows), "no_entry": 0, "applied": collections.Counter(), "pool": collections.Counter(), "kind": collections.Counter(),
      "machine": collections.Counter(), "review": collections.Counter(), "entries": len({r["entry_uid"] for r in tc_rows})}
tc_all = []
per_entry = collections.Counter(r["entry_uid"] for r in tc_rows)
seen_k = collections.Counter()
for r in tc_rows:
    ap_ = "y" if (r.get("applied") or "").strip().lower() in ("y", "yes", "true", "1") else "n"
    TC["applied"][ap_] += 1
    ei = C.uid2e.get(r["entry_uid"])
    base = f"tc:{r['entry_uid']}|{r['old_text']}|{r['new_text']}"
    seen_k[base] += 1
    key = base if seen_k[base] == 1 else f"{base}#{seen_k[base]}"
    kind = change_kind(r["old_text"], r["new_text"])
    mc = TCHECK.get((r["entry_uid"], r["old_text"], r["new_text"]))
    if mc:
        TC["machine"][mc.get("verdict") or ""] += 1
    if ei is None:
        TC["no_entry"] += 1
        continue
    stratum = kind + "-" + ap_
    TC["pool"][stratum] += 1
    TC["kind"][kind] += 1
    tc_all.append((key, r, ei, ap_, kind, stratum, mc))
tc_items = {}
by_stratum = collections.defaultdict(list)
for x in tc_all:
    by_stratum[x[5]].append(x)
for sid, lst in by_stratum.items():
    lst.sort(key=lambda x: hkey(args.seed, "tc", x[0]))
    for rank, x in enumerate(lst[:args.tc_sample_per_stratum]):
        tc_items[x[0]] = {"x": x, "samp": sid, "srank": rank, "rev": []}
for x in tc_all:
    key, r, ei, ap_, kind, stratum, mc = x
    rev = []
    if mc and (mc.get("verdict") or "") in ("wrong", "unclear"):
        rev.append("m-" + mc["verdict"])
    if ap_ == "n" and NREC.get(r["entry_uid"], 0) > 0:
        rev.append("not-applied")
    if rev:
        tc_items.setdefault(key, {"x": x, "samp": None, "srank": None, "rev": []})["rev"] = rev
        for v in rev:
            TC["review"][v] += 1
REV_ORDER = {"m-wrong": 0, "m-unclear": 1, "not-applied": 2}
TC_ORDER = sorted(tc_items.values(), key=lambda d: (0, d["samp"], d["srank"], 0, 0) if d["samp"] else
                  (1, "", min(REV_ORDER.get(v, 3) for v in d["rev"]), -NREC.get(d["x"][1]["entry_uid"], 0), d["x"][2]))
for d in TC_ORDER:
    key, r, ei, ap_, kind, stratum, mc = d["x"]
    text = E[ei][7]
    s0, e0 = find_pos(text, r["new_text"] if ap_ == "y" else r["old_text"])
    if s0 < 0:
        s0, e0 = find_pos(text, r["old_text"] if ap_ == "y" else r["new_text"])
    hl = None
    if s0 >= 0:
        best = None
        for tt_, mi in C.men_of_entry.get(ei, []):
            m = SEC[tt_]["men"][mi]
            if isinstance(m[4], list) and len(m[4]) >= 5 and m[2] >= 0:
                dist = abs(m[2] - s0)
                if dist <= 250 and (best is None or dist < best[0]):
                    best = (dist, m[4])
        if best:
            hl = best[1][:5] + [1]
    it = {"t": "tc", "key": key, "q": "tc", "k": kind, "label": r["old_text"], "new": r["new_text"], "applied": ap_, "ei": ei, "n": 1, "rnd": mc["_rnd"] if mc else 0, "src": [],
          "note": r.get("note") or "", "by0": r.get("reviewed_by") or "", "tpos": [s0, e0], "hl": hl, "nrec": NREC.get(r["entry_uid"], 0), "others": per_entry[r["entry_uid"]] - 1,
          "stratum": d["samp"], "srank": d["srank"], "rev": d["rev"]}
    if mc:
        it["m"] = {"v": mc.get("verdict") or "", "better": mc.get("better_text") or "", "reason": mc.get("reason") or "", "r": mc["_rnd"]}
    USED_E.add(ei)
    add(it)
TC["sampled"] = collections.Counter(d["samp"] for d in tc_items.values() if d["samp"])
TC["items"] = len(tc_items)
log("transcript corrections", {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in TC.items()})

# ---------------------------------------------------------------- ordering within queues
for it in ITEMS:
    it.setdefault("n", 0)
FORORD = {"species": 0, "place": 1, "person": 2, "count": 3, "date": 4}
ORDER = {"change": lambda it: (-it.get("auto", 0), -it["n"], it["t"]), "open": lambda it: (-it["n"],), "sample": lambda it: (it["stratum"], it["rank"]),
         "extract": lambda it: (-(it["wrong"] + it["spurious"]) - it["missing"] * 0.5, it["id"]), "text": lambda it: (FORORD.get(it.get("for"), 5), it["ei"]),
         "rest": lambda it: (-it["n"],), "unchecked": lambda it: (-it["n"],), "habitat": lambda it: (-it["n"],), "qa": lambda it: it["i"], "tc": lambda it: it["i"]}
queues = collections.defaultdict(list)
for it in ITEMS:
    queues[it["q"]].append(it)
for q, lst in queues.items():
    lst.sort(key=ORDER[q])
    for pos, it in enumerate(lst):
        it["pos"] = pos

# ---------------------------------------------------------------- legacy import map (Laubmann_Pruefung.html of 2026-09-30)
LEGACY = None
if args.legacy_pruefung:
    lp = Path(args.legacy_pruefung)
    L = load_payload(lp) if lp.suffix.lower() in (".html", ".htm", ".b64") else json.loads(lp.read_text(encoding="utf-8"))
    LE, LF, LM = L["E"], L["FORMS"], L["MEN"]
    keys, obs, miss = [], {}, {}
    for it in L["items"]:
        t = it["t"]
        if t in ("taxon", "form", "person", "place"):
            k = ("taxon" if t == "taxon" else t) + ":" + lc(it["label"])
        elif t == "mention":
            v = it.get("vrow") or {}
            k = f"men:{v.get('entry_uid')}|{lc(v.get('old_value') or '')}|{v.get('occurrence') or 0}"
        elif t == "text":
            k = f"text:{LE[str(it['ei'])][1]}|{it['label']}"
        elif t == "entry":
            k = "entry:" + LE[str(it["ei"])][1]
            obs[it["i"]] = {str(o["i"]): lc(o["written"]) + "|" + str(o.get("occ") or 0) for o in it["obs"]}
            miss[it["i"]] = [lc(m["text"]).strip() for m in it["miss"]]
        else:
            k = None
        keys.append(k)
    forms = {tt: {fi: lc(f[0]) for fi, f in LF[tt].items()} for tt in LF}
    mens = {}
    for tt, d in LM.items():
        mens[tt] = {}
        for mi, m in d.items():
            f = LF[tt].get(str(m[0]))
            e = LE.get(str(m[1]))
            if f and e:
                mens[tt][mi] = e[1] + "|" + lc(f[0]) + "|" + str(m[-1] if len(m) > 6 else 0)
    LEGACY = {"export": L.get("export"), "built": L.get("built"), "keys": keys, "forms": forms, "mens": mens, "obs": obs, "miss": miss}
    log("legacy map: items", len(keys), "matched here", sum(1 for k in keys if k in KEYS))

# ---------------------------------------------------------------- compact payload
pages_used = set()
E_out = {}
for ei in USED_E:
    e = E[ei]
    E_out[ei] = [e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7], e[8]]
    pages_used.update(e[8])
for t in TYPES:
    for mi in USED_MEN[t]:
        m = SEC[t]["men"][mi]
        if isinstance(m[4], list) and m[4]:
            pages_used.add(m[4][0])
for it in ITEMS:
    if it.get("hl"):
        pages_used.add(it["hl"][0])
for pidx in list(pages_used):
    for d in (-1, 1):
        j = pidx + d
        if 0 <= j < len(PG) and PG[j][1] == PG[pidx][1]:
            pages_used.add(j)
DRIVE_out = {PG[p][0]: DRIVE[PG[p][0]] for p in pages_used if PG[p][0] in DRIVE}
MEN_out, FORMS_out, SUG_out = {}, {}, {"g": {}, "o": {}, "s": {}}
for t in TYPES:
    MEN_out[t] = {mi: SEC[t]["men"][mi][:6] + [int(C.mkey[t][mi].rsplit("|", 1)[1])] for mi in USED_MEN[t]}
    FORMS_out[t] = {fi: SEC[t]["forms"][fi][:4] for fi in USED_FORMS[t]}
for mi in USED_MEN["taxon"]:
    for src, key in (("g", "sug"), ("o", "sug3"), ("s", "sugs")):
        a = P.get(key, {}).get(str(mi))
        if a:
            SUG_out[src][mi] = a[:7]
used_rows = sorted({ri for it in ITEMS for ri in it.get("rows", [])})
ROWS_out = {ri: {k: v for k, v in ALLROWS[ri].items()} for ri in used_rows}

cnt = lambda pred: sum(1 for it in ITEMS if pred(it))   # noqa: E731
stats = {
    "items": len(ITEMS), "queues": {q: len(lst) for q, lst in queues.items()},
    "by_type_queue": {f"{a}|{b}|{c}": n_ for (a, b, c), n_ in sorted(collections.Counter((it["t"], it["q"], it["k"]) for it in ITEMS).items())},
    "auto_changes": cnt(lambda it: it["q"] == "change" and it.get("auto")),
    "entries_embedded": len(E_out), "mentions_embedded": {t: len(v) for t, v in MEN_out.items()}, "pages": len(DRIVE_out),
    "sample": sample_info, "dropped": dict(DROP), "superseded": SUPERSEDED,
    "round2": {"place_scan": dict(place_scan_stats), "taxa_a": dict(TAXA_A_STATS), "entries2": cnt(lambda it: it["t"] == "entry" and it["rnd"] == 2)},
    "machine": {
        "taxon": dict(collections.Counter(it["k"] for it in ITEMS if it["t"] == "taxon" and it["q"] != "unchecked")),
        "person": dict(collections.Counter(it["k"] for it in ITEMS if it["t"] == "person" and it["q"] != "unchecked")),
        "place": dict(collections.Counter(it["k"] for it in ITEMS if it["t"] == "place" and it["q"] != "unchecked")),
        "habitat": dict(collections.Counter(it["k"] for it in ITEMS if it["t"] == "habitat" and it["q"] != "habitat")),
        "by_round": dict(collections.Counter(f"{it['t']}|{it['rnd']}" for it in ITEMS if it.get("rnd"))),
        "checked": {"taxon": cnt(lambda it: it["t"] == "taxon" and it["q"] != "unchecked"), "taxon_total": len(TX["ent"]), "taxon_forms": len(USED_FORMS["taxon"] & CHECKED_FORMS["taxon"]),
                    "forms_total": len(TX["forms"]), "scan_mentions": len(P.get("sugs", {})),
                    "person": cnt(lambda it: it["t"] == "person" and it["q"] != "unchecked"), "person_total": len(PS["ent"]),
                    "place": cnt(lambda it: it["t"] == "place" and it["q"] != "unchecked"), "place_total": len(PL["ent"]),
                    "entries": cnt(lambda it: it["t"] == "entry"), "entries_total": len(E),
                    "obs": sum(it["n_obs"] for it in ITEMS if it["t"] == "entry"), "obs_ok": sum(it["ok"] for it in ITEMS if it["t"] == "entry"),
                    "obs_wrong": sum(it["wrong"] for it in ITEMS if it["t"] == "entry"), "obs_spurious": sum(it["spurious"] for it in ITEMS if it["t"] == "entry"),
                    "obs_unsure": sum(it["unsure"] for it in ITEMS if it["t"] == "entry"), "obs_missing": sum(it["missing"] for it in ITEMS if it["t"] == "entry"),
                    "text_corr": cnt(lambda it: it["t"] == "text"), "value_corr": cnt(lambda it: it["t"] == "mention"),
                    "rows": len(ALLROWS), "rows_auto": sum(1 for r in ALLROWS if row_auto(r))},
    },
    "unchecked": {f"{a}|{b}": n_ for (a, b), n_ in UNCHECKED.items()}, "habitat": dict(HB_N), "qa": dict(QA_N),
    "tc": {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in TC.items()}, "nrec_src": NREC_SRC,
}
TAXA = [[e[0], e[1], e[2], e[3]] for e in TX["ent"] if e[2]]
payload = {"v": 2, "app": "laubmann-validierung", "TAXA": TAXA, "built": args.built or P.get("built") or "", "export": P.get("export"),
           "rounds": [R.info for R in ROUNDS], "thresholds": {"conf": MIN_CONF, "agree": MIN_AGREE},
           "E": E_out, "PG": PG, "DRIVE": DRIVE_out, "MEN": MEN_out, "FORMS": FORMS_out, "SUG": SUG_out,
           "ROWS": ROWS_out, "EUNIS": P.get("eunis", []), "items": ITEMS, "stats": stats, "LEGACY": LEGACY}
raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
Path(str(out) + ".json").write_bytes(raw)
gz = gzip.compress(raw, 9, mtime=0)
Path(str(out) + ".b64").write_text(base64.b64encode(gz).decode())
print(json.dumps({k: v for k, v in stats.items() if k not in ("by_type_queue",)}, ensure_ascii=False, indent=1))
print(f"raw {len(raw) / 1e6:.1f} MB, gz {len(gz) / 1e6:.1f} MB -> {out}.json / .b64")
