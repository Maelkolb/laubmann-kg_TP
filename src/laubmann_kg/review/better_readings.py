"""The machine layer of the text: the checks' better readings and the scan agent's corrections.

The reading stage (``extraction/reading.py``) corrects the transcription against the scans; two
machine checks then judge every correction and, where they find it wrong, give a better reading,
and the scan agent of the machine review corrected some further passages. Together they are a
layer over the text the graph holds.

``place`` cuts a better reading down to the span of its correction: the checks quote it with some
words around it, a decision replaces only the span. A reading that stays much longer or shorter
than the span, or whose span is not in the text, cannot be placed and is left to the reviewer.
``machine_decision`` turns a placed reading into a decision on the correction.

``classify`` decides for every change how it reaches the graph without a new extraction where it
can: a change of words no record depends on is patched into the text (``after``); a change of a
bird name that is one record's written name to a name the graph knows, or of a place name of the
entry to a known place, is patched into the text and corrects that record's species or the place
as a value correction (``after``); any other change (numbers, birds without a record, ambiguous
names) is applied before the extraction, which reads the entry anew (``before``). An entry with one
``before`` change takes all its changes before the extraction.

``patch`` applies the ``after`` changes to the extracted entries (text, header, record passages);
the pipeline then applies their value corrections. A reviewer's decision on a correction wins over
the layer, and an entry with any reviewer decision on its text is extracted anew.
"""

from __future__ import annotations

import csv
import difflib
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

FIELD = re.compile(r"^(location_header|date|text|previous_entry_ends): ")   # corrections of a header field, not of the text
BOUND = re.compile(r"[\s.,;:!?()\[\]\"„“'«»–-]")
TAG = re.compile(r"</?u>")
WORD = re.compile(r"\w[\w\-]*")
CONTEXT = 300
# what a check adds that is no reading: its doubts and comments ("vermutlich Bidingen", "Trupp [?]", "Gef. Welt = Gefiederte Welt")
HEDGE = re.compile(r"\b(?:vermutlich|wahrscheinlich|wohl|unsicher|unleserlich|illegible|evtl|eventuell|möglicherweise|vielleicht)\b"
                   r"|\(\?\)|\[\?\]|\?\)|\?\]|\[\.\.\.\]|\[…\]|=", re.I)

LAYER_FIELDS = ["entry_uid", "entry_id", "source", "old_text", "new_text", "decision", "final_text",
                "text_now", "pos", "apply", "header_place", "note", "reviewed_by"]


def squeeze(s: str) -> tuple[str, list[int]]:
    """Whitespace runs as one space, with the position of every kept character in ``s``."""
    out, at = [], []
    for i, ch in enumerate(s):
        white = ch.isspace()
        if white and out and out[-1] == " ":
            continue
        out.append(" " if white else ch)
        at.append(i)
    at.append(len(s))
    return "".join(out), at


def commentary(now: str, final: str) -> bool:
    """``final`` brings doubts or comments of a check that ``now`` does not have (the diarist's own "(?)" stays a reading)."""
    now, final = now or "", final or ""
    if len(HEDGE.findall(final)) > len(HEDGE.findall(now)):
        return True
    # a parenthesis or bracket the transcription does not have: a note of the check ("Maining (Graph-Ort weicht ab …)")
    return any(final.count(ch) > now.count(ch) for ch in "([")


def _words(s: str) -> int:
    return len(TAG.sub("", s).split())


def place(old: str, new: str, applied: bool, pos: int, better: str, text: str, loose: bool = False) -> Optional[str]:
    """The better reading as a replacement of the correction's span in ``text`` (the corrected entry text);
    '' = no better reading, None = it cannot be placed (``loose``: without the length check)."""
    if not better:
        return ""
    field = FIELD.match(old or "")
    if field:
        return better if better.startswith(field.group()) else field.group() + better
    span = new if applied else old
    p = pos if applied and pos >= 0 and text[pos:pos + len(new)] == new else text.find(span)
    if p < 0:
        span = TAG.sub("", span)
        p = text.find(span)
    if p < 0:
        return None
    b = better if "/" in span else re.sub(r"\s+/\s+", "\n", better)
    left = squeeze(TAG.sub("", text[max(0, p - CONTEXT):p]))[0]
    right = squeeze(TAG.sub("", text[p + len(span):p + len(span) + CONTEXT]))[0]
    b = b.strip()
    q, at = squeeze(b)
    i, j = 0, len(q)
    for k in range(len(q), 0, -1):
        if left.endswith(q[:k]) and (k == len(q) or BOUND.match(q[k - 1]) or BOUND.match(q[k])):
            i = k
            break
    for k in range(i, len(q)):
        if right.startswith(q[k:]) and (BOUND.match(q[k]) or (k > 0 and BOUND.match(q[k - 1]))):
            j = k
            break
    r = b[at[i]:at[j]].strip()
    if not r:
        return None
    lo, hi = min(_words(old), _words(new)) - 1, max(_words(old), _words(new)) + 1
    if loose:
        return r
    return r if lo <= _words(r) <= hi and not commentary(span, r) else None


