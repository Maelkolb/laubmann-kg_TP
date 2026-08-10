"""Metadata-rich corpus builder for the Laubmann ornithological journals.

Public surface used by the CLI wrappers and downstream agents:

    from laubmann_corpus import build_text_corpus, build_multimodal_corpus
    from laubmann_corpus import write_report, iter_volume_dirs, load_volume
"""

from .ids import page_uid, region_uid, entry_uid, content_hash
from .loading import iter_volume_dirs, load_volume, region_crop_path
from .entries import (
    find_entry_starts,
    normalize_date,
    extract_location,
    strip_markup,
)
from .stream import segment_entries
from .corpus import build_text_corpus
from .multimodal import build_multimodal_corpus
from .report import build_report, write_report

__all__ = [
    "page_uid", "region_uid", "entry_uid", "content_hash",
    "iter_volume_dirs", "load_volume", "region_crop_path",
    "find_entry_starts", "normalize_date", "extract_location", "strip_markup",
    "segment_entries",
    "build_text_corpus",
    "build_multimodal_corpus",
    "build_report", "write_report",
]
