# Laubmann-Validierung

Eine Seite (`Laubmann_Validierung.html`, eigenständig, im Browser öffnen) für die menschliche
Prüfung des endgültigen Graphen. Deutsch, Knopf **EN/DE** oben rechts. Scans und Zeilenbilder
laden von Google Drive (Konto mit Zugriff auf `HistOrniGraph_output`), GBIF-/Wikidata-/Nominatim-Suche
und Karte brauchen Netz; alles andere geht offline.

## Aufbau

**Teil A — maschinell geprüft, freigeben.** Die Maschine hat in mehreren Runden geurteilt
(R1 und R2 vom 30.09. am Graph vom 19.08., R3 am endgültigen Graph); eine spätere Runde ersetzt
das Urteil einer früheren zum selben Schlüssel (Kennzeichen R1/R2/R3 an jedem Fall, frühere
Runden im Maschinen-Kasten). Wo eine Runde an einem anderen Graph lief, zeigt die Karte
„vorher“ (Graph der Runde) → Vorschlag und darunter, was jetzt im Graph steht.

| Reiter | Inhalt |
|---|---|
| Änderungen | Vorschläge der Maschine (Arten, Namen, Personen, Orte, Lebensräume, einzelne Belege); zuerst die, die die Pipeline automatisch übernimmt (Konfidenz ≥ 0,9 und ≥ 2 Quellen, Badge „auto“) |
| Stichprobe | geschichtete Zufallsstichprobe der Bestätigungen → Präzision je Schicht (Wilson-Intervall); „alle Bestätigungen“ als Liste |
| Offen | Fälle ohne Maschinenurteil (unsicher, kein Kandidat) |
| Transkription | Korrekturen der Bildlesung (Gemini am Scan, vor der Extraktion): Stichprobe je Art der Änderung (Vogelname / Zahl-Datum / Ort / anderes Wort / Einfügung / Streichung × übernommen / nicht übernommen) mit Präzision je Schicht, dann alle, die die Maschine (R3) für falsch/unklar hält, und alle nicht übernommenen in Einträgen mit Datensätzen |
| Extraktion | Einträge Scan gegen Graph, Befund je Zeile; Lesekorrekturen |

**Teil B — nicht maschinell geprüft, selbst prüfen** (dieselben Karten, ohne Maschinen-Kasten):
Nicht geprüft (jede Art/Person/jeder Ort, den keine Runde gesehen hat; verknüpft / ohne
Verknüpfung), Lebensräume ohne Maschinenurteil (EUNIS-Klasse richtig / andere / keine; von R3 geprüfte
Lebensräume stehen in Teil A), Hinweise (QA-Flags nach Grund: bestätigen / Fehlalarm / korrigieren).

**Übersicht** = Aufgabenliste in empfohlener Reihenfolge mit Zahl, Zeitschätzung, Fortschritt;
**Protokoll** = alle Entscheidungen (einzeln entfernbar), Präzisionstabellen.

## Tasten

`J` ja/übernehmen · `N` nein/ablehnen · `A` anders (Suche, Karte, Kandidaten) · `E` Transkription
bearbeiten · `U` unsicher · `1`–`9` Kandidat/Treffer · `⏎` nächster offener · `↑ ↓` Liste · `Z`
rückgängig · `S` Scan ein/aus · `/` Liste durchsuchen · `Strg+K` alles durchsuchen · `Esc` schließen.
Kleine Knöpfe an Namen, Belegen und Zeilen entscheiden nur diesen Teil.

## Entscheidungen und Export

Entscheidungen hängen an stabilen Schlüsseln — geschriebener Name (`taxon:amsel`, Namen je Typ),
Belegschlüssel `entry_uid|name|vorkommen`, `tc:entry_uid|alt|neu`, `qa:entry_uid|grund|wert`,
`entry:entry_uid` —, nie an Graph-Nummern; sie überstehen also einen neuen Export. Sie liegen im
Browser; „Sichern & Export“ verbindet eine Sicherungsdatei und lädt das ZIP:

| Datei | Vertrag / Verbraucher |
|---|---|
| `review/identities.csv` | `laubmann_kg.review.identities` (section, name_form, decision same/own/none/unsure/link/nolink, authority `gbif:`/`wd:`/`gnd:`/`gn:`/`osm:`/`eunis:`, eunis_match …); Lebensräume als `link eunis:<Code>` |
| `review/value_corrections.csv` | `normalization.corrections.load_corrections` (einzelne Belege) |
| `review/text_corrections.csv` | `review.text_corrections` (Lesekorrekturen der Extraktionsprüfung + aus dem Abgleich importierte) |
| `review/transcript_decisions.csv` | `extraction.reading.load_transcript_decisions`: entry_uid, entry_id, old_text, new_text, decision (accept\|reject\|edit\|unsure), final_text, note, reviewed_by, reviewed_at |
| `review/qa_decisions.csv` | `qa.load_qa_decisions`: entry_uid, entry_id, reason, value, decision (confirm\|false_alarm\|fix), note, reviewed_by, reviewed_at („unsicher“ wird nicht exportiert) |
| `observation_corrections.csv` | Befunde je Beobachtung (noch ohne Verbraucher) |
| `machine_audit.csv`, `validation_log.csv` | jede Entscheidung mit Maschinenurteil/Runde; Protokoll |
| `validation_progress.json` | Sicherung, über „Fortschritt laden“ wieder einlesbar |

