# Graph-Prüfung (`Laubmann_Graphpruefung.html`) und Graph-Explorer (`Laubmann_Graph_Explorer.html`)

Eine einzelne HTML-Seite, mit der eine Historikerin oder ein Historiker den exportierten Wissensgraphen **Eintrag für Eintrag am Scan prüft**. Bisher ist nichts von einem Menschen geprüft: Die Bildlesung hat Transkriptionen korrigiert, die Maschinenprüfung hat Namensentscheidungen automatisch angewendet (Konfidenz ≥ 0,9 und ≥ 2 Quellen), und zwei Scanprüfungen (Gemini auf allen Einträgen, Claude auf der Stichprobe) haben die Datensätze des Graphen mit den Seiten verglichen. Jede dieser Änderungen und jeder Befund ist eine Behauptung – die Seite zeigt sie neben Graph und Scan und lässt sie annehmen, ablehnen oder korrigieren.

Die Seite ist ein **Fork des Graph-Explorers** (`tools/explorer/`): gleiche Datenpackung (alle Tripel der Exportdatei), gleiche Übersicht, Knoten-, Klassenansicht und Suche. Neu ist die Prüfschicht aus `build_review.py` und alles, was man damit tun kann.

## Bauen

```powershell
# 1. Prüfschicht (liest Export, Korpus, Seitengeometrie, Maschinenprüfung, Scanprüfungen) -> review.json
.venv\Scripts\python.exe tools\validation_ui\graph_check\build_review.py --help

# 2. Seite: Graph-Prüfung (entscheiden, exportieren)
.venv\Scripts\python.exe tools\validation_ui\graph_check\build_graph_check.py `
    data\exports\kg_exports_2026-10-01_checked\rdf\laubmann_sample.ttl `
    data\cache\graph_check\review.json `
    data\exports\graph_check\Laubmann_Graphpruefung.html

# 3. dieselbe Anwendung als Graph-Explorer (nur lesen): --mode explorer
.venv\Scripts\python.exe tools\validation_ui\graph_check\build_graph_check.py `
    data\exports\kg_exports_2026-10-01_checked\rdf\laubmann_sample.ttl `
    data\cache\graph_check\review.json `
    data\exports\graph_check\Laubmann_Graph_Explorer.html --mode explorer
#   --mode review|explorer   review (Standard) = Graph-Prüfung; explorer = dieselbe Anzeige ohne Entscheidungen
#   --scans drive            (Standard) Drive-Vorschau je Seite, lokale JPEGs als Rückfall
#   --scans local:<Ordner>   <Ordner>/<Seiten-ID>.jpg relativ zur HTML-Datei zuerst
#   --local-crops <Ordner>   Ausschnitte der multimodalen Regionen, <region_uid>.jpg, relativ zur HTML-Datei
#                            (Standard: data/region_crops dieses Repos, falls vorhanden; none = keine lokalen)
#   --no-cache               Graph neu parsen (sonst: Packung aus <Ausgabeordner>/.cache, Schlüssel = Name, Größe, mtime)
```

Der erste Lauf parst die Turtle-Datei (ca. 30 s für 2 Mio. Tripel), jeder weitere braucht ca. 5 s. Ergebnis: eine Datei von rund 20 MB (Graph 13,7 MB, Prüfschicht 6 MB, jeweils gzip + base64), die in etwa 1 s öffnet. Sie läuft ohne Server direkt aus dem Dateisystem (`file://`) in Edge und Chrome; Netz braucht sie nur für Scans von Google Drive, Kartenkacheln und die GBIF-Suche. Der Builder gibt aus, wie Graph und Prüfschicht zusammenpassen (Einträge/Datensätze ohne Prüfdaten, abweichende Namen) und warnt, wenn `review.json` für einen anderen Export gebaut wurde.

Der Builder nimmt die Drive-Kennungen aller Seiten der Prüfschicht auf (auch der Seiten, die nur Bilder eines Eintrags tragen und im Graph keine `lkg:DiaryPage` sind) und trägt den lokalen Ordner der Ausschnitte in die Seite ein (`meta.scans.crops`). Er ergänzt die Prüfschicht um drei Dinge: `obs` (je Eintrag Knoten, Extraktionsindex und Vorkommen jedes Datensatzes – der Index wird aus der IRI zurückgerechnet: `sha1("<entry_uid>|<Name wie geschrieben>|<Index>")[:12]`), `sample` (die feste Stichprobe: `sha1(entry_uid) mod 33 == 0`) und `graph` (Quelle, Zahlen).

## Eine Anwendung, zwei Builds: Graph-Prüfung und Graph-Explorer

Derselbe Code, dieselben Daten, zwei Seiten – der Builder schreibt den Modus in die eingebetteten Metadaten (`<script id="gc-meta">`, außerdem `meta.mode` von Graph und Prüfschicht), die Module lesen ihn als `EXPLORER`. Es gibt keine zweite Codebasis.

