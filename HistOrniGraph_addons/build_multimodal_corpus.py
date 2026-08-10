#!/usr/bin/env python3
"""Build the multimodal catalogue of Laubmann's non-body-text regions.

Catalogues every ImageRegion, ObjectRegion, GraphicRegion, MarginaliaRegion and
InsertRegion (including folded inserts) across all volumes, each linked to the
nearest preceding diary entry header in reading order.

Thin CLI over ``laubmann_corpus.build_multimodal_corpus``; equivalent to
``build_corpus.py --multimodal``.

Usage:
    python build_multimodal_corpus.py
    python build_multimodal_corpus.py --output-base "D:/path" --volumes 1 5 9

Output (into <corpus-dir>/multimodal/):
    multimodal.jsonl  — one non-body-text region per line
    multimodal.csv    — flat catalogue
    multimodal.md     — browsable, inlines crop image paths
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from laubmann_corpus.loading import print_schema_census
from laubmann_corpus.multimodal import build_multimodal_corpus

OUTPUT_BASE = Path(r"G:\My Drive\HistOrniGraph_output")
CORPUS_DIR = Path(__file__).parent / "corpus"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-base", type=Path, default=OUTPUT_BASE)
    ap.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    ap.add_argument("--loose", action="store_true",
                    help="Use loose header detection when assigning entry context")
    ap.add_argument("--volumes", type=int, nargs="*", default=None)
    ap.add_argument("--no-census", action="store_true")
    args = ap.parse_args()

    if not args.no_census:
        print_schema_census(args.output_base, args.volumes)
    build_multimodal_corpus(args.output_base, args.corpus_dir, args.loose, args.volumes)


if __name__ == "__main__":
    main()
