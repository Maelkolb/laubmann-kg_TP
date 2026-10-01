#!/usr/bin/env python3
"""Graph explorer for the Laubmann knowledge graph (ontology 0.7.0).

Reads an EXPORTED graph (Turtle, N-Triples, …) and writes one self-contained
HTML page: every triple of the file is packed into the page (columnar,
gzip + base64, decoded in the browser with DecompressionStream), so whatever
the explorer shows is really in the published graph.

    python tools/explorer/build_graph_explorer.py <graph.ttl> <out.html>
        [--scans drive | local:<dir relative to out.html>]

Class and property labels (DE/EN) come from ontologies/laubmann.ttl, the labels
of controlled values from ontologies/controlled_vocabularies.ttl. Page scans
load from Google Drive by file id (configs/drive_scan_files.json; visible to
accounts with access to the HistOrniGraph_output folder) with the local JPEGs
(data/pages_jpg) as fallback, or local first with ``--scans local:<dir>``.

Only needs rdflib; the page itself needs no network except scans and map tiles.
See tools/explorer/README_graph_explorer.md.
"""
from __future__ import annotations

import argparse
import array
import base64
import datetime as _dt
import gzip
import json
import os
import struct
import sys
import time
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rdflib.util import guess_format

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

# Compact IRIs in the page ("pfx:local"); the page expands them for display
# and copying. Order does not matter: the longest matching namespace wins.
PREFIXES = {
    "data": "https://w3id.org/laubmann-kg/data/",
    "lkg": "https://w3id.org/laubmann-kg/ontology#",
    "dwc": "http://rs.tdwg.org/dwc/terms/",
    "dwciri": "http://rs.tdwg.org/dwc/iri/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "prov": "http://www.w3.org/ns/prov#",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "gsp": "http://www.opengis.net/ont/geosparql#",
    "schema": "https://schema.org/",
    "rico": "https://www.ica.org/standards/RiC/ontology#",
    "gbif": "https://www.gbif.org/species/",
    "wd": "http://www.wikidata.org/entity/",
    "gn": "https://sws.geonames.org/",
    "eunis": "http://eunis.eea.europa.eu/eunishabitats/",
    "gnd": "https://d-nb.info/gnd/",
}