| | `--mode review` (Standard) | `--mode explorer` |
|---|---|---|
| Datei, Titel | `Laubmann_Graphpruefung.html`, „Laubmann-KG · Graph-Prüfung“ | `Laubmann_Graph_Explorer.html`, „Laubmann-KG · Graph-Explorer“ |
| Anzeige | Teilgraph mit Eigenschaftszeilen und Voreinstellungen, Tabelle mit allen Spalten, Scan mit Regionen, Zeile des Datensatzes und Rahmen der Bilder, Ausschnitte und Karten für Bilder und Einlagen, Korpusleiste, Knoten-, Klassenansicht, Suche, Zahlen der Übersicht für Graph und Korpora | **identisch** (der Test vergleicht für denselben Eintrag Knoten, Zeilen, Kanten, Markierungen, Karten, Tabellenspalten und -zellen, Scan-Overlays und die Zahlen der Übersicht) |
| Entscheiden | Knöpfe und Tasten `J N E X U`, Formulare, „Datensatz hinzufügen“, Name der Prüferin, „Sichern & Export“, „Laden“, „Eintrag geprüft“, Warteschlange „Geprüft“, „von dir entschieden“ | **nichts davon**: keine Entscheidungsknöpfe, -tasten oder Formulare, keine bearbeitbare Zelle, kein Export; gespeicherte Entscheidungen der Graph-Prüfung werden nicht geladen |
| Befunde, automatische Änderungen | Karten mit Entscheidung | dieselben Karten **nur lesend** (gleiche Farben und Zeichen, „ist → soll“, Begründung), Reiter „Hinweise“; Schalter **„Prüfhinweise zeigen“** in der Korpusleiste (Standard: an) – aus = der Graph ohne Ringe, Marken, Geisterknoten, Hinweiskarten, Chips und Lesekorrektur-Marken |
| Liste links | Arbeitsliste, Standard „Befund der Maschine“, schwer zuerst, Zahlen „offen / gesamt“ | alle Einträge Band für Band in Tagebuchfolge; die Warteschlangen bleiben als Filter (Zahl der Einträge) |
| Einstellungen im Browser | Präfix `lkgc.` | Präfix `lkge.` (die beiden Seiten stören sich nicht) |

Der alte, einfache Explorer aus `tools/explorer/` ist eine andere Seite (andere Ebenen, keine Eigenschaftszeilen, keine Ausschnitte, kein Korpusfilter); wer dieselben Daten wie in der Graph-Prüfung sehen will, nimmt `Laubmann_Graph_Explorer.html`.

## Aufbau der Seite

- **Links – Arbeitsliste.** Warteschlangen mit der Zahl der noch offenen Einträge: *Befund der Maschine* (Datensätze, die eine Scanprüfung für falsch oder überzählig hält, oder fehlende Datensätze) · *Automatisch geändert* (angewendete Namensentscheidung mit geänderter Verknüpfung, automatische Wertkorrektur, Ausschluss) · *Lesung an Art/Zahl/Ort* · *Texteinlagen* · *Bilder* (Einträge mit mindestens einer Zeichnung, Karte, Fotografie, einem Druck oder Objekt) · *Hinweise* (QA) · *Stichprobe* · *Alle* · *Geprüft*. Darunter die **Stufen-Chips** schwer / mittel / leicht (Einträge mit offenen Befunden dieser Stufe; kombinierbar untereinander und mit der Warteschlange), Band-Filter, Textfilter und die Sortierung: Standard „schwer zuerst“ (meiste offene schwere Befunde, dann mittlere, dann leichte) oder Tagebuchfolge. Je Zeile stehen die **offenen Befunde als farbige Zahlen je Stufe** (rot, orange, gelb), dazu ¶ = Texteinlage, ▣ = Bild/Karte/Objekt, ✓ = geprüft. Unter einem Korpusfilter zeigt die Zeile „n im Korpus / n gesamt“.
- **Mitte – Teilgraph** wie im Explorer, mit Markierungsschicht: **die Farbe von Ring und Marke ist die Schwere** (rot schwer · orange mittel · gelb leicht · graublau Hinweis, nur Marke), **das Zeichen ist die Art** – `!` Befund einer Scanprüfung · `M` automatisch geändert · `?` Vorschlag bzw. fehlender Datensatz (Geisterknoten „fehlt?“) · `×` entfernt (Geisterknoten, durchgestrichen) · grünes `✓` von dir entschieden; eine Gruppe trägt die Zahl ihrer offenen Datensätze in der Farbe des schwersten. Die Ebene **Eigenschaften** schreibt alle Angaben eines Knotens in seinen Kasten, `K0`–`K3` am Datensatz ist seine Korpusstufe (siehe unten). Ein Klick auf einen Knoten öffnet seine Karte. `G` schaltet auf die **Tabelle der Datensätze**: die zehn korrigierbaren Felder (Art, Anzahl, Ort, Datum, Beobachter, Nachweistyp, Geschlecht, Stadium, Brut, Status), die Korpusstufe und **eine Spalte je Eigenschaft**, die ein Datensatz des Eintrags im Graphen trägt. Befunde stehen als „ist → soll“-Chips in der Zelle ihres Feldes (Klick = übernehmen), eine Zelle der gewählten Zeile lässt sich direkt bearbeiten.
- **Rechts oben – Scan** (dauerhaft, `S` blendet ihn aus): die Seite(n) des Eintrags, seine Regionen umrandet (gestrichelt + „ungefähr“, wenn geschätzt), Rad = Zoom, Ziehen = verschieben, Doppelklick = Eintrag einpassen. Der gewählte Datensatz markiert seine Zeile und die Wortspanne. Die multimodalen Regionen des Eintrags sind dünn violett umrandet und mit ihrer Art beschriftet („▣ Bilder“ blendet die Rahmen aus); ein Klick auf einen Rahmen öffnet die Karte der Region, die gewählte Karte hebt ihren Rahmen hervor. Seiten, die nur Bilder tragen, stehen mit in der Seitenleiste. Wo die Prüfschicht keine Position hat (Lesekorrekturen, 195 Regionen ohne Rahmen), wird nichts markiert.
- **Rechts unten – Reiter.** *Prüfen*: eine Karte je Entscheidung, **nach Schwere geordnet**: schwer · mittel · leicht (jeweils „offen / gesamt“), dann eingeklappt die Hinweise der Stufe 0 („+ n Hinweise zeigen“: bestätigte Verknüpfungen, unstrittige oder nicht angewendete Lesekorrekturen, Vermerke der Qualitätsprüfung, Vorschläge unter den Schwellen), eigene Änderungen an Datensätzen ohne Befund, Eintragskopf, Bilder und Einlagen, „Eintrag geprüft“. Der Rand der Karte hat die Farbe ihrer Stufe, die Marke davor das Zeichen ihrer Art; eine entschiedene Karte wird grün und zählt nicht mehr. Namensentscheidungen gelten für ALLE Einträge (mit Zahl der Nennungen). *Text*: Eintragstext mit den Lesekorrekturen an Ort und Stelle (alt durchgestrichen, neu unterlegt, Farbe nach Urteil), Belegstellen der Datensätze, „Auswahl korrigieren“ für eine eigene Lesung. *Knoten*: alle Tripel des gewählten Knotens.
- **Kopf des Eintrags:** die offenen Befunde getrennt nach Stufe („offen 1 schwer 2 mittel 1 leicht + 9 Hinweise“), unter einem Korpusfilter „Kern: 5 von 8“.
- **Übersicht:** Warteschlangen, **offene Befunde je Stufe und je Art**, die **vier Korpora** (Datensätze, Einträge, Taxa; Klick wählt den Filter) mit der Verteilung der Gründe, Abdeckung der Prüfungen, Fortschritt, Kurzanleitung, die Präzisionstabelle der bisherigen Entscheidungen und – aufklappbar – die **Regeln der Schwere**; darunter die Übersicht des Explorers.