def machine_decision(old: str, new: str, applied: bool, placed: Optional[str]) -> Optional[tuple[str, str]]:
    """(decision, final_text) the checks' placed reading amounts to, or None when it changes nothing."""
    if not placed or FIELD.match(old or ""):
        return None
    if placed == new:
        return None if applied else ("accept", new)
    if placed == old:
        return ("reject", old) if applied else None
    return ("edit", placed)


# ---------------------------------------------------------------- how a change reaches the graph

def fold(s: Optional[str]) -> str:
    return " ".join(TAG.sub("", s or "").split()).casefold()


def word_changes(now: str, final: str) -> tuple[list[list[str]], list[list[str]]]:
    """The runs of words ``now`` loses and ``final`` gains (punctuation and markup ignored)."""
    a, b = WORD.findall(TAG.sub("", now)), WORD.findall(TAG.sub("", final))
    sm = difflib.SequenceMatcher(None, [x.casefold() for x in a], [x.casefold() for x in b], autojunk=False)
    lost, gained = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if i2 > i1:
            lost.append(a[i1:i2])
        if j2 > j1:
            gained.append(b[j1:j2])
    return lost, gained


def _grams(run: list[str]) -> Iterable[str]:
    for n in range(1, min(3, len(run)) + 1):
        for i in range(len(run) - n + 1):
            yield " ".join(run[i:i + n]).casefold()


MONTHS = {"januar", "jänner", "jan", "februar", "feber", "febr", "feb", "märz", "märz", "april", "apr", "mai", "juni", "juli",
          "august", "aug", "september", "sept", "sep", "oktober", "okt", "november", "nov", "dezember", "dez"}
ROMAN = re.compile(r"^[ivx]+$")


def _variants(name: str) -> list[str]:
    """A folded name and its likely singular forms (plural and case endings of German bird names)."""
    out = [name]
    for a, b in (("vögel", "vogel"), ("hühner", "huhn"), ("gänse", "gans"), ("schwäne", "schwan"), ("spechte", "specht"),
                 ("finken", "fink"), ("meisen", "meise"), ("tauben", "taube"), ("enten", "ente"), ("drosseln", "drossel")):
        if name.endswith(a):
            out.append(name[:-len(a)] + b)
    for suf in ("en", "n", "e", "er", "s", "es"):
        if name.endswith(suf) and len(name) - len(suf) >= 4:
            out.append(name[:-len(suf)])
    return out