# Labels for the standard terms the graph uses (the ontology labels only its
# own lkg: terms). {compact: (de, en)}
EXTERNAL_LABELS = {
    "rdf:type": ("Typ", "type"),
    "rdfs:label": ("Bezeichnung", "label"),
    "rdfs:comment": ("Kommentar", "comment"),
    "rdfs:seeAlso": ("siehe auch", "see also"),
    "dcterms:identifier": ("Kennung", "identifier"),
    "dcterms:isPartOf": ("ist Teil von", "is part of"),
    "dcterms:hasPart": ("hat Teil", "has part"),
    "dcterms:temporal": ("Zeitraum", "temporal coverage"),
    "dcterms:type": ("DCMI-Typ", "DCMI type"),
    "dcterms:description": ("Beschreibung", "description"),
    "dcterms:title": ("Titel", "title"),
    "dwc:eventDate": ("Datum", "event date"),
    "dwc:verbatimEventDate": ("Datum (wörtlich)", "verbatim event date"),
    "dwc:eventTime": ("Uhrzeit", "event time"),
    "dwc:fieldNotes": ("Eintragstext", "field notes"),
    "dwc:verbatimLocality": ("Ort (wörtlich)", "verbatim locality"),
    "dwc:basisOfRecord": ("Nachweisgrundlage", "basis of record"),
    "dwc:occurrenceStatus": ("Vorkommensstatus", "occurrence status"),
    "dwc:occurrenceRemarks": ("Bemerkungen", "occurrence remarks"),
    "dwc:individualCount": ("Anzahl", "individual count"),
    "dwc:habitat": ("Habitat (wörtlich)", "habitat (verbatim)"),
    "dwciri:habitat": ("Habitat", "habitat"),
    "dwciri:recordedBy": ("beobachtet von", "recorded by"),
    "dwciri:toTaxon": ("zu Taxon", "to taxon"),
    "dwc:behavior": ("Verhalten", "behaviour"),
    "dwc:sex": ("Geschlecht", "sex"),
    "dwc:lifeStage": ("Altersstadium", "life stage"),
    "dwc:reproductiveCondition": ("Fortpflanzungszustand", "reproductive condition"),
    "dwc:vitality": ("Vitalität", "vitality"),
    "dwc:identificationQualifier": ("Bestimmungsvorbehalt", "identification qualifier"),
    "dwc:verbatimIdentification": ("Bestimmung (wörtlich)", "verbatim identification"),
    "dwc:associatedReferences": ("Literatur", "associated references"),
    "dwc:minimumElevationInMeters": ("Höhe min. (m)", "minimum elevation (m)"),
    "dwc:maximumElevationInMeters": ("Höhe max. (m)", "maximum elevation (m)"),
    "dwc:scientificName": ("wissenschaftlicher Name", "scientific name"),
    "dwc:vernacularName": ("Trivialname", "vernacular name"),
    "dwc:taxonRank": ("Rang", "taxon rank"),
    "dwc:taxonID": ("Taxon-ID", "taxon ID"),
    "dwc:kingdom": ("Reich", "kingdom"),
    "dwc:phylum": ("Stamm", "phylum"),
    "dwc:class": ("Klasse", "class"),
    "dwc:order": ("Ordnung", "order"),
    "dwc:family": ("Familie", "family"),
    "dwc:genus": ("Gattung", "genus"),
    "dwc:decimalLatitude": ("Breite (dez.)", "decimal latitude"),
    "dwc:decimalLongitude": ("Länge (dez.)", "decimal longitude"),
    "dwc:geodeticDatum": ("geodätisches Datum", "geodetic datum"),
    "dwc:coordinateUncertaintyInMeters": ("Koordinatenunsicherheit (m)", "coordinate uncertainty (m)"),
    "dwc:georeferenceSources": ("Georeferenzquelle", "georeference sources"),
    "geo:lat": ("Breite", "latitude"),
    "geo:long": ("Länge", "longitude"),
    "gsp:hasGeometry": ("hat Geometrie", "has geometry"),
    "gsp:asWKT": ("Geometrie (WKT)", "as WKT"),
    "skos:prefLabel": ("Vorzugsbezeichnung", "preferred label"),
    "skos:altLabel": ("Namensvariante", "alternative label"),
    "skos:notation": ("Notation (Kennung)", "notation (id)"),
    "skos:inScheme": ("in Schema", "in scheme"),
    "skos:broader": ("Oberbegriff", "broader"),
    "skos:exactMatch": ("exakte Entsprechung", "exact match"),
    "skos:closeMatch": ("enge Entsprechung", "close match"),
    "skos:broadMatch": ("weitere Entsprechung", "broad match"),
    "skos:note": ("Anmerkung", "note"),
    "skos:definition": ("Definition", "definition"),
    "prov:wasDerivedFrom": ("abgeleitet aus", "was derived from"),
    "prov:wasGeneratedBy": ("erzeugt durch", "was generated by"),
    "prov:used": ("verwendete", "used"),
    "prov:wasAssociatedWith": ("ausgeführt von", "was associated with"),
    "prov:startedAtTime": ("gestartet", "started at"),
    "prov:endedAtTime": ("beendet", "ended at"),
    "schema:name": ("Name", "name"),
    "schema:image": ("Bild", "image"),
    "schema:mentions": ("erwähnt", "mentions"),
    "owl:sameAs": ("identisch mit (owl:sameAs)", "same as (owl:sameAs)"),
    # classes that are not lkg: terms
    "skos:Concept": ("Konzept", "Concept"),
    "skos:ConceptScheme": ("Konzeptschema", "Concept scheme"),
    "gsp:Geometry": ("Geometrie", "Geometry"),
    "prov:Activity": ("Extraktionslauf", "Extraction run"),
    "prov:SoftwareAgent": ("Software-Agent", "Software agent"),
    "prov:Entity": ("Prompt (prov:Entity)", "Prompt (prov:Entity)"),
    "dcmitype:Text": ("Text", "Text"),
    "dcmitype:StillImage": ("Bild", "Still image"),
    "dcmitype:PhysicalObject": ("Objekt", "Physical object"),
}

# Controlled values on standard (dwc) properties: the ontology names the
# scheme only for its own properties (rdfs:seeAlso).
DWC_SCHEMES = {
    "dwc:sex": "lkg:sexScheme",
    "dwc:lifeStage": "lkg:lifeStageScheme",
    "dwc:vitality": "lkg:vitalityScheme",
    "dwc:occurrenceStatus": "lkg:occurrenceStatusScheme",
    "dwc:taxonRank": "lkg:taxonRankScheme",
}

TYPES = {"u8": ("B", 1), "u16": ("H", 2), "u32": ("I", 4), "i32": ("i", 4)}


def compact(iri: str) -> str:
    best = None
    for pfx, ns in PREFIXES.items():
        if iri.startswith(ns) and (best is None or len(ns) > len(PREFIXES[best])):
            best = pfx
    if best is None:
        return iri
    return best + ":" + iri[len(PREFIXES[best]):]


