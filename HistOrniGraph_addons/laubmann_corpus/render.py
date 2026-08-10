"""Renderers for the primary text corpus (md / txt).

These consume ``reg['starts']`` produced by ``stream.annotate_pages`` — the
header scan is never re-run here.  The Markdown / txt byte output matches the
original build_corpus.py for the same inputs; the only markdown change is the
addition of ``region_uid`` / ``page_uid`` to the HTML comments (documented in
CHANGELOG), which downstream joins need and which no consumer parses as prose.
"""

import re
from typing import Any, Dict, List, Optional

_MD_LIST_RE = re.compile(r"(?m)^([ \t]*)(\d{1,2})\.(?=\s)")


def _md_safe(text: str) -> str:
    return _MD_LIST_RE.sub(r"\1\2\\.", text)


def _entry_label(h: Dict[str, Any]) -> str:
    loc = f" · {h['location']}" if h["location"] else ""
    tag = f" `{h['date_norm']}`" if h.get("date_norm") else ""
    return f"{h['date']}{loc}{tag}"


def render_volume_md(vol_num: int, pages: List[Dict[str, Any]]) -> str:
    out: List[str] = [f"# Laubmann · Vol. {vol_num:02d}", ""]
    last_entry: Optional[Dict[str, Any]] = None
    for page in pages:
        pid, scan, pnum = page["page_id"], page["scan"], page["page_number"]
        head = f"## Vol. {vol_num:02d} · scan {scan:04d}"
        if pnum:
            head += f" · p. {pnum}"
        out.append(
            f"<!-- page volume={vol_num} page_uid={page['page_uid']} page_id={pid} "
            f"image={page['image']} scan={scan} page_number={pnum or ''} "
            f"regions={len(page['regions'])} -->"
        )
        out.append(head)
        out.append(f"`{pid}`")
        out.append("")
        for reg in page["regions"]:
            lc = reg["line_count"]
            starts = reg.get("starts", [])
            out.append(
                f"<!-- region region_uid={reg['region_uid']} id={reg['id']} "
                f"type={reg['type']} order={reg['reading_order']} "
                f"side={reg['page_side'] or ''} "
                f"lines={lc if lc is not None else ''} entries={len(starts)} "
                f"crop={reg['crop']} -->"
            )
            if starts and starts[0]["offset"] == 0:
                out.append(f"**⮞ Entry — {_entry_label(starts[0])}**")
                if len(starts) > 1:
                    extra = "; ".join(_entry_label(h) for h in starts[1:])
                    out.append(f"*[+ further entry start(s): {extra}]*")
            elif starts:
                if last_entry:
                    out.append(f"*(…continued from {_entry_label(last_entry)})*")
                joined = "; ".join(_entry_label(h) for h in starts)
                out.append(f"*[entry start(s) mid-region: {joined}]*")
            elif reg.get("scan_entries") and last_entry:
                out.append(f"*(…continued from {_entry_label(last_entry)})*")
            if starts:
                last_entry = starts[-1]
            out.append(_md_safe(reg["text"]))
            out.append("")
    return "\n".join(out)


def render_txt(vol_num: int, pages: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for page in pages:
        lines.append(f"\n=== Vol.{vol_num:02d}  scan {page['scan']:04d}  {page['page_id']} ===")
        for reg in page["regions"]:
            for h in reg.get("starts", []):
                lines.append(f"--- ENTRY  {h['date']}  |  {h['location']} ---")
            lines.append(reg["text"])
            lines.append("")
    return lines