def classify(now: str, final: str, *, header: bool, records: list[dict], places_here: set[str],
             taxa: dict[str, tuple], places: dict[str, str], entry_place: str, location_raw: str) -> tuple[str, list[dict]]:
    """('after' | 'before', value corrections) for one change of ``now`` (the text the graph holds there)
    into ``final``. ``records``: the entry's records (written, taxon); ``places_here``: the folded names of
    every place the entry uses (entry place, header, record localities, travel legs); ``taxa``: unambiguous
    taxon name forms (folded) -> (German name, scientific name, GBIF key); ``places``: place forms -> name."""
    lost, gained = word_changes(now, final)
    if not lost and not gained:
        return "after", []
    numbers = lambda runs: sorted(re.findall(r"\d+", " ".join(w for run in runs for w in run)))
    if numbers(lost) != numbers(gained):
        return "before", []                      # a count, a time: the model reads it anew
    changed = [w.casefold() for run in lost + gained for w in run]
    if any(w in MONTHS or ROMAN.match(w) for w in changed):
        return "before", []                      # a date
    written = Counter(fold(r.get("written")) for r in records)
    by_taxon: dict[str, list[str]] = {}
    for r in records:
        if r.get("taxon"):
            by_taxon.setdefault(fold(r["taxon"]), []).append(r["written"])

    def taxon_of(name: str):
        return next((taxa[v] for v in _variants(fold(name)) if v in taxa), None)

    def meaning(run):
        out = set()
        for g in _grams(run):
            if g in written or taxon_of(g):
                out.add("taxon")
            if g in places or g in places_here:
                out.add("place")
        return out

    senses = [meaning(run) for run in lost + gained]
    if not any(senses):
        return "after", []                       # no record depends on these words
    if len(lost) == 1 and len(gained) == 1:
        was, name = " ".join(lost[0]), " ".join(gained[0])
        both = senses[0] | senses[1]
        new_taxon = taxon_of(name)
        if new_taxon and "place" not in both:   # a bird name: the one record it is written for gets the new species
            old = was if written.get(fold(was)) == 1 else None
            if old is None and taxon_of(was):
                same = by_taxon.get(fold(taxon_of(was)[0]), [])
                old = same[0] if len(same) == 1 and written.get(fold(same[0])) == 1 else None
            if old is not None:
                de, sci, key = new_taxon
                was_taxon = next((fold(r.get("taxon")) for r in records if fold(r.get("written")) == fold(old)), "")
                if was_taxon == fold(de):
                    return "after", []                   # another spelling of the same bird: the text only
                return "after", [{"kind": "taxon", "old_value": old, "new_value": de, "scientific_name": sci or "", "gbif_key": key or ""}]
        if "taxon" not in both and fold(name) in places:   # to a place the graph knows: the entry's use of the old name moves there
            target = places[fold(name)]
            if fold(target) == fold(was):
                return "after", []
            if header and (entry_place or location_raw):
                return "after", [{"kind": "place", "old_value": entry_place or location_raw, "new_value": target, "header": name}]
            if fold(was) in places_here:
                return "after", [{"kind": "place", "old_value": was, "new_value": target}]
    return "before", []


def name_indexes(payload: dict) -> tuple[dict, dict]:
    """Unambiguous taxon and place name forms of a validation payload (folded form -> target)."""
    taxa, seen = {}, Counter()
    for f in payload["taxon"]["forms"]:
        seen[fold(f[0])] += 1
    for f in payload["taxon"]["forms"]:
        e = payload["taxon"]["ent"][f[2]]
        if seen[fold(f[0])] == 1 and e[0]:
            taxa[fold(f[0])] = (e[0], e[1], e[2])
    for e in payload["taxon"]["ent"]:
        if e[0] and fold(e[0]) not in taxa:
            taxa[fold(e[0])] = (e[0], e[1], e[2])
    places, seen = {}, Counter()
    for f in payload["place"]["forms"]:
        seen[fold(f[0])] += 1
    for f in payload["place"]["forms"]:
        e = payload["place"]["ent"][f[2]]
        if seen[fold(f[0])] == 1 and e[0] and len(f[0]) >= 4:
            places[fold(f[0])] = e[0]
    return taxa, places


# ---------------------------------------------------------------- the layer in the pipeline

def load_layer(path) -> list[dict]:
    if not path or not Path(path).is_file():
        return []
    with open(path, encoding="utf-8", newline="") as h:
        return [r for r in csv.DictReader(h) if r.get("entry_uid") and r.get("text_now") is not None]


def reviewed_entries(transcript_decisions: dict, text_corrections: Iterable) -> set[str]:
    """Entries with a reviewer decision on their text: they are extracted anew, the whole layer before."""
    return {k[0] for k in transcript_decisions} | {r.entry_uid for r in text_corrections if r.entry_uid}


def layer_parts(rows: list[dict], reviewed: set[str]) -> tuple[dict, list, list[dict], set[str]]:
    """(decisions before the extraction, scan-agent readings before it, changes after it, entries patched after it)."""
    before_entries = {r["entry_uid"] for r in rows if r["apply"] == "before"} | reviewed
    decisions, readings, after = {}, [], []
    from laubmann_kg.review.readings import Reading
    for r in rows:
        if r["entry_uid"] in before_entries:
            if r["source"] == "check":
                decisions[(r["entry_uid"], r["old_text"], r["new_text"])] = (r["decision"], r["final_text"])
            else:
                readings.append(Reading(r["old_text"], r["new_text"], r["entry_uid"], r["entry_id"], r.get("note") or ""))
        else:
            after.append(r)
    return decisions, readings, after, {r["entry_uid"] for r in after}


