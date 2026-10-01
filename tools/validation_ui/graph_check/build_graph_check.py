#!/usr/bin/env python3
"""Graph validation page ("Graph-Prüfung") for the Laubmann knowledge graph.

Packs an EXPORTED graph exactly as the graph explorer does (the packing is
imported from tools/explorer/build_graph_explorer.py: every triple of the file,
columnar, gzip + base64) and embeds the review layer of build_review.py next to
it (gzip + base64 JSON): entry regions and record lines on the scans, reading
corrections, QA flags, the findings of the two record checks, the machine
review's name decisions. The page shows, entry by entry, the subgraph, the
scan and every automatic change or finding as a card the reviewer accepts,
rejects or corrects; the decisions are exported in the pipeline's review
contracts (see README.md).

    python tools/validation_ui/graph_check/build_graph_check.py <graph.ttl> <review.json> <out.html>
        [--scans drive | local:<dir relative to out.html>] [--no-cache]

What the builder adds to the review layer:

    obs     {entry_id: [node, obs_index, occurrence, node, obs_index, occurrence, ...]}
            node = index of the observation in the packed node table; obs_index = the extraction
            index recovered from the IRI (sha1("<entry_uid>|<written name>|<index>")[:12]);
            occurrence = 0-based index among the entry's records with that written name
    sample  [entry_id, ...]   the fixed random sample: sha1(entry_uid) mod 33 == 0
    (meta.scans.crops = the local folder of the region crops, see --local-crops)
    graph   {source, entries, records}

Only needs rdflib (through the explorer builder). The parsed graph is cached in
``<out dir>/.cache`` (keyed by file name, size and mtime), so a rebuild after a
change of the page sources or of review.json takes seconds.
"""
from __future__ import annotations

import argparse
import base64
import collections
import datetime as _dt
import gzip
import hashlib
import json
import os
import pickle
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "explorer"))
sys.dont_write_bytecode = True     # the import must not leave a __pycache__ in tools/explorer
import build_graph_explorer as X  # noqa: E402  (packing, ontology labels, blob layout)

# page sources, concatenated in this order into one script (one shared function scope)
JS_FILES = ["gc_explorer.js", "gc_i18n.js", "gc_state.js", "gc_severity.js", "gc_corpus.js", "gc_props.js", "gc_scan.js", "gc_media.js", "gc_cards.js", "gc_views.js", "gc_table.js", "gc_export.js",
            "gc_boot.js"]
CSS_FILES = ["gc_explorer.css", "gc_review.css", "gc_levels.css"]
TEMPLATE = "graph_check_template.html"
SAMPLE_MOD = 33