class _Packer(Graph):
    """rdflib parse target that interns terms into integer tables instead of
    storing triples (a 2M-triple graph fits in a few hundred MB)."""

    def __init__(self):
        super().__init__()
        self.node_ix: dict = {}
        self.nodes: list[str] = []
        self.pred_ix: dict = {}
        self.preds: list[str] = []
        self.lit_ix: dict = {}
        self.lits: list[str] = []
        self.lit_dt = array.array("B")
        self.lit_lang = array.array("B")
        self.dt_ix: dict = {"": 0}
        self.lang_ix: dict = {"": 0}
        self.keys: list[int] = []  # packed (s, p, o) per triple

    def _node(self, t) -> int:
        i = self.node_ix.get(t)
        if i is None:
            i = self.node_ix[t] = len(self.nodes)
            self.nodes.append("_:" + str(t) if isinstance(t, BNode) else compact(str(t)))
        return i

    def _lit(self, t: Literal) -> int:
        dt = compact(str(t.datatype)) if t.datatype is not None else ""
        lang = t.language or ""
        key = (str(t), dt, lang)
        i = self.lit_ix.get(key)
        if i is None:
            i = self.lit_ix[key] = len(self.lits)
            self.lits.append(str(t))
            d = self.dt_ix.setdefault(dt, len(self.dt_ix))
            g = self.lang_ix.setdefault(lang, len(self.lang_ix))
            if d > 255 or g > 255:
                raise SystemExit("more than 255 datatypes or languages")
            self.lit_dt.append(d)
            self.lit_lang.append(g)
        return i

    def add(self, triple):  # called by the rdflib parsers
        s, p, o = triple
        si = self._node(s)
        pi = self.pred_ix.get(p)
        if pi is None:
            pi = self.pred_ix[p] = len(self.preds)
            self.preds.append(compact(str(p)))
        if isinstance(o, Literal):
            oi = (self._lit(o) << 1) | 1
        else:
            oi = self._node(o) << 1
        self.keys.append((si << 48) | (pi << 34) | oi)
        return self


def ontology_info(onto_dir: Path) -> dict:
    g = Graph()
    for name in ("laubmann.ttl", "controlled_vocabularies.ttl"):
        path = onto_dir / name
        if path.exists():
            g.parse(path, format="turtle")
        else:
            print(f"warning: {path} not found; labels fall back to IRIs", file=sys.stderr)
    labels: dict[str, dict[str, str]] = {}
    for c, (de, en) in EXTERNAL_LABELS.items():
        labels[c] = {"de": de, "en": en}
    for s, o in g.subject_objects(RDFS.label):
        if isinstance(s, URIRef) and isinstance(o, Literal):
            labels.setdefault(compact(str(s)), {})[o.language or "en"] = str(o)
    defs: dict[str, str] = {}
    for s, o in g.subject_objects(RDFS.comment):
        if isinstance(s, URIRef) and isinstance(o, Literal) and (o.language in (None, "en")):
            c = compact(str(s))
            if c.startswith("lkg:"):
                defs[c] = str(o)
    sub_prop = {}
    for s, o in g.subject_objects(RDFS.subPropertyOf):
        sub_prop[compact(str(s))] = compact(str(o))
    schemes: dict[str, dict] = {}
    for sch in g.subjects(RDF.type, SKOS.ConceptScheme):
        d = {}
        for lab in g.objects(sch, SKOS.prefLabel):
            d[lab.language or "en"] = str(lab)
        nota = g.value(sch, SKOS.notation)
        if nota is not None:
            d["notation"] = str(nota)
        space = g.value(sch, URIRef("http://rdfs.org/ns/void#uriSpace"))
        if space is not None:
            d["uriSpace"] = str(space)
        schemes[compact(str(sch))] = d
    concepts: dict[str, dict[str, dict]] = {}
    for c in g.subjects(RDF.type, SKOS.Concept):
        sch = g.value(c, SKOS.inScheme)
        nota = g.value(c, SKOS.notation)
        if sch is None or nota is None:
            continue
        concepts.setdefault(compact(str(sch)), {})[str(nota)] = {
            (lab.language or "en"): str(lab) for lab in g.objects(c, SKOS.prefLabel)}
    prop_scheme = dict(DWC_SCHEMES)
    for p, sch in g.subject_objects(RDFS.seeAlso):
        cs = compact(str(sch))
        if cs in schemes and cs in concepts:
            prop_scheme[compact(str(p))] = cs
    vocab = {p: concepts[s] for p, s in prop_scheme.items() if s in concepts}
    version = None
    for onto in g.subjects(RDF.type, OWL.Ontology):
        if str(onto) == "https://w3id.org/laubmann-kg/ontology":
            v = g.value(onto, OWL.versionInfo)
            version = str(v) if v is not None else None
    return {"labels": labels, "defs": defs, "subProp": sub_prop, "schemes": schemes,
            "vocab": vocab, "propScheme": prop_scheme, "ontologyVersion": version}


