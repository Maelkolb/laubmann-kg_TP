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

_CITATION_RE = re.compile(
    r"\b(?:teste|nach\s+(?:Angabe|Mitteilung|Beobachtung)\s+von|laut|cf\.|vgl\.|"
    r"nach\s+[A-ZÄÖÜ][a-zäöüß]+)\b[^.;]*",
    re.UNICODE,
)


@dataclass(frozen=True)
class Citation:
    verbatim: str
    kind: str = "in_text_reference"


def extract_citations(text: str) -> list[Citation]:
    return [Citation(verbatim=m.group(0).strip()) for m in _CITATION_RE.finditer(text or "")]