## Bilder und Einlagen (multimodale Regionen)

Jede Region des Eintrags (`media` der Prüfschicht: Zeichnung, Karte, Foto, Druck, Objekt, Texteinlage, Liste) hat im Reiter *Prüfen* eine Karte in der Gruppe „Bilder und Einlagen“: den Ausschnitt, die Art, Beschreibung (`dcterms:description`) und sichtbaren Text (`lkg:visibleText`) aus dem Graph-Knoten `data:region_<region_uid>`, bei Texteinlagen und Listen außerdem den Lesezustand (gelesen / teilweise / nicht gelesen / in anderem Eintrag gelesen) mit dem Hinweis, fehlende Datensätze zu ergänzen (`J`). Ein Klick auf den Ausschnitt öffnet die Großansicht (Rad oder `+`/`-` = Zoom, Ziehen = verschieben, Doppelklick = einpassen, `Esc` schließt). Derselbe Ausschnitt erscheint im Reiter *Knoten* und in der Knotenansicht einer `lkg:MultimodalRegion` und – bei eingeschalteter Ebene „Archiv“ – als Vorschaubild im Tooltip der Bild- und Objekt-Knoten des Teilgraphen.

Ladereihenfolge eines Ausschnitts (wie bei den Scans, mit `loading="lazy"`):

1. Drive-Vorschau über die Dateikennung (`crops` der Prüfschicht; braucht eine Google-Anmeldung mit Zugriff auf `HistOrniGraph_output`),
2. die lokale Kopie `<Ordner>/<region_uid>.jpg` (Standard `data/region_crops`),
3. ein Ausschnitt aus dem Seitenscan nach dem Rahmen der Region (wenn die Prüfschicht einen hat; als solcher beschriftet),
4. sonst der Hinweis „Bild nicht ladbar“.

Die Dateien dazu entstehen außerhalb dieses Ordners: `tools/export_region_crops.py` schreibt die lokalen JPEGs (`data/region_crops/<region_uid>.jpg`, längste Seite 1.400 px), `tools/validation_ui/drive_ids.py --regions drive_regions.json` liest die Drive-Kennungen der Ausschnitte, die `build_review.py --drive-regions` als `crops` in die Prüfschicht übernimmt.

## Eigenschaften, „Alles zeigen“ und die Spalten der Tabelle

Nichts davon ist eine feste Liste: Kästen und Spalten entstehen aus den ausgehenden Tripeln der Knoten.