def pack(pk: _Packer) -> tuple[dict, list[tuple[str, str, array.array]]]:
    keys = pk.keys
    keys.sort()
    # drop duplicate triples (possible when several files are concatenated)
    uniq = []
    last = None
    for k in keys:
        if k != last:
            uniq.append(k)
            last = k
    pk.keys = []
    n_nodes = len(pk.nodes)
    s_off = array.array("I", [0]) * (n_nodes + 1)
    wide = len(pk.preds) > 255
    t_p = array.array("H" if wide else "B")
    t_o = array.array("i")
    m34 = (1 << 34) - 1
    for k in uniq:
        s = k >> 48
        s_off[s + 1] += 1
        t_p.append((k >> 34) & 0x3FFF)
        o = k & m34
        t_o.append(-((o >> 1) + 1) if o & 1 else (o >> 1))
    for i in range(n_nodes):
        s_off[i + 1] += s_off[i]
    arrays = [
        ("sOff", "u32", s_off),
        ("tP", "u16" if wide else "u8", t_p),
        ("tO", "i32", t_o),
        ("litDt", "u8", pk.lit_dt),
        ("litLang", "u8", pk.lit_lang),
    ]
    meta = {
        "triples": len(uniq),
        "nodes": pk.nodes,
        "preds": pk.preds,
        "lits": pk.lits,
        "dts": [d for d, _ in sorted(pk.dt_ix.items(), key=lambda x: x[1])],
        "langs": [d for d, _ in sorted(pk.lang_ix.items(), key=lambda x: x[1])],
    }
    return meta, arrays


def page_identifiers(meta: dict, arrays) -> list[str]:
    """dcterms:identifier of every lkg:DiaryPage node (for the scan id table)."""
    nodes, preds, lits = meta["nodes"], meta["preds"], meta["lits"]
    a = {name: arr for name, _, arr in arrays}
    try:
        p_type = preds.index("rdf:type")
        p_id = preds.index("dcterms:identifier")
    except ValueError:
        return []
    try:
        page_cls = nodes.index("lkg:DiaryPage")
    except ValueError:
        return []
    s_off, t_p, t_o = a["sOff"], a["tP"], a["tO"]
    out = []
    for s in range(len(nodes)):
        lo, hi = s_off[s], s_off[s + 1]
        is_page = False
        ident = None
        for i in range(lo, hi):
            if t_p[i] == p_type and t_o[i] == page_cls:
                is_page = True
            elif t_p[i] == p_id and t_o[i] < 0:
                ident = lits[-t_o[i] - 1]
        if is_page and ident:
            out.append(ident)
    return out


