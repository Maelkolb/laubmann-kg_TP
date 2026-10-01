#!/usr/bin/env python3
"""Assemble the standalone page "Laubmann-Verknüpfungen": template + inlined Leaflet + app scripts + data.

    python tools/validation_ui/link_check/assemble.py [--data data/exports/link_check/data] [out.html]

--data    prefix of build_data.py --out (reads <prefix>.b64)
--scans   folder with the page JPEGs (data/pages_jpg); the page loads <scans>/<page id>.jpg relative to
          itself first and falls back to the Drive thumbnail. "" = Drive only.
"""
import argparse
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("out", nargs="?", default=str(REPO / "data" / "exports" / "link_check" / "Laubmann_Verknuepfungen.html"))
ap.add_argument("--data", default=str(REPO / "data" / "exports" / "link_check" / "data"))
ap.add_argument("--scans", default=str(REPO / "data" / "pages_jpg"))
args = ap.parse_args()

out = Path(args.out).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
LEAF = HERE.parent                       # leaflet.css / leaflet.js live in tools/validation_ui
scans = ""
if args.scans:
    try:
        scans = Path(os.path.relpath(Path(args.scans).resolve(), out.parent)).as_posix().rstrip("/") + "/"
    except ValueError:                   # another drive: no relative path
        scans = Path(args.scans).resolve().as_uri().rstrip("/") + "/"
app = "\n".join((HERE / f).read_text(encoding="utf-8") for f in ("app_i18n.js", "app_core.js", "app_view.js", "app_actions.js"))
app = ("(async function(){\n'use strict';\n" + app + "\n})().catch(e => { console.error(e); document.body.insertAdjacentHTML('beforeend', "
       "'<pre style=\"position:fixed;inset:0;background:#fff;color:#900;padding:20px;z-index:9999;white-space:pre-wrap\">Fehler beim Start: ' + String(e && e.stack || e).replace(/</g, '&lt;') + '</pre>'); });")
b64 = Path(args.data + ".b64").read_text(encoding="ascii").strip()
html = (HERE / "template.html").read_text(encoding="utf-8")
for mark, value in (("/*LEAFLET_CSS*/", (LEAF / "leaflet.css").read_text(encoding="utf-8")),
                    ("/*LEAFLET_JS*/", (LEAF / "leaflet.js").read_text(encoding="utf-8").replace("</script>", "<\\/script>")),
                    ("/*CFG*/", json.dumps({"scans": scans})),
                    ("/*APP*/", app.replace("</script>", "<\\/script>")),
                    ("/*DATA*/", b64)):
    if html.count(mark) != 1:
        raise SystemExit(f"template: marker {mark} expected once")
    html = html.replace(mark, value)
out.write_text(html, encoding="utf-8")
print(f"{out} — {out.stat().st_size / 1e6:.1f} MB (scans: {scans or 'Drive only'})")
