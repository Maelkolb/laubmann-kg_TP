# Cleaning the image and insert regions

The graph carries the drawings, maps, photographs, mounted objects and inserted texts of the diaries as
`lkg:MultimodalRegion` nodes, each with a crop of its page scan. They come from the region catalogue
(`data/corpus_patched/multimodal_regions.jsonl`, built by the layout stage of HistOrniGraph). The scanning shows
many objects more than once, and some crops cut their object off:

- a fold-out map photographed folded with its page and again opened as a whole spread (7–9 June 1950: a strip of
  the railway map "Internationale Verbindungen" on scan 99, the whole map on scan 100);
- a clipping, photograph or pressed plant visible on two consecutive scans;
- the mirror image of a photograph or typed sheet seen through the paper or rubbed off on the facing page;
- empty paper, scanner background or a sliver of a page edge taken for an object;
- a box drawn too tight, so that a caption, a legend or part of the object is missing.

## The check

`tools/validation_ui/machine_review/region_check.py` checks the 1,626 regions placed with an entry in 824 groups:
regions of one volume on scans at most one apart (longer runs in windows of eight with an overlap of two). The model
sees every region's crop (R1, R2, …) and the page scans with all region boxes drawn and labelled (P1, P2, …) and
says for each region:

| Field | Values |
|---|---|
| content | object, text, blank, fragment |
| complete | true, or false with the cut sides and the cause: the page edge (the object continues beyond the scanned page) or the box (the page shows more) |
| same_as | regions that show the same physical object or an overlapping part of it |
| parts_of | regions that show other, non-overlapping parts of it (page 2 of a letter) |
| best | among the same object, the region that shows it most completely |
| box | for a box cut-off: the box that holds the whole object, on its page scan |

Two models answer independently: Gemini 3.8 Flash and Gemini 3.7 Flash ($3.64 and $3.73; 5 and 2 groups stayed
unreadable, their regions stay as they are).

`region_check_combine.py` keeps what both say:

- **dropped as a duplicate** when both say the region shows the same object as another region, that the other one
  shows it better, and that both have the same kind of content (an object or a text);
- **dropped as blank** when both say blank, **as a fragment** when both say blank or fragment and neither sees it as
  a part of a larger object;
- **complete** or **cut off** when both agree, with the cause where they agree on it;
- **a new box** when both say the box cut the object off and their boxes overlap by at least half (the mean of the
  two, plus a margin of 1 % of the page).

Before a duplicate is dropped, `region_duplicate_check.py` shows the pair to Gemini 3.8 Flash once more and asks
whether the region adds anything its twin lacks (the other side of a postcard, a handwritten note, a caption, a
missing part). 32 of 92 duplicates do and stay. `recrop.py` cuts the regions with a new box anew from their page
scans (`data/region_crops_v2`, Drive `HistOrniGraph_output/regions_v2/<page_id>/<region_uid>.jpg`; the original crops
are kept in `data/region_crops_orig`).

## Result

| Decision | Regions |
|---|---|
| dropped: duplicate (a repeat scan, a cut-off strip, a mirror image) | 60 |
| dropped: blank paper, scanner background | 10 |
| dropped: fragment | 7 |
| cut off by the box, cut anew | 202 |
| cut off by the box, boxes disagree (kept) | 24 |
| cut off at the page edge (fold-outs, inserts sticking out) | 42 |
| cut off, cause disputed | 12 |
| complete | 1,137 |
| disputed or not judged by both (kept as they were) | 132 |

47 of the dropped duplicates were placed with a neighbouring entry: the same physical object belongs to one entry,
and the copy on the other scan had been linked to the other entry by reading order.

Checked by eye on a sample of 30 decisions (duplicates with their twins, blanks and fragments, old and new crops,
duplicates across entries): 29 right. The wrong one, the written back of a postcard taken for a repeat of its
picture side, is what the pair check now keeps.

## In the graph and the pages

The pipeline reads `review.machine.regions` (`data/review/machine/region_quality_machine.csv`) where it places the
regions with their entries (`src/laubmann_kg/review/regions.py`): a dropped region is not exported; a kept region
carries `lkg:regionCompleteness` ("complete", "cut off"; ontology 0.7.1) where both checks agree, and the new crop's
path as `dcterms:identifier` where it was cut anew. A reviewer's file of the same form (`review.regions`) wins over
the machine rows. `build_review.py --region-decisions` leaves the dropped regions out of the validation pages and
shows a region cut anew by its new box, cut out of the page scan.
