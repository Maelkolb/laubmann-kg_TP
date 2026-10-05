# Laubmann-Verknüpfungen (link check)

Eine Seite (`Laubmann_Verknuepfungen.html`, eigenständig, im Browser öffnen) für die menschliche Prüfung
**genau einer Stufe** der Pipeline: der Verknüpfung der Namen des Tagebuchs mit Normdaten
(Arten → GBIF, Personen → Wikidata/GND, Orte → GeoNames/OSM/Wikidata mit Koordinaten,
Lebensräume → EUNIS) und des Zusammenführens von Schreibungen. Nichts anderes: keine Transkription,
keine Extraktion, keine QA-Hinweise (dafür gibt es `pruefung/`).

Deutsch, Knopf **EN/DE** oben rechts; helles Design, dunkles über **◐**. Läuft von `file://` in
Edge/Chrome. Scans laden zuerst aus `data/pages_jpg/` neben der Seite, sonst als Drive-Thumbnail
(Konto mit Zugriff auf `HistOrniGraph_output`). GBIF-/Wikidata-/GND-/Nominatim-Suche und die Karte
brauchen Netz; alles andere geht offline.

## Aufbau

Oben der Typ (**Übersicht · Arten · Personen · Orte · Lebensräume**), darunter immer dasselbe Layout:
links die Liste, in der Mitte die Karte des Eintrags, rechts dauerhaft der Scan.

**Warteschlangen** (Chips über der Liste, „offen/gesamt“; Liste nach Zahl der Nennungen sortiert).
Jeder Eintrag gehört zu genau einer der ersten fünf:

| Warteschlange | Bedeutung |
|---|---|
| Von der Maschine geändert | eine Maschinenzeile ist übernommen (Konfidenz ≥ 0,9 **und** ≥ 2 Quellen) und der Graph weicht von dem ab, was die Pipeline allein hatte: neu verknüpft, umverknüpft, verlegt, Verknüpfung entfernt, GND ergänzt, einzelne Namen zugeordnet, Name entfernt (kein Taxon/Ort/…) |
| Von der Maschine bestätigt | übernommene Maschinenzeile, gleich der Pipeline-Verknüpfung |
| Vorschlag der Maschine | Maschinenurteil unter den Schwellen (nicht übernommen); Unterfilter *würde ändern* / *anderen Stand geprüft* / *stimmt mit Graph überein* / *unsicher, uneins*. Auch Zeilen, die die Schwellen erfüllen, im Graph aber nicht wirken, und „nicht verortbar“, wo die Pipeline trotzdem einen Punkt hat |
| Nur Pipeline | von den Regeln verknüpft, kein Maschinenurteil |
| Ohne Verknüpfung | kein Normdatensatz, und die Maschine hat nichts vorgeschlagen („nicht verortbar“ mit Lagehinweis steht hier, der Hinweis in der Karte) |
| Zusammenführen | offene Kandidaten der Regeln (`*_merges.csv`, Status `candidate`, noch ohne Entscheidung in `data/review/*_merges.csv`) |
| Entschieden | vom Prüfer entschieden |

Der Balken über der Liste zählt **Nennungen**, nicht Einträge („x % der Nennungen entschieden“):
wenige Entscheidungen zu häufigen Namen decken den größten Teil des Graphen.

**Karte**, von oben nach unten:

1. **Im Graph** – der Normdatensatz mit Link, Übereinstimmungsgrad (exact/close/broad) und wer ihn gesetzt
   hat (Pipeline-Regel, maschinelle Prüfung mit Runde/Konfidenz/Quellen, früher geprüfte Tabelle). Orte mit Karte
   (Punkt, Unschärfekreis, Kopfzeilen-Orte der Einträge, Kandidaten).
2. **Vorher → Nachher** – nur wo die Maschine geändert hat: Pipeline-Verknüpfung neben der jetzigen, Begründung,
   Stimmen der Quellen (Textagent, Gemini, Scan-Agent, Opus, Nominatim/Kopfzeilen-/Gattungswort-Probe, Wikidata↔GND).
