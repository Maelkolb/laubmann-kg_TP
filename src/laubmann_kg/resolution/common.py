"""Shared helpers of the entity-resolution stage: name normalisation, review
rows and the decision contract.

Review CSV contract (all four sections): one row per proposed merge
``variant -> canonical`` with a ``status``:

* ``auto``       – applied unless a reviewer writes ``n`` / ``no`` / ``0`` /
                   ``reject`` / ``keep`` into ``decision``;
* ``candidate``  – applied only when ``decision`` is ``y`` / ``yes`` / ``merge`` / ``1``;
* ``manual``     – a row a reviewer ADDED to the CSV (``merge_id`` = "<section>: <variant> -> <canonical>",
                   decision accepted) for a merge no rule proposes, e.g. an OCR variant "H. W. Wüst"
                   → "Walter Wüst"; applied when both names exist in the run.

The pipeline reads decisions from ``reviewed_csv`` (config) or, absent that,
from the review file it writes itself, so adjudication is a matter of editing
the CSV in place and re-running (same contract as the linking stage).
"""

from __future__ import annotations

import csv
import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

ACCEPT = {"y", "yes", "merge", "1", "accept"}
REJECT = {"n", "no", "0", "reject", "keep", "separate"}

MERGE_FIELDS = ["merge_id", "section", "variant", "canonical", "rule", "status",
                "n_variant", "n_canonical", "detail", "decision"]

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"})
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def fold(text: str) -> str:
    """Case-, umlaut- and punctuation-insensitive comparison key."""
    t = unicodedata.normalize("NFC", text or "").translate(_UMLAUTS).lower()
    t = t.replace("st. ", "sankt ").replace("st.", "sankt ")
    t = _PUNCT.sub(" ", t)
    return _WS.sub(" ", t).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass
class MergeRow:
    section: str
    variant: str
    canonical: str
    rule: str
    status: str            # auto | candidate
    n_variant: int = 0
    n_canonical: int = 0
    detail: str = ""

    @property
    def merge_id(self) -> str:
        return f"{self.section}: {self.variant} -> {self.canonical}"

    def as_dict(self) -> dict:
        return {"merge_id": self.merge_id, "section": self.section, "variant": self.variant,
                "canonical": self.canonical, "rule": self.rule, "status": self.status,
                "n_variant": self.n_variant, "n_canonical": self.n_canonical, "detail": self.detail}


@dataclass
class Decisions:
    """Reviewer decisions keyed by merge_id, i.e. by the exact
    ``variant -> canonical`` pair. A decision never spills over to another
    pair with the same variant: rejecting the candidate "Müller -> Arno Müller"
    must not veto the automatic "Müller -> Adolf Müller"."""
    by_id: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path | str]) -> "Decisions":
        d = cls()
        if not path:
            return d
        path = Path(path)
        if not path.exists():
            logger.warning("resolution decisions not found: %s", path)
            return d
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                dec = (row.get("decision") or "").strip().lower()
                if not dec:
                    continue
                d.by_id[row.get("merge_id") or ""] = dec
        return d

    def applies(self, row: MergeRow, variant_aliases: Iterable[str] = (), canonical_aliases: Iterable[str] = ()) -> bool:
        """``variant_aliases`` / ``canonical_aliases``: other spellings of the two
        sides (cluster members) — a decision recorded under one of them (an
        older canonical label, say) applies to this pair as well."""
        dec = self.by_id.get(row.merge_id)
        if dec is None and (variant_aliases or canonical_aliases):
            for v in (row.variant, *variant_aliases):
                for c in (row.canonical, *canonical_aliases):
                    dec = self.by_id.get(f"{row.section}: {v} -> {c}")
                    if dec is not None:
                        break
                if dec is not None:
                    break
        if row.status == "auto":
            return dec not in REJECT
        return dec in ACCEPT

    def manual(self, section: str) -> list[tuple[str, str]]:
        """Accepted (variant, canonical) pairs of ``section`` present in the
        decisions file — used for reviewer-added merges no rule proposed."""
        out = []
        prefix = f"{section}: "
        for mid, dec in self.by_id.items():
            if dec in ACCEPT and mid.startswith(prefix) and " -> " in mid:
                variant, canonical = mid[len(prefix):].split(" -> ", 1)
                out.append((variant.strip(), canonical.strip()))
        return out


def write_merge_rows(rows: Iterable[MergeRow], path: Path) -> Path:
    """Write review rows, carrying over non-blank decisions from an existing file
    (same behaviour as linking.review.write_review_csv)."""
    from laubmann_kg.linking.review import write_review_csv
    return write_review_csv([r.as_dict() for r in rows], MERGE_FIELDS, Path(path))


def choose_canonical(candidates: list[tuple[str, int]]) -> str:
    """Pick the canonical spelling: most used wins; ties -> the clean form (no
    stray punctuation / double spaces), then the shorter form (base form of a
    taxon name; "Wörthsee" over the longer folded "Woerthsee"), then diacritics."""
    def score(item):
        name, n = item
        clean = int(name == _WS.sub(" ", name).strip() and not name.rstrip().endswith((".", ",", ";", ":")))
        diacritics = sum(1 for ch in name if ch in "äöüÄÖÜß")
        return (n, clean, -len(name), diacritics)
    return max(candidates, key=score)[0]
