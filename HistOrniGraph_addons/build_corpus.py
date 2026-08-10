#!/usr/bin/env python3
"""Build a metadata-rich text corpus from all processed Laubmann volumes.

Reads regions/*.json from every Laubmann_NN_gemini output directory and
reconstructs, per page, the transcribed regions in reading order together with
their metadata, then segments each volume's reading-order stream into entries by
detecting line-initial dated headers.

This is a thin CLI over the ``laubmann_corpus`` package (importable, decoupled);
the flags below are unchanged so the existing Colab notebook keeps working.

Usage:
    python build_corpus.py
    python build_corpus.py --output-base "D:/some/other/path"
    python build_corpus.py --per-volume --include-nontext
    python build_corpus.py --volumes 1 5 9
    python build_corpus.py --report            # coverage summary only
    python build_corpus.py --multimodal        # multimodal catalogue only
    python build_corpus.py --no-census         # skip the schema sanity print

Output (written to corpus/ next to this script by default):
    corpus/corpus.md      — metadata-rich Markdown reconstruction (all volumes)
    corpus/corpus.json    — structured page-by-page corpus + per-region entries
    corpus/corpus.txt     — flat text with page/entry markers (grep-friendly)
    corpus/entries.jsonl  — one detected entry per line (full text)
    corpus/entries.csv    — entry index (cleaned text + preview)
    corpus/by_volume/Laubmann_NN.md      — only with --per-volume
    corpus/report.{json,md}              — only with --report
    corpus/multimodal/multimodal.{jsonl,csv,md}  — only with --multimodal
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from laubmann_corpus.corpus import build_text_corpus
from laubmann_corpus.loading import print_schema_census
from laubmann_corpus.multimodal import build_multimodal_corpus
from laubmann_corpus.report import write_report

OUTPUT_BASE = Path(r"G:\My Drive\HistOrniGraph_output")
CORPUS_DIR = Path(__file__).parent / "corpus"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-base", type=Path, default=OUTPUT_BASE,
                    help="Root dir containing Laubmann_NN_gemini folders")
    ap.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR,
                    help="Where to write the corpus (default: corpus/ next to this script)")
    ap.add_argument("--per-volume", action="store_true",
                    help="Also write one Markdown file per volume under corpus/by_volume/")
    ap.add_argument("--include-nontext", action="store_true",
                    help="Include Image/Object/Marginalia region descriptions in the body")
    ap.add_argument("--loose", action="store_true",
                    help="Also detect date headers that omit the year "
                         "(higher recall, lower precision)")
    ap.add_argument("--volumes", type=int, nargs="*", default=None,
                    help="Restrict to specific volume numbers, e.g. --volumes 1 5 9")
    ap.add_argument("--report", action="store_true",
                    help="Also write a per-volume coverage summary (report.{json,md})")
    ap.add_argument("--multimodal", action="store_true",
                    help="Also build the multimodal catalogue (multimodal/)")
    ap.add_argument("--only", choices=("text", "report", "multimodal"), default=None,
                    help="Run only one phase (skip the others). Default: run the text "
                         "corpus plus whichever of --report/--multimodal are set")
    ap.add_argument("--no-census", action="store_true",
                    help="Skip the one-line schema census sanity check")
    args = ap.parse_args()

    if not args.no_census:
        print_schema_census(args.output_base, args.volumes)

    # Phases are independent: --report and --multimodal now ADD outputs to a
    # normal run instead of replacing it. --only isolates a single phase.
    run_text   = args.only in (None, "text")
    run_report = args.report or args.only == "report"
    run_mm     = args.multimodal or args.only == "multimodal"

    if run_text:
        build_text_corpus(args.output_base, args.corpus_dir, args.per_volume,
                          args.include_nontext, args.loose, args.volumes)
    if run_report:
        write_report(args.output_base, args.corpus_dir, args.loose, args.volumes)
    if run_mm:
        build_multimodal_corpus(args.output_base, args.corpus_dir, args.loose, args.volumes)


if __name__ == "__main__":
    main()
