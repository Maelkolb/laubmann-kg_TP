"""Google Drive file ids of the page scans, read from the local Drive-for-desktop
metadata database (a read-only copy), so the UI can show every page by id.

    python tools/validation_ui/drive_ids.py tools/validation_ui/drive_pages.json

Covers ``Laubmann_XX_gemini/pages/<page id>.png`` of all volumes. Ids starting
with "local-" (upload not finished) are skipped. Needs Drive for desktop with
the HistOrniGraph_output folder synced on this machine; the page previews then
load in the UI for any Google account with access to that folder.
"""
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile


def page_ids() -> dict[str, str]:
    dbs = glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "Google", "DriveFS", "*", "metadata_sqlite_db"))
    if not dbs:
        raise SystemExit("no Drive-for-desktop metadata database found")
    tmp = tempfile.mkdtemp()
    try:
        ids: dict[str, str] = {}
        for n, db_path in enumerate(dbs):
            copy = os.path.join(tmp, f"meta{n}.db")
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(db_path + suffix):
                    shutil.copy2(db_path + suffix, copy + suffix)
            db = sqlite3.connect(copy)
            rows = db.execute("""SELECT c.local_title, c.id FROM items c
                JOIN stable_parents sp ON sp.item_stable_id = c.stable_id
                JOIN items f ON f.stable_id = sp.parent_stable_id
                JOIN stable_parents sp2 ON sp2.item_stable_id = f.stable_id
                JOIN items g ON g.stable_id = sp2.parent_stable_id
                WHERE f.local_title = 'pages' AND g.local_title LIKE 'Laubmann_%_gemini' AND c.trashed = 0""").fetchall()
            db.close()
            for title, fid in rows:
                if title.endswith(".png") and not fid.startswith("local-"):
                    ids[os.path.splitext(title)[0]] = fid
        return ids
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def region_ids() -> dict[str, str]:
    """Drive file ids of the region crops ``Laubmann_XX_gemini/regions/<page id>/<file>.png``,
    keyed ``regions/<page id>/<file>.png`` (the ``crop`` of multimodal_regions.jsonl)."""
    dbs = glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "Google", "DriveFS", "*", "metadata_sqlite_db"))
    if not dbs:
        raise SystemExit("no Drive-for-desktop metadata database found")
    tmp = tempfile.mkdtemp()
    try:
        ids: dict[str, str] = {}
        for n, db_path in enumerate(dbs):
            copy = os.path.join(tmp, f"meta{n}.db")
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(db_path + suffix):
                    shutil.copy2(db_path + suffix, copy + suffix)
            db = sqlite3.connect(copy)
            rows = db.execute("""SELECT f.local_title, c.local_title, c.id FROM items c
                JOIN stable_parents sp ON sp.item_stable_id = c.stable_id
                JOIN items f ON f.stable_id = sp.parent_stable_id
                JOIN stable_parents sp2 ON sp2.item_stable_id = f.stable_id
                JOIN items g ON g.stable_id = sp2.parent_stable_id
                JOIN stable_parents sp3 ON sp3.item_stable_id = g.stable_id
                JOIN items h ON h.stable_id = sp3.parent_stable_id
                WHERE g.local_title = 'regions' AND h.local_title LIKE 'Laubmann_%_gemini' AND c.trashed = 0""").fetchall()
            db.close()
            for folder, title, fid in rows:
                if title.endswith(".png") and not fid.startswith("local-"):
                    ids[f"regions/{folder}/{title}"] = fid
        return ids
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--regions":      # drive_ids.py --regions drive_regions.json
        ids, out, what = region_ids(), sys.argv[2], "region crop"
    else:
        ids, out, what = page_ids(), (sys.argv[1] if len(sys.argv) > 1 else "drive_pages.json"), "page"
    with open(out, "w", encoding="utf-8") as h:
        json.dump(dict(sorted(ids.items())), h, indent=0)
    print(f"{len(ids)} {what} ids -> {out}")
