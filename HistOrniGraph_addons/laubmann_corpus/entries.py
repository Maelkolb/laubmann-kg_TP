"""Entry-header detection and date / location normalization.

A Laubmann entry header is a LINE-INITIAL date (with a year), e.g.

    7. April 1917. <u>München</u>.        location underlined
    30. Juli 1960. München.               location plain
    26. I. 48 Karlsfeld                   roman month, 2-digit year, plain loc
    10. August 1938.                      date only (no location on the line)

The date is the reliable anchor; the location may be underlined or plain.  A
date inside running prose is rejected (a lowercase word / "," / ";" follows it).

Normalization returns structured provenance so ambiguous headers can be reviewed
later: which regex variant matched, and char offsets on the header line.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

_MONTH_NAME = (
    r"J[äa]n(?:ner|uar|\.)?|Feb(?:ruar|\.)?|M[äa]r(?:z|\.)?|Apr(?:il|\.)?|Mai|"
    r"Jun[i]?|Jul[i]?|Aug(?:ust|\.)?|Sept?(?:ember|\.)?|Okt(?:ober|\.)?|"
    r"Nov(?:ember|\.)?|Dez(?:ember|\.)?"
)
_MONTH_EN = (
    r"January|February|March|May|June|July|"
    r"September|October|November|December|"
    r"Oct\.?|Nov\.?|Dec\.?|Sept?\.?"
)
_MONTH_ROMAN = r"VIII|XII|VII|III|XI|IX|IV|VI|II|X|V|I"
_MONTH = rf"(?:{_MONTH_NAME}|{_MONTH_EN}|(?:{_MONTH_ROMAN})\.?)"
_DAY = r"\d{1,2}\.?"
_YEAR = r"(?:1[5-9]\d{2}|20\d{2}|\d{2})"
_DATEY = rf"{_DAY}\s*{_MONTH}[\s.]*{_YEAR}"
_DATE = rf"{_DAY}\s*{_MONTH}[\s.]*(?:{_YEAR})?"
_BULLET = r"(?:[-*\u2022]\s*)?"


def _header_re(year_required: bool) -> "re.Pattern":
    date = _DATEY if year_required else _DATE
    return re.compile(
        rf"^[ \t]*{_BULLET}(?:<u>[ \t]*)?(?P<date>(?i:{date}))[ \t]*(?:</u>)?[ \t]*"
        rf"[.:]?(?P<rest>[^\n]*)$",
        re.MULTILINE,
    )


HEADER_STRICT = _header_re(True)
HEADER_LOOSE = _header_re(False)

_U_FIRST = re.compile(r"^<u>\s*(.*?)\s*</u>")
_WEEKDAY = re.compile(
    r"(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonnabend|Sonntag)",
    re.IGNORECASE,
)
_WD_LEAD = re.compile(rf"^{_WEEKDAY.pattern}\b\.?,?\s*", re.IGNORECASE)

_DATE_PARSE = re.compile(
    rf"^\s*(?P<d>\d{{1,2}})\.?\s*(?P<m>{_MONTH})[\s.]*(?P<y>{_YEAR})?", re.IGNORECASE
)

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
          "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
_MNAME = {"jan": 1, "jän": 1, "feb": 2, "mar": 3, "mär": 3, "apr": 4,
          "mai": 5, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
          "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12}

_MARKUP_RE = re.compile(r"</?(?:u|sup|sub|b|i|em|strong)\s*>", re.IGNORECASE)
_DEHYPHEN_RE = re.compile(r"(\w)-[ \t]*\n+[ \t]*([a-zäöüß])")
_WS_RE = re.compile(r"\s*\n+\s*")


def _month_to_num(raw: str) -> Optional[int]:
    s = raw.strip().rstrip(".").lower()
    if s in _ROMAN:
        return _ROMAN[s]
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= 12 else None
    return _MNAME.get(s[:3])


def normalize_date(date_raw: str) -> Dict[str, Any]:
    """Best-effort ISO date with provenance.  2-digit years read as 19xx —
    Laubmann's diary is entirely 20th-century, so "48" → 1948, "03" → 1903.

    Returns a dict: date_norm, year, month, day, month_source, year_form.
    """
    m = _DATE_PARSE.match(date_raw)
    if not m:
        return {"date_norm": None, "year": None, "month": None, "day": None,
                "month_source": None, "year_form": None}
    day = int(m.group("d"))
    m_raw = m.group("m") or ""
    mon = _month_to_num(m_raw)
    mkey = m_raw.strip().rstrip(".").lower()
    if mkey in _ROMAN:
        month_source = "roman"
    elif mkey.isdigit():
        month_source = "numeric"
    else:
        month_source = "name"
    yraw = m.group("y") or ""
    if len(yraw) == 4:
        year: Optional[int] = int(yraw)
        year_form = "4-digit"
    elif len(yraw) == 2:
        year = 1900 + int(yraw)
        year_form = "2-digit→19xx"
    else:
        year = None
        year_form = None
    date_norm = None
    if year and mon and 1 <= day <= 31:
        date_norm = f"{year:04d}-{mon:02d}-{day:02d}"
    return {"date_norm": date_norm, "year": year, "month": mon, "day": day,
            "month_source": month_source, "year_form": year_form}


def extract_location(rest: str) -> Dict[str, Any]:
    """Pull the location out of the text after a date header, with provenance.

    Returns a dict: location (str), reject (bool), loc_source
    ("date-only" | "underlined" | "plain" | "weekday-stripped" | None).
    ``reject`` is True when the line is actually prose and the whole header
    match must be discarded.
    """
    r = rest.strip().lstrip(".:").strip()
    if not r:
        return {"location": "", "reject": False, "loc_source": "date-only"}
    if r[0].islower() or r[0] in ",;":
        return {"location": None, "reject": True, "loc_source": None}
    stripped_wd = _WD_LEAD.sub("", r).strip()
    weekday_stripped = stripped_wd != r
    r = stripped_wd
    if not r or r[0].islower():
        return {"location": "", "reject": False,
                "loc_source": "weekday-stripped" if weekday_stripped else "date-only"}
    m = _U_FIRST.match(r)
    if m:
        loc = m.group(1)
        source = "underlined"
    else:
        loc = re.split(r"\.(?:\s|$)", r, maxsplit=1)[0]
        loc = re.split(r"\s{2,}|\t", loc)[0]
        source = "plain"
    loc = loc.strip().strip('"').rstrip(".").strip()
    if loc and (not loc[0].isalpha() or _WEEKDAY.fullmatch(loc)):
        return {"location": "", "reject": False, "loc_source": "date-only"}
    if weekday_stripped and source == "plain":
        source = "weekday-stripped"
    return {"location": loc, "reject": False, "loc_source": source}


def find_entry_starts(text: str, loose: bool = False) -> List[Dict[str, Any]]:
    """Scan ``text`` once and return every entry-header match with provenance.

    Each hit: offset, end, date, location, date_norm, year, month, day,
    variant, month_source, year_form, loc_source, header_line.
    """
    rx = HEADER_LOOSE if loose else HEADER_STRICT
    out: List[Dict[str, Any]] = []
    for m in rx.finditer(text):
        loc_info = extract_location(m.group("rest"))
        if loc_info["reject"]:
            continue
        location = loc_info["location"]
        date = re.sub(r"\s+", " ", m.group("date").strip())
        rest_l = m.group("rest").strip().lstrip(".:").strip()
        variant = ("date-only" if not location
                   else "underlined" if rest_l.startswith("<u>") else "plain")
        dn = normalize_date(date)
        out.append({
            "offset": m.start(),
            "end": m.end(),
            "date": date,
            "location": location,
            "date_norm": dn["date_norm"],
            "year": dn["year"],
            "month": dn["month"],
            "day": dn["day"],
            "variant": variant,
            "month_source": dn["month_source"],
            "year_form": dn["year_form"],
            "loc_source": loc_info["loc_source"],
            "header_line": m.group(0).strip(),
        })
    return out


def strip_markup(text: str) -> str:
    t = _MARKUP_RE.sub("", text)
    t = _DEHYPHEN_RE.sub(r"\1\2", t)
    t = _WS_RE.sub(" ", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()
