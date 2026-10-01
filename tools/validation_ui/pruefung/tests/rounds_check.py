"""Build-level check of the round merge (no browser): writes a small fake round r3 on the graph
under review (machine_review.json, identities_machine.csv, transcript_checks.csv), runs
build_data.py with r1 (+ r2) and that r3, and checks that r3 supersedes r1 on the same key,
keeps r1 as "prev", marks transcript corrections the machine called wrong/unclear for review,
and that a missing round folder is tolerated.

    python tests/rounds_check.py --payload <graph payload> --machine <r1 dir>[@graph] [<r2 dir>[@graph]] \
        --review <export>/review --work <scratch dir> [build_data args ...]
"""
import argparse
import base64
import csv
import gzip
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--payload", required=True)
ap.add_argument("--machine", nargs="+", required=True)
ap.add_argument("--review", required=True)
ap.add_argument("--work", required=True)

a, REST = ap.parse_known_args()
W = Path(a.work)
R3 = W / "machine_review3_fixture"
R3.mkdir(parents=True, exist_ok=True)
raw = Path(a.payload).read_bytes()
P = json.loads(raw) if a.payload.endswith(".json") else json.loads(gzip.decompress(base64.b64decode(raw.strip())))
FAILS = []


def check(c, m):
    print(("ok   " if c else "FAIL ") + m)
    if not c:
        FAILS.append(m)


# r3 verdicts: the most frequent linked taxon (confirmed) and the most frequent place (confirmed)
tx = P["taxon"]
n_of = {}
for f in tx["forms"]:
    n_of[f[2]] = n_of.get(f[2], 0) + f[1]
ti = max((i for i, e in enumerate(tx["ent"]) if e[2]), key=lambda i: n_of.get(i, 0))
te = tx["ent"][ti]
pl = P["place"]
pn = {}
for f in pl["forms"]:
    pn[f[2]] = pn.get(f[2], 0) + f[1]
pi = max((i for i, e in enumerate(pl["ent"]) if e[1] is not None), key=lambda i: pn.get(i, 0))
pe = pl["ent"][pi]
hb = P["habitat"]
hn = {}
for f in hb["forms"]:
    hn[f[2]] = hn.get(f[2], 0) + f[1]
hord = sorted(range(len(hb["ent"])), key=lambda i: -hn.get(i, 0))[:4]
HV = ["ok", "other", "none", "unsure"]
hab_ent = {str(i): {"verdict": v, "code": ("C1.1" if v == "other" else (hb["ent"][i][1] if v == "ok" else "")), "match": "close", "confidence": 0.95, "agreement": 2,
                    "sources": "text+gemini", "reason": "R3 fixture " + v, "label": hb["ent"][i][0], "cur_code": hb["ent"][i][1]} for i, v in zip(hord, HV)}
mr = {"model": "claude-test-r3", "built": "2026-10-01T09:00", "habitat": {"ent": hab_ent},
      "taxon": {"ent": {str(ti): {"link": "ok", "confidence": 0.99, "reason": "R3 fixture", "sci": te[1], "species_de": te[0], "label": te[0], "cur_key": te[2]}}, "form": {}},
      "person": {"ent": {}},
      "place": {"ent": {str(pi): {"verdict": "ok", "confidence": 0.97, "reason": "R3 fixture", "hint": None, "candidate": None, "uncertainty_m": 2000, "label": pe[0], "sources": ["text", "nominatim"]}}}}
(R3 / "machine_review.json").write_text(json.dumps(mr, ensure_ascii=False), encoding="utf-8")
head = ["section", "name_form", "decision", "target", "authority", "scientific_name", "rank", "lat", "lon", "uncertainty_m", "eunis_match", "reason", "note", "reviewed_by", "reviewed_at", "confidence", "agreement", "sources"]
with open(R3 / "identities_machine.csv", "w", encoding="utf-8", newline="") as h:
    w = csv.DictWriter(h, head)
    w.writeheader()
    w.writerow({"section": "taxa", "name_form": te[0], "decision": "same", "target": te[0], "authority": "gbif:" + te[2], "scientific_name": te[1], "rank": te[3],
                "reason": "R3 fixture", "reviewed_by": "machine:claude-test-r3", "reviewed_at": "2026-10-01T09:00", "confidence": "0.99", "agreement": "2", "sources": "text+scan"})
    if True:
        hv = hab_ent[str(hord[1])]
        w.writerow({"section": "habitats", "name_form": hv["label"], "decision": "link", "target": hv["label"], "authority": "eunis:C1.1", "eunis_match": "close",
                    "reason": "R3 fixture", "reviewed_by": "machine:claude-test-r3", "reviewed_at": "2026-10-01T09:00", "confidence": "0.95", "agreement": "2", "sources": "text+gemini"})