3. **Vorschlag der Maschine** – nur wo ein Urteil nicht übernommen wurde.
4. **Andere Datensätze** – Kandidaten (Maschine, Stand vorher, Pipeline-Kandidaten, Wikidata/GND/Nominatim aus der
   Maschinenprüfung) und die Suche: GBIF, Wikidata, GND (lobid; von `file://` aus über Wikidata P227), Nominatim,
   EUNIS und die Arten des Graphen lokal.
5. **Geschriebene Namen** – jede Schreibung mit Zahl, Herkunft (eigener Name, Regel, geprüfte Entscheidung,
   Maschine) und Schalter *gehört dazu / eigener Eintrag / anderer Eintrag … / kein Name*; darunter Kandidaten,
   die hierher gehören könnten.
6. **Belege** – bis zu sechs Stellen, über Jahre und Schreibungen gestreut; ein Klick zeigt die Zeile im Scan
   (gestrichelter Kasten und „ungefähre Zeile“, wenn die Lage geschätzt ist).
7. Personen: **Nennungen nach Jahr** mit den Lebensdaten des Normdatensatzes.

## Beleg der Verknüpfung

Jeder Eintrag trägt eine Klasse, die sagt, wodurch seine Verknüpfung gestützt ist (`lb` in `build_data.py`,
aus „gesetzt von“ abgeleitet):

| Klasse | heißt |
|---|---|
| zwei Quellen | eine übernommene Maschinenzeile: mindestens zwei unabhängige Quellen einig (Claude-Textagent, Scan-Agent, Gemini, Opus, Ortsverzeichnis), Konfidenz ≥ 0,9 |
| eine Quelle | nur von der Pipeline verknüpft: Arten exakter GBIF-Namenstreffer, Personen exaktes Wikidata-Label, Lebensräume eine Gemini-Antwort je Bezeichnung |
| nur Namensabgleich | Orte: Koordinaten nur aus einem Namenstreffer in OpenStreetMap/Nominatim oder GeoNames, von der Ortsprüfung nicht bestätigt |
| Maschine: keine Verknüpfung | die Maschine hält die Verknüpfung für falsch oder den Namen für keinen Eintrag (auch entfernte Namen) |
| nicht verknüpft | keine Verknüpfung, keine übernommene Maschinenentscheidung |

Bei Arten hat jeder geschriebene Name seine eigene Klasse (Status `reviewed` = zwei Quellen, sonst der eigene
GBIF-Treffer); der Eintrag trägt die Klasse der meisten Nennungen, abweichende Namen zeigen ihre Klasse in
„Geschriebene Namen“. Eine übernommene Zeile ohne Wirkung im Graph zählt nicht als zwei Quellen.

- Karte: die Klasse als Plakette neben der Warteschlange; der Tooltip nennt, was die Verknüpfung stützt, die
  Blindprüfung vom 3.10. (734 Datensätze gegen den Scan) und – wo die Maschine mit ≥ 2 Quellen einig war, aber
  unter der Konfidenzschwelle blieb – dieses Urteil.
- Liste: Chips unter den Warteschlangen filtern nach Klasse (nochmals klicken hebt den Filter auf); nur eine
  Ansicht wie die Unterfilter.
- Übersicht: je Typ Einträge, Nennungen und Anteil je Klasse (Arten: Nennungen je geschriebenem Namen), eine Zeile
  der Blindprüfung je Klasse (Orte mit geprüfter Verknüpfung: Koordinaten in etwa 12 % falsch, n = 394; nur
  Namensabgleich: etwa 75 %, n = 61; Arten: 5,6 % gegen 3,0 % Artfehler, sie kommen aus verlesenen Namen und
  falscher Zuordnung, nicht aus der Verknüpfung; Personen und Lebensräume nicht gemessen) und die Zahl der
  Maschinenzeilen mit ≥ 2 übereinstimmenden Quellen unter der Konfidenzschwelle (Lebensräume 1.447, meist
  Konfidenz 0,7). Eine Zeile anklicken öffnet den Typ mit diesem Filter.
