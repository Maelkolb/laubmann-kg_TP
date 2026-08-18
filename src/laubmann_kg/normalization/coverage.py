"""Volume time-coverage checks: OCR year repair and out-of-span flags.

Every diary volume states its span on the title page ("Ornithologische
Tagebuchnotizen … Juli 1950 - August 1951"); ``configs/volume_coverage.yaml``
holds that table. An entry dated outside its volume's span is either

* an OCR slip in the year (``1901`` for ``1951``, ``1934`` for ``1943``,
  ``194.`` truncated to ``19``) — repaired when the sequence neighbours of the
  entry (previous/next entries in page order that ARE inside the span) agree
  on a year and the entry is a dated day (field-day / correspondence / other),
  never a species digest or retrospective note, which legitimately carry old
  dates (an 1859 museum specimen listed in 1919, Kaufbeuren youth notes …);
* a scan of another volume filed under this one (page-document → volume
  reassignment; the known Vol 1 pages in the Vol 15 scan set);
* content that is not an entry at all (an obituary with a 19th-century birth
  date) — outside Laubmann's diary span altogether → excluded;
* or a genuinely off-span record — kept and flagged for review.

Nothing here reads prose: the decisions use the entry date, the entry kind the
model assigned, the page document id and the neighbours' dates.
"""

from __future__ import annotations

import calendar
import difflib
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

from laubmann_kg.qa import QAFlag

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("configs/volume_coverage.yaml")
# entry kinds whose dates are corrected against the neighbours; digests and
# retrospective notes keep their (old) dates untouched
CORRECT_KINDS = ("field-day", "correspondence", "other")
RETROSPECTIVE_KINDS = ("species-digest", "retrospective")


@dataclass(frozen=True)
class Span:
    start: str   # YYYY-MM
    end: str     # YYYY-MM

    def contains(self, ym: str, tolerance_months: int = 0) -> bool:
        return _ym_add(self.start, -tolerance_months) <= ym <= _ym_add(self.end, tolerance_months)


def _ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += k
    while m < 1:
        m += 12; y -= 1
    while m > 12:
        m -= 12; y += 1
    return f"{y:04d}-{m:02d}"


class VolumeCoverage:
    def __init__(self, spans: dict[int, Span]) -> None:
        self.spans = spans

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "VolumeCoverage":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        spans = {}
        for vol, item in (data.get("volumes") or {}).items():
            spans[int(vol)] = Span(str(item["start"])[:7], str(item["end"])[:7])
        return cls(spans)

    def span(self, volume: int) -> Optional[Span]:
        return self.spans.get(int(volume))

    def contains(self, volume: int, iso_date: str, tolerance_months: int = 1) -> Optional[bool]:
        """True/False, or None when the volume has no span."""
        span = self.span(volume)
        if span is None or not iso_date or len(iso_date) < 7:
            return None
        return span.contains(iso_date[:7], tolerance_months)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _doc_prefix(page_id: str) -> str:
    return (page_id or "").split("_")[0]


