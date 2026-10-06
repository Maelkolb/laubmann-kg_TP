"""Cut anew the regions whose box cut their object off (region_quality_machine.csv rows with a new box).

    python tools/validation_ui/machine_review/recrop.py data/review/machine/region_quality_machine.csv \\
        [--pages data/pages_jpg] [--crops data/region_crops] [--out data/region_crops_v2]

Writes <out>/<region_uid>.jpg, replaces the local crop data/region_crops/<region_uid>.jpg (the original goes to
data/region_crops_orig/) and fills the row's `crop` with regions_v2/<page_id>/<region_uid>.jpg, the path of the new
crop under HistOrniGraph_output on Drive.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from PIL import Image

MARGIN = 0.01


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decisions")
    ap.add_argument("--pages", default="data/pages_jpg")
    ap.add_argument("--crops", default="data/region_crops")
    ap.add_argument("--out", default="data/region_crops_v2")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keep = Path(args.crops).parent / "region_crops_orig"
    keep.mkdir(parents=True, exist_ok=True)
    with open(args.decisions, encoding="utf-8", newline="") as h:
        reader = csv.DictReader(h)
        fields, rows = reader.fieldnames, list(reader)
    if "crop" not in fields:
        fields = fields + ["crop"]
    done = 0
    for r in rows:
        if r.get("decision") == "drop" or not r.get("box"):
            continue
        page = Path(args.pages) / f"{r['page_id']}.jpg"
        if not page.exists():
            continue
        x0, y0, x1, y1 = json.loads(r["box"])
        img = Image.open(page)
        w, h = img.size
        box = (max(0, round((x0 - MARGIN) * w)), max(0, round((y0 - MARGIN) * h)),
               min(w, round((x1 + MARGIN) * w)), min(h, round((y1 + MARGIN) * h)))
        img.crop(box).convert("RGB").save(out / f"{r['region_uid']}.jpg", "JPEG", quality=90)
        local = Path(args.crops) / f"{r['region_uid']}.jpg"
        if local.exists() and not (keep / local.name).exists():
            shutil.copy2(local, keep / local.name)
        shutil.copy2(out / f"{r['region_uid']}.jpg", local)
        r["crop"] = f"regions_v2/{r['page_id']}/{r['region_uid']}.jpg"
        done += 1
    with open(args.decisions, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{done} regions cut anew -> {out}")


if __name__ == "__main__":
    main()