def packed_graph(src: Path, fmt: str | None, cache_dir: Path | None):
    """(meta, arrays) of the explorer's packing; cached by name, size and mtime."""
    st = src.stat()
    key = hashlib.sha1(f"{src.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    cache = cache_dir / f"pack_{src.stem}_{key}.pkl" if cache_dir else None
    if cache and cache.exists():
        with open(cache, "rb") as h:
            meta, arrays = pickle.load(h)
        print(f"packed graph from cache {cache.name}: {meta['triples']:,} triples", file=sys.stderr)
        return meta, arrays
    t0 = time.time()
    pk = X._Packer()
    pk.parse(str(src), format=fmt or X.guess_format(str(src)) or "turtle")
    print(f"parsed {len(pk.keys):,} triples, {len(pk.nodes):,} nodes, {len(pk.lits):,} literals in {time.time() - t0:.1f} s",
          file=sys.stderr)
    meta, arrays = X.pack(pk)
    del pk
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        for old in cache.parent.glob(f"pack_{src.stem}_*.pkl"):
            old.unlink()
        with open(cache, "wb") as h:
            pickle.dump((meta, arrays), h, protocol=pickle.HIGHEST_PROTOCOL)
    return meta, arrays


class Packed:
    """Read access to the packed graph (the page reads the same tables)."""

    def __init__(self, meta: dict, arrays) -> None:
        self.nodes, self.preds, self.lits = meta["nodes"], meta["preds"], meta["lits"]
        a = {name: arr for name, _, arr in arrays}
        self.s_off, self.t_p, self.t_o = a["sOff"], a["tP"], a["tO"]
        self.lang = [meta["langs"][i] for i in a["litLang"]]
        self.p = {p: i for i, p in enumerate(self.preds)}
        self.n = {c: i for i, c in enumerate(self.nodes)}

    def objects(self, s: int, pred: str):
        p = self.p.get(pred)
        if p is None:
            return
        for i in range(self.s_off[s], self.s_off[s + 1]):
            if self.t_p[i] == p:
                yield self.t_o[i]

    def literals(self, s: int, pred: str) -> list[str]:
        """Literal values, German and untagged ones first."""
        vals = [(-o - 1) for o in self.objects(s, pred) if o < 0]
        vals.sort(key=lambda l: {"de": 0, "": 1}.get(self.lang[l], 2))
        return [self.lits[l] for l in vals]

    def node_objects(self, s: int, pred: str) -> list[int]:
        return [o for o in self.objects(s, pred) if o >= 0]

    def of_type(self, cls: str) -> list[int]:
        c = self.n.get(cls)
        p = self.p.get("rdf:type")
        if c is None or p is None:
            return []
        return [s for s in range(len(self.nodes))
                if any(self.t_p[i] == p and self.t_o[i] == c for i in range(self.s_off[s], self.s_off[s + 1]))]


def local(compact: str) -> str:
    return compact.rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def obs_index(obs_local: str, entry_uid: str, names: list[str]) -> tuple[int, str]:
    """(extraction index, written name) of an observation, recovered from its IRI
    (tools/validation_ui/machine_review/prepare_entries.py obs_index)."""
    want = obs_local.replace("obs_", "")
    for written in names:
        for i in range(1000):
            if hashlib.sha1(f"{entry_uid}|{written}|{i}".encode("utf-8")).hexdigest()[:12] == want:
                return i, written
    return -1, names[0] if names else ""


def graph_layer(P: Packed, review: dict) -> tuple[dict, list, dict, set]:
    """The per-entry observation table, the sample, the statistics of the join with
    review.json and the entry ids of the graph."""
    obs_map, sample, idents = {}, [], set()
    stats = collections.Counter()
    entries = review.get("entries", {})
    for s in P.of_type("lkg:DiaryEntry"):
        ident = (P.literals(s, "dcterms:identifier") or [local(P.nodes[s])])[0]
        uid = local(P.nodes[s])
        uid = uid[len("entry_"):] if uid.startswith("entry_") else uid
        stats["entries in the graph"] += 1
        rv = entries.get(ident)
        if rv is None:
            stats["entries without review data"] += 1
        elif rv.get("uid") != uid:
            stats["entries whose uid differs from review.json"] += 1
        if int(hashlib.sha1(uid.encode("utf-8")).hexdigest(), 16) % SAMPLE_MOD == 0:
            sample.append(ident)
        rows = []
        for o in P.node_objects(s, "lkg:containsObservation"):
            names = P.literals(o, "dwc:verbatimIdentification")
            if not names:
                for tx in P.node_objects(o, "lkg:observedTaxon"):
                    names += P.literals(tx, "skos:prefLabel") + P.literals(tx, "rdfs:label") + P.literals(tx, "schema:name")
                    if not names:
                        names.append(local(P.nodes[tx]))
            idx, written = obs_index(local(P.nodes[o]), uid, names or [""])
            rows.append((idx if idx >= 0 else 10 ** 6, o, written))
            stats["records in the graph"] += 1
            stats["records with unrecoverable index"] += idx < 0
        rows.sort()
        occ: collections.Counter = collections.Counter()
        flat = []
        for idx, o, written in rows:
            k = written.casefold()
            flat += [o, idx, occ[k]]
            occ[k] += 1
            rec = (rv or {}).get("rec", {}).get(str(idx))
            if rec is None:
                stats["records without review data"] += 1
            elif rec.get("w", "").casefold() != k:
                stats["records whose name differs from review.json"] += 1
            if k != written.lower().replace("ß", "ss"):
                stats["names where casefold() != lower()+ss"] += 1
        if flat:
            obs_map[ident] = flat
        idents.add(ident)
    stats["review entries"] = len(entries)
    stats["review entries not in the graph"] = len(set(entries) - idents)
    return obs_map, sample, dict(stats), idents


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("graph", help="exported graph (Turtle .ttl, N-Triples .nt, …)")
    ap.add_argument("review", help="review layer (build_review.py: review.json)")
    ap.add_argument("out", help="output HTML file")
    ap.add_argument("--scans", default="drive",
                    help="'drive' (Drive thumbnails by file id, local JPEG fallback) or "
                         "'local:<dir>' (JPEGs <page id>.jpg in <dir>, relative to the HTML file; Drive fallback)")
    ap.add_argument("--drive-map", default=str(REPO / "configs" / "drive_scan_files.json"))
    ap.add_argument("--local-scans", default=None,
                    help="fallback directory of <page id>.jpg in drive mode, relative to the HTML "
                         "(default: data/pages_jpg of this repository, if it exists)")
    ap.add_argument("--local-crops", default=None,
                    help="directory of the crops of the multimodal regions, <region uid>.jpg (tools/export_region_crops.py), "
                         "relative to the HTML; fallback when a crop does not load from Drive "
                         "(default: data/region_crops of this repository, if it exists; 'none' = no local crops)")
    ap.add_argument("--ontology-dir", default=str(REPO / "ontologies"))
    ap.add_argument("--title", default="Laubmann-KG · Graph-Prüfung")
    ap.add_argument("--format", default=None, help="rdflib parser format (default: from the file extension)")
    ap.add_argument("--no-cache", action="store_true", help="parse the graph even when a cached packing exists")
    args = ap.parse_args(argv)

    t0 = time.time()
    src, out = Path(args.graph), Path(args.out)
    out_dir = out.resolve().parent
    meta, arrays = packed_graph(src, args.format, None if args.no_cache else out_dir / ".cache")
    meta = dict(meta)
    meta.update(X.ontology_info(Path(args.ontology_dir)))
    meta["prefixes"] = X.PREFIXES
    meta["title"] = args.title
    meta["source"] = src.name
    meta["sourcePath"] = (str(src.resolve().relative_to(REPO)).replace("\\", "/")
                          if src.resolve().is_relative_to(REPO) else src.name)
    meta["built"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    # scans: as in the explorer (Drive file ids of the pages in this graph, local directory)
    scans = {"mode": "drive", "drive": {}, "local": None}
    pages = X.page_identifiers(meta, arrays)
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
    crops = args.local_crops
    if crops is None and (REPO / "data" / "region_crops").is_dir():
        crops = os.path.relpath(REPO / "data" / "region_crops", out_dir)
    scans["crops"] = crops.rstrip("/\\").replace("\\", "/") if crops and crops.lower() != "none" else None
    meta["scans"] = scans

    # review layer: only the entries of this graph, plus the observation table and the sample
    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    # pages the review layer shows beyond the pages of the graph (pages that only carry images of an entry)
    extra = [p[0] for p in review.get("pages", []) if p and p[0] not in scans["drive"] and p[0] in drive_map]
    scans["drive"].update({p: drive_map[p] for p in extra})
    obs_map, sample, stats, idents = graph_layer(Packed(meta, arrays), review)
    layer = {"meta": review.get("meta", {}), "pages": review.get("pages", []),
             "entries": {k: v for k, v in review.get("entries", {}).items() if k in idents},
             "names": review.get("names", {}), "crops": review.get("crops", {}), "obs": obs_map, "sample": sorted(sample),
             "graph": {"source": meta["sourcePath"], "entries": stats.get("entries in the graph", 0),
                       "records": stats.get("records in the graph", 0)}}
    export = (review.get("meta") or {}).get("export")
    if export and export not in meta["sourcePath"]:
        print(f"WARNING: review.json was built for export {export!r}, the graph file is {meta['sourcePath']!r}", file=sys.stderr)
    rv_raw = json.dumps(layer, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rv_b64 = base64.b64encode(gzip.compress(rv_raw, compresslevel=9, mtime=0)).decode("ascii")

    raw, blob = X.encode_blob(meta, arrays)
    b64 = base64.b64encode(blob).decode("ascii")

    tpl = (HERE / TEMPLATE).read_text(encoding="utf-8")
    css = "\n".join((HERE / f).read_text(encoding="utf-8") for f in CSS_FILES)
    js = "\n".join((HERE / f).read_text(encoding="utf-8") for f in JS_FILES)
    lf_js = (REPO / "tools" / "validation_ui" / "leaflet.js").read_text(encoding="utf-8")
    lf_css = (REPO / "tools" / "validation_ui" / "leaflet.css").read_text(encoding="utf-8")
    html = (tpl.replace("{{TITLE}}", args.title.replace("<", "&lt;"))
               .replace("/*{{LEAFLET_CSS}}*/", lf_css)
               .replace("/*{{APP_CSS}}*/", css)
               .replace("/*{{LEAFLET_JS}}*/", lf_js.replace("</script", "<\\/script"))
               .replace("/*{{APP_JS}}*/", js.replace("</script", "<\\/script"))
               .replace("{{REVIEW}}", rv_b64)
               .replace("{{DATA}}", b64))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    mb = 1024 * 1024
    print(json.dumps(stats, indent=1), file=sys.stderr)
    print(f"wrote {out} - {len(html) / mb:.1f} MB (graph {len(b64) / mb:.1f} MB base64, review layer {len(rv_raw) / mb:.1f} MB raw / "
          f"{len(rv_b64) / mb:.1f} MB base64); {meta['triples']:,} triples, {len(layer['entries']):,} entries with review data, "
          f"{len(sample):,} sample entries, {len(scans['drive']):,} pages with Drive id ({len(pages):,} pages in the graph, {len(extra):,} more in the "
          f"review layer), {len(layer['crops']):,} region crops with Drive id, local crops: {scans['crops'] or '-'}; {time.time() - t0:.1f} s",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
