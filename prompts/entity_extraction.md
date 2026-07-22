# Entity Extraction

Extract named entities from a single German diary entry by Adolf Laubmann. Only
report entities that appear in the text.

```
text: $text
```

Return a JSON object:

```json
{
  "taxa": ["<German bird name as lemma>"],
  "persons": [{"surface": "<as written>", "name": "<normalized name>"}],
  "places": ["<locality as written>"]
}
```

Rules:

- `taxa`: German vernacular bird names only, lemmatized.
- `persons`: informants, collectors, correspondents, cited authors. Include the
  title/initials as `surface`; give a best-effort normalized `name`.
- `places`: localities, stations, rivers, habitats mentioned in the text.
- Output only the JSON object.
