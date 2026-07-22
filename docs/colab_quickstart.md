# Colab quickstart — build the KG for one volume end-to-end

Runs the corpus → knowledge-graph → Darwin Core Archive pipeline for a single
volume (default: Vol. 2) on Google Colab. The corpus files themselves are **not**
in the repo (they are large and gitignored); you supply `entries.csv` and
`multimodal.md` from your Google Drive.

## 1. Clone and install

```python
# Colab cell
!git clone https://github.com/Maelkolb/laubmann-kg_TP.git
%cd laubmann-kg_TP
!pip -q install -e .
```

## 2. Provide the corpus (from Google Drive)

Mount Drive and copy the two files into `data/corpus/`. Rename them to exactly
`entries.csv` and `multimodal.md` if they have different names on Drive.

```python
from google.colab import drive
drive.mount('/content/drive')

import shutil, pathlib
pathlib.Path('data/corpus').mkdir(parents=True, exist_ok=True)
# adjust these two source paths to where the files live on your Drive:
shutil.copy('/content/drive/MyDrive/laubmann/entries.csv',    'data/corpus/entries.csv')
shutil.copy('/content/drive/MyDrive/laubmann/multimodal.md',  'data/corpus/multimodal.md')
```

(Alternatively, use the Colab file uploader: `from google.colab import files; files.upload()`
and move the files into `data/corpus/`.)

## 3. Choose the volume

`configs/sample.yaml` builds Vol. 2 by default. To build a different clean
volume, edit `sample.volume`; set it to `null` to build the whole corpus.

```python
# optional: build a different volume
!sed -i 's/^  volume: 2/  volume: 2/' configs/sample.yaml   # change the number here
```

## 4. Run both exports

```python
# Knowledge graph (Turtle + JSON-LD, SHACL-validated)
!laubmann-kg export-jsonld --config configs/sample.yaml --input-dir data/corpus --output-dir data/exports

# Darwin Core Archive (event + occurrence + measurementOrFact + multimedia, zipped)
!laubmann-kg export-dwca   --config configs/sample.yaml --input-dir data/corpus --output-dir data/exports
```

Outputs land in:

- `data/exports/rdf/laubmann_sample.ttl`
- `data/exports/jsonld/laubmann_sample.jsonld`
- `data/exports/dwca/laubmann_sample_dwca.zip`

## 5. Inspect / download

```python
from laubmann_kg.kg.sparql import load_graph, run_query
g = load_graph('data/exports/rdf/laubmann_sample.ttl')
for row in run_query(g, 'CQ1_species_frequency')[:15]:
    print(row['n'], row['vernacular'])

from google.colab import files
files.download('data/exports/dwca/laubmann_sample_dwca.zip')
```

## Notes

- The build is deterministic and offline (rule-based extraction, no API key).
- SHACL warnings for entries with no matched bird name are expected (weather- or
  travel-only entries); they are warnings, not errors.
- To resolve taxa via the Vol. 35 index linker later, set `taxa.links_long_path`
  in the config to the linker's `links_long` table. See `INTERFACES.md`.
