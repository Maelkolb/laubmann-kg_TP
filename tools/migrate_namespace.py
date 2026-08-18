"""Rewrite the KG namespace in an existing export folder (TTL, JSON-LD, DwC-A
text files, review CSVs) — e.g. from the pre-2026-08-18 placeholder
``https://lkg.example.org/`` to ``https://w3id.org/laubmann-kg/``.

All instance uids are content-addressed, so a namespace change is a pure prefix
rewrite; no re-extraction is needed. Files are rewritten in place (a ``.bak``
copy is kept unless --no-backup).

    python tools/migrate_namespace.py <export_dir> [--from URL] [--to URL] [--no-backup]
"""
from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

DEFAULT_FROM = "https://lkg.example.org/"
DEFAULT_TO = "https://w3id.org/laubmann-kg/"
TEXT_SUFFIXES = {".ttl", ".jsonld", ".json", ".txt", ".csv", ".xml", ".nt", ".nq"}


def rewrite_file(path: Path, old: str, new: str, backup: bool) -> int:
    data = path.read_bytes()
    o, n = old.encode("utf-8"), new.encode("utf-8")
    count = data.count(o)
    if not count:
        return 0
    if backup:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    path.write_bytes(data.replace(o, n))
    return count


def rewrite_zip(path: Path, old: str, new: str, backup: bool) -> int:
    """DwC-A zip: rewrite member files and repack."""
    tmp = path.with_suffix(".tmp.zip")
    total = 0
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if Path(item.filename).suffix in TEXT_SUFFIXES:
                c = data.count(old.encode("utf-8"))
                if c:
                    total += c
                    data = data.replace(old.encode("utf-8"), new.encode("utf-8"))
            zout.writestr(item, data)
    if total:
        if backup:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        tmp.replace(path)
    else:
        tmp.unlink()
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("--from", dest="old", default=DEFAULT_FROM)
    ap.add_argument("--to", dest="new", default=DEFAULT_TO)
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()
    root = args.export_dir
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    grand = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix == ".bak":
            continue
        if path.suffix == ".zip":
            c = rewrite_zip(path, args.old, args.new, not args.no_backup)
        elif path.suffix in TEXT_SUFFIXES:
            c = rewrite_file(path, args.old, args.new, not args.no_backup)
        else:
            continue
        if c:
            grand += c
            print(f"{c:>9,}  {path.relative_to(root)}")
    print(f"replaced {grand:,} occurrences of {args.old} -> {args.new} under {root}")


if __name__ == "__main__":
    main()