def apply_change(e, now: str, final: str, pos: int = -1) -> bool:
    """Replace ``now`` by ``final`` in the entry text: at ``pos`` when the text holds ``now`` there (the offset
    in the text the layer was computed on), else at its first whole-word occurrence (markup tolerant, as the
    reading stage places its corrections). The record passages and the header place follow. False: not found."""
    from laubmann_kg.extraction.reading import _locate

    text = e.text_clean or ""
    if pos is not None and pos >= 0 and text[pos:pos + len(now)] == now:
        start, end = pos, pos + len(now)
    else:
        hit = _locate(text, now)
        if not hit:
            return False
        start, end, _ = hit
    e.text_clean = text[:start] + final + text[end:]
    plain_now, plain_final = TAG.sub("", now), TAG.sub("", final)
    for o in getattr(e, "observations", None) or []:
        if o.verbatim_notes and plain_now in o.verbatim_notes:
            o.verbatim_notes = o.verbatim_notes.replace(plain_now, plain_final, 1)
        elif o.verbatim_notes and now in o.verbatim_notes:
            o.verbatim_notes = o.verbatim_notes.replace(now, final, 1)
    if e.location_raw and plain_now and plain_now in e.location_raw:
        e.location_raw = e.location_raw.replace(plain_now, plain_final, 1)
    e.reading_notes.append(f"Lesung nach der Maschinenprüfung korrigiert: „{plain_now}“ → „{plain_final}“")
    return True


def _apply_rows(entries, rows: list[dict]) -> list:
    """Apply changes {entry_uid, text_now, final_text, pos, header_place} entry by entry: the ones with a
    position from the back of the text to the front (the offsets stay valid), then the others."""
    from laubmann_kg.qa import QAFlag

    by_uid: dict[str, list[dict]] = {}
    for r in rows:
        by_uid.setdefault(r["entry_uid"], []).append(r)
    flags = []
    for e in entries:
        todo = by_uid.get(e.entry_uid)
        if not todo:
            continue
        key = lambda r: _int(r.get("pos"))
        for r in sorted([r for r in todo if key(r) >= 0], key=key, reverse=True) + [r for r in todo if key(r) < 0]:
            now, final = r["text_now"], r["final_text"]
            if not apply_change(e, now, final, key(r)):
                flags.append(QAFlag(e.entry_id, e.entry_uid, "reading_unmatched", f"Lesung „{now}“ steht nicht (mehr) im Eintragstext",
                                    "flagged", f"{now} -> {final}"))
                continue
            if r.get("header_place"):   # the header's place, as the checks read it
                e.location_raw = r["header_place"]
            flags.append(QAFlag(e.entry_id, e.entry_uid, "reading_corrected",
                                f"Lesung nach der Maschinenprüfung korrigiert: „{TAG.sub('', now)}“ → „{TAG.sub('', final)}“",
                                "flagged", f"{now} -> {final}"))
    return flags


def doubled_edges(text: str, changes: list[dict]) -> set[int]:
    """Indexes of the changes that would double a word together with the text next to them or with another
    change ("Ein Ein Zaunkönig", "Lachmöven Lachmöven"): the reading was cut one word too wide. A repetition
    inside one reading ("kuik kuik") is the checker's and stays."""
    from laubmann_kg.extraction.reading import _locate

    spans = []
    for i, c in enumerate(changes):
        now, p = c["text_now"], _int(c.get("pos"))
        if p >= 0 and text[p:p + len(now)] == now:
            spans.append((p, p + len(now), i))
        elif (hit := _locate(text, now)):
            spans.append((hit[0], hit[1], i))
    kept, cut = [], len(text)
    for a, b, i in sorted(spans, reverse=True):
        if b <= cut:
            kept.append((a, b, i))
            cut = a
    merged, owner, at = "", [], 0
    for a, b, i in reversed(kept):
        for piece, src in ((text[at:a], -1), (changes[i]["final_text"], i)):
            plain = TAG.sub(lambda m: " " * len(m.group()), piece)
            merged += plain
            owner += [src] * len(plain)
        at = b
    merged += TAG.sub(lambda m: " " * len(m.group()), text[at:])
    owner += [-1] * (len(merged) - len(owner))
    doubled = set()
    for m in re.finditer(r"\b(\w{2,})\b(?=[^\w\n]+(\w+)\b)", merged):
        second = m.end() + merged[m.end():].index(m.group(2))
        if m.group(1).casefold() != m.group(2).casefold():
            continue
        s1, s2 = set(owner[m.start(1):m.end(1)]), set(owner[second:second + len(m.group(2))])
        if s1 == s2 and len(s1) == 1:
            continue   # the text's own repetition, or one reading's
        doubled |= {x for x in s1 | s2 if x >= 0}
    return doubled