- **Ebene „Eigenschaften“** (Standard: an): jede Literal-Aussage eines Knotens als Zeile „Bezeichnung der Ontologie · Wert“ (dieselben Bezeichnungen DE/EN wie im Reiter *Knoten*) – bei Datensätzen also auch Nachweisart, Lautäußerungstyp, Zahlenqualifikator, Verhalten, Tageszeit, Mikrohabitat, Originalwortlaut …, bei Taxa die Systematik, bei Orten Koordinaten und Unschärfe, beim Eintrag Kennung, Daten, Eintragsart und Text. Nur die Bezeichnung, die schon als Titel des Kastens steht, wird nicht wiederholt. Lange Werte sind auf eine Zeile gekürzt; ein Klick auf die Zeile klappt sie auf und zu.
- **kompakt / alle** (Auswahl „Eigensch.“): bis 12 Datensätze zeigt jeder Knoten alle Zeilen; darüber eine Zeile Zusammenfassung je Knoten, alle Zeilen beim gewählten Knoten und im Tooltip des überfahrenen. „alle“ erzwingt alle Zeilen, „kompakt“ die Kurzform.
- **Ebene „Verweise“**: jede Aussage eines gezeichneten Knotens, die auf einen Knoten zeigt und im Bild keine Kante hat, als Zeile „→ Ziel“ (z. B. Typ, „ist Teil von“, Provenienz, Geometrie eines Orts).
- **„Alles zeigen“** schaltet jede Ebene ein: Datensätze, Taxa, Orte, Personen, Habitate, Archiv (Band, Seiten, Quell- und multimodale Regionen), Normdaten, Provenienz, Eigenschaften, Verweise. Dann ist jedes Tripel jedes gezeichneten Knotens eine Kante oder eine Zeile (der Test prüft das). **„Standard“** stellt die Ausgangslage wieder her (ohne Archiv, Normdaten, Provenienz, Verweise).
- Mit Eigenschaften ist der Graph breiter als das Fenster: die Ansicht bleibt lesbar und zeigt Eintrag, Datensätze und Taxa; der Knopf am unteren Rand („Orte · Personen · Habitate ▸“), Ziehen oder Umschalt + Mausrad führen weiter, `⤢` zeigt den ganzen Graphen, `☰` blendet die Arbeitsliste aus.
- **Tabelle:** Standard ist jede Spalte, die in diesem Eintrag einen Wert oder einen Vorschlag hat. „Spalten ▾“ blendet Spalten ein und aus („alle“, „Standard“); die Wahl gilt für alle Einträge und bleibt gespeichert. Nummer, Marke und Art bleiben beim seitlichen Rollen stehen. Befunde zu Feldern ohne korrigierbare Spalte (Nachweisart, Ruf, Verhalten, Notiz) stehen als gepunkteter Chip in der Spalte ihrer Eigenschaft.

Was auch mit „Alles zeigen“ **nicht gezeichnet** wird: die Datensätze einer eingeklappten Gruppe (bei mehr als 30 Datensätzen gruppiert die Seite nach Ordnung; `▾▾` klappt alle auf) · Knoten in zweiter Reihe, auf die nur ein Verweis zeigt (die Geometrie eines Orts mit ihrem WKT, Konzeptschemata, Klassen der Ontologie) – der Verweis nennt sie, ihre Angaben stehen im Reiter *Knoten* bzw. in der Knotenansicht · eingehende Aussagen von außerhalb des Eintrags (andere Einträge, die dieselbe Art oder denselben Ort nennen): Knotenansicht, Tabelle „Verwendung“ · Geisterknoten („fehlt?“, „entfernt“) und die Korpusstufe sind keine Tripel des Graphen, sondern stammen aus der Prüfschicht.

## Schwere der Befunde

Vier Stufen, überall gleich verwendet für Farbe, Reihenfolge und Zählung: **3 schwer** (rot) · **2 mittel** (orange) · **1 leicht** (gelb) · **0 Hinweis** (graublau). Die Farbe trägt die Stufe, das Zeichen die Art (`!` Befund · `M` automatisch · `?` Vorschlag/fehlt · `×` entfernt · `✓` entschieden). Alle Regeln stehen in EINER Tabelle, `SEV` in `gc_severity.js`; die Seite baut daraus die Tabelle in Hilfe und Übersicht.

| Art | Regel | Stufe |
|---|---|---|
| Befund einer Scanprüfung an einem Datensatz (das schwerste Feld zählt) | Datensatz überzählig (steht nicht auf der Seite) | 3 |
| | Art (Feldcodes `species`, `sci`, `name`) oder Status (anwesend/abwesend) falsch | 3 |
| | Anzahl, Datum, Ort, Beobachter oder Nachweistyp falsch | 2 |
| | Georeferenz / Ortsverknüpfung (`georef`, `place`; betrifft den Ortsnamen) | 1 |
| | Geschlecht, Alter, Brut, Nachweisart, Ruf, Verhalten, Notiz, Sonstiges | 1 |
| | Urteil „unsicher“ | 1 |
| | beide Prüfungen beanstanden den Datensatz | +1 (höchstens 3) |
| | Sicherheit der Prüfung unter 0,8 | −1 (mindestens 1) |
| Fehlendes | fehlender Beobachtungsdatensatz | 2 |
| | fehlende Person, Reise, Wetterangabe, sonstige Angabe | 1 |
| Eintragskopf | Datum falsch | 3 |
| | Ort falsch | 2 |
| | Art des Eintrags falsch | 1 |
| Automatische Änderung an einem Namen (angewendete Maschinenentscheidung) | Art auf ein anderes Taxon umgehängt (anderer wissenschaftlicher Name) oder als „kein Taxon“ entfernt | 2 |
| | Art neu verknüpft | 1 |
| | Art: anderer GBIF-Eintrag desselben wissenschaftlichen Namens | 1 |
| | Ort verschoben oder entfernt | 1 |
| | Personenverknüpfung entfernt | 1 |
| | Lebensraum entfernt (oder Zuordnung geändert) | 1 |
| | Ort oder Person neu verknüpft · jede „bestätigt, unverändert“ | 0 |
| Automatische Wertkorrektur an einem Datensatz (`rec.auto`) | Art ersetzt oder Datensatz gestrichen | 2 |
| | anderes Feld | 1 |
| Angewendete Lesekorrektur | eine Prüfung nennt sie falsch/teilweise und sie ändert einen Vogelnamen oder eine Zahl (`rel` enthält b oder n) | 2 |
| | beanstandet, ändert nur einen Ortsnamen (`rel` nur p) | 1 |
| | beanstandet ohne Bezug · unbeanstandet · nicht angewendet | 0 |
| Qualitätsprüfung | `transcript_illegible` | 2 |
| | Ausschluss `non_bird` / `low_confidence_taxon` · `nonplace` · `date_year_corrected`, `date_corrected`, `date_from_position` | 1 |
| | alles Übrige | 0 |
| Texteinlage | nicht gelesen | 2 |
| | teilweise gelesen | 1 |
| | gelesen · im Eintrag mitgelesen | 0 |
| Vorschlag der Maschine | unter den Schwellen, nicht angewendet | 0 |

