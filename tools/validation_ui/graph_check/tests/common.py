"""Shared helpers of the Playwright tests (python tests/<name>.py [page.html] [shots dir]).

Run them with an interpreter that has Playwright + Chromium (on this machine
``C:\\Users\\totom\\Projects\\laubmann-kg_TP\\.venv\\Scripts\\python.exe``); the loaders are called with the
repository's own interpreter (``GC_REPO_PYTHON``, default ``.venv/Scripts/python.exe``)."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
for _s in (sys.stdout, sys.stderr):      # Windows consoles default to cp1252
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
PAGE = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GC_PAGE", REPO / "data" / "exports" / "graph_check" / "Laubmann_Graphpruefung.html")).resolve()
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else os.environ.get("GC_SHOTS", REPO / "data" / "exports" / "graph_check" / "shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
REPO_PY = os.environ.get("GC_REPO_PYTHON", str(REPO / ".venv" / "Scripts" / "python.exe"))
URL = PAGE.as_uri()
# the explorer build of the same app (build_graph_check.py --mode explorer), next to the review build
EXPLORER_PAGE = Path(os.environ.get("GC_EXPLORER", PAGE.with_name("Laubmann_Graph_Explorer.html"))).resolve()
FAILS = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)
    return bool(cond)


def done(errs):
    real = [e for e in errs if "ERR_" not in e and "net::" not in e and "Failed to load resource" not in e]
    check(not real, "no page errors " + (repr(real[:5]) if real else ""))
    print("RESULT:", "FAILED " + str(len(FAILS)) if FAILS else "ALL OK", flush=True)
    sys.exit(1 if FAILS else 0)


async def ready(pg):
    await pg.wait_for_function("window.LKGC && window.LKGC.ready", timeout=120000)
    await pg.wait_for_timeout(150)


async def open_page(p, clear=True, locale="de-DE", viewport=(1440, 900), local_scans=True, url=None):
    """A fresh browser; the network is blocked (scans from Drive, map tiles), local files are allowed
    unless ``local_scans`` is False (then the page runs without any image). ``url``: another page than
    the review build (the explorer build)."""
    b = await p.chromium.launch()
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, locale=locale, accept_downloads=True)

    async def only_local(route):
        url = route.request.url
        if url.startswith("file:") and (local_scans or not url.lower().endswith(".jpg")):
            await route.continue_()
        else:
            await route.abort()
    await ctx.route("**/*", only_local)
    pg = await ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept())
    await pg.goto(url or URL)
    await ready(pg)
    if clear:
        await pg.evaluate("localStorage.clear()")
        await pg.reload()
        await ready(pg)
    return b, pg, errs


async def reload(pg):
    await pg.reload()
    await ready(pg)


async def goto_entry(pg, entry_id, wait=350):
    await pg.evaluate(f"LKGC.go('/e/' + {entry_id!r})")
    await pg.wait_for_timeout(wait)


# JS: the first entry id whose review data satisfies a predicate (rv, summary) => bool
FIND = """(pred) => { const f = eval(pred); for (const r of LKGC.G.ent) { const rv = LKGC.R.entries[r.id] || {}; const s = LKGC.RVS.get(r.n); if (f(rv, s, r)) return r.id; } return null; }"""


async def find_entry(pg, pred):
    return await pg.evaluate(FIND, pred)


async def focus_item(pg, pred):
    """Focus the first visible card matching a JS predicate (it => bool); returns its index or None."""
    i = await pg.evaluate(f"(() => {{ const m = LKGC.EM; const items = LKGC.visibleItems(m); const i = items.findIndex({pred}); if (i >= 0) LKGC.focusCard(i); return i; }})()")
    await pg.wait_for_timeout(120)
    return None if i is None or i < 0 else i