def document_volumes(entries) -> dict[str, int]:
    """Home volume of every page document (the volume it mostly appears in)."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for e in entries:
        doc = _doc_prefix(e.page_id)
        if doc:
            counts[doc][int(e.volume)] += 1
    return {doc: c.most_common(1)[0][0] for doc, c in counts.items()}


_YEAR_TOKEN = re.compile(r"(\d{2,4})\s*[.\)]?\s*$")


def _raw_year_digits(verbatim: Optional[str]) -> Optional[str]:
    """The year token as OCR wrote it (last number of the verbatim date)."""
    if not verbatim:
        return None
    m = _YEAR_TOKEN.search(verbatim.strip())
    return m.group(1) if m else None


def _digit_distance(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))


def _valid_date(year: int, month: int, day: int) -> Optional[str]:
    try:
        last = calendar.monthrange(year, month)[1]
    except ValueError:
        return None
    if not 1 <= day <= last:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _months_between(a: str, b: str) -> int:
    return abs((int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7]))


def _similar(a: str, b: str, limit: int = 300) -> float:
    return difflib.SequenceMatcher(None, (a or "")[:limit], (b or "")[:limit]).ratio()


# --------------------------------------------------------------------------
# main pass
# --------------------------------------------------------------------------

def apply_coverage(entries: list, coverage: VolumeCoverage, config: Optional[dict] = None
                   ) -> tuple[list, list[QAFlag]]:
    """Reassign misfiled entries, repair OCR years, flag/exclude off-span entries.

    Returns ``(kept_entries, flags)``; ``entries`` must be in corpus (page)
    order. Mutates entry.volume / entry_date / entry_date_end / date_note.
    """
    cfg = config or {}
    tol = int(cfg.get("tolerance_months", 1))
    neighbours = int(cfg.get("neighbours", 2))
    max_digits = int(cfg.get("max_digit_changes", 2))
    earliest = int(cfg.get("earliest_year", 1900))
    latest = int(cfg.get("latest_year", 1966))
    correct_kinds = tuple(cfg.get("correct_kinds", CORRECT_KINDS))
    exclude = bool(cfg.get("exclude", True))
    dup_threshold = float(cfg.get("duplicate_similarity", 0.85))
    flags: list[QAFlag] = []

    # 1. page document -> volume (misfiled scans)
    homes = document_volumes(entries)
    reassigned = []
    for e in entries:
        home = homes.get(_doc_prefix(e.page_id))
        if home is not None and home != int(e.volume):
            flags.append(QAFlag(e.entry_id, e.entry_uid, "volume_reassigned",
                                f"Seitendokument gehört zu Band {home} (digitalisiert unter Band {e.volume})",
                                "flagged", str(home)))
            e.volume = home
            reassigned.append(e)

    # 2. per volume, in sequence
    by_vol: dict[int, list] = defaultdict(list)
    for e in entries:
        by_vol[int(e.volume)].append(e)
    drop: set[str] = set()

    for vol, seq in by_vol.items():
        span = coverage.span(vol)
        if span is None:
            continue
        inside = [bool(e.entry_date) and span.contains(e.entry_date[:7], tol) for e in seq]
        for k, e in enumerate(seq):
            if not e.entry_date or inside[k]:
                continue
            year = int(e.entry_date[:4])
            # neighbours inside the span, up to N on each side
            ctx = [seq[j].entry_date for j in range(k - 1, -1, -1) if inside[j]][:neighbours] + \
                  [seq[j].entry_date for j in range(k + 1, len(seq)) if inside[j]][:neighbours]
            years = Counter(int(d[:4]) for d in ctx)
            fixed = None
            if ctx and e.entry_kind in correct_kinds:
                cand_year, votes = years.most_common(1)[0]
                agree = votes >= min(2, len(ctx))
                raw = _raw_year_digits(e.verbatim_event_date)
                digits_ok = (raw is not None and len(raw) < 4) or \
                            _digit_distance(f"{year:04d}", f"{cand_year:04d}") <= max_digits
                if agree and digits_ok:
                    new = _valid_date(cand_year, int(e.entry_date[5:7]), int(e.entry_date[8:10]))
                    if new and span.contains(new[:7], tol) and \
                            all(_months_between(new, d) <= 3 for d in ctx):
                        fixed = new
            if fixed:
                old = e.entry_date
                note = (f"Jahr aus Bandabdeckung/Nachbareinträgen korrigiert "
                        f"(OCR {e.verbatim_event_date or old} → {fixed[:4]}, Band {vol} {span.start}…{span.end})")
                if e.entry_date_end and e.entry_date_end[:4] == old[:4]:
                    e.entry_date_end = fixed[:4] + e.entry_date_end[4:]
                e.entry_date = fixed
                e.date_note = f"{e.date_note}; {note}" if e.date_note else note
                flags.append(QAFlag(e.entry_id, e.entry_uid, "date_year_corrected",
                                    note, "flagged", f"{old} -> {fixed}"))
                continue
            retrospective = e.entry_kind in RETROSPECTIVE_KINDS
            if (year < earliest or year > latest) and not retrospective:
                excluded = exclude
                flags.append(QAFlag(e.entry_id, e.entry_uid, "date_out_of_span",
                                    f"Jahr {year} ausserhalb der Tagebuchzeit {earliest}-{latest} "
                                    f"(Band {vol} {span.start}…{span.end}); kein Eintrag",
                                    "excluded" if excluded else "flagged", e.entry_date))
                if excluded:
                    drop.add(e.entry_uid)
                continue
            flags.append(QAFlag(e.entry_id, e.entry_uid, "date_out_of_coverage",
                                f"Datum ausserhalb Band {vol} ({span.start}…{span.end})"
                                + (f"; Eintragstyp {e.entry_kind}" if e.entry_kind else "")
                                + (f"; Nachbarn {sorted(set(d[:7] for d in ctx))}" if ctx else ""),
                                "flagged", e.entry_date))

    # 3. duplicates created by misfiled scans: same volume, same date, near-identical text
    for e in reassigned:
        if e.entry_uid in drop or not e.entry_date:
            continue
        for other in by_vol[int(e.volume)]:
            if other is e or other.entry_uid in drop or other.entry_date != e.entry_date:
                continue
            if len(e.text_clean or "") >= 80 and _similar(e.text_clean, other.text_clean) >= dup_threshold:
                flags.append(QAFlag(e.entry_id, e.entry_uid, "duplicate_entry",
                                    f"Doublette von {other.entry_id} (gleiches Datum, Text ≥ {dup_threshold:.0%} ähnlich)",
                                    "excluded" if exclude else "flagged", other.entry_id))
                if exclude:
                    drop.add(e.entry_uid)
                break

    kept = [e for e in entries if e.entry_uid not in drop]
    if flags:
        logger.info("coverage: %s", dict(Counter(f.reason for f in flags)))
    return kept, flags


def summarize(flags: Iterable[QAFlag]) -> dict[str, int]:
    return dict(Counter(f.reason for f in flags))
