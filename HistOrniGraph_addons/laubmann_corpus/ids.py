"""Stable, content-addressed identifiers for pages, regions and entries.

A uid is deterministic given its inputs, so any downstream tool (Agents C/D)
can recompute the same key without re-parsing the corpus artifacts.  The scheme
is versioned via ``_UID_SALT`` — bump it only if the derivation changes, since
that invalidates every previously emitted uid.
"""

import hashlib

_UID_SALT = "hog-v1"
_HASH_LEN = 12


def content_hash(*parts: object) -> str:
    h = hashlib.sha1(_UID_SALT.encode())
    for p in parts:
        h.update(b"\x1f")
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:_HASH_LEN]


def page_uid(volume: int, page_id: str) -> str:
    return f"p_{content_hash(volume, page_id)}"


def region_uid(volume: int, page_id: str, region_id: str, reading_order: object) -> str:
    return f"r_{content_hash(volume, page_id, region_id, reading_order)}"


def entry_uid(volume: int, page_id: str, region_id: str, stream_offset: object) -> str:
    return f"e_{content_hash(volume, page_id, region_id, stream_offset)}"
