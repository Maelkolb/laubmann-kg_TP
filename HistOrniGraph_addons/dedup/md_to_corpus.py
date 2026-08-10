#!/usr/bin/env python3
"""Reconstruct corpus.json page records from corpus/by_volume/Laubmann_NN.md.

The per-volume Markdown written by build_corpus.py embeds the full page/region
metadata in HTML comments, so the structured corpus can be recovered losslessly
when only the Markdown artifacts are at hand (e.g. partial Drive sync).
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "HistOrniGraph"))
from build_corpus import find_entry_starts  # noqa: E402

PAGE_RE = re.compile(
    r"<!-- page volume=(?P<vol>\d+) page_id=(?P<pid>\S+) image=(?P<img>\S+) "
    r"scan=(?P<scan>\d+) page_number=(?P<pnum>.*?) regions=(?P<nreg>\d+) -->")
REGION_RE = re.compile(
    r"<!-- region id=(?P<rid>\S+) type=(?P<rtype>\S+) order=(?P<order>\d+) "
    r"side=(?P<side>\S*) lines=(?P<lines>\d*) entries=(?P<ent>\d+) "
    r"crop=(?P<crop>.*?) -->")
MARKER_RE = re.compile(
    r"^(?:\*\*⮞ Entry —.*|\*\[\+ further entry start\(s\):.*|"
    r"\*\(…continued from.*|\*\[entry start\(s\) mid-region:.*)$")
UNESC_RE = re.compile(r"(?m)^([ \t]*)(\d{1,2})\\\.(?=\s)")


def _clean_region_text(lines):
    body = [ln for ln in lines if not MARKER_RE.match(ln.strip())]
    text = "\n".join(body).strip()
    return UNESC_RE.sub(r"\1\2.", text)


def parse_volume_md(path: Path):
    text = path.read_text(encoding="utf-8")
    pages, cur_page, cur_region, buf = [], None, None, []

    def flush_region():
        nonlocal cur_region, buf
        if cur_page is not None and cur_region is not None:
            cur_region["text"] = _clean_region_text(buf)
            scan_types = {"ParagraphRegion", "ListRegion"}
            starts = (find_entry_starts(cur_region["text"])
                      if cur_region["type"] in scan_types else [])
            cur_region["entry_starts"] = [
                {"date": h["date"], "location": h["location"],
                 "date_norm": h.get("date_norm"), "offset": h["offset"]}
                for h in starts]
            cur_page["regions"].append(cur_region)
        cur_region, buf = None, []

    for raw in text.splitlines():
        pm = PAGE_RE.match(raw.strip())
        rm = REGION_RE.match(raw.strip())
        if pm:
            flush_region()
            if cur_page:
                pages.append(cur_page)
            cur_page = {
                "volume": int(pm["vol"]), "page_id": pm["pid"], "image": pm["img"],
                "scan": int(pm["scan"]), "page_number": pm["pnum"].strip(),
                "regions": [],
            }
        elif rm:
            flush_region()
            cur_region = {
                "id": rm["rid"], "type": rm["rtype"],
                "reading_order": int(rm["order"]),
                "page_side": rm["side"],
                "line_count": int(rm["lines"]) if rm["lines"] else None,
                "crop": rm["crop"].strip(),
            }
        elif cur_region is not None:
            if raw.startswith("## ") or raw.startswith(f"`{cur_page['page_id']}`"):
                continue
            buf.append(raw)
    flush_region()
    if cur_page:
        pages.append(cur_page)
    return pages


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("md_dir", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("corpus.json"))
    args = ap.parse_args()
    corpus = []
    for f in sorted(args.md_dir.glob("Laubmann_*.md")):
        pages = parse_volume_md(f)
        corpus.extend(pages)
        print(f"{f.name}: {len(pages)} pages, "
              f"{sum(len(p['regions']) for p in pages)} regions")
    args.out.write_text(json.dumps(corpus, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"→ {args.out} ({len(corpus)} pages)")


if __name__ == "__main__":
    main()