Zwei Ergänzungen, die die Daten verlangen: Ausschlüsse `review_not_taxon|place|person|habitat` ohne eigene Namenszeile folgen der Namensregel (Taxon 2, sonst 1), `value_dropped` (2 Fälle) zählt als automatische Wertkorrektur eines anderen Feldes (1).

Wirkung: Kartenrand, Marke und Knotenring in der Farbe der Stufe · Reiter *Prüfen* nach Stufe, der schwerste offene Befund zuerst und fokussiert · Arbeitsliste mit Zahlen je Stufe, Standard-Sortierung und Stufen-Chips · „offen“ im Kopf des Eintrags je Stufe · Übersicht je Stufe und Art. **Ein entschiedener Befund zählt nicht mehr**, ein als geprüft markierter Eintrag hat keine offenen Befunde; Stufe 0 ist eingeklappt und wird getrennt gezählt. „Eintrag geprüft“ fragt nur dann ein zweites Mal, wenn noch schwere oder mittlere Befunde offen sind. Bilder und nicht gelesene Texteinlagen haben keine eigene Entscheidung – sie bleiben offen, bis der Eintrag geprüft ist.

## Korpusfilter

`build_review.py --dwca` gibt jedem Datensatz eine Stufe `t` und die Gründe `tw`, warum er nicht in der nächsten Stufe ist:

| Stufe | Korpus | Gründe (`tw`) |
|---|---|---|
| K0 | außerhalb des Kerns | `spurious` eine Scanprüfung findet den Datensatz nicht · `duplicate` Doppel · `no-taxon` kein GBIF-Taxon · `flagged` eine Scanprüfung nennt ein Feld falsch · `unchecked` nicht beurteilt |
| K1 | Kern | `rank` nicht auf Artniveau · `name` geschriebener Name kein belegter deutscher Name des Taxons · `reading` strittige Lesekorrektur in der Textstelle · `date` Datum des Eintrags falsch beurteilt · `illegible` Scan nicht lesbar |
| K2 | strenger Kern | `no-coords` Ort ohne Koordinaten |
| K3 | strenger Kern mit Koordinaten | – |

**Die Korpusleiste** steht in beiden Builds als eigene Zeile direkt unter der Kopfzeile und ist in jeder Ansicht da (Übersicht, Einträge, Klassen, Knotenansicht, Suche): links „Korpus“, dann vier beschriftete Knöpfe mit der Zahl ihrer Datensätze – **Vollständig 85.631 · Kern 74.909 · Strenger Kern 69.150 · Strenger Kern mit Koordinaten 44.372** –, der gewählte ist gefüllt. Der Knopf wählt die niedrigste Stufe, die gezeigt wird; die Wahl bleibt im Browser gemerkt. `ⓘ` daneben öffnet die Erklärung der vier Korpora in Worten (jeder Knopf trägt sie auch als Tooltip, die Hilfe ebenso). Ist ein Filter aktiv, färbt sich die Leiste, nennt „n von m Datensätzen, n von m Einträgen“ und bietet „Filter aufheben“. Im Explorer-Build steht rechts in der Leiste der Schalter „Prüfhinweise zeigen“. Im Endstand liegen die 85.631 · 74.909 · 69.150 · 44.372 Datensätze in 9.148 · 8.607 · 8.198 · 6.743 Einträgen mit 642 · 491 · 388 · 369 Taxa.

Der Filter ist **nur eine Ansicht**:

- Teilgraph, Tabelle und Karten zeigen die Datensätze des Korpus; „n außerhalb zeigen“ (Werkzeugzeile, Hinweis im Reiter *Prüfen*) blendet die übrigen abgeblendet ein, mit Stufe und Grund in Worten.
- Die Arbeitsliste führt nur Einträge mit mindestens einem Datensatz im Korpus („n im Korpus / n gesamt“); Warteschlangen, Stufen-Chips und offene Befunde zählen entsprechend (Befunde an Datensätzen außerhalb des Korpus zählen nicht).
- Knotenansicht (Verwendung, je Jahr, je Monat, Karte), Klassenansicht und die Zahlen der Übersicht zählen nur Datensätze und Einträge des Korpus; Taxa, Orte, Personen und Habitate ohne Verwendung im Korpus fallen aus den Listen.
- Jeder Datensatz zeigt seine Stufe (`K0`–`K3` am Knoten, Zeile „Korpus“ im Kasten, Spalte „Korpus“ der Tabelle, Chip auf der Karte, Reiter *Knoten*) und, wenn er nicht in der strengsten Stufe ist, den Grund.
- **Entscheidungen und Export betreffen immer alle Datensätze** – der Export ist unter jedem Filter derselbe (Test). „Eintrag geprüft“ bestätigt auch die ausgeblendeten Datensätze des Eintrags.

