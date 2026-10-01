"""Shared helpers of the Playwright tests (python tests/<name>.py <page.html> [shots dir])."""
import os
import sys
from pathlib import Path

PAGE = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LV_PAGE", "Laubmann_Validierung.html")).resolve()
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else os.environ.get("LV_SHOTS", Path(__file__).resolve().parent / "shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
URL = PAGE.as_uri()
FAILS = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def done(errs):
    real = [e for e in errs if "ERR_" not in e and "net::" not in e and "Failed to load resource" not in e]
    check(not real, "no page errors " + (repr(real[:5]) if real else ""))
    print("RESULT:", "FAILED " + str(len(FAILS)) if FAILS else "ALL OK")
    sys.exit(1 if FAILS else 0)


async def open_page(p, clear=True, locale="de-DE", viewport=(1600, 1000)):
    b = await p.chromium.launch()
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, locale=locale, accept_downloads=True)
    # scans and tiles come from the network; the tests work offline
    async def only_local(route):
        if route.request.url.startswith("file:"):
            await route.continue_()
        else:
            await route.abort()
    await ctx.route("**/*", only_local)
    pg = await ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept())
    await pg.goto(URL)
    await pg.wait_for_selector("#loading", state="detached", timeout=180000)
    if clear:
        await pg.evaluate("localStorage.clear()")
        await pg.reload()
        await pg.wait_for_selector("#loading", state="detached", timeout=180000)
    await pg.wait_for_timeout(300)
    return b, pg, errs


async def reload(pg):
    await pg.reload()
    await pg.wait_for_selector("#loading", state="detached", timeout=180000)
    await pg.wait_for_timeout(300)


async def open_item(pg, js_find, tab=None):
    """Open the first item matching the JS predicate (x => ...); returns its index or None."""
    i = await pg.evaluate(f"(__lp.ITEMS.find({js_find}) || {{}}).i")
    if i is None:
        return None
    await pg.evaluate(f"__lp.goto({i})")
    await pg.wait_for_timeout(250)
    return i