- `link_audit.csv` hat die Spalte `link_basis` (Präzision je Klasse).

Stand `kg_exports_2026-10-05_attribution` (Einträge / Nennungen): Arten zwei Quellen 295 / 64.323 (74,8 %),
eine Quelle 245 / 21.402 (24,9 %); Personen zwei Quellen 95 / 639, eine Quelle 84 / 490, nicht verknüpft
3.532 / 8.128; Orte zwei Quellen 1.419 / 20.101, nur Namensabgleich 993 / 3.567, nicht verknüpft 6.196 / 13.683;
Lebensräume eine Quelle 1.785 / 14.125 (97,4 %).

## Verlässlichkeitsfilter

Derselbe Filter wie auf der Graph-Prüfseite, mit denselben Schwellen. `build_review.py --quality` gibt jedem
Datensatz `q.p`, die geschätzte Wahrscheinlichkeit, dass mindestens eines seiner Felder falsch ist
(`record_quality.py`, geeicht an der blinden Scanprüfung), dazu `po` (Vorkommen, Art, Anzahl, Datum) und `pc`
(Koordinaten). Diese Seite liest sie aus `data/cache/graph_check/review_quality.json`.

Direkt unter der Kopfzeile steht in jeder Ansicht die Leiste **Verlässlichkeit** mit vier Knöpfen und der Zahl
ihrer Datensätze: **Alle**, **< 50 %**, **< 25 %**, **< 10 %**. Der gewählte ist gefüllt, die Wahl wird im Browser gemerkt;
**ⓘ** erklärt die Schätzung. Ist ein Filter aktiv, färbt sich die Leiste und bietet „Filter aufheben“.

**Was eine Schwelle für einen Eintrag heißt:** seine Nennungen, deren Datensatz darunter liegt.

- Eine Nennung, die an einem Datensatz hängt, zählt, wenn dieser Datensatz unter der Schwelle liegt: die Art eines
  Datensatzes, ein Ort als Fundort (`hasLocality` / `observedAt`), eine Person als Beobachter (`recordedBy`),
  der Lebensraum eines Datensatzes.
- Eine Nennung, die am Tagebucheintrag hängt (Kopfzeilen-Ort, im Eintrag genannte Personen, Orte der Reiseetappen),
  zählt, wenn der beste Datensatz des Tagebucheintrags unter der Schwelle liegt.

`build_data.py` schreibt je Eintrag und je geschriebenem Namen die Nennungen unter den vier Schwellen (`nc`) und je
gezeigtem Beleg die Stufe (`k`, 0–3), die geschätzten Fehler in Prozent (`kp`, `ko`, `kc`, abgerundet) und ob er am
Tagebucheintrag hängt (`ke`). Die Arten-Nennungen folgen dem Datensatz über Tagebucheintrag + geschriebenen Namen +
Vorkommen (wie `rec.w` / `rec.occ` der Prüfschicht); Personen, Orte und Lebensräume über den Graph (`--triples`).

Der Filter ist **nur eine Ansicht**:

- Die Listen führen nur Einträge mit mindestens einer Nennung unter der Schwelle, sortiert nach diesen Nennungen,
  mit „n im Filter / n gesamt“. Warteschlangen-Zahlen, der Fortschritt je Typ und die Tabellen der Übersicht zählen
  nur diese Nennungen.
- Die Karte zeigt beide Zahlen. „Belege“ stellt die Stellen unter der Schwelle voran; jede Stelle trägt den
  geschätzten Fehler ihres Datensatzes (bei Stellen am Tagebucheintrag: seines besten Datensatzes), Stellen
  darüber sind abgeblendet und nennen Wert und Schwelle.
