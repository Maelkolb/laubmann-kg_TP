# Maschinelle Prüfung (claude-sonnet-5-5) — Bericht 2026-09-30

Grundlage: Export kg_exports_2026-08-19 (Payload der Abgleich-Oberfläche v4). Alle Entscheidungen sind an den geschriebenen Namen, die Normdaten-Kennung und den Belegschlüssel (entry_uid|Name|Vorkommen) gebunden, nicht an Graph-IRIs.

## Arten (GBIF)

- Entitäten mit Textprüfung: 1182 von 1182 (fehlende Batches: 0)
- Belege mit Bildprüfung (Zeilenbilder): 1620 (fehlende Blätter: 0)
- entity link confirmed: 522
- entity subspecies key normalised: 12
- entity relinked: 27
- entity newly linked: 375
- entity no taxon: 71
- entity unsure: 175

| Klasse | Namen | same | none | unsure | davon umverknüpft |
|---|---|---|---|---|---|
| A | 735 | 696 | 3 | 36 | 3 |
| B | 198 | 190 | 0 | 8 | 19 |
| C | 728 | 651 | 11 | 66 | 307 |
| L | 591 | 452 | 71 | 68 | 136 |

- Korrekturen einzelner Belege (value_corrections_machine.csv): 3
- identities_machine.csv, Abschnitt taxa: 2074 Zeilen, davon 471 mit Konfidenz ≥ 0.9 und ≥ 2 übereinstimmenden Quellen

## Personen (Wikidata / GND)

- geprüfte Personen: 691 (fehlende Batches: 0)
- person link: 163
- person nolink: 119
- person unsure: 409
- person auto link confirmed: 129
- person auto link rejected: 163
- Zeilen in identities_machine.csv: 282 (mit GND: 151), davon 100 mit Konfidenz ≥ 0.9 und ≥ 2 Quellen

## Orte (GeoNames / OSM)

- geprüfte Orte: 1571 (fehlende Batches: 0)
- place corroborated (anchor): 79
- place corroborated (generic): 14
- place corroborated (nominatim): 664
- place newly located: 73
- place not_a_place: 44
- place ok: 728
- place relocated: 41
- place unlocatable: 511
- place unlocated_ok: 89
- place unsure: 68
- place wrong: 131
- Zeilen in identities_machine.csv: 868, davon 606 mit Konfidenz ≥ 0.9 und ≥ 2 Quellen (zweite Quelle: Nominatim-Kandidat am Graph-Punkt / Kandidat ≤ 30 km vom Hauptanker / Gattungswort)

## Extraktionsprüfung (Stichprobe von Einträgen)

- Einträge geprüft: 60 (fehlend: 0); Beobachtungen beurteilt: 572
- obs ok: 437 (76.4 %)
- obs wrong: 95 (16.6 %)
- obs spurious: 6 (1.0 %)
- obs unsure: 34 (5.9 %)
- fehlende Datensätze laut Text: travel 4, observation 118, other 7, person 4, weather 4
- falsche Felder: species 38, locality 30, observer 16, date 14, count 7, other 6, breeding 2, behaviour 2
- Eintragsfelder falsch: place_ok false 5
- Vorschläge für Lesekorrekturen (text_corrections_machine.csv, nicht angewendet): 127

## Dateien

- `identities_machine.csv` — Vertrag von review/identities.csv plus confidence/agreement/sources; Pipeline: `review.machine` (nur Zeilen ≥ Schwelle, menschliche Entscheidungen gehen vor)
- `value_corrections_machine.csv` — einzelne Belege (Kontrakt review/value_corrections.csv)
- `text_corrections_machine.csv` — Lesevorschläge, nur zur Sichtung
- `readings_machine.json` — Lesungen des Bild-Agenten je Belegschlüssel
- `machine_review.json` — Urteile für die Abgleich-Oberfläche (Kasten „Maschinelle Prüfung“)
- `graph_checks.csv`, `graph_checks_missing.csv`, `graph_checks_misreadings.csv`, `graph_checks_entries.csv` — Extraktionsprüfung
