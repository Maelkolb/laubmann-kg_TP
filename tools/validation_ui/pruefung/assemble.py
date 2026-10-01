#!/usr/bin/env python3
"""Assemble the standalone page: template + leaflet + app scripts + data (<prefix>.b64 of build_data.py).

    python assemble.py [--data data] [out.html]
"""
import argparse, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default=str(HERE.parent / "Laubmann_Validierung.html"))
ap.add_argument("--data", default=str(HERE / "data"), help="prefix of build_data.py --out (reads <prefix>.b64 and <prefix>.json)")
args = ap.parse_args()
LEAF = HERE.parent          # leaflet.css / leaflet.js live in tools/validation_ui
tpl = (HERE / "template.html").read_text(encoding="utf-8")
app = "\n".join((HERE / f).read_text(encoding="utf-8") for f in ("app_i18n.js", "app_core.js", "app_views.js", "app_actions.js", "app_io.js"))
app = "(async function(){\n'use strict';\n" + app + "\n})().catch(e => { document.body.insertAdjacentHTML('beforeend', '<pre style=\"position:fixed;inset:0;background:#fff;color:#900;padding:20px;z-index:9999\">Fehler beim Start: ' + (e && e.stack || e) + '</pre>'); });"
b64 = Path(args.data + ".b64").read_text().strip()
meta = json.loads(Path(args.data + ".json").read_text(encoding="utf-8"))
html = (tpl.replace("/*LEAFLET_CSS*/", (LEAF / "leaflet.css").read_text(encoding="utf-8"))
        .replace("/*LEAFLET_JS*/", (LEAF / "leaflet.js").read_text(encoding="utf-8"))
        .replace("/*DRIVE*/", "{}")
        .replace("/*DATA*/", b64)
        .replace("/*APP*/", app.replace("</script>", "<\\/script>")))
out = Path(args.out)
out.write_text(html, encoding="utf-8")
print(f"{out} — {out.stat().st_size / 1e6:.1f} MB; items {len(meta['items'])}; export {meta.get('export')}")