- Einträge ohne Nennung unter der Schwelle sind ausgeblendet, behalten aber ihre Entscheidungen. Namen, die die
  Maschine entfernt hat, stehen in keinem Datensatz mehr und erscheinen nur unter „Alle“.
- **Entscheidungen und Export betreffen immer alle Einträge** – `identities.csv`, `link_audit.csv` und der
  Fortschritt sind unter jedem Filter dieselben (Test).
- Übersicht: Tabelle der vier Schwellen je Typ (Einträge, Nennungen); eine Zeile anklicken wählt den Filter.

Fehlt die Prüfschicht, wird die Seite ohne Filter gebaut; fehlt nur `--triples`, zählen Personen, Orte und
Lebensräume nach der Regel für den Tagebucheintrag.

## Tasten

`J` Verknüpfung stimmt (bei unverknüpften: bleibt ohne Verknüpfung; bei entfernten Namen: Entfernen stimmt) ·
`A` anderer Datensatz (Suchfeld) · `N` kein Datensatz passt · `X` kein Taxon / keine Person / kein Ort / kein Lebensraum ·
`U` unsicher · `V` Vorschlag der Maschine übernehmen · `R` zurück zum Stand vor der Maschine ·
`1`–`9` Kandidat · `Z` rückgängig · `⏎` nächster offener · `↑ ↓` Liste · `/` Liste filtern · `S` Scan ein/aus ·
`Esc` schließen · `?` Anleitung. In **Zusammenführen**: `J` dasselbe wie der erste Kandidat, Ziffer = dieser
Kandidat, `N` verschieden. Für Arten und Lebensräume wählt die Leiste *exact / close / broad* den Grad.
Eine Entscheidung ändert die Karte sofort („Entschieden von dir: …“), lässt sich ändern und zurücknehmen;
kein automatisches Weiterspringen.

## Entscheidungen und Export

Entscheidungen hängen am **geschriebenen Namen** bzw. am Namen des Eintrags (casefold, wie
`review/identities.py`), nie an Nummern des Graphen – sie überstehen einen neuen Export. Sie liegen im
Browser (localStorage); **Sichern & Export** fragt einmal nach dem Prüfernamen und lädt ein ZIP:

| Datei | Inhalt |
|---|---|
| `review/identities.csv` | genau der Vertrag von `laubmann_kg.review.identities` → nach `data/review/identities.csv` |
| `link_audit.csv` | eine Zeile je Entscheidung: Warteschlange, Maschinenurteil (übernommen, Konfidenz, Quellen, Runde), Pipeline-/Graph-/Maschinen-Verknüpfung, Beleg der Verknüpfung (`link_basis`), Entscheidung, `agrees_with_graph`, `agrees_with_machine` – für Präzisionsstatistik |
| `link_progress.json` | Sicherung, über **Fortschritt laden** wieder einlesbar |
| `LIESMICH.txt` | Stand und Erklärung |

Was eine Entscheidung in `identities.csv` schreibt:

| Entscheidung | Arten | Personen / Orte / Lebensräume |
|---|---|---|
| Verknüpfung stimmt, anderer Datensatz, Vorschlag übernommen | `same` + `gbif:<key>`, `scientific_name`, `rank` je geschriebenem Namen | `link` für den Namen des Eintrags: `wd:` `gnd:` · `gn:` `wd:` `osm:` mit `lat`/`lon`/`uncertainty_m` · `eunis:<Code>` mit `eunis_match` |
| kein Datensatz passt | `own` je Name (GBIF-Verknüpfung gelöst) | `nolink` |
| kein Taxon / … | `none` je Name | `none` je Name |
| unsicher | `unsure` (keine Wirkung) | `unsure` |
| Name: gehört dazu / anderer Eintrag | `same` mit `target` (+ `gbif:` des Ziels) | `same` mit `target` |
| Name: eigener Eintrag · kein Name | `own` · `none` | `own` · `none` |
| Zusammenführen: dasselbe · verschieden | – | `same` mit `target` · `own` |