def encode_blob(meta: dict, arrays) -> bytes:
    """[u32 json length][json][pad][arrays, 8-byte aligned] → gzip."""
    descr = []
    # first pass with placeholder offsets to get the JSON size stable
    for name, typ, arr in arrays:
        descr.append({"name": name, "type": typ, "offset": 0, "length": len(arr)})
    meta["arrays"] = descr
    for _ in range(3):  # offsets change the JSON length; iterate to a fixpoint
        js = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        pos = 4 + len(js)
        pos += (-pos) % 8
        changed = False
        for d, (name, typ, arr) in zip(descr, arrays):
            if d["offset"] != pos:
                d["offset"] = pos
                changed = True
            pos += len(arr) * TYPES[typ][1]
            pos += (-pos) % 8
        if not changed:
            break
    js = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    parts = [struct.pack("<I", len(js)), js]
    pos = 4 + len(js)
    for d, (name, typ, arr) in zip(descr, arrays):
        pad = d["offset"] - pos
        assert pad >= 0, "offset fixpoint failed"
        parts.append(b"\0" * pad)
        code, size = TYPES[typ]
        assert arr.itemsize == size, (name, arr.itemsize)
        if sys.byteorder != "little":
            arr = array.array(arr.typecode, arr)
            arr.byteswap()
        b = arr.tobytes()
        parts.append(b)
        pos = d["offset"] + len(b)
    raw = b"".join(parts)
    return raw, gzip.compress(raw, compresslevel=9, mtime=0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("graph", help="exported graph (Turtle .ttl, N-Triples .nt, …)")
    ap.add_argument("out", help="output HTML file")
    ap.add_argument("--scans", default="drive",
                    help="'drive' (Drive thumbnails by file id, local JPEG fallback) or "
                         "'local:<dir>' (JPEGs <page id>.jpg in <dir>, relative to the HTML file; Drive fallback)")
    ap.add_argument("--drive-map", default=str(REPO / "configs" / "drive_scan_files.json"),
                    help="JSON page id → Google Drive file id (default configs/drive_scan_files.json)")
    ap.add_argument("--local-scans", default=None,
                    help="fallback directory of <page id>.jpg in drive mode, relative to the HTML "
                         "(default: data/pages_jpg of this repository, if it exists)")
    ap.add_argument("--ontology-dir", default=str(REPO / "ontologies"))
    ap.add_argument("--title", default="Laubmann-KG · Graph-Explorer")
    ap.add_argument("--format", default=None, help="rdflib parser format (default: from the file extension)")
    args = ap.parse_args(argv)

    t0 = time.time()
    src = Path(args.graph)
    out = Path(args.out)
    fmt = args.format or guess_format(str(src)) or "turtle"
    pk = _Packer()
    pk.parse(str(src), format=fmt)
    t_parse = time.time() - t0
    print(f"parsed {len(pk.keys):,} triples, {len(pk.nodes):,} nodes, {len(pk.lits):,} literals "
          f"in {t_parse:.1f} s", file=sys.stderr)

    meta, arrays = pack(pk)
    del pk
    info = ontology_info(Path(args.ontology_dir))
    meta.update(info)
    meta["prefixes"] = PREFIXES
    meta["title"] = args.title
    meta["source"] = src.name
    meta["sourcePath"] = str(src.resolve().relative_to(REPO)).replace("\\", "/") if src.resolve().is_relative_to(REPO) else src.name
    meta["built"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    # scans: Drive file ids for the pages in this graph, local directory
    out_dir = out.resolve().parent
    scans = {"mode": "drive", "drive": {}, "local": None}
    pages = page_identifiers(meta, arrays)
    drive_map = {}
    if args.drive_map and Path(args.drive_map).exists():
        drive_map = json.loads(Path(args.drive_map).read_text(encoding="utf-8"))
    scans["drive"] = {p: drive_map[p] for p in pages if p in drive_map}
    if args.scans.startswith("local:"):
        scans["mode"] = "local"
        scans["local"] = args.scans[len("local:"):].rstrip("/\\").replace("\\", "/") or "."
    elif args.scans != "drive":
        ap.error("--scans must be 'drive' or 'local:<dir>'")
    else:
        loc = args.local_scans
        if loc is None and (REPO / "data" / "pages_jpg").is_dir():
            loc = os.path.relpath(REPO / "data" / "pages_jpg", out_dir)
        scans["local"] = loc.replace("\\", "/") if loc else None
    meta["scans"] = scans

    raw, blob = encode_blob(meta, arrays)
    b64 = base64.b64encode(blob).decode("ascii")

    tpl = (HERE / "graph_explorer_template.html").read_text(encoding="utf-8")
    css = (HERE / "graph_explorer.css").read_text(encoding="utf-8")
    js = (HERE / "graph_explorer.js").read_text(encoding="utf-8")
    lf_js = (REPO / "tools" / "validation_ui" / "leaflet.js").read_text(encoding="utf-8")
    lf_css = (REPO / "tools" / "validation_ui" / "leaflet.css").read_text(encoding="utf-8")
    html = (tpl.replace("{{TITLE}}", args.title.replace("<", "&lt;"))
               .replace("/*{{LEAFLET_CSS}}*/", lf_css)
               .replace("/*{{APP_CSS}}*/", css)
               .replace("/*{{LEAFLET_JS}}*/", lf_js.replace("</script", "<\\/script"))
               .replace("/*{{APP_JS}}*/", js.replace("</script", "<\\/script"))
               .replace("{{DATA}}", b64))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    t_all = time.time() - t0
    mb = 1024 * 1024
    print(f"wrote {out} - {len(html) / mb:.1f} MB (data: {len(raw) / mb:.1f} MB raw, "
          f"{len(blob) / mb:.1f} MB gzip, {len(b64) / mb:.1f} MB base64); "
          f"{meta['triples']:,} triples, {len(meta['nodes']):,} nodes, {len(meta['lits']):,} literals, "
          f"{len(scans['drive']):,}/{len(pages):,} pages with Drive id; {t_all:.1f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