def doubled_in_reading(text: str, corrections: list[tuple[str, str]], changes: list[dict]) -> set[int]:
    """Indexes of the changes that double a word when the reading stage applies them (``before``): its
    corrections ``(old, new)`` in turn on the transcription ``text``, each at the first occurrence of its old
    text so far, the changes' decisions taken ("10.) 10.) Feldlerche"). A change counts when its reading holds
    the doubled word once; a repetition inside one reading ("kuik kuik") stays."""
    from laubmann_kg.extraction.reading import correct_text

    items = [{"old": o, "new": n} for o, n in corrections]
    decisions = {("", c["old_text"], c["new_text"]): (c["decision"], c["final_text"]) for c in changes if c.get("decision")}
    reps = lambda t: Counter(m.group(1).casefold() for m in re.finditer(r"\b(\w{2,})\b(?=[^\w\n]+\1\b)", TAG.sub(" ", t), re.I))
    new = reps(correct_text(text, items, decisions)[0]) - reps(correct_text(text, items)[0])
    return {i for i, c in enumerate(changes) if c.get("decision") and any(
        re.search(r"\b" + re.escape(w) + r"\b", TAG.sub(" ", c["final_text"]), re.I) and w not in reps(c["final_text"])
        for w in new)}


def overrun_in_reading(text: str, corrections: list[tuple[str, str]], changes: list[dict]) -> set[int]:
    """Indexes of the changes whose reading a later correction of the reading stage lands in, because it finds
    its old text there first ("Seidenschwanz Ringamseln" -> "Nordischen Ringamseln", then "Ringamseln" -> ""):
    the reading stage's loop replayed correction by correction on the transcription ``text``."""
    from laubmann_kg.extraction.reading import _locate, correct_text

    decided = {(c["old_text"], c["new_text"]): i for i, c in enumerate(changes) if c.get("decision")}
    decisions = {("", o, n): (changes[i]["decision"], changes[i]["final_text"]) for (o, n), i in decided.items()}
    spans, hit = [], set()
    for old, new in corrections:
        at = _locate(text, old)
        after, out = correct_text(text, [{"old": old, "new": new}], decisions)
        if not at or not out or not out[0][2]:
            continue
        a, b, delta = at[0], at[1], len(after) - len(text)
        hit |= {i for s, e, i in spans if a < e and b > s}
        spans = [(s + delta, e + delta, i) if s >= b else (s, e, i) for s, e, i in spans if not (a < e and b > s)]
        if (old, new) in decided:
            spans.append((a, b + delta, decided[(old, new)]))
        text = after
    return hit


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def patch(entries, rows: list[dict]) -> list:
    """Apply the ``after`` changes to the extracted entries: the entry text, the header strings and the
    passages of the records (after their value corrections, which still address the names as extracted).
    Returns the QA flags (``reading_corrected`` / ``reading_unmatched``)."""
    return _apply_rows(entries, rows)


def machine_readings(entries, readings, decisions_path) -> list:
    """The scan agent's corrections of the corrected entry text, applied after the reading stage (before the
    extraction) at their first whole-word occurrence. A reviewer's decision on the same correction
    (``transcript_decisions.csv``) wins: ``reject`` drops it, ``edit`` replaces its new text.
    ``readings``: a list of Reading or a path to a readings CSV."""
    from laubmann_kg.extraction.reading import load_transcript_decisions
    from laubmann_kg.review.readings import load_readings

    human = load_transcript_decisions(decisions_path)
    rows = []
    for r in (load_readings(readings) if isinstance(readings, (str, Path)) else readings):
        decided = human.get((r.entry_uid, r.old, r.new))
        if decided and decided[0] == "reject":
            continue
        final = decided[1] if decided and decided[0] == "edit" and decided[1] else r.new
        rows.append({"entry_uid": r.entry_uid, "text_now": r.old, "final_text": final, "pos": -1})
    flags = _apply_rows(entries, rows)
    seen = {e.entry_uid for e in entries}
    from laubmann_kg.qa import QAFlag
    for r in rows:
        if r["entry_uid"] not in seen:
            flags.append(QAFlag("", r["entry_uid"], "reading_unmatched", "Eintrag nicht in diesem Lauf", "flagged", f"{r['text_now']} -> {r['final_text']}"))
    return flags
