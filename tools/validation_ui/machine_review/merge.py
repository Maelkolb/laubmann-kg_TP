"""Consolidate the machine review answers into decision files.

Reads the answer files of the four checks (taxa text batches, taxa contact
sheets, persons, places, entry dossiers), combines the independent opinions
per written name form (text agent, scan agent, earlier Gemini/Opus readings)
and writes:

    machine_review/identities_machine.csv        review/identities.csv contract + confidence, agreement, model
    machine_review/value_corrections_machine.csv per-mention corrections (review/value_corrections.csv contract)
    machine_review/text_corrections_machine.csv  suggested reading corrections (NOT applied; readings.py contract)
    machine_review/readings_machine.json         the scan agent's readings per mention key (third_reading.json shape)
    machine_review/machine_review.json           verdicts per entity/form/mention for the validation UI
    machine_review/graph_checks.csv              the extraction check per observation of the sample entries
    machine_review/report.md                     numbers and findings

Every row is keyed by the written name form (identities), by
entry_uid + written name + occurrence (mention corrections) or by the entry
text (readings) - never by graph IRIs - so it stays valid after a re-extraction.

    python tools/validation_ui/machine_review/merge.py payload.b64 --work <workdir> --out <workdir>/machine_review \
        [--second-reading second_reading.json] [--third-reading third_reading.json] [--person-matches person_matches.json]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Cache, gbif_match, gbif_species, load_payload, mention_keys, read_json, write_json, written_of  # noqa: E402

MODEL = "claude-sonnet-5-5"
BY = "machine:" + MODEL
IDENTITY_FIELDS = ["section", "name_form", "decision", "target", "authority", "scientific_name", "rank", "lat", "lon", "uncertainty_m",
                   "eunis_match", "reason", "note", "reviewed_by", "reviewed_at", "confidence", "agreement", "sources"]
CORRECTION_FIELDS = ["kind", "entry_uid", "entry_id", "old_value", "occurrence", "action", "new_value", "scientific_name", "gbif_key",
                     "is_bird", "reason", "note", "reviewed_by", "reviewed_at", "confidence", "sources"]
READING_FIELDS = ["entry_uid", "entry_id", "old_text", "new_text", "note", "reviewed_by", "reviewed_at", "confidence", "matters_for"]
NOW = dt.datetime.now().strftime("%Y-%m-%dT%H:%M")


def fnum(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def write_csv(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------- GBIF resolution
class Resolver:
    """Scientific name -> (species-level GBIF key, canonical name, rank); GBIF key -> species key."""

    def __init__(self, cache: Cache):
        self.cache = cache
        self.memo = {}

    def key_of_name(self, sci: str | None, rank_hint: str | None = None):
        sci = (sci or "").strip()
        if not sci or sci.lower() in ("null", "none", "?"):
            return None
        if sci in self.memo:
            return self.memo[sci]
        hit = gbif_match(sci, self.cache)
        res = None
        if hit and hit.get("matchType") in ("EXACT", "FUZZY", "HIGHERRANK") and hit.get("usageKey"):
            rank = (hit.get("rank") or "").upper()
            if hit.get("matchType") == "HIGHERRANK" and (rank_hint or "species") in ("species", "subspecies"):
                res = None      # a species name that GBIF only knows at genus level: no link
            else:
                key = hit.get("acceptedUsageKey") or hit.get("usageKey")
                canonical = hit.get("canonicalName") or sci
                if rank == "SUBSPECIES" and hit.get("speciesKey"):
                    key, canonical, rank = hit["speciesKey"], hit.get("species") or canonical, "SPECIES"
                res = (str(key), canonical, rank.lower())
        self.memo[sci] = res
        return res

    def species_key(self, key: str | None):
        if not key:
            return None
        k = "sk:" + str(key)
        if k in self.memo:
            return self.memo[k]
        sp = gbif_species(key, self.cache) or {}
        rank = (sp.get("rank") or "").upper()
        res = str(sp.get("speciesKey")) if rank == "SUBSPECIES" and sp.get("speciesKey") else str(sp.get("acceptedKey") or key)
        self.memo[k] = (res, (sp.get("species") if rank == "SUBSPECIES" else sp.get("canonicalName")) or "", (("species" if rank == "SUBSPECIES" else rank.lower()) or ""))
        return self.memo[k]


# ---------------------------------------------------------------- taxa
def gemini_answers(work: Path, check: str) -> dict:
    """``<check>/answers_gemini/batch_*.json`` of gemini_verify.py: entity id -> answer."""
    out = {}
    for f in sorted((work / check / "answers_gemini").glob("batch_*.json")):
        try:
            rows = read_json(f)
        except Exception:  # noqa: BLE001 - an unparseable second opinion is no opinion
            continue
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("entity") is not None:
                out[r["entity"]] = r
    return out


def merge_taxa(P, work: Path, resolver: Resolver, second, third):
    T, E = P["taxon"], P["E"]
    keys = mention_keys(P, "taxon")
    forms_of = collections.defaultdict(list)
    for fi, f in enumerate(T["forms"]):
        forms_of[f[2]].append(fi)
    men_of = collections.defaultdict(list)
    for mi, m in enumerate(T["men"]):
        men_of[m[0]].append(mi)

    # --- text batches
    text_ent, text_form, incoming, missing_batches, bad = {}, {}, collections.defaultdict(list), [], []
    for bat in sorted((work / "taxa" / "batches").glob("batch_*.json")):
        ans = work / "taxa" / "answers" / bat.name
        if not ans.exists():
            missing_batches.append(bat.stem)
            continue
        try:
            rows = read_json(ans)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{bat.stem}: {exc}")
            continue
        for r in rows:
            ei = r.get("entity")
            if ei is None:
                continue
            text_ent[ei] = r
            for fr in r.get("forms", []):
                if fr.get("form") is not None:
                    text_form[fr["form"]] = (ei, fr)
            for inc in r.get("incoming", []):
                if inc.get("form") is not None:
                    incoming[inc["form"]].append((ei, inc))
    gem_form = {}
    for ei, r in gemini_answers(work, "taxa").items():
        for fr in r.get("forms", []) or []:
            if isinstance(fr, dict) and fr.get("form") is not None:
                gem_form[fr["form"]] = (ei, fr)
    # --- sheets
    sheet_read = {}      # mention -> answer
    readings_out = {}
    missing_sheets = []
    for man in sorted((work / "sheets").glob("sheet_*.json")):
        ans = work / "sheets" / "answers" / man.name
        if not ans.exists():
            missing_sheets.append(man.stem)
            continue
        try:
            by_n = {int(a["n"]): a for a in read_json(ans)}
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{man.stem}: {exc}")
            continue
        for item in read_json(man):
            a = by_n.get(int(item["n"]))
            if not a:
                continue
            sheet_read[item["mention"]] = a
            readings_out[item["key"]] = {"reading": a.get("reading"), "legible": a.get("legible", True), "kind": a.get("kind"),
                                         "species_de": a.get("species_de"), "sci": a.get("sci"), "confidence": a.get("confidence"),
                                         "agrees_t": a.get("agrees_with_transcription"), "agrees_c": a.get("agrees_with_current"),
                                         "note": a.get("note"), "model": MODEL}

    # --- current species key per entity
    cur_key = {}
    for ei, ent in enumerate(T["ent"]):
        cur_key[ei] = resolver.species_key(ent[2]) if ent[2] else None

    def target_of(sci, species_de, kind, rank=None):
        """A vote: ('none', label) for non-birds, (key, canonical, rank, de) for a taxon, None for no opinion."""
        if kind and kind != "bird":
            return ("none", kind)
        r = resolver.key_of_name(sci, rank)
        if r:
            return (r[0], r[1], r[2], species_de or "")
        return None

    identities, mention_rows, ent_verdict, form_verdict, men_verdict = [], [], {}, {}, {}
    stats = collections.Counter()
    ent_new_key = {}
    for ei, ent in enumerate(T["ent"]):
        te = text_ent.get(ei)
        if not te:
            continue
        link = (te.get("link") or "unsure").lower()
        new = None
        if link == "wrong" or (link != "none" and not ent[2] and te.get("link_sci")):
            r = resolver.key_of_name(te.get("link_sci"), te.get("link_rank"))
            if r:
                new = r
        cur = cur_key[ei]
        verdict = {"link": link, "confidence": fnum(te.get("link_confidence")), "reason": te.get("link_reason") or "",
                   "sci": te.get("link_sci"), "species_de": te.get("link_species_de"), "label": ent[0], "cur_key": ent[2]}
        if new and (not cur or new[0] != cur[0]):
            verdict["new_key"], verdict["new_sci"], verdict["new_rank"] = new
            ent_new_key[ei] = new
            stats["entity relinked" if ent[2] else "entity newly linked"] += 1
        elif link == "wrong" and new and cur and new[0] == cur[0]:
            verdict["link"] = "ok"         # subspecies -> species: already normalised by the resolver
            verdict["note"] = "GBIF-Schlüssel zeigt auf eine Unterart; die Art ist gemeint"
            stats["entity subspecies key normalised"] += 1
        elif link == "ok":
            stats["entity link confirmed"] += 1
        elif link == "none":
            stats["entity no taxon"] += 1
        else:
            stats["entity unsure"] += 1
        ent_verdict[ei] = verdict

    for fi, f in enumerate(T["forms"]):
        ei = f[2]
        ent = T["ent"][ei]
        cur = ent_new_key.get(ei) or cur_key[ei]
        cur_k = cur[0] if cur else None
        votes = []      # (source, target tuple or None, confidence, note)
        for src, tf in (("text", text_form.get(fi)), ("gemtext", gem_form.get(fi))):
            if not tf:
                continue
            _, fr = tf
            d = (fr.get("decision") or "unsure").lower()
            c = fnum(fr.get("confidence")) * (0.95 if src == "gemtext" else 1.0)
            if d == "same":
                votes.append((src, (cur_k, cur[1], cur[2], ent[0]) if cur_k else None, c, fr.get("reason") or ""))
            elif d == "other":
                votes.append((src, target_of(fr.get("sci"), fr.get("species_de"), "bird", fr.get("rank")), c, fr.get("reason") or ""))
            elif d == "none":
                votes.append((src, ("none", "text"), c, fr.get("reason") or ""))
            else:
                votes.append((src, None, c, fr.get("reason") or ""))
        for ei2, inc in incoming.get(fi, []):
            if inc.get("belongs") is True:
                k2 = ent_new_key.get(ei2) or cur_key[ei2]
                if k2:
                    votes.append(("incoming", (k2[0], k2[1], k2[2], T["ent"][ei2][0]), 0.75, inc.get("reason") or ""))
            elif inc.get("belongs") is False:
                pass
        crops = [(mi, sheet_read[mi]) for mi in men_of[fi] if mi in sheet_read]
        for mi, a in crops:
            if not a.get("legible", True):
                continue
            votes.append(("scan", target_of(a.get("sci"), a.get("species_de"), a.get("kind"), a.get("rank")), fnum(a.get("confidence")), a.get("note") or ""))
        for src, table in (("gemini", second), ("opus", third)):
            agg = collections.Counter()
            best = {}
            for mi in men_of[fi]:
                a = table.get(keys[mi]) if table else None
                if not a or not a.get("reading") or a.get("legible") is False:
                    continue
                t = target_of(a.get("sci"), a.get("species_de"), a.get("kind"))
                if t is None:
                    continue
                agg[t[0]] += 1
                if fnum(a.get("confidence")) >= fnum(best.get(t[0], {}).get("confidence")):
                    best[t[0]] = a
            if agg:
                top, n = agg.most_common(1)[0]
                if n >= max(1, sum(agg.values()) * 0.6):
                    a = best[top]
                    votes.append((src, target_of(a.get("sci"), a.get("species_de"), a.get("kind")), fnum(a.get("confidence")) * (0.9 if src == "gemini" else 1.0), a.get("note") or ""))
        # tally
        tally = collections.defaultdict(lambda: [0.0, 0, set(), ""])
        for src, t, c, note in votes:
            if t is None or c <= 0:
                continue
            k = t[0]
            tally[k][0] = max(tally[k][0], c)
            tally[k][1] += 1
            tally[k][2].add(src)
            tally[k][3] = tally[k][3] or note
            tally[k].append(t)
        decision, target, note, conf, agreement, sources = "unsure", None, "", 0.0, 0, ""
        if tally:
            ranked = sorted(tally.items(), key=lambda kv: (kv[1][1], kv[1][0]), reverse=True)
            win_k, (win_c, win_n, win_src, win_note, *ts) = ranked[0]
            rival = [(k, v) for k, v in ranked[1:] if v[0] >= 0.7]
            conf = win_c * (1.0 if win_n >= 2 else 0.85)
            if rival and rival[0][1][1] >= win_n:
                decision, note = "unsure", "widersprüchliche Urteile: " + "; ".join(f"{k}({','.join(sorted(v[2]))})" for k, v in ranked[:3])
                conf = 0.0
            else:
                if rival:
                    conf *= 0.8
                    note = "Gegenstimme: " + ", ".join(f"{k}({','.join(sorted(v[2]))})" for k, v in rival[:2])
                agreement, sources = win_n, "+".join(sorted(win_src))
                if win_k == "none":
                    decision, target = "none", None
                else:
                    decision, target = "same", ts[0]
            note = (win_note[:200] + (" · " + note if note else "")) if decision != "unsure" else note
            # the graph's key was a subspecies and the winner is its species: GBIF itself vouches for that lift
            if decision == "same" and ent[2] and target[0] != ent[2] and cur_key[ei] and target[0] == cur_key[ei][0]:
                agreement += 1
                sources = (sources + "+gbif") if sources else "gbif"
                note = (note + " · " if note else "") + "GBIF-Schlüssel der Unterart auf die Art gehoben"
        stats[f"form {decision}"] += 1
        fv = {"decision": decision, "confidence": round(conf, 2), "agreement": agreement, "sources": sources, "note": note,
              "name": f[0], "ent_label": ent[0]}
        if target:
            fv.update({"key": target[0], "sci": target[1], "rank": target[2], "species_de": target[3],
                       "changed": bool(cur_k) and target[0] != cur_k or not cur_k})
        form_verdict[fi] = fv
        if decision in ("same", "none"):
            row = {"section": "taxa", "name_form": f[0], "decision": decision, "reviewed_by": BY, "reviewed_at": NOW,
                   "confidence": f"{conf:.2f}", "agreement": agreement, "sources": sources, "reason": note[:300], "note": f"Klasse {f[3]}, {f[1]} Belege"}
            if decision == "same":
                row.update({"target": target[3] or target[1], "authority": f"gbif:{target[0]}", "scientific_name": target[1], "rank": target[2]})
            identities.append(row)
        # per-mention deviations from the form decision (multi-mention forms only)
        if f[1] >= 2 and decision == "same":
            for mi, a in crops:
                if not a.get("legible", True) or fnum(a.get("confidence")) < 0.8:
                    continue
                t = target_of(a.get("sci"), a.get("species_de"), a.get("kind"), a.get("rank"))
                if not t or t[0] == target[0]:
                    continue
                m = T["men"][mi]
                e = E[m[1]]
                occ = int(keys[mi].rsplit("|", 1)[1])
                row = {"kind": "taxon", "entry_uid": e[1], "entry_id": e[0], "old_value": written_of(P, "taxon", m), "occurrence": occ,
                       "reviewed_by": BY, "reviewed_at": NOW, "confidence": f"{fnum(a.get('confidence')):.2f}", "sources": "scan",
                       "reason": (a.get("note") or "")[:300]}
                if t[0] == "none":
                    row.update({"action": "drop", "note": f"Lesung: {a.get('reading')}"})
                else:
                    row.update({"action": "replace", "new_value": t[3] or t[1], "scientific_name": t[1], "gbif_key": t[0],
                                "note": f"Lesung: {a.get('reading')}"})
                mention_rows.append(row)
                men_verdict[mi] = {"action": row["action"], "new": row.get("new_value"), "sci": row.get("scientific_name"),
                                   "confidence": row["confidence"], "reading": a.get("reading"), "note": row["reason"]}
    stats["mention corrections"] = len(mention_rows)
    stats["missing taxa batches"] = len(missing_batches)
    stats["missing sheets"] = len(missing_sheets)
    return {"identities": identities, "mentions": mention_rows, "ent": ent_verdict, "form": form_verdict, "men": men_verdict,
            "readings": readings_out, "stats": stats, "missing": missing_batches + missing_sheets, "bad": bad,
            "n_text_entities": len(text_ent), "n_sheet_mentions": len(sheet_read)}


# ---------------------------------------------------------------- persons
def merge_persons(P, work: Path, person_matches):
    PS, E = P["person"], P["E"]
    forms_of = collections.defaultdict(list)
    for fi, f in enumerate(PS["forms"]):
        forms_of[f[2]].append(fi)
    men_of = collections.defaultdict(list)
    for mi, m in enumerate(PS["men"]):
        men_of[m[0]].append(mi)
    wd = read_json(work / "persons" / "wd_cache.json", {}) or {}
    answers, missing, bad = {}, [], []
    batches = {}
    for bat in sorted((work / "persons" / "batches").glob("batch_*.json")):
        for r in read_json(bat):
            batches[r["entity"]] = r
        ans = work / "persons" / "answers" / bat.name
        if not ans.exists():
            missing.append(bat.stem)
            continue
        try:
            for a in read_json(ans):
                if a.get("entity") is not None:
                    answers[a["entity"]] = a
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{bat.stem}: {exc}")
    identities, verdicts = [], {}
    stats = collections.Counter()
    gem = gemini_answers(work, "persons")
    for ei, a in answers.items():
        ent = PS["ent"][ei]
        rec = batches.get(ei, {})
        q = (a.get("wikidata") or "unclear").strip()
        g = (a.get("gnd") or "unclear").strip()
        conf = fnum(a.get("confidence"))
        qid = q if q.upper().startswith("Q") and q[1:].isdigit() else None
        gnd = g if g not in ("none", "unclear", "") else None
        note = []
        xref = False
        # cross-checks
        if qid and gnd:
            x = wd.get(qid) or {}
            gc = next((c for c in rec.get("gnd_candidates", []) if c.get("gnd") == gnd), {})
            if x.get("gnd") and x["gnd"] != gnd and gc.get("wikidata") and gc["wikidata"] != qid:
                note.append("Wikidata und GND widersprechen sich")
                conf = min(conf, 0.4)
            elif (x.get("gnd") == gnd) or (gc.get("wikidata") == qid):
                note.append("Wikidata↔GND stimmig")
                xref = True          # the two authority files point at each other: an independent confirmation
        years = rec.get("years", "")
        if qid and years:
            x = wd.get(qid) or {}
            try:
                first, last = int(years[:4]), int(years[-4:])
                died = int(x["died"]) if x.get("died") else None
                born = int(x["born"]) if x.get("born") else None
                cited_only = set(rec.get("roles", {})) <= {"zitiert"}
                if died and died < first and not cited_only:
                    note.append(f"Kandidat starb {died}, erste Erwähnung {first}")
                    conf = min(conf, 0.3)
                if born and born > last:
                    note.append(f"Kandidat geboren {born}, letzte Erwähnung {last}")
                    conf = min(conf, 0.2)
            except ValueError:
                pass
        pm = (person_matches or {}).get(ent[0]) or {}
        opus = pm.get("decision")
        agreement, sources = 1, "text"
        if opus and qid:
            if opus == qid:
                agreement, sources = 2, "text+opus"
            elif opus not in ("none", "unclear"):
                note.append(f"Opus: {opus}")
                conf = min(conf, 0.5)
        elif opus == "none" and q == "none":
            agreement, sources = 2, "text+opus"
        if xref:
            agreement += 1
            sources += "+xref"
        ga = gem.get(ei)
        if ga:
            gq = (ga.get("wikidata") or "unclear").strip()
            gg = (ga.get("gnd") or "unclear").strip()
            if (qid and gq == qid) or (not qid and gnd and gg == gnd) or (q == "none" and gq == "none"):
                agreement += 1
                sources += "+gemini"
                stats["person gemini agrees"] += 1
            elif gq not in ("unclear", "") and (qid or q == "none"):
                note.append(f"Gemini: {gq}")
                conf = min(conf, 0.6)
                stats["person gemini disagrees"] += 1
        auto_ok = a.get("auto_link_ok")
        decision = None
        if (qid or gnd) and conf >= 0.5:
            decision = "link"
        elif ent[1] and q == "none" and auto_ok is False and conf >= 0.7:
            decision = "nolink"
        verdict = {"wikidata": q, "gnd": g, "confidence": round(conf, 2), "reason": a.get("reason") or "", "auto_link_ok": auto_ok,
                   "decision": decision or "unsure", "agreement": agreement, "sources": sources, "note": "; ".join(note), "label": ent[0]}
        verdicts[ei] = verdict
        stats[f"person {decision or 'unsure'}"] += 1
        if ent[1] and auto_ok is False:
            stats["person auto link rejected"] += 1
        if ent[1] and auto_ok is True:
            stats["person auto link confirmed"] += 1
        if decision:
            auth = " ".join(x for x in ((f"wd:{qid}" if qid else ""), (f"gnd:{gnd}" if gnd else "")) if x)
            identities.append({"section": "persons", "name_form": ent[0], "decision": decision, "target": ent[0], "authority": auth if decision == "link" else "",
                               "reason": (a.get("reason") or "")[:300], "note": "; ".join(note)[:200], "reviewed_by": BY, "reviewed_at": NOW,
                               "confidence": f"{conf:.2f}", "agreement": agreement, "sources": sources})
    stats["missing person batches"] = len(missing)
    return {"identities": identities, "ent": verdicts, "stats": stats, "missing": missing, "bad": bad, "n": len(answers)}


# ---------------------------------------------------------------- places
PLACE_GENERIC = {"see", "weiher", "wald", "wiese", "moos", "moor", "bach", "fluss", "teich", "garten", "park", "damm", "forst", "insel",
                 "berg", "tal", "au", "feld", "felder", "acker", "straße", "strasse", "ufer", "brücke", "bahnhof", "friedhof", "allee", "kanal",
                 "schloss", "schloß", "kirche", "dorf", "stadt", "hof", "wirtschaft", "haus", "sammlung", "museum", "akademie", "wohnung",
                 "zimmer", "gasthof", "post", "hafen", "bad", "küchenfenster", "fenster", "balkon"}


def _km(lat1, lon1, lat2, lon2):
    import math
    try:
        lat1, lon1, lat2, lon2 = (float(x) for x in (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _place_corroboration(v, ent, rec, cand):
    """Deterministic second opinions for a place verdict, independent of the agent's judgement.

    ok           — a Nominatim candidate (queried independently of the linking stage) lies within
                   max(3 km, 2 x uncertainty) of the graph point, or carries the same Wikidata item.
    wrong/unlocated_ok + candidate — the candidate lies within 30 km of the main anchor (the header
                   place of most mentioning entries) while the current point, if any, is > 50 km from it.
    not_a_place  — the label is a generic noun (Feld, Weiher, Gasthof ...).
    """
    srcs = []
    anchors = rec.get("anchors") or []
    main = anchors[0] if anchors else None
    if v == "ok" and ent[1] is not None:
        tol = max(3.0, 2 * (float(ent[3] or 0) / 1000.0))
        for c in rec.get("candidates") or []:
            d = _km(ent[1], ent[2], c.get("lat"), c.get("lon"))
            if (d is not None and d <= tol) or (c.get("wikidata") and ent[5] and c["wikidata"] == ent[5]):
                srcs.append("nominatim")
                break
    elif v in ("wrong", "unlocated_ok") and cand and main:
        d_c = _km(cand.get("lat"), cand.get("lon"), main.get("lat"), main.get("lon"))
        d_g = _km(ent[1], ent[2], main.get("lat"), main.get("lon")) if ent[1] is not None else None
        if d_c is not None and d_c <= 30 and (d_g is None or d_g > 50):
            srcs.append("anchor")
    elif v == "not_a_place" and ent[0].strip().lower() in PLACE_GENERIC:
        srcs.append("generic")
    return srcs


def merge_places(P, work: Path):
    PL = P["place"]
    answers, batches, missing, bad = {}, {}, [], []
    gemini_primary = set()        # batches no Claude agent answered: Gemini's answer is the (single) verdict
    for bat in sorted((work / "places" / "batches").glob("batch_*.json")):
        rows_ = read_json(bat)
        for r in rows_:
            batches[r["entity"]] = r
        ans = work / "places" / "answers" / bat.name
        if not ans.exists() and (work / "places" / "answers_gemini" / bat.name).exists():
            ans = work / "places" / "answers_gemini" / bat.name
            gemini_primary.update(r["entity"] for r in rows_)
        if not ans.exists():
            missing.append(bat.stem)
            continue
        try:
            for a in read_json(ans):
                if a.get("entity") is not None:
                    answers[a["entity"]] = a
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{bat.stem}: {exc}")
    identities, verdicts = [], {}
    stats = collections.Counter()
    gem = gemini_answers(work, "places")
    for ei, a in answers.items():
        ent = PL["ent"][ei]
        rec = batches.get(ei, {})
        v = (a.get("verdict") or "unsure").lower()
        conf = fnum(a.get("confidence"))
        cand = next((c for c in rec.get("candidates", []) if c.get("id") == a.get("candidate")), None) if a.get("candidate") else None
        unc = a.get("uncertainty_m")
        verdict = {"verdict": v, "confidence": round(conf, 2), "reason": a.get("reason") or "", "hint": a.get("location_hint"),
                   "candidate": cand, "uncertainty_m": unc, "label": ent[0]}
        verdicts[ei] = verdict
        stats[f"place {v}"] += 1
        row = None
        if v == "ok" and ent[1] is not None and conf >= 0.6:
            auth = " ".join(x for x in ((f"gn:{ent[4]}" if ent[4] else ""), (f"wd:{ent[5]}" if ent[5] else "")) if x)
            row = {"decision": "link", "authority": auth, "lat": ent[1], "lon": ent[2], "uncertainty_m": ent[3] or unc or ""}
        elif v in ("wrong", "unlocated_ok") and cand and conf >= 0.6:
            auth = " ".join(x for x in ((f"wd:{cand['wikidata']}" if cand.get("wikidata") else ""), (f"osm:{cand['osm']}" if cand.get("osm") else "")) if x)
            row = {"decision": "link", "authority": auth, "lat": cand["lat"], "lon": cand["lon"], "uncertainty_m": unc or 1000}
            stats["place relocated" if ent[1] is not None else "place newly located"] += 1
        elif v == "wrong" and not cand and ent[1] is not None and conf >= 0.7:
            row = {"decision": "nolink", "authority": ""}
        elif v == "not_a_place" and conf >= 0.8:
            row = {"decision": "none", "authority": ""}
        ga = gem.get(ei) if ei not in gemini_primary else None
        gem_agrees = False
        if ga:
            gv = (ga.get("verdict") or "unsure").lower()
            gc = next((c for c in rec.get("candidates", []) if c.get("id") == ga.get("candidate")), None) if ga.get("candidate") else None
            if gv == v and (not cand or (gc and (gc.get("id") == cand.get("id")
                                                 or (_km(gc.get("lat"), gc.get("lon"), cand.get("lat"), cand.get("lon")) or 99) <= 5))):
                gem_agrees = True
                stats["place gemini agrees"] += 1
            elif gv not in ("unsure",):
                verdict["gemini"] = gv
                conf = min(conf, 0.6) if row is None else conf * 0.8
                stats["place gemini disagrees"] += 1
        if row:
            extra = _place_corroboration(v, ent, rec, cand) + (["gemini"] if gem_agrees else [])
            first = "gemini" if ei in gemini_primary else "text"
            verdict["sources"] = [first] + extra
            row.update({"section": "places", "name_form": ent[0], "target": ent[0], "reason": (a.get("reason") or "")[:300],
                        "note": (a.get("location_hint") or "")[:200], "reviewed_by": BY, "reviewed_at": NOW, "confidence": f"{conf:.2f}",
                        "agreement": 1 + len(extra), "sources": "+".join([first] + extra)})
            if extra:
                stats[f"place corroborated ({extra[0]})"] += 1
            identities.append(row)
    stats["missing place batches"] = len(missing)
    return {"identities": identities, "ent": verdicts, "stats": stats, "missing": missing, "bad": bad, "n": len(answers)}


# ---------------------------------------------------------------- entries (extraction check)
def merge_entries(P, work: Path, resolver: Resolver):
    rows, missing_rows, misread_rows, corrections, text_rows, per_entry = [], [], [], [], [], []
    stats = collections.Counter()
    field_err = collections.Counter()
    missing = []
    for d in sorted((work / "entries").glob("dossier_*")):
        dossier = read_json(d / "dossier.json")
        ans = work / "entries" / "answers" / (d.name + ".json")
        if not ans.exists():
            missing.append(d.name)
            continue
        try:
            a = read_json(ans)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{d.name} (unparseable: {exc})")
            continue
        ent = dossier["entry"]
        obs = {o["index"]: o for o in dossier["graph"]["observations"]}
        occ_counter = collections.Counter()
        occ_of = {}
        for o in sorted(dossier["graph"]["observations"], key=lambda o: o["index"]):
            k = o["written"].lower()
            occ_of[o["index"]] = occ_counter[k]
            occ_counter[k] += 1
        n_ok = n_wrong = n_sp = n_un = 0
        for r in a.get("observations", []):
            v = (r.get("verdict") or "unsure").lower()
            stats[f"obs {v}"] += 1
            n_ok += v == "ok"
            n_wrong += v == "wrong"
            n_sp += v == "spurious"
            n_un += v == "unsure"
            for fld in r.get("fields") or []:
                if v == "wrong":
                    field_err[fld] += 1
            o = obs.get(r.get("index"), {})
            corr = r.get("correction") or {}
            rows.append({"entry_id": ent["id"], "entry_uid": ent["uid"], "obs_index": r.get("index"), "occurrence": occ_of.get(r.get("index"), ""),
                         "written": r.get("written") or o.get("written", ""), "taxon": o.get("taxon", ""), "sci": o.get("sci", ""),
                         "count": o.get("count", ""), "verdict": v, "fields": ";".join(r.get("fields") or []),
                         "correction": json.dumps(corr, ensure_ascii=False) if corr else "", "confidence": fnum(r.get("confidence")),
                         "reason": r.get("reason") or ""})
            conf = fnum(r.get("confidence"))
            written = o.get("written") or r.get("written")
            if written and r.get("index") in occ_of and conf >= 0.85:
                base = {"kind": "taxon", "entry_uid": ent["uid"], "entry_id": ent["id"], "old_value": written, "occurrence": occ_of[r["index"]],
                        "reviewed_by": BY, "reviewed_at": NOW, "confidence": f"{conf:.2f}", "sources": "entry-check", "reason": (r.get("reason") or "")[:300]}
                if v == "spurious":
                    corrections.append(dict(base, action="drop"))
                elif v == "wrong" and "species" in (r.get("fields") or []) and corr.get("sci"):
                    t = resolver.key_of_name(corr.get("sci"))
                    if t:
                        corrections.append(dict(base, action="replace", new_value=corr.get("species_de") or t[1], scientific_name=t[1], gbif_key=t[0]))
        for m in a.get("missing", []) or []:
            stats[f"missing {m.get('kind', '?')}"] += 1
            missing_rows.append({"entry_id": ent["id"], "entry_uid": ent["uid"], "kind": m.get("kind"), "text": m.get("text"),
                                 "species_de": m.get("species_de"), "sci": m.get("sci"), "count": m.get("count"), "note": m.get("note")})
        for m in a.get("misreadings", []) or []:
            misread_rows.append({"entry_id": ent["id"], "entry_uid": ent["uid"], "transcribed": m.get("transcribed"), "correct": m.get("correct"),
                                 "matters_for": m.get("matters_for")})
            if m.get("transcribed") and m.get("correct") and m["transcribed"] in dossier["transcription"] and m.get("matters_for") in ("species", "count", "date", "place", "person"):
                text_rows.append({"entry_uid": ent["uid"], "entry_id": ent["id"], "old_text": m["transcribed"], "new_text": m["correct"],
                                  "note": f"betrifft {m.get('matters_for')}", "reviewed_by": BY, "reviewed_at": NOW, "confidence": "",
                                  "matters_for": m.get("matters_for")})
        ef = a.get("entry_fields") or {}
        per_entry.append({"dossier": dossier["dossier"], "entry_id": ent["id"], "entry_uid": ent["uid"], "volume": ent["volume"], "date": ent["date"],
                          "n_obs": len(dossier["graph"]["observations"]), "ok": n_ok, "wrong": n_wrong, "spurious": n_sp, "unsure": n_un,
                          "missing": len(a.get("missing") or []), "date_ok": ef.get("date_ok"), "place_ok": ef.get("place_ok"), "kind_ok": ef.get("kind_ok"),
                          "scan_legible": a.get("scan_legible"), "summary": a.get("summary") or ""})
        for k in ("date_ok", "place_ok", "kind_ok"):
            if ef.get(k) is False:
                stats[f"entry {k} false"] += 1
    return {"rows": rows, "missing_rows": missing_rows, "misreadings": misread_rows, "corrections": corrections, "text": text_rows,
            "per_entry": per_entry, "stats": stats, "field_err": field_err, "missing": missing}


# ---------------------------------------------------------------- habitats (EUNIS)
def merge_habitats(P, work: Path):
    H = P.get("habitat") or {"ent": []}
    answers, missing, bad = {}, [], []
    for bat in sorted((work / "habitats" / "batches").glob("batch_*.json")):
        ans = work / "habitats" / "answers" / bat.name
        if not ans.exists():
            missing.append(bat.stem)
            continue
        try:
            for a in read_json(ans):
                if a.get("entity") is not None:
                    answers[a["entity"]] = a
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{bat.stem}: {exc}")
    gem = gemini_answers(work, "habitats")
    identities, verdicts = [], {}
    stats = collections.Counter()
    for ei, a in answers.items():
        ent = H["ent"][ei]
        v = (a.get("verdict") or "unsure").lower()
        conf = fnum(a.get("confidence"))
        code = (a.get("code") or "").strip() if v == "other" else (ent[1] if v == "ok" else "")
        match = (a.get("match") or ent[2] or "close").lower() if code else ""
        agreement, sources = 1, "text"
        ga = gem.get(ei)
        if ga:
            gv = (ga.get("verdict") or "unsure").lower()
            gcode = (ga.get("code") or "").strip() if gv == "other" else (ent[1] if gv == "ok" else "")
            if gv == "none" and v == "none" or (code and gcode == code):
                agreement, sources = 2, "text+gemini"
                stats["habitat gemini agrees"] += 1
            elif gv != "unsure":
                conf = min(conf, 0.6)
                stats["habitat gemini disagrees"] += 1
        verdicts[ei] = {"verdict": v, "code": code, "match": match, "confidence": round(conf, 2), "agreement": agreement,
                        "sources": sources, "reason": a.get("reason") or "", "label": ent[0], "cur_code": ent[1]}
        stats[f"habitat {v}"] += 1
        row = None
        if code and conf >= 0.6:
            row = {"decision": "link", "authority": f"eunis:{code}", "eunis_match": match if match in ("exact", "close", "broad") else "close"}
        elif v == "none" and conf >= 0.8:
            row = {"decision": "none", "authority": ""}
        if row:
            row.update({"section": "habitats", "name_form": ent[0], "target": ent[0], "reason": (a.get("reason") or "")[:300],
                        "note": "", "reviewed_by": BY, "reviewed_at": NOW, "confidence": f"{conf:.2f}",
                        "agreement": agreement, "sources": sources})
            identities.append(row)
    stats["missing habitat batches"] = len(missing)
    return {"identities": identities, "ent": verdicts, "stats": stats, "missing": missing, "bad": bad, "n": len(answers)}


def merge_transcript_checks(work: Path):
    """The dossier agents' verdicts on the visual reading's corrections."""
    rows = []
    for d in sorted((work / "entries").glob("dossier_*")):
        ans = work / "entries" / "answers" / (d.name + ".json")
        if not ans.exists():
            continue
        try:
            a = read_json(ans)
            dossier = read_json(d / "dossier.json")
        except Exception:  # noqa: BLE001
            continue
        tc = {c["i"]: c for c in dossier.get("transcript_corrections") or []}
        for r in a.get("transcript_checks") or []:
            c = tc.get(r.get("i"))
            if not c:
                continue
            rows.append({"entry_uid": dossier["entry"]["uid"], "entry_id": dossier["entry"]["id"], "stratum": dossier["entry"].get("stratum", ""),
                         "old_text": c["old"], "new_text": c["new"], "applied": "y" if c.get("applied") else "n",
                         "verdict": (r.get("verdict") or "unclear").lower(), "better_text": r.get("better") or "",
                         "reviewed_by": BY, "reviewed_at": NOW})
    return rows


# ---------------------------------------------------------------- report
def report(P, tx, ps, pl, en, out: Path) -> str:
    T = P["taxon"]
    cls = collections.Counter(f[3] for f in T["forms"])
    by_cls = collections.defaultdict(collections.Counter)
    changed = collections.Counter()
    for fi, v in tx["form"].items():
        c = T["forms"][fi][3]
        by_cls[c][v["decision"]] += 1
        if v["decision"] == "same" and v.get("changed"):
            changed[c] += 1
    L = []
    L.append(f"# Maschinelle Prüfung ({MODEL}) — Bericht {NOW[:10]}\n")
    L.append("Grundlage: Export kg_exports_2026-08-19 (Payload der Abgleich-Oberfläche v4). Alle Entscheidungen sind an den geschriebenen Namen, "
             "die Normdaten-Kennung und den Belegschlüssel (entry_uid|Name|Vorkommen) gebunden, nicht an Graph-IRIs.\n")
    L.append("## Arten (GBIF)\n")
    L.append(f"- Entitäten mit Textprüfung: {tx['n_text_entities']} von {len(T['ent'])} (fehlende Batches: {tx['stats']['missing taxa batches']})")
    L.append(f"- Belege mit Bildprüfung (Zeilenbilder): {tx['n_sheet_mentions']} (fehlende Blätter: {tx['stats']['missing sheets']})")
    for k in ("entity link confirmed", "entity subspecies key normalised", "entity relinked", "entity newly linked", "entity no taxon", "entity unsure"):
        L.append(f"- {k}: {tx['stats'][k]}")
    L.append("\n| Klasse | Namen | same | none | unsure | davon umverknüpft |\n|---|---|---|---|---|---|")
    for c in "ABCL":
        d = by_cls[c]
        L.append(f"| {c} | {cls[c]} | {d['same']} | {d['none']} | {d['unsure']} | {changed[c]} |")
    L.append(f"\n- Korrekturen einzelner Belege (value_corrections_machine.csv): {tx['stats']['mention corrections']}")
    hi = sum(1 for r in tx["identities"] if fnum(r["confidence"]) >= 0.9 and int(r["agreement"]) >= 2)
    L.append(f"- identities_machine.csv, Abschnitt taxa: {sum(1 for r in tx['identities'])} Zeilen, davon {hi} mit Konfidenz ≥ 0.9 und ≥ 2 übereinstimmenden Quellen")
    L.append("\n## Personen (Wikidata / GND)\n")
    L.append(f"- geprüfte Personen: {ps['n']} (fehlende Batches: {ps['stats']['missing person batches']})")
    for k in ("person link", "person nolink", "person unsure", "person auto link confirmed", "person auto link rejected"):
        L.append(f"- {k}: {ps['stats'][k]}")
    n_pass = sum(1 for r in ps['identities'] if float(r['confidence']) >= 0.9 and int(r['agreement']) >= 2)
    L.append(f"- Zeilen in identities_machine.csv: {len(ps['identities'])} (mit GND: {sum(1 for r in ps['identities'] if 'gnd:' in r['authority'])}), "
             f"davon {n_pass} mit Konfidenz ≥ 0.9 und ≥ 2 Quellen")
    L.append("\n## Orte (GeoNames / OSM)\n")
    L.append(f"- geprüfte Orte: {pl['n']} (fehlende Batches: {pl['stats']['missing place batches']})")
    for k in sorted(k for k in pl["stats"] if k.startswith("place ")):
        L.append(f"- {k}: {pl['stats'][k]}")
    n_pass = sum(1 for r in pl['identities'] if float(r['confidence']) >= 0.9 and int(r['agreement']) >= 2)
    L.append(f"- Zeilen in identities_machine.csv: {len(pl['identities'])}, davon {n_pass} mit Konfidenz ≥ 0.9 und ≥ 2 Quellen "
             "(zweite Quelle: Nominatim-Kandidat am Graph-Punkt / Kandidat ≤ 30 km vom Hauptanker / Gattungswort)")
    L.append("\n## Extraktionsprüfung (Stichprobe von Einträgen)\n")
    n_e = len(en["per_entry"])
    tot = sum(en["stats"][k] for k in en["stats"] if k.startswith("obs "))
    L.append(f"- Einträge geprüft: {n_e} (fehlend: {len(en['missing'])}); Beobachtungen beurteilt: {tot}")
    for k in ("obs ok", "obs wrong", "obs spurious", "obs unsure"):
        L.append(f"- {k}: {en['stats'][k]}" + (f" ({100 * en['stats'][k] / tot:.1f} %)" if tot else ""))
    L.append("- fehlende Datensätze laut Text: " + ", ".join(f"{k[8:]} {v}" for k, v in en["stats"].items() if k.startswith("missing ")))
    L.append("- falsche Felder: " + ", ".join(f"{k} {v}" for k, v in en["field_err"].most_common()))
    L.append("- Eintragsfelder falsch: " + ", ".join(f"{k[6:]} {v}" for k, v in en["stats"].items() if k.startswith("entry ")))
    L.append(f"- Vorschläge für Lesekorrekturen (text_corrections_machine.csv, nicht angewendet): {len(en['text'])}")
    L.append("\n## Dateien\n")
    L.append("- `identities_machine.csv` — Vertrag von review/identities.csv plus confidence/agreement/sources; Pipeline: `review.machine` (nur Zeilen ≥ Schwelle, menschliche Entscheidungen gehen vor)")
    L.append("- `value_corrections_machine.csv` — einzelne Belege (Kontrakt review/value_corrections.csv)")
    L.append("- `text_corrections_machine.csv` — Lesevorschläge, nur zur Sichtung")
    L.append("- `readings_machine.json` — Lesungen des Bild-Agenten je Belegschlüssel")
    L.append("- `machine_review.json` — Urteile für die Abgleich-Oberfläche (Kasten „Maschinelle Prüfung“)")
    L.append("- `graph_checks.csv`, `graph_checks_missing.csv`, `graph_checks_misreadings.csv`, `graph_checks_entries.csv` — Extraktionsprüfung")
    if tx["bad"] or ps["bad"] or pl["bad"]:
        L.append("\n## Nicht lesbare Antwortdateien\n")
        for b in tx["bad"] + ps["bad"] + pl["bad"]:
            L.append(f"- {b}")
    txt = "\n".join(L) + "\n"
    (out / "report.md").write_text(txt, encoding="utf-8")
    return txt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--second-reading", default=None)
    ap.add_argument("--third-reading", default=None)
    ap.add_argument("--person-matches", default=None)
    ap.add_argument("--gbif-cache", default=None)
    args = ap.parse_args()
    P = load_payload(args.payload)
    work, out = Path(args.work), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    resolver = Resolver(Cache(args.gbif_cache or work / "gbif_cache.json"))
    second = read_json(args.second_reading, {}) if args.second_reading else {}
    third = read_json(args.third_reading, {}) if args.third_reading else {}
    pm = read_json(args.person_matches, {}) if args.person_matches else {}

    tx = merge_taxa(P, work, resolver, second, third)
    ps = merge_persons(P, work, pm)
    pl = merge_places(P, work)
    en = merge_entries(P, work, resolver)
    hb = merge_habitats(P, work)
    tchecks = merge_transcript_checks(work)
    resolver.cache.flush()

    write_csv(out / "identities_machine.csv", IDENTITY_FIELDS, tx["identities"] + ps["identities"] + pl["identities"] + hb["identities"])
    write_csv(out / "transcript_checks.csv", ["entry_uid", "entry_id", "stratum", "old_text", "new_text", "applied", "verdict", "better_text",
                                              "reviewed_by", "reviewed_at"], tchecks)
    write_csv(out / "value_corrections_machine.csv", CORRECTION_FIELDS, tx["mentions"] + en["corrections"])
    write_csv(out / "text_corrections_machine.csv", READING_FIELDS, en["text"])
    write_json(out / "readings_machine.json", tx["readings"], indent=0)
    write_json(out / "machine_review.json", {"model": MODEL, "built": NOW,
                                             "taxon": {"ent": tx["ent"], "form": tx["form"], "men": tx["men"]},
                                             "person": {"ent": ps["ent"]}, "place": {"ent": pl["ent"]},
                                             "habitat": {"ent": hb["ent"]}}, indent=0)
    write_csv(out / "graph_checks.csv", ["entry_id", "entry_uid", "obs_index", "occurrence", "written", "taxon", "sci", "count", "verdict", "fields",
                                         "correction", "confidence", "reason"], en["rows"])
    write_csv(out / "graph_checks_missing.csv", ["entry_id", "entry_uid", "kind", "text", "species_de", "sci", "count", "note"], en["missing_rows"])
    write_csv(out / "graph_checks_misreadings.csv", ["entry_id", "entry_uid", "transcribed", "correct", "matters_for"], en["misreadings"])
    write_csv(out / "graph_checks_entries.csv", ["dossier", "entry_id", "entry_uid", "volume", "date", "n_obs", "ok", "wrong", "spurious", "unsure",
                                                 "missing", "date_ok", "place_ok", "kind_ok", "scan_legible", "summary"], en["per_entry"])
    txt = report(P, tx, ps, pl, en, out)
    extra = ["\n## Habitate (EUNIS)\n", f"- geprüfte Habitate: {hb['n']} (fehlende Batches: {hb['stats']['missing habitat batches']})"]
    extra += [f"- {k}: {v}" for k, v in sorted(hb["stats"].items()) if k.startswith("habitat ")]
    n_pass = sum(1 for r in hb["identities"] if float(r["confidence"]) >= 0.9 and int(r["agreement"]) >= 2)
    extra.append(f"- Zeilen in identities_machine.csv: {len(hb['identities'])}, davon {n_pass} mit Konfidenz ≥ 0.9 und ≥ 2 Quellen")
    vc = collections.Counter(r["verdict"] for r in tchecks)
    extra += ["\n## Lesekorrekturen der visuellen Lesung (Stichprobe der Dossiers)\n",
              f"- beurteilt: {len(tchecks)}: " + ", ".join(f"{k} {v} ({100 * v / max(1, len(tchecks)):.0f} %)" for k, v in vc.most_common())]
    for ap_ in ("y", "n"):
        sub_ = [r for r in tchecks if r["applied"] == ap_]
        if sub_:
            c = collections.Counter(r["verdict"] for r in sub_)
            extra.append(f"- {'angewendet' if ap_ == 'y' else 'nicht angewendet'} ({len(sub_)}): " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    gem_lines = [f"- {k}: {v}" for st in (ps["stats"], pl["stats"], hb["stats"]) for k, v in sorted(st.items()) if "gemini" in k]
    if gem_lines:
        extra += ["\n## Zweitmeinung Gemini\n"] + gem_lines
    txt += "\n".join(extra) + "\n"
    (out / "report.md").write_text(txt, encoding="utf-8")
    print(txt)
    if tx["missing"] or ps["missing"] or pl["missing"] or en["missing"] or hb["missing"]:
        print("MISSING:", tx["missing"], ps["missing"], pl["missing"], en["missing"], hb["missing"])


if __name__ == "__main__":
    main()