## Tasten

| Taste | Wirkung auf der fokussierten Karte |
|---|---|
| `J` | übernehmen (vorgeschlagene Werte), bestätigen, „richtig“; bei „überzählig“: streichen; bei fehlendem Datensatz: Formular zum Hinzufügen |
| `N` | Datensatz stimmt (Befund falsch) · Namensentscheidung zurücknehmen · Lesung falsch (alter Text gilt) · Fehlalarm · nicht hinzufügen |
| `E` | Werte bearbeiten / eigene Lesung / Eintragskopf bearbeiten |
| `X` | Datensatz streichen |
| `U` | unsicher |
| `↑` `↓` | Karte davor / danach |
| `←` `→` | voriger / nächster Eintrag der Liste |
| `⏎` | auf der letzten Karte: Eintrag geprüft (Datensätze ohne Entscheidung gelten als richtig; bei offenen schweren oder mittleren Befunden zweimal) – im Formular: speichern |
| `Z` | letzte Entscheidung rückgängig |
| `S` · `G` · `/` · `Esc` | Scan ein/aus · Graph/Tabelle · Suche · Formular oder Großansicht schließen |

## Entscheidungen und Export

Entscheidungen liegen im Browser (`localStorage`, Schlüssel `laubmann-graphpruefung`) und – wenn unter „Sichern & Export“ verbunden – in einer Sicherungsdatei, die nach jeder Entscheidung mitgeschrieben wird (File System Access API). „Fortschritt laden“ liest `graph_progress.json` oder ein Export-ZIP wieder ein (je Schlüssel gewinnt die neuere Entscheidung). Der Graph ändert sich erst beim nächsten Pipeline-Lauf; bis dahin zeigt die Seite die Entscheidung als „von dir entschieden“.

Zustandsschlüssel (stabil über neue Exporte): `rec:<entry_uid>|<name klein>|<obs_index>` · `tc:<entry_uid>|<alt>|<neu>` · `qa:<entry_uid>|<reason>|<value>` · `miss:<entry_uid>|<text>` · `entry:<entry_uid>` · `name:<section>|<name klein>` · `txt:<entry_uid>|<alt>` (eigene Textkorrektur). Jede Entscheidung trägt, was der Export braucht (`ref`) und was die Maschine vorgeschlagen hatte (`m`) – der Export hängt also nicht davon ab, mit welcher `review.json` die Seite gebaut wurde.

„Sichern & Export“ lädt ein ZIP:

| Datei | liest | Inhalt |
|---|---|---|
| `review/observation_corrections.csv` | `src/laubmann_kg/normalization/observation_corrections.py` (`load_observation_corrections`) | je korrigiertem Feld eines Datensatzes eine Zeile (`action=set`: count, locality, date, observer, co_observers, record_type, sex, life_stage, breeding, status; `-` leert) · ergänzte Datensätze (`action=add`) · Datum/Art des Eintrags (`written` leer, `field=entry_date\|entry_kind`) |
| `review/value_corrections.csv` | `src/laubmann_kg/normalization/corrections.py` (`load_corrections`) | andere Art für einen Datensatz (`kind=taxon, action=replace` mit wissenschaftlichem Namen und GBIF-Schlüssel) · gestrichener Datensatz (`action=drop`) · Ort des Eintrags ersetzt (`kind=place`) |
| `review/transcript_decisions.csv` | `src/laubmann_kg/extraction/reading.py` (`load_transcript_decisions`) | accept / reject / edit (+ `final_text`) je Lesekorrektur, Schlüssel (entry_uid, old_text, new_text) |
| `review/text_corrections.csv` | `src/laubmann_kg/review/readings.py` (`load_readings`) | eigene Korrektur einer Textstelle |
| `review/qa_decisions.csv` | `src/laubmann_kg/qa.py` (`load_qa_decisions`) | confirm / false_alarm je QA-Hinweis, Schlüssel (entry_uid, reason, value) |
| `review/identities.csv` | `src/laubmann_kg/review/identities.py` (`Identities.load`) | Namensentscheidungen: bestätigte Maschinenzeile (jetzt mit `reviewed_by` = Mensch), übernommener Vorschlag, oder zurückgenommen = frühere Verknüpfung als `same`/`link`/`nolink`, sonst `unsure` (die menschliche Zeile verdrängt die Maschinenzeile, es gilt wieder die automatische Zuordnung) |
| `entry_checks.csv` | Statistik | je geprüftem Eintrag: Warteschlange, Zahl der Datensätze, bestätigt, korrigiert, ergänzt, gestrichen |
| `graph_audit.csv` | Statistik | jede Entscheidung mit dem Vorschlag von Prüfung/Maschine und `agreed` = yes / partly / no; auch die stillschweigend bestätigten Datensätze geprüfter Einträge (`human_decision=implicit_ok`) |
| `graph_progress.json`, `LIESMICH.txt` | diese Seite / Mensch | der ganze Stand (wieder einlesbar) und eine Beschreibung der Dateien |

Die Dateien aus `review/` gehören nach `data/review/` (an vorhandene Dateien anhängen). Was der Export beachtet:

