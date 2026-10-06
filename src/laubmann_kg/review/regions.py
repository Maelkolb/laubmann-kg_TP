"""Decisions on the image and insert regions: which are dropped, how complete the others are, new crops.

``data/review/machine/region_quality_machine.csv`` (tools/validation_ui/machine_review/region_check_combine.py and
recrop.py) holds one row per region of the region catalogue::

    region_uid     required
    decision       keep | drop
    reason         duplicate | blank | fragment (drop only)
    duplicate_of   the region of the same entry that shows the object better (duplicate only)
    completeness   complete | cut off | empty (the two checks do not agree)
    crop           the new crop of a region its box cut off (regions_v2/<page_id>/<region_uid>.jpg)
    agreement      sources that agree (a drop needs 2)

A reviewer's file of the same form (``review/region_decisions.csv``) wins over the machine rows.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from laubmann_kg.normalization import vocabularies as vocab

logger = logging.getLogger(__name__)


@dataclass
class RegionDecision:
    drop: bool = False
    reason: str = ""
    duplicate_of: str = ""
    completeness: Optional[str] = None
    crop: Optional[str] = None


def load_region_decisions(*paths: Optional[str], min_agreement: int = 2) -> dict[str, RegionDecision]:
    """region_uid -> decision; later files win (machine first, then the reviewer's)."""
    decisions: dict[str, RegionDecision] = {}
    for path in paths:
        if not path or not Path(path).exists():
            if path:
                logger.info("no region decisions at %s", path)
            continue
        with open(path, encoding="utf-8", newline="") as h:
            rows = list(csv.DictReader(h))
        for r in rows:
            uid = (r.get("region_uid") or "").strip()
            if not uid:
                continue
            try:
                agreement = int(r.get("agreement") or 0)
            except ValueError:
                agreement = 0
            human = not (r.get("reviewed_by") or "").startswith("machine")
            drop = (r.get("decision") or "").strip() == "drop" and (human or agreement >= min_agreement)
            completeness = (r.get("completeness") or "").strip() or None
            if completeness not in vocab.REGION_COMPLETENESS:
                completeness = None
            decisions[uid] = RegionDecision(drop=drop, reason=(r.get("reason") or "").strip(),
                                            duplicate_of=(r.get("duplicate_of") or "").strip(), completeness=completeness,
                                            crop=(r.get("crop") or "").strip() or None)
        logger.info("region decisions %s: %d rows, %d drops", Path(path).name, len(rows),
                    sum(1 for r in rows if (r.get("decision") or "") == "drop"))
    return decisions