Übernommene Maschinen-Zeilen werden mit `reviewed_by` = Prüfer geschrieben; „Ablehnen“ schreibt den
Zustand vor der Maschine fest; „Nein“ in der Stichprobe löst die Verknüpfung (Arten `own`,
Personen/Orte `nolink`), besser „A“ mit dem Richtigen.

**Fortschritt laden** liest: Sicherungen dieser Seite (JSON oder ZIP), `validation_progress.json`
von `Laubmann_Pruefung.html` (30.09.; deren Fallnummern werden über die beim Bauen eingebettete
Tabelle `--legacy-pruefung` auf die Schlüssel übersetzt) und Sicherungen von `Laubmann_Abgleich.html`
(v2–v4: Namen, Einträge, Belege, Namensgruppen, Lesungen, Hinweise, Stichprobe). Bei Konflikten gilt
die neuere Entscheidung. Liegen Entscheidungen jener Seiten noch im selben Browser, bietet die
Übersicht die Übernahme an. Was hier keinen Fall hat, bleibt gespeichert (Protokoll zählt es).

## Bauen

```bash
D="G:/My Drive/Laubmann_KG_Maschinenpruefung_2026-09-30"
X=data/exports/kg_exports_2026-10-01
# 1. Payload des Graphen (tools/validation_ui/README.md): load.py + build_payload.py ... --out payload.b64
# 2. Daten der Seite; R1/R2 liefen am Graph vom 19.08. -> "@<Seite oder Payload dieses Graphen>"
python tools/validation_ui/pruefung/build_data.py --payload payload.b64 \
  --machine "$D/machine_review@$D/Laubmann_Abgleich.html" "$D/machine_review2@$D/Laubmann_Abgleich.html" <machine_review3> \
  --arbeit "$D/arbeit" "$D/arbeit2" [<arbeit3>] --review $X/review --dwca $X/dwca \
  --legacy-pruefung "$D/Laubmann_Pruefung/Laubmann_Pruefung.html" --out <scratch>/data
# 3. Seite
python tools/validation_ui/pruefung/assemble.py --data <scratch>/data Laubmann_Validierung.html
```

`--machine` nimmt die Runden in Reihenfolge (fehlende Ordner/Dateien werden übersprungen); genutzt
werden, wo vorhanden: `machine_review.json`, `identities_machine.csv`, `value_corrections_machine.csv`,
`text_corrections*.csv`, `graph_checks*.csv`, `place_readings.json`, `taxa_a_readings.json`,
`transcript_checks.csv` (entry_uid, entry_id, old_text, new_text, applied, verdict
right|partly|wrong|unclear, better_text[, reason]); `machine_review.json` auch mit `habitat.ent`
(verdict ok|other|none|unsure, code, match). Ohne `@` gilt der Graph von `--payload`; lief eine Runde
an einem anderen Export (auch R3), `DIR@<Payload dieses Exports>`.
Weitere Schalter: `--sample-per-stratum 40`, `--tc-sample-per-stratum 25`, `--seed`, `--max-ev`.
Stichproben sind nach Schlüssel-Hash gezogen und bleiben bei einem Neubau stabil.

## Tests

Playwright (Python) in einer eigenen venv: `pip install playwright && python -m playwright install chromium`.

```bash
python tests/smoke.py        Laubmann_Validierung.html [shots]   # alle Reiter/Kartentypen, DE+EN, keine Fehler
python tests/interaction_export.py Laubmann_Validierung.html     # alle Entscheidungsarten, ZIP, Pipeline-Loader, Undo, Rundreise
python tests/import_progress.py    Laubmann_Validierung.html     # Pruefung-/Abgleich-Sicherungen, ZIP, Browser-Speicher
python tests/lang_switch.py        Laubmann_Validierung.html
python tests/rounds_check.py --payload <payload> --machine <r1>@<graph> <r2>@<graph> --review <export>/review --work <scratch>
```
`interaction_export.py` ruft `tests/loaders_check.py` mit dem Python des Repos (`.venv`, oder `LV_REPO_PYTHON`).
