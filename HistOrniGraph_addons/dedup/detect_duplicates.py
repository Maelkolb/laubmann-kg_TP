#!/usr/bin/env python3
"""Detect duplicate / near-duplicate pages in a Laubmann corpus.

Reads corpus/corpus.json (the page-level source of truth; entries.jsonl and
entries.csv are derived from it) and writes:

    duplicates_report.csv    one row per suspected duplicate cluster
    duplicates_report.jsonl  clusters with full pair-level evidence
    quality_report.csv       per-page transcription-quality flags

Usage:
    python detect_duplicates.py corpus/corpus.json -o reports/
    python detect_duplicates.py corpus/corpus.json --scan-window 3 \
        --cluster-threshold 0.55 --image-root /path/to/HistOrniGraph_output
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

from laubmann_dedup import (Cluster, PageRecord, load_corpus_pages,
                            run_detection)

try:
    import imagehash
    from PIL import Image
    _HAVE_IMAGEHASH = True
except ImportError:
    _HAVE_IMAGEHASH = False


def _image_path(root: Path, p: PageRecord) -> Optional[Path]:
    cand = root / f"Laubmann_{p.volume:02d}_gemini" / "pages" / p.image
    return cand if cand.exists() else None


def add_image_signals(clusters: List[Cluster], image_root: Path) -> int:
    if not _HAVE_IMAGEHASH:
        print("[!] imagehash/PIL not installed — skipping image layer")
        return 0
    hashes: Dict[str, object] = {}
    confirmed = 0
    for c in clusters:
        for p in c.members:
            if p.page_uid in hashes:
                continue
            path = _image_path(image_root, p)
            if path:
                try:
                    hashes[p.page_uid] = imagehash.phash(Image.open(path))
                except Exception:
                    pass
        for s in c.pairs:
            ha, hb = hashes.get(s.a_uid), hashes.get(s.b_uid)
            if ha is None or hb is None:
                continue
            dist = ha - hb
            if dist <= 8:
                s.signals.append(f"phash_match(d={dist})")
                s.confidence = round(min(1.0, s.confidence + 0.15), 4)
                confirmed += 1
            elif dist >= 24:
                s.signals.append(f"phash_mismatch(d={dist})")
                s.confidence = round(max(0.0, s.confidence - 0.20), 4)
        if c.pairs:
            c.confidence = max(s.confidence for s in c.pairs)
            c.signals = sorted({sig for s in c.pairs for sig in s.signals})
    return confirmed


def write_reports(clusters: List[Cluster], pages: List[PageRecord],
                  out_dir: Path, review_threshold: float,
                  high_threshold: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "duplicates_report.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cluster_id", "confidence", "suggested_action", "relation",
                    "n_members", "members", "volumes", "scans", "page_numbers",
                    "signals", "suggested_keep", "suggested_drop", "decision",
                    "keep_override", "notes"])
        for c in clusters:
            action = "drop_duplicates" if c.confidence >= high_threshold else "review"
            w.writerow([
                c.cluster_id, f"{c.confidence:.3f}", action, c.relation,
                len(c.members),
                " | ".join(p.page_uid for p in c.members),
                " | ".join(sorted({f"{p.volume:02d}" for p in c.members})),
                " | ".join(str(p.scan) for p in c.members),
                " | ".join(p.page_number or "-" for p in c.members),
                "; ".join(c.signals),
                c.suggested_keep,
                " | ".join(c.suggested_drop),
                "", "", "",
            ])

    jsonl_path = out_dir / "duplicates_report.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for c in clusters:
            fh.write(json.dumps({
                "cluster_id": c.cluster_id,
                "confidence": c.confidence,
                "relation": c.relation,
                "signals": c.signals,
                "suggested_keep": c.suggested_keep,
                "suggested_drop": c.suggested_drop,
                "members": [{
                    "page_uid": p.page_uid, "volume": p.volume,
                    "page_id": p.page_id, "scan": p.scan, "side": p.side,
                    "page_number": p.page_number, "image": p.image,
                    "n_regions": p.n_body_regions,
                    "n_entry_starts": p.n_entry_starts,
                    "n_chars": len(p.norm_text),
                    "quality_flags": p.quality["flags"],
                } for p in c.members],
                "pairs": [{
                    "a": s.a_uid, "b": s.b_uid, "confidence": s.confidence,
                    "lev": s.lev, "token_set": s.token_set,
                    "jaccard": s.jaccard, "containment": s.containment,
                    "relation": s.relation, "signals": s.signals,
                    "sources": s.sources,
                } for s in c.pairs],
            }, ensure_ascii=False) + "\n")

    q_path = out_dir / "quality_report.csv"
    with q_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["page_uid", "volume", "scan", "page_number", "n_chars",
                    "repetition", "compression", "alpha_ratio", "flags"])
        for p in sorted(pages, key=lambda p: (-p.quality["repetition"],
                                              p.quality["alpha_ratio"])):
            if not p.quality["degenerate"]:
                continue
            q = p.quality
            w.writerow([p.page_uid, p.volume, p.scan, p.page_number,
                        q["n_chars"], f"{q['repetition']:.3f}",
                        f"{q['compression']:.3f}", f"{q['alpha_ratio']:.3f}",
                        "; ".join(q["flags"])])

    print(f"→ {csv_path}")
    print(f"→ {jsonl_path}")
    print(f"→ {q_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus_json", type=Path)
    ap.add_argument("-o", "--out-dir", type=Path, default=Path("dedup_reports"))
    ap.add_argument("--scan-window", type=int, default=3)
    ap.add_argument("--lsh-threshold", type=float, default=0.45)
    ap.add_argument("--cluster-threshold", type=float, default=0.55,
                    help="min pair confidence to enter a cluster (review floor)")
    ap.add_argument("--high-threshold", type=float, default=0.80,
                    help="confidence at which drop is suggested outright")
    ap.add_argument("--image-root", type=Path, default=None,
                    help="HistOrniGraph_output root for the optional "
                         "perceptual-hash layer")
    args = ap.parse_args()

    pages = load_corpus_pages(args.corpus_json)
    print(f"{len(pages)} pages loaded from {args.corpus_json}")
    clusters, scored = run_detection(
        pages, scan_window=args.scan_window,
        lsh_threshold=args.lsh_threshold,
        cluster_threshold=args.cluster_threshold)
    print(f"{len(scored)} candidate pairs scored, "
          f"{len(clusters)} clusters ≥ {args.cluster_threshold}")

    if args.image_root:
        n = add_image_signals(clusters, args.image_root)
        print(f"image layer confirmed {n} pairs")

    n_deg = sum(1 for p in pages if p.quality["degenerate"])
    print(f"{n_deg} pages flagged as degenerate transcription")
    write_reports(clusters, pages, args.out_dir,
                  args.cluster_threshold, args.high_threshold)


if __name__ == "__main__":
    main()
