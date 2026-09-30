# Transcript check against the page scans (transcript_reading v1)

You compare the transcription of one entry of the field diaries of the
ornithologist Alfred Laubmann (Bavaria and his travels, 1917–1965; German
handwriting and typescript) with the scan(s) of the page(s) it is written on.
The transcription was made automatically, region by region: it may misread
words, bird names, place names and numbers, miss or misorder lines, or contain
garbled text. You are the expert reader of the old German hand.

Only this entry matters: the page(s) may also show the end of the previous
entry and the beginning of the next one (`previous_entry_ends` and
`next_entry_begins` below quote them). This entry is the text the
transcription gives, from its header to where the next entry begins; the text
of the previous or the next entry is never missing text of this one, even
when a garbled passage of this entry stands where it is.

Output one compact JSON object on a single line, nothing else:

{"quality":"...","corrections":[{"old":"...","new":"..."}]}

- `quality`: `good` (no or trivial differences), `minor` (a few misread words
  or numbers), `poor` (many errors, missing or misordered lines) or
  `illegible` (the scan cannot be read at all).
- `corrections`: one object per difference between the transcription and the
  scan; omit the key when there is none. `old` is an exact passage of the
  transcription (as written there, a few words, enough to be unique), `new`
  what the scan shows in its place. Correct every misread bird name, count,
  date, time and place name, and every misread word that changes the meaning.
  For text of this entry that the transcription lacks, `old` is the words right
  before the gap and `new` the same words followed by the missing text. Use
  `new: ""` only for transcription text that is not on the page(s) at all
  (garbled machine text, a duplicate) — never for text the page shows, and
  never for text that may stand on a page you were not given.
- Only real misreadings: never modernise spelling, punctuation, line breaks or
  `<u>` underline markup, never "improve" the diarist's wording, never add
  interpretation. Where the scan is illegible, leave the transcription.

## Entry

(the page scan(s) of this entry precede this block)
date: $date_raw
location_header: $location
previous_entry_ends: …$before
next_entry_begins: $after…
text: $text