- **Reihenfolge in `value_corrections.csv`:** `corrections.py` zählt `occurrence` unter den Datensätzen, die den Namen *in diesem Moment* tragen. Darum stehen die Zeilen eines Namens von der höchsten `occurrence` abwärts und vor Zeilen, die einen anderen Datensatz in diesen Namen umbenennen. Nicht umsortieren.
- **Art ersetzt und Felder korrigiert:** die Feld-Zeilen in `observation_corrections.csv` tragen dann den NEUEN Artnamen als `written` (die Wertkorrekturen laufen zuerst) und den `obs_index`.
- **Georeferenz-Befund** (`f` enthält `georef`, `fix.place`): betrifft den Ort, nicht den Datensatz. Die Karte bietet „nur dieser Datensatz“ (→ `locality` = vorgeschlagener Ort) und verweist für den Namen auf die Verknüpfungsseite.
- **Werte im falschen Format** (Anzahl „500 + x“, Datum „1932“, Eintragsart „third-party-report“) werden nie exportiert: `J` öffnet dann das Formular.
- **Nicht über die Verträge umsetzbar** (stehen nur in `graph_audit.csv`): zurückgenommene automatische Wertkorrekturen (die Zeile muss aus `data/review/machine/value_corrections_machine.csv` entfernt werden) und als falsch markierte, von der Maschine nur bestätigte Verknüpfungen (auf der Verknüpfungsseite korrigieren).

## Dateien

| Datei | Zweck |
|---|---|
| `build_review.py` | Prüfschicht `review.json` (Schema im Modul-Docstring) |
| `build_graph_check.py` | Builder beider Seiten (`--mode review` / `explorer`); importiert Packung, Ontologie-Labels und Blob-Format aus `tools/explorer/build_graph_explorer.py` |
| `graph_check_template.html` | **Fork** von `tools/explorer/graph_explorer_template.html` (Arbeitsliste, Scan-Bereich, Reiter, Export-Knöpfe, zweiter Datenblock) |
| `gc_explorer.js` | **Fork** von `tools/explorer/graph_explorer.js`; jede Änderung ist mit `[GC]` markiert (Einstieg in die Prüfmodule, Markierungsschicht, Geisterknoten, Reiter, Tasten, Start) |
| `gc_explorer.css` | **Fork** (unveränderte Kopie) von `tools/explorer/graph_explorer.css` |
| `gc_i18n.js` | Texte DE/EN der Prüfmodule; `GX_DE`/`GX_EN` = abweichende Wortlaute des Explorer-Builds |
| `gc_state.js` | Prüfschicht, Zustand, Formate der Verträge, Eintragsmodell, Warteschlangen, Entscheiden/Rückgängig/Speichern |
| `gc_severity.js` | **die Tabelle der Schwere** (`SEV`), Stufe und Zeichen je Befund, Tabelle für Hilfe/Übersicht, Legende |
| `gc_corpus.js` | Korpusfilter: Stufe je Datensatz, die Korpusleiste (vier Knöpfe, ⓘ, „Filter aufheben“, im Explorer-Build „Prüfhinweise zeigen“), Zählungen für Explorer-Ansichten, Gründe in Worten, Tabellen der Übersicht |
| `gc_props.js` | Ebene „Eigenschaften“ / „Verweise“: Zeilen aus den Tripeln, kompakt/alle, „Alles zeigen“/„Standard“, Hinweis auf Spalten außerhalb des Fensters |
| `gc_scan.js` | Scan-Bereich |
| `gc_media.js` | multimodale Regionen: Ausschnitte mit Rückfallkette, Karten, Großansicht |
| `gc_cards.js` | Reiter „Prüfen“: Karten, Aktionen, Formulare, Tastatur |
| `gc_views.js` | Arbeitsliste (Stufen, Sortierung, Chips), Kopfzeile, Markierungsschicht, Text, Übersicht |
| `gc_table.js` | Tabelle der Datensätze: Spalten aus den Prädikaten, Spaltenwahl, Bearbeiten in der Zelle |
| `gc_export.js` | CSV-Dateien, ZIP, Fortschritt laden |
| `gc_review.css` | Stile der Prüfmodule |
| `gc_levels.css` | Farben der Stufen und Korpusstufen (hell/dunkel), Eigenschaftszeilen, Spalten der Tabelle, Korpusfilter |
| `gc_boot.js` | Start; schließt den gemeinsamen Funktionsrahmen (der Builder hängt die JS-Dateien in dieser Reihenfolge aneinander) |
| `tests/` | Playwright-Tests und der Lader-Check |

Leaflet kommt wie beim Explorer aus `tools/validation_ui/leaflet.{js,css}`; kein CDN.

## Tests

Die Browser-Tests brauchen Playwright mit Chromium (auf diesem Rechner im Interpreter von `laubmann-kg_TP`); die Lader laufen mit dem Interpreter des Repos (`GC_REPO_PYTHON`, Standard `.venv\Scripts\python.exe`). Alle Tests blockieren das Netz und kommen ohne Scans aus.

```powershell
$py = "C:\Users\totom\Projects\laubmann-kg_TP\.venv\Scripts\python.exe"
& $py tools\validation_ui\graph_check\tests\smoke.py               # [Seite.html] [Ordner für Bilder]
& $py tools\validation_ui\graph_check\tests\interaction_export.py
& $py tools\validation_ui\graph_check\tests\reload.py
& $py tools\validation_ui\graph_check\tests\screenshots.py         # 1440×900-Bilder beider Builds nach data\exports\graph_check\shots
```

