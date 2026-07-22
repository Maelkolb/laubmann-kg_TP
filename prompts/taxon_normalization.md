# Taxon Normalization

Map a historical German bird name to a current scientific name. This prompt is a
fallback for names the gazetteer and the index-linker `links_long` table do not
cover; prefer those structured sources when available.

```
vernacular_de: $vernacular_de
context: $context
```

Return a JSON object:

```json
{
  "scientific_name": "<binomial or null>",
  "match_method": "llm_normalization",
  "confidence": 0.0
}
```

Rules:

- Return `null` for `scientific_name` if you are not confident. Never fabricate
  a binomial or a taxon IRI.
- Account for historical spelling (e.g. "Lachmöve" = "Lachmöwe") and regional
  names, but do not resolve ambiguous group names ("Möwe", "Laubvogel") to a
  species.
- Output only the JSON object.