tc = list(csv.DictReader(open(Path(a.review) / "transcript_corrections.csv", encoding="utf-8", newline="")))
picks = tc[:6]
verdicts = ["right", "right", "partly", "wrong", "wrong", "unclear"]
with open(R3 / "transcript_checks.csv", "w", encoding="utf-8", newline="") as h:
    # the columns machine_review/merge.py writes (no reason column)
    w = csv.DictWriter(h, ["entry_uid", "entry_id", "stratum", "old_text", "new_text", "applied", "verdict", "better_text", "reviewed_by", "reviewed_at"])
    w.writeheader()
    for r, v in zip(picks, verdicts):
        w.writerow({"entry_uid": r["entry_uid"], "entry_id": r["entry_id"], "stratum": "x", "old_text": r["old_text"], "new_text": r["new_text"], "applied": r["applied"], "verdict": v,
                    "better_text": (r["new_text"] + " [besser]") if v == "partly" else "", "reviewed_by": "machine:claude-test-r3", "reviewed_at": "2026-10-01T09:00"})
out = W / "rounds_check"
cmd = [sys.executable, str(HERE.parent / "build_data.py"), "--payload", a.payload, "--machine", *a.machine, str(R3), str(W / "missing_round_r4"),
       "--review", a.review, "--out", str(out)] + REST
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
check(res.returncode == 0, "build_data runs with r3 and a missing r4 folder " + res.stderr[-600:])
if res.returncode == 0:
    D = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))
    by = {it["key"]: it for it in D["items"]}
    k = "taxon:" + te[0].lower()
    it = by.get(k)
    check(it is not None and it["rnd"] == 3, f"r3 verdict on {k} is the one shown (round {it and it['rnd']})")
    if it:
        check(any(p["r"] == 1 for p in it.get("prev", [])) or not any(i2.get("rnd") == 1 for i2 in D["items"]), "the superseded r1 verdict is kept as prev")
        check(any(ri for ri in it.get("rows", []) if D["ROWS"][str(ri)]["_rnd"] == 3), "the item uses r3's identities rows")
    kp = "place:" + pe[0].lower()
    check(by.get(kp, {}).get("rnd") == 3, f"r3 place verdict shown for {kp}")
    check([r["n"] for r in D["rounds"]] == [*range(1, len(a.machine) + 1), len(a.machine) + 1], f"rounds {[r['n'] for r in D['rounds']]} (missing r4 skipped)")
    tcs = [it for it in D["items"] if it["t"] == "tc" and it.get("m")]
    check(len(tcs) >= 3 and all(it["m"]["v"] in ("right", "partly", "wrong", "unclear") for it in tcs), f"transcript corrections in the queues carry the machine verdict ({len(tcs)} of 6; right/partly only when sampled)")
    rev = [it for it in tcs if any(v in ("m-wrong", "m-unclear") for v in it["rev"])]
    check(len(rev) == 3, f"machine wrong/unclear corrections are in the review set ({len(rev)})")
    check(any(it["m"]["better"].endswith("[besser]") for it in tcs), "better_text is passed on")
    hk = {v: "habitat:" + hab_ent[str(i)]["label"].lower() for i, v in zip(hord, HV)}
    q = {v: (by.get(k) or {}).get("q") for v, k in hk.items()}
    check(q["ok"] in ("sample", "rest") and q["other"] == "change" and q["none"] == "change" and q["unsure"] == "open", f"habitat verdicts routed to the machine queues {q}")
    check(by.get(hk["other"], {}).get("prop", {}).get("code") == "C1.1" and by.get(hk["other"], {}).get("auto") == 1, "habitat 'other' proposes the class, auto with 2 sources")
    check("gemtext" in by.get(hk["other"], {}).get("src", []), "Gemini's text opinion is labelled as text, not scan")
    check(not any(it["q"] == "habitat" and it["key"] in hk.values() for it in D["items"]), "machine-checked habitats are not repeated in the B list")
print("RESULT:", "FAILED " + str(len(FAILS)) if FAILS else "ALL OK")
sys.exit(1 if FAILS else 0)