Wird ein Name, den die Maschine entfernt hat (oder entfernen will), als Person/Ort/Lebensraum bestätigt, schreibt die
Seite zusätzlich `own` für ihn: die Pipeline führt `none` in der Namens-Tabelle und `link`/`nolink` in der
Verknüpfungs-Tabelle, nur eine Zeile derselben Tabelle hebt die Maschinenzeile auf.
Eine Entscheidung zu einem einzelnen Namen gewinnt gegen die des Eintrags. „Verknüpfung stimmt“ lässt Namen
offen, zu denen die Maschine etwas anderes vorschlägt (in der Karte markiert). Der Grad bei Arten steht als
`match=<exact|close|broad>` in `note`: die Pipeline wertet bei Arten noch keinen Grad aus (menschliche Zeilen
werden exactMatch); bei Lebensräumen steht er in `eunis_match`.

**Fortschritt laden** liest `link_progress.json` oder das ZIP dieser Seite und außerdem
`validation_progress.json` / das ZIP von `Laubmann_Validierung.html` (`pruefung/`): Namensentscheidungen
(gehört dazu, andere Art/anderer Eintrag, kein Name, eigener Eintrag) und Eintragsentscheidungen
(stimmt, keine, unsicher, anderer Datensatz, Maschine angenommen/abgelehnt). Übernommene
Eintragsentscheidungen sind in der Karte als „bitte kurz prüfen“ markiert; bei Konflikten gilt die neuere.

## Bauen

```bash
# 1. Daten: Graph, Pipeline-Graph, Maschinenzeilen, Urteile und Antworten der Runden, Merge-Tabellen
.venv/Scripts/python.exe tools/validation_ui/link_check/build_data.py
#    = mit allen Vorgaben; nach einem neuen Export:
.venv/Scripts/python.exe tools/validation_ui/link_check/build_data.py \
    --payload <payload des neuen Graphen>.b64 --payload-pipeline <payload des Pipeline-Graphen>.b64 \
    --export-review data/exports/<export>/review --identities data/review/machine/identities_machine.csv \n    --review-layer data/cache/graph_check/review_quality.json --triples <Tripel des neuen Graphen>.pkl
# 2. Seite
.venv/Scripts/python.exe tools/validation_ui/link_check/assemble.py     # -> data/exports/link_check/Laubmann_Verknuepfungen.html
```

`build_data.py` (≈ 50 s) schreibt `data/exports/link_check/data.json` und `.b64` und druckt Zahlen je Typ und
Warteschlange sowie Auffälligkeiten. Eingaben (alle mit Vorgabe, `--help`):

| Schalter | Vorgabe | wozu |
|---|---|---|
| `--payload` | `data/cache/graph_check/in/payload_final.b64` | Graph unter Prüfung (`build_payload.py`) |
| `--payload-pipeline` | `data/cache/graph_check/in/payload_pipeline.b64` | derselbe Lauf vor den Maschinenentscheidungen der letzten Runden → „vorher“ |
| `--payload-r1` | Drive `Laubmann_KG_Maschinenpruefung_2026-09-30/Laubmann_Abgleich.html` | Graph, den die **erste** Runde beurteilt hat; „vorher“ für Namen, bei denen schon der Pipeline-Graph eine Maschinenzeile trägt |
| `--identities` | `data/review/machine/identities_machine.csv` | die Zeilen, die die Pipeline liest; übernommen = Konfidenz ≥ `--min-confidence` und Quellen ≥ `--min-agreement` |
| `--rounds`, `--round-labels` | die vier `machine_review*`-Ordner in der Reihenfolge von `combine_rounds.py` | Urteile (`machine_review.json`); Spalte `round` = Position |
| `--arbeit` | die Arbeitsordner dazu (`-` = keiner) | Stimmen (answers / answers_gemini), Kandidaten und Wikidata-/GND-Details aus den Paketen |
| `--export-review` | `data/exports/kg_exports_2026-10-05_attribution/review` | `*_merges.csv` (Regeln, offene Kandidaten), `*_link_review.csv` |
| `--reviewed-merges` | `data/review` | frühere Entscheidungen zu Merge-Kandidaten (y/n) |
| `--review-layer` | `data/cache/graph_check/review_quality.json` | Prüfschicht der Graph-Prüfseite (`build_review.py --quality`): geschätzter Fehler `q.p` je Datensatz → Verlässlichkeitsfilter |
| `--triples` | `data/cache/graph_check/in/triples_final.pkl` | Tripel des Graphen unter Prüfung (`load.py`): an welchem Datensatz eine Personen-, Orts-, Lebensraum-Nennung hängt |
| `--drive` | `tools/validation_ui/drive_pages.json`, `configs/drive_scan_files.json` | Drive-Kennungen der Seitenscans |

