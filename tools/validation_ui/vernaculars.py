"""German vernacular names of the linked taxa (GBIF + Wikidata), the evidence the
UI uses to tell an attested name ("Dompfaff" for Pyrrhula pyrrhula) from an
unattested one ("Kameradeneingang").

    python tools/validation_ui/vernaculars.py triples.pkl vernaculars.json

Resumable: keys already in the output file are not fetched again.
GBIF: /species/{key}/vernacularNames (language deu). Wikidata: rdfs:label and
skos:altLabel (de) of the item with GBIF taxon ID (P846) = key.
"""
import json
import os
import pickle
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "laubmann-kg validation UI (research use)"}


def get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def taxon_keys(triples_path: str) -> list[str]:
    keys = set()
    for s, p, o in pickle.load(open(triples_path, "rb")):
        if str(p).endswith("/taxonID") and "gbif.org/species/" in str(o):
            keys.add(str(o).rsplit("/", 1)[-1])
    return sorted(keys)


def main(triples_path: str, out_path: str) -> None:
    keys = taxon_keys(triples_path)
    V = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    todo = [k for k in keys if "gbif" not in V.get(k, {})]
    print(len(keys), "keys,", len(todo), "to fetch", flush=True)
    for i, k in enumerate(todo):
        try:
            names, off = [], 0
            while True:
                j = get(f"https://api.gbif.org/v1/species/{k}/vernacularNames?limit=1000&offset={off}")
                names += [x["vernacularName"] for x in j.get("results", []) if x.get("language") in ("deu", "ger", "de")]
                if j.get("endOfRecords", True):
                    break
                off += 1000
            V.setdefault(k, {})["gbif"] = sorted(set(names))
        except Exception as exc:  # noqa: BLE001 - a failed key is retried next run
            print("GBIF failed", k, exc)
        if i % 100 == 0:
            json.dump(V, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
        time.sleep(0.05)
    todo = [k for k in keys if "wd" not in V.get(k, {})]
    for c in range(0, len(todo), 200):
        chunk = todo[c:c + 200]
        q = ("SELECT ?g ?item ?l WHERE { VALUES ?g { " + " ".join(f'"{k}"' for k in chunk) + " } ?item wdt:P846 ?g . "
             "{ ?item rdfs:label ?l } UNION { ?item skos:altLabel ?l } FILTER(lang(?l) = \"de\") }")
        try:
            j = get("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q))
            for k in chunk:
                V.setdefault(k, {}).setdefault("wd", [])
            for b in j["results"]["bindings"]:
                d = V[b["g"]["value"]]
                d["wd"].append(b["l"]["value"])
                d["qid"] = b["item"]["value"].rsplit("/", 1)[-1]
        except Exception as exc:  # noqa: BLE001
            print("Wikidata failed", c, exc)
        time.sleep(1)
    for d in V.values():
        if "wd" in d:
            d["wd"] = sorted(set(d["wd"]))
    json.dump(V, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    print(len(V), "keys;", sum(1 for d in V.values() if d.get("gbif") or d.get("wd")), "with German names")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
