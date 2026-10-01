"""Shared helpers of the Playwright tests (python tests/<name>.py [page.html] [shots dir])."""
import base64
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PAGE = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LC_PAGE", REPO / "data" / "exports" / "link_check" / "Laubmann_Verknuepfungen.html")).resolve()
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else os.environ.get("LC_SHOTS", PAGE.parent / "shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
URL = PAGE.as_uri()
FAILS = []
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGN49PQFAAVcArDars8JAAAAAElFTkSuQmCC")   # 1x1 light grey


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)
    return bool(cond)


def done(errs):
    # a page scan that is not on this machine may fail to load (the page then tries Drive); everything else counts
    real = [e for e in errs if not ("ERR_FILE_NOT_FOUND" in e and e.rstrip().endswith(".jpg"))]
    check(not real, "no console or page errors " + (repr(real[:5]) if real else ""))
    print("RESULT:", "FAILED " + str(len(FAILS)) if FAILS else "ALL OK")
    sys.exit(1 if FAILS else 0)


async def open_page(p, clear=True, locale="de-DE", viewport=(1440, 900)):
    b = await p.chromium.launch()
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, locale=locale, accept_downloads=True)

    # the tests work offline: local files pass, map tiles and Drive thumbnails get a 1x1 PNG, look-ups an empty answer
    async def route(r):
        url = r.request.url
        if url.startswith("file:"):
            await r.continue_()
        elif r.request.resource_type == "image":
            await r.fulfill(status=200, content_type="image/png", body=PNG)
        else:
            await r.fulfill(status=200, content_type="application/json", body="{}", headers={"Access-Control-Allow-Origin": "*"})
    await ctx.route("**/*", route)
    pg = await ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text + " @ " + str(m.location.get("url", ""))[-80:]) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept())
    await pg.goto(URL)
    await pg.wait_for_selector("#loading", state="detached", timeout=120000)
    if clear:
        await clear_state(pg)
    await pg.wait_for_timeout(200)
    return b, pg, errs


async def clear_state(pg):
    """Empty the browser storage and reload (after the page's delayed save has run, so it cannot write the state back)."""
    await pg.wait_for_timeout(450)
    await pg.evaluate("localStorage.clear()")
    await pg.reload()
    await pg.wait_for_selector("#loading", state="detached", timeout=120000)
    await pg.wait_for_timeout(200)


async def reload(pg):
    await pg.wait_for_timeout(400)            # the state is written to localStorage with a short delay
    await pg.reload()
    await pg.wait_for_selector("#loading", state="detached", timeout=120000)
    await pg.wait_for_timeout(200)


async def open_first(pg, ty, js_pred, queue=None):
    """Open the first entity of a type matching the JS predicate (e => ...); returns its key or None."""
    key = await pg.evaluate(f"((__lc.ENTS['{ty}'].find({js_pred})) || {{}}).k")
    if key is None:
        return None
    if queue:
        await pg.evaluate(f"__lc.S.ui.q['{ty}'] = '{queue}'; __lc.S.ui.sub['{ty}'] = ''; __lc.S.ui.find['{ty}'] = ''")
    else:
        await pg.evaluate(f"__lc.S.ui.q['{ty}'] = __lc.BYK['{ty}'].get({key!r}).q; __lc.S.ui.sub['{ty}'] = ''; __lc.S.ui.find['{ty}'] = ''")
    await pg.evaluate(f"__lc.openEntity('{ty}', {key!r})")
    await pg.wait_for_timeout(150)
    return key