Fehlt ein Drive-Ordner, wird er übersprungen (dann fehlen Stimmen bzw. das „vorher“ der ersten Runde).
`assemble.py --scans <Ordner>` setzt den Ort der Seiten-JPEGs relativ zur Seite (`""` = nur Drive).

Quellen: `app_i18n.js` (Texte DE/EN), `app_core.js` (Zustand, Modell, Export, Import), `app_view.js`
(Liste, Karte, Scan, Karte der Orte), `app_actions.js` (Entscheidungen, Suche, Tasten, Dialoge, Start);
`assemble.py` fügt sie in einer async-IIFE in `template.html` ein, Leaflet aus `tools/validation_ui/` inline.

## Wie „vorher“ und die Warteschlangen bestimmt werden

- *Übernommen* ist eine Zeile von `identities_machine.csv`, die beide Schwellen erfüllt und zu einem Namen des
  Eintrags gehört (Arten: je geschriebenem Namen; sonst der Name des Eintrags oder eine seiner Schreibungen).
- *Vorher* ist die Verknüpfung desselben Namens im Pipeline-Graph. Trägt der dort schon eine Maschinenzeile
  (Runde 1 war beim Volllauf bereits aktiv), gilt der Graph, den Runde 1 beurteilt hat; die Karte nennt die Quelle.
- Unterschiede zwischen Pipeline-Graph und Graph **ohne** übernommene Maschinenzeile sind keine Änderung der
  Maschine; die Karte zeigt sie als Hinweis.
- Namen, die die Maschine entfernt hat (`none` übernommen), stehen nicht mehr im Graph; sie erscheinen mit den
  Belegen des letzten Graphen, der sie hatte, als „entfernt“.

## Tests

Playwright (Python) mit Chromium, z. B. aus `laubmann-kg_TP/.venv`; die Tests laufen ohne Netz (Kacheln und
Drive werden durch ein leeres Bild ersetzt), Scans kommen aus `data/pages_jpg`.

```bash
cd tools/validation_ui/link_check
python tests/smoke.py            [Seite] [shots]   # alle Typen und Warteschlangen, Karten durchblättern, Scan-Zeile, DE/EN, hell/dunkel, Verlässlichkeitsfilter (Zahlen gegen review_quality.json), Beleg der Verknüpfung (Klassen, Filter, Übersicht), keine Konsolenfehler; Screenshots 1440×900 (Beleg: `shots_quality/`)
python tests/export_roundtrip.py [Seite]           # 23 Arten von Entscheidungen, ZIP, Identities.load() + apply_mappings der Pipeline, Export unter jedem Verlässlichkeitsfilter identisch, Undo, Rundreisen, Import aus Laubmann_Validierung
```

`export_roundtrip.py` ruft `tests/loaders_check.py` mit dem Python des Repos (`.venv`, oder `LC_REPO_PYTHON`);
die Seite wird über `LC_PAGE` oder das erste Argument gewählt (Vorgabe: die gebaute Seite).
