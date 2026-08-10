#!/usr/bin/env python3
"""Duplicate-page detection for the HistOrniGraph Laubmann corpus.

Detects pages that correspond to the same physical journal page but appear
more than once in the corpus. Observed root causes (see METHODS.md):

  A. double capture   — the same spread photographed twice; consecutive scan
                        numbers, same batch UUID, both L and R sides repeat
  B. cross-run        — the same page images processed by a second pipeline
                        run whose outputs landed in a (possibly different)
                        volume directory; identical page_id, different OCR
  C. split/unsplit    — a scan present both as _L/_R pages and as an unsplit
                        whole-scan page (containment, not symmetric equality)
  D. _full variants   — secondary "full view" captures of insert pages

Layers: adjacency-windowed candidate generation, page-number and page-id
collisions, a global MinHash-LSH pass for stragglers, then per-pair scoring
that combines text similarity (rapidfuzz + shingle Jaccard) with structural
signals (page-number token, entry-date sequence, text boundaries). A page
quality screen flags degenerate transcriptions (repetition loops, bleed-
through gibberish) whose text similarity cannot be trusted.

Import surface:
    load_corpus_pages, PageRecord, quality_metrics,
    generate_candidates, score_pair, PairScore,
    cluster_pairs, Cluster, suggest_keep, run_detection
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from rapidfuzz import fuzz as _rf_fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:
    from difflib import SequenceMatcher as _SeqMatcher
    _HAVE_RAPIDFUZZ = False

try:
    from datasketch import MinHash as _DsMinHash, MinHashLSH as _DsLSH
    _HAVE_DATASKETCH = True
except ImportError:
    _HAVE_DATASKETCH = False

MINHASH_PERM = 128
SHINGLE_K = 5
BOUNDARY_N = 40
MIN_TEXT_LEN = 60

_MARKUP_RE = re.compile(r"</?(?:u|sup|sub|b|i|em|strong)\s*>", re.IGNORECASE)
_DEHYPH_RE = re.compile(r"(\w)-[ \t]*\n+[ \t]*")
_WS_RE = re.compile(r"\s+")
_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_PID_RE = re.compile(r"^(?P<stem>.*?)_(?P<scan>\d{3,5})(?:_(?P<side>[LRlr]))?(?:_(?P<variant>full))?$")
_PNUM_RE = re.compile(r"\d+")


def normalize_text(text: str) -> str:
    t = _MARKUP_RE.sub("", text)
    t = _DEHYPH_RE.sub(r"\1", t)
    t = unicodedata.normalize("NFC", t)
    t = _WS_RE.sub(" ", t).casefold()
    return t.translate(_UMLAUT).strip()


def normalize_pnum(pnum: str) -> str:
    nums = _PNUM_RE.findall(pnum or "")
    return nums[-1] if nums else ""


def quality_metrics(norm_text: str) -> Dict[str, Any]:
    """Screen for degenerate transcription output.

    repetition   — dominant-trigram fraction; a Gemini repetition loop pushes
                   this toward 1.0
    compression  — zlib ratio; looped text compresses far below normal prose
    alpha_ratio  — letters+spaces / all chars; bleed-through gibberish is
                   symbol-heavy
    """
    n = len(norm_text)
    out = {"n_chars": n, "repetition": 0.0, "compression": 1.0,
           "alpha_ratio": 1.0, "degenerate": False, "flags": []}
    if n < 200:
        return out
    toks = norm_text.split()
    grams = [" ".join(toks[i:i + 3]) for i in range(len(toks) - 2)]
    if grams:
        out["repetition"] = Counter(grams).most_common(1)[0][1] / len(grams)
    out["compression"] = len(zlib.compress(norm_text.encode("utf-8"), 6)) / n
    out["alpha_ratio"] = sum(c.isalpha() or c.isspace() for c in norm_text) / n
    if out["repetition"] > 0.20 or (out["compression"] < 0.12 and n > 1000):
        out["flags"].append("repetition_loop")
    if out["alpha_ratio"] < 0.60:
        out["flags"].append("low_alpha")
    if n > 8000 and out["compression"] < 0.20:
        out["flags"].append("suspicious_length")
    out["degenerate"] = bool(out["flags"])
    return out


@dataclass
class PageRecord:
    volume: int
    page_id: str
    scan: int
    page_number: str
    regions: List[Dict[str, Any]]
    image: str = ""

    page_uid: str = field(init=False)
    stem: str = field(init=False)
    side: str = field(init=False)
    variant: str = field(init=False)
    norm_text: str = field(init=False)
    pnum_norm: str = field(init=False)
    date_seq: Tuple[str, ...] = field(init=False)
    boundary: Tuple[str, str] = field(init=False)
    text_hash: str = field(init=False)
    n_body_regions: int = field(init=False)
    n_entry_starts: int = field(init=False)
    quality: Dict[str, Any] = field(init=False)
    shingles: Set[int] = field(init=False, repr=False)
    minhash: Any = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self.page_uid = f"L{self.volume:02d}:{self.page_id}"
        m = _PID_RE.match(self.page_id)
        self.stem = m.group("stem") if m else self.page_id
        self.side = (m.group("side") or "").upper() if m else ""
        self.variant = (m.group("variant") or "") if m else ""
        self.norm_text = normalize_text(
            "\n".join(r.get("text", "") for r in self.regions))
        self.pnum_norm = normalize_pnum(self.page_number)
        self.date_seq = tuple(
            e["date_norm"] or e["date"]
            for r in self.regions for e in r.get("entry_starts", []))
        t = self.norm_text
        self.boundary = (t[:BOUNDARY_N], t[-BOUNDARY_N:]) if t else ("", "")
        self.text_hash = hashlib.sha1(t.encode("utf-8")).hexdigest() if t else ""
        self.n_body_regions = sum(1 for r in self.regions if r.get("text"))
        self.n_entry_starts = len(self.date_seq)
        self.quality = quality_metrics(t)
        self.shingles = _shingle_set(t)
        if _HAVE_DATASKETCH and self.shingles:
            mh = _DsMinHash(num_perm=MINHASH_PERM)
            for s in self.shingles:
                mh.update(s.to_bytes(8, "little"))
            self.minhash = mh

    @classmethod
    def from_corpus_page(cls, page: Dict[str, Any]) -> "PageRecord":
        return cls(volume=int(page["volume"]), page_id=page["page_id"],
                   scan=int(page.get("scan", 0)),
                   page_number=str(page.get("page_number", "") or ""),
                   regions=page.get("regions", []),
                   image=page.get("image", ""))


def _shingle_set(text: str, k: int = SHINGLE_K) -> Set[int]:
    if len(text) < k:
        return set()
    return {zlib.crc32(text[i:i + k].encode("utf-8")) & 0xFFFFFFFFFFFFFFFF
            for i in range(len(text) - k + 1)}


def load_corpus_pages(corpus_json: Path) -> List[PageRecord]:
    data = json.loads(Path(corpus_json).read_text(encoding="utf-8"))
    return [PageRecord.from_corpus_page(p) for p in data]


# ── similarity ───────────────────────────────────────────────────────────────

def _lev_ratio(a: str, b: str) -> float:
    if _HAVE_RAPIDFUZZ:
        return _rf_fuzz.ratio(a, b) / 100.0
    return _SeqMatcher(None, a, b).ratio()


def _token_set_ratio(a: str, b: str) -> float:
    if _HAVE_RAPIDFUZZ:
        return _rf_fuzz.token_set_ratio(a, b) / 100.0
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / max(len(ta | tb), 1)


def _jaccard(a: Set[int], b: Set[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _containment(a: Set[int], b: Set[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


@dataclass
class PairScore:
    a_uid: str
    b_uid: str
    lev: float
    token_set: float
    jaccard: float
    containment: float
    relation: str
    confidence: float
    signals: List[str]
    sources: List[str]


def score_pair(a: PageRecord, b: PageRecord,
               sources: Optional[Sequence[str]] = None) -> PairScore:
    """Combine text similarity with structural corroboration.

    confidence blends the text layer (Levenshtein / token-set / shingle
    Jaccard) with structural signals; degenerate pages cap the text layer
    because repetition loops look alike without being the same page.
    """
    signals: List[str] = []
    ta, tb = a.norm_text, b.norm_text
    short = min(len(ta), len(tb)) < MIN_TEXT_LEN

    exact = bool(a.text_hash and a.text_hash == b.text_hash)
    lev = 1.0 if exact else (_lev_ratio(ta, tb) if not short else 0.0)
    tsr = 1.0 if exact else (_token_set_ratio(ta, tb) if not short else 0.0)
    jac = 1.0 if exact else _jaccard(a.shingles, b.shingles)
    con = 1.0 if exact else _containment(a.shingles, b.shingles)

    degenerate = a.quality["degenerate"] or b.quality["degenerate"]
    text_score = 0.5 * lev + 0.2 * tsr + 0.3 * jac
    if degenerate:
        text_score = min(text_score, 0.45)
        signals.append("degenerate_member")
    if exact:
        signals.append("exact_text")
    elif lev >= 0.90:
        signals.append("near_exact_text")
    elif lev >= 0.75:
        signals.append("high_text_sim")

    len_ratio = (min(len(ta), len(tb)) / max(len(ta), len(tb))
                 if ta and tb else 0.0)
    relation = "same_page"
    if con >= 0.70 and jac < 0.60 and len_ratio < 0.65:
        relation = "containment"
        signals.append("containment")
        text_score = max(text_score, min(con, 0.75) if not degenerate else 0.45)

    struct = 0.0
    if a.pnum_norm and a.pnum_norm == b.pnum_norm:
        struct += 0.40
        signals.append("same_page_number")
    if a.date_seq and a.date_seq == b.date_seq:
        struct += 0.45
        signals.append("same_entry_dates")
    elif a.date_seq and b.date_seq:
        overlap = len(set(a.date_seq) & set(b.date_seq)) / \
            max(len(set(a.date_seq) | set(b.date_seq)), 1)
        if overlap >= 0.5:
            struct += 0.25
            signals.append("overlapping_entry_dates")
    if not short and a.boundary[0] and a.boundary[0] == b.boundary[0]:
        struct += 0.20
        signals.append("same_start")
    if not short and a.boundary[1] and a.boundary[1] == b.boundary[1]:
        struct += 0.15
        signals.append("same_end")
    if a.volume == b.volume and abs(a.scan - b.scan) <= 2:
        struct += 0.10
        signals.append("adjacent_scan")
    if a.page_id == b.page_id and a.volume != b.volume:
        struct += 0.50
        signals.append("same_page_id_cross_volume")
    struct = min(struct, 1.0)

    if short:
        confidence = min(0.5 * (1.0 if ta == tb and ta else 0.0) + 0.5 * struct,
                         0.70)
        signals.append("short_text")
    else:
        confidence = min(0.72 * text_score + 0.28 * struct, 1.0)
        if text_score < 0.35:
            confidence = min(confidence, 0.40)

    return PairScore(a.page_uid, b.page_uid, round(lev, 4), round(tsr, 4),
                     round(jac, 4), round(con, 4), relation,
                     round(confidence, 4), signals, list(sources or []))


# ── candidate generation ─────────────────────────────────────────────────────

def generate_candidates(pages: Sequence[PageRecord], scan_window: int = 3,
                        lsh_threshold: float = 0.45
                        ) -> Dict[Tuple[str, str], Set[str]]:
    """Return {(uid_a, uid_b): {source layers}} with uid_a < uid_b."""
    cands: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    by_uid = {p.page_uid: p for p in pages}

    def add(a: PageRecord, b: PageRecord, src: str) -> None:
        if a.page_uid == b.page_uid:
            return
        key = tuple(sorted((a.page_uid, b.page_uid)))
        cands[key].add(src)

    by_vol: Dict[int, List[PageRecord]] = defaultdict(list)
    for p in pages:
        by_vol[p.volume].append(p)

    for vol_pages in by_vol.values():
        ordered = sorted(vol_pages, key=lambda p: (p.scan, p.side))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if b.scan - a.scan > scan_window:
                    break
                add(a, b, "scan_window")
        by_pnum: Dict[str, List[PageRecord]] = defaultdict(list)
        for p in vol_pages:
            if p.pnum_norm:
                by_pnum[p.pnum_norm].append(p)
        for group in by_pnum.values():
            for a, b in combinations(group, 2):
                add(a, b, "page_number")

    by_pid: Dict[str, List[PageRecord]] = defaultdict(list)
    for p in pages:
        by_pid[p.page_id].append(p)
    for group in by_pid.values():
        for a, b in combinations(group, 2):
            add(a, b, "page_id_collision")

    for key in _lsh_pairs(pages, lsh_threshold):
        add(by_uid[key[0]], by_uid[key[1]], "lsh_global")

    return dict(cands)


def _lsh_pairs(pages: Sequence[PageRecord],
               threshold: float) -> Set[Tuple[str, str]]:
    pairs: Set[Tuple[str, str]] = set()
    usable = [p for p in pages if len(p.norm_text) >= MIN_TEXT_LEN]
    if _HAVE_DATASKETCH:
        lsh = _DsLSH(threshold=threshold, num_perm=MINHASH_PERM)
        for p in usable:
            if p.minhash is not None:
                lsh.insert(p.page_uid, p.minhash)
        by_uid = {p.page_uid: p for p in usable}
        for p in usable:
            if p.minhash is None:
                continue
            for other in lsh.query(p.minhash):
                if other != p.page_uid:
                    pairs.add(tuple(sorted((p.page_uid, other))))
        return pairs
    buckets: Dict[int, List[PageRecord]] = defaultdict(list)
    for p in usable:
        for h in sorted(p.shingles)[:24]:
            buckets[h].append(p)
    for group in buckets.values():
        if len(group) < 2 or len(group) > 20:
            continue
        for a, b in combinations(group, 2):
            pairs.add(tuple(sorted((a.page_uid, b.page_uid))))
    return pairs


# ── clustering ───────────────────────────────────────────────────────────────

@dataclass
class Cluster:
    cluster_id: str
    members: List[PageRecord]
    pairs: List[PairScore]
    confidence: float
    signals: List[str]
    relation: str
    suggested_keep: str
    suggested_drop: List[str]


class _UnionFind:
    def __init__(self) -> None:
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _keep_score(p: PageRecord, dominant_stem: Dict[int, str]) -> Tuple:
    return (
        0 if p.quality["degenerate"] else 1,
        1 if p.stem == dominant_stem.get(p.volume, p.stem) else 0,
        p.n_entry_starts,
        p.n_body_regions,
        len(p.norm_text),
        -p.scan,
    )


def suggest_keep(members: Sequence[PageRecord],
                 dominant_stem: Dict[int, str]) -> str:
    return max(members, key=lambda p: _keep_score(p, dominant_stem)).page_uid


def cluster_pairs(pages: Sequence[PageRecord], scored: Sequence[PairScore],
                  threshold: float) -> List[Cluster]:
    by_uid = {p.page_uid: p for p in pages}
    stems: Dict[int, Counter] = defaultdict(Counter)
    for p in pages:
        stems[p.volume][p.stem] += 1
    dominant = {v: c.most_common(1)[0][0] for v, c in stems.items()}

    uf = _UnionFind()
    kept = [s for s in scored if s.confidence >= threshold]
    for s in kept:
        uf.union(s.a_uid, s.b_uid)
    groups: Dict[str, List[str]] = defaultdict(list)
    for uid in {u for s in kept for u in (s.a_uid, s.b_uid)}:
        groups[uf.find(uid)].append(uid)

    clusters: List[Cluster] = []
    for uids in groups.values():
        members = sorted((by_uid[u] for u in uids),
                         key=lambda p: (p.volume, p.scan, p.side))
        muids = {p.page_uid for p in members}
        cpairs = [s for s in kept if s.a_uid in muids and s.b_uid in muids]
        conf = max(s.confidence for s in cpairs)
        signals = sorted({sig for s in cpairs for sig in s.signals})
        relation = ("containment"
                    if all(s.relation == "containment" for s in cpairs)
                    else "same_page")
        keep = suggest_keep(members, dominant)
        clusters.append(Cluster(
            cluster_id="", members=members, pairs=cpairs,
            confidence=conf, signals=signals, relation=relation,
            suggested_keep=keep,
            suggested_drop=[u for u in sorted(muids) if u != keep]))
    clusters.sort(key=lambda c: (-c.confidence,
                                 c.members[0].volume, c.members[0].scan))
    for i, c in enumerate(clusters, 1):
        c.cluster_id = f"dup{i:04d}"
    return clusters


# ── driver ───────────────────────────────────────────────────────────────────

def run_detection(pages: Sequence[PageRecord], scan_window: int = 3,
                  lsh_threshold: float = 0.45, cluster_threshold: float = 0.55
                  ) -> Tuple[List[Cluster], List[PairScore]]:
    by_uid = {p.page_uid: p for p in pages}
    cands = generate_candidates(pages, scan_window, lsh_threshold)
    scored = [score_pair(by_uid[a], by_uid[b], sorted(srcs))
              for (a, b), srcs in cands.items()]
    clusters = cluster_pairs(pages, scored, cluster_threshold)
    return clusters, scored