- `smoke.py` – prüft BEIDE Builds. Graph-Prüfung: Ladezeit ≤ 5 s, jede Warteschlange, Karten jedes Typs, Markierungen im Graph, Tabelle, Scan-Overlay, **Eigenschaften** (jedes Literal jedes gezeichneten Knotens ist eine Zeile; kompakt/alle; „Alles zeigen“: jedes Tripel ist Kante oder Zeile; „Standard“), **Spalten der Tabelle** (jedes Prädikat der Datensätze hat eine Spalte, Standard, Spaltenwahl, feste erste Spalte, Chips in ihrer Zelle), **Schwere** (Regeltabelle, Stufen einzelner Fälle, Zahlen je Zeile, Sortierung, Stufen-Chips allein und mit Warteschlange, Kopf, Reihenfolge der Karten, eingeklappte Hinweise, Ringfarbe, „entschieden zählt nicht mehr“, Legende, Übersicht, Hilfe), **Korpusfilter** (Zahlen der Auswahl gegen die Prüfschicht und gegen 85.631 / 74.909 / 69.150 / 44.372, Balken, Warteschlangen, Arbeitsliste, Statistik, Eintrag mit „n außerhalb zeigen“, Tabelle, Knotenansicht eines Taxons, Klassenansicht, Übersicht, gemerkt nach Neuladen, Aufheben), Bilder und Einlagen (Karten, lokaler Ausschnitt, Großansicht, Rahmen auf dem Scan, Knoten-Reiter und Knotenansicht), alle Reiter, DE/EN (gleiche Schlüssel, keine unübersetzten), die übrigen Explorer-Ansichten, der größte Eintrag (391 Datensätze), Betrieb ganz ohne Bilder, keine Konsolenfehler.
  Dazu die **Korpusleiste** (vier Knöpfe mit Namen und Zahlen, Beschriftung „Korpus“, gefüllter aktiver Knopf, eigene Zeile unter der Kopfzeile, in Übersicht / Eintrag / Klassen / Knotenansicht / Suche vorhanden, ⓘ mit vier Erklärungen, Wahl und „Filter aufheben“). **Explorer-Build** (`Laubmann_Graph_Explorer.html` neben der Seite, sonst `GC_EXPLORER`): Modus in den Metadaten, Titel; derselbe Eintrag (`L17-e0132`) zeigt dieselben Knoten mit denselben Eigenschaftszeilen, Kanten, Markierungen, Karten, Tabellenspalten und -zellen und Scan-Overlays wie die Graph-Prüfung, „Alles zeigen“ denselben Graphen, die Übersicht dieselben Zahlen; kein Entscheidungselement in Übersicht, Eintrag (alle Reiter), Tabelle, Knoten- und Klassenansicht; Entscheidungstasten wirkungslos, nichts wird gespeichert, ein gespeicherter Stand der Graph-Prüfung wird nicht geladen; Liste in Tagebuchfolge, Warteschlangen als Filter; „Prüfhinweise zeigen“ aus/an; Korpusleiste und Korpusfilter wie oben; DE/EN; keine Konsolenfehler.
- `interaction_export.py` – mindestens eine Entscheidung jeder Art per Tastatur und Maus, Export (derselbe unter dem strengsten Korpusfilter), ZIP; dann liest `tests/loaders_check.py` jede `review/*.csv` mit dem Lader der Pipeline und wendet Wert- und Datensatzkorrekturen in der Reihenfolge der Pipeline auf Modell-Einträge an. Geprüft wird, dass die Zeilen mit den richtigen Werten ankommen und genau die gemeinten Datensätze ändern.
- `reload.py` – Rückgängig, Neuladen, Fortschritt aus JSON und ZIP in ein frisches Browserprofil, identischer Re-Export, „neuer gewinnt“ beim Zusammenführen.

## Grenzen

- Mit der Ebene „Eigenschaften“ passen bei 1.440 px Breite Eintrag, Datensätze und Taxa lesbar ins Fenster; die Spalte der Orte, Personen und Habitate liegt rechts davon (Knopf am unteren Rand, `⤢` oder Arbeitsliste ausblenden).
- Zwei Karten mit demselben Schlüssel (dieselbe Lesekorrektur zweimal im Eintrag) sind eine Entscheidung und zählen einmal.
- Scans von Drive laden nur mit Google-Anmeldung und Zugriff auf `HistOrniGraph_output`; sonst die lokalen JPEGs (`data/pages_jpg`), die es nur auf diesem Rechner gibt.
- Der Graph unterscheidet Beobachter und Mitbeobachter nicht (beide `dwciri:recordedBy`); das Formular teilt nach der Reihenfolge im Graph.
- `occurrence` zählt nach dem geschriebenen Namen (wie `review.json`); `value_corrections.csv` kennt keinen `obs_index`.
- Lesekorrekturen haben in der Prüfschicht keine Position auf der Seite und werden auf dem Scan nicht markiert; 195 der 1.625 multimodalen Regionen haben keinen Rahmen („nicht verortet“).
- 145 Seiten, die nur Bilder tragen, haben weder Seitengeometrie noch ein lokales JPEG in `data/pages_jpg`; ihr Scan kommt nur von Drive (die Ausschnitte selbst liegen lokal vor).
- Die eigene Textkorrektur verlangt eine Stelle, die keine Lesekorrektur berührt (sonst passt `old_text` nicht auf die Transkription vor der Bildlesung) – dafür gibt es `E` auf der Karte der Lesekorrektur.
