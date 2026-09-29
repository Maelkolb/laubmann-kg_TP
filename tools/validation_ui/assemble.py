"""Inline Leaflet, the Drive page-image map, the app script and the payload into one standalone HTML page.

    python tools/validation_ui/assemble.py payload.b64 Laubmann_Abgleich.html

The app is kept in five parts (app_core.js, app_ui.js, app_views.js, app_actions.js, app_io.js);
they are concatenated inside one async IIFE, so the parts share one scope and the start-up
sequence at the end of app_io.js may ``await`` the payload.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_PARTS = ["app_core.js", "app_ui.js", "app_views.js", "app_actions.js", "app_io.js"]


def app_js() -> str:
    body = "\n".join((HERE / p).read_text(encoding="utf-8") for p in APP_PARTS)
    return "(async function () {\n" + body + "\n})();\n"


if __name__ == "__main__":
    payload, out = sys.argv[1], sys.argv[2]
    d = json.loads((HERE / "drive_pages.json").read_text(encoding="utf-8"))
    # vol. 01 scan 0031 exists on Drive only as an unsplit _full page
    full = "900847d2-aabe-4b16-b0e6-203b103bd1e1_0031_full"
    for s in ("_L", "_R"):
        d.setdefault(full.replace("_full", s), d.get(full))
    t = (HERE / "template.html").read_text(encoding="utf-8")
    html = (t.replace("/*LEAFLET_CSS*/", (HERE / "leaflet.css").read_text(encoding="utf-8"))
             .replace("__DRIVE__", json.dumps(d, separators=(",", ":")))
             .replace("/*LEAFLET_JS*/", (HERE / "leaflet.js").read_text(encoding="utf-8"))
             .replace("/*APP_JS*/", app_js())
             .replace("__PAYLOAD__", Path(payload).read_text(encoding="utf-8")))
    Path(out).write_text(html, encoding="utf-8")
    print(f"{out}: {len(html) / 1e6:.1f} MB")
