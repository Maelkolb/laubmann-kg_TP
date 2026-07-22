"""Extract in-text source references from diary entries.

Conservative heuristic for the historical convention of crediting an informant
or a written source ("teste X", "nach Angabe von Y", "cf. Z"). Returns verbatim
citation spans; downstream linking to a bibliography is out of scope here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Attribution markers only. Requires a following capitalized name so that travel
# ("nach München"), foraging ("nach Nahrung"), and "laut rufend" (loud, not
# "according to") are not mistaken for source references.
_NAME = r"[A-ZÄÖÜ][\wäöüß.\-]*(?:\s+[A-ZÄÖÜ][\wäöüß.\-]*)?"
_CITATION_RE = re.compile(
    r"\b(?:"
    rf"teste\s+{_NAME}"
    rf"|nach\s+(?:Angabe|Mitteilung|Beobachtung|Bericht)\s+(?:von\s+)?{_NAME}"
    rf"|laut\s+(?:Angabe|Mitteilung)\s+(?:von\s+)?{_NAME}"
    r"|(?:cf\.|vgl\.)\s+[A-ZÄÖÜ][^.;,]{0,40}"
    r")",
    re.UNICODE,
)


@dataclass(frozen=True)
class Citation:
    verbatim: str
    kind: str = "in_text_reference"


def extract_citations(text: str) -> list[Citation]:
    return [Citation(verbatim=m.group(0).strip()) for m in _CITATION_RE.finditer(text or "")]
