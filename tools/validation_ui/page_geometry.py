"""Page geometry for the validation UI: image size and region boxes of every
corpus page, read once from the HistOrniGraph PAGE-XML.

    python tools/validation_ui/page_geometry.py <corpus_dir> <volumes_root> pages_geometry.json

``corpus_dir`` holds ``corpus.json`` (the deduplicated corpus); ``volumes_root``
is the HistOrniGraph output folder with ``Laubmann_XX_gemini/pagexml/<page id>.xml``.
The output maps page id -> {"w", "h", "r": {region id: [x0, y0, x1, y1]}}; the
UI turns a region box and the line index of a mention into a line crop of the
scan. Pages without PAGE-XML are listed with w = h = 0.
"""
import json
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"}


def read_page(path: Path) -> dict:
    root = ET.parse(path).getroot()
    page = root.find("p:Page", NS)
    out = {"w": int(page.get("imageWidth") or 0), "h": int(page.get("imageHeight") or 0), "r": {}}
    for reg in page.iter():
        if not reg.tag.endswith("Region") or reg.get("id") is None:
            continue
        coords = reg.find("p:Coords", NS)
        if coords is None:
            continue
        pts = [tuple(int(float(v)) for v in p.split(",")) for p in (coords.get("points") or "").split() if "," in p]
        if not pts:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out["r"][reg.get("id")] = [min(xs), min(ys), max(xs), max(ys)]
    return out


def main(corpus_dir: str, volumes_root: str, out: str) -> None:
    pages = json.loads((Path(corpus_dir) / "corpus.json").read_text(encoding="utf-8"))
    root = Path(volumes_root)
    folders = sorted(p for p in root.glob("Laubmann_*_gemini") if (p / "pagexml").is_dir())
    by_prefix: dict[str, Path] = {}          # scan-batch uuid -> volume folder
    for f in folders:
        for x in (f / "pagexml").glob("*.xml"):
            by_prefix.setdefault(x.name.split("_")[0], f)
            break
    geo, missing, t = {}, 0, time.time()
    for i, pg in enumerate(pages):
        pid = pg["page_id"]
        cand = [root / f"Laubmann_{int(pg['volume']):02d}_gemini", by_prefix.get(pid.split("_")[0])]
        path = next((c / "pagexml" / f"{pid}.xml" for c in cand if c and (c / "pagexml" / f"{pid}.xml").exists()), None)
        if path is None and pid.endswith(("_L", "_R")):
            # a split page whose PAGE-XML exists only for the unsplit capture
            full = re.sub(r"_[LR]$", "_full", pid)
            path = next((c / "pagexml" / f"{full}.xml" for c in cand if c and (c / "pagexml" / f"{full}.xml").exists()), None)
        if path is None:
            geo[pid] = {"w": 0, "h": 0, "r": {}}
            missing += 1
            continue
        geo[pid] = read_page(path)
        if i % 500 == 0:
            print(f"{i}/{len(pages)} pages, {time.time() - t:.0f} s", flush=True)
    Path(out).write_text(json.dumps(geo, separators=(",", ":")), encoding="utf-8")
    print(f"{len(geo)} pages, {missing} without PAGE-XML -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
