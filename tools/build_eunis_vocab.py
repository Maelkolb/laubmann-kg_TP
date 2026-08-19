"""Build data/eunis_habitats.csv from the Eionet Data Dictionary SKOS vocabulary
of the EUNIS habitat classification (2012, amended).

    python tools/build_eunis_vocab.py [--rdf <local eunishabitats.rdf>] [--out data/eunis_habitats.csv]

Source: https://dd.eionet.europa.eu/vocabulary/biodiversity/eunishabitats/ (EEA,
standard re-use policy). Concept URIs are code-based
(http://eunis.eea.europa.eu/eunishabitats/G1.2); each concept also carries a
skos:exactMatch to the EUNIS web-site habitat page (…/habitats/<id>). The CSV
(code, label, level, parent, uri, site_uri, definition) is what
``linking/habitats.py`` loads: levels 1–3 go into the LLM prompt, every code is
accepted as an answer.
"""

from __future__ import annotations

import argparse
import csv
import urllib.request
from pathlib import Path

from rdflib import Graph, RDF, SKOS

SOURCE = "https://dd.eionet.europa.eu/vocabulary/biodiversity/eunishabitats/rdf"
FIELDS = ["code", "label", "level", "parent", "uri", "site_uri", "definition"]


def level_of(code: str) -> int:
    # A -> 1, A1 -> 2, A1.1 -> 3, A1.11 -> 4, … (X habitat complexes follow the same scheme)
    if "." not in code:
        return 1 if len(code) == 1 else 2
    head, tail = code.split(".", 1)
    return 2 + len(tail)


def parent_of(code: str) -> str:
    if "." not in code:
        return "" if len(code) == 1 else code[0]
    head, tail = code.split(".", 1)
    return head if len(tail) == 1 else f"{head}.{tail[:-1]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rdf", default=None, help="local copy of the vocabulary RDF (default: download)")
    ap.add_argument("--out", default="data/eunis_habitats.csv")
    args = ap.parse_args()
    g = Graph()
    if args.rdf:
        g.parse(args.rdf, format="xml")
    else:
        req = urllib.request.Request(SOURCE, headers={"User-Agent": "laubmann-kg (HistOrniGraph)", "Accept": "application/rdf+xml"})
        g.parse(data=urllib.request.urlopen(req, timeout=600).read(), format="xml")
    rows = []
    for c in g.subjects(RDF.type, SKOS.Concept):
        code = str(g.value(c, SKOS.notation) or "").strip()
        if not code:
            continue
        site = next((str(o) for o in g.objects(c, SKOS.exactMatch) if "eunis.eea.europa.eu/habitats/" in str(o)), "")
        rows.append({"code": code, "label": str(g.value(c, SKOS.prefLabel) or "").strip(), "level": level_of(code),
                     "parent": parent_of(code), "uri": str(c), "site_uri": site,
                     "definition": " ".join(str(g.value(c, SKOS.definition) or "").split())[:400]})
    rows.sort(key=lambda r: (r["code"][0], r["level"], r["code"]))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} EUNIS habitat types to {out}")


if __name__ == "__main__":
    main()
