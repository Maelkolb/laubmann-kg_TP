#!/usr/bin/env python3
"""Merge the answers of the second visual round (arbeit2/) into machine_review2/.

  entries/answers/dossier_NNN.json  -> graph_checks2*.csv, text_corrections2.csv
  places/answers/sheet_NNN.json     -> place_readings.json  (item id -> readings)
  taxa_a/answers/sheet_NNN.json     -> taxa_a_readings.json (mention idx -> reading) + stats
  report2.md
"""
import argparse, collections, csv, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--work', default=str(Path.home() / 'Laubmann_Maschinenpruefung/arbeit2'))
ap.add_argument('--out', default=str(Path.home() / 'Laubmann_Maschinenpruefung/machine_review2'))
args = ap.parse_args()
W, O = Path(args.work), Path(args.out)
O.mkdir(parents=True, exist_ok=True)
MODEL = 'machine:claude-sonnet-5-5'
WHEN = '2026-09-30T16:00'


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception as exc:
        print('unreadable', p, exc)
        return default


def wcsv(path, head, rows):
    with open(path, 'w', encoding='utf-8', newline='') as h:
        w = csv.DictWriter(h, fieldnames=head, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- entries
checks, missing, misread, entries, textc = [], [], [], [], []
n_dossiers = 0
missing_answers = []
for d in sorted((W / 'entries').glob('dossier_*/dossier.json')):
    k = int(d.parent.name.split('_')[1])
    doss = jload(d)
    ans = jload(W / 'entries' / 'answers' / f'dossier_{k:03d}.json')
    if not doss:
        continue
    if not ans or not isinstance(ans, dict):
        missing_answers.append(k)
        continue
    n_dossiers += 1
    e = doss['entry']
    ef = ans.get('entry_fields') or {}
    obs_by = {o['index']: o for o in doss['graph'].get('observations', [])}
    occ = collections.Counter()
    okc = collections.Counter()
    for o in sorted(ans.get('observations') or [], key=lambda x: num(x.get('index'), 0)):
        idx = int(num(o.get('index'), 0))
        go = obs_by.get(idx, {})
        written = o.get('written') or go.get('written') or ''
        v = (o.get('verdict') or 'unsure').lower()
        if v not in ('ok', 'wrong', 'spurious', 'unsure'):
            v = 'unsure'
        okc[v] += 1
        fields = [f for f in (o.get('fields') or []) if f]
        checks.append({'entry_id': e['id'], 'entry_uid': e['uid'], 'obs_index': idx, 'occurrence': occ[written.lower()], 'written': written,
                       'taxon': go.get('taxon') or '', 'sci': go.get('sci') or '', 'count': go.get('count') or '', 'verdict': v, 'fields': ';'.join(fields),
                       'correction': json.dumps(o.get('correction'), ensure_ascii=False) if o.get('correction') else '',
                       'confidence': round(num(o.get('confidence'), 0), 2), 'reason': o.get('reason') or ''})
        occ[written.lower()] += 1
    for m in ans.get('missing') or []:
        missing.append({'entry_id': e['id'], 'entry_uid': e['uid'], 'kind': m.get('kind') or 'other', 'text': m.get('text') or '', 'species_de': m.get('species_de') or '',
                        'sci': m.get('sci') or '', 'count': m.get('count') or '', 'note': m.get('note') or ''})
    for m in ans.get('misreadings') or []:
        if not m.get('transcribed') or not m.get('correct'):
            continue
        misread.append({'entry_id': e['id'], 'entry_uid': e['uid'], 'transcribed': m['transcribed'], 'correct': m['correct'], 'matters_for': m.get('matters_for') or 'other'})
        if (m.get('matters_for') or 'other') in ('species', 'place', 'person', 'count', 'date'):
            textc.append({'entry_uid': e['uid'], 'entry_id': e['id'], 'old_text': m['transcribed'], 'new_text': m['correct'], 'note': 'betrifft ' + m.get('matters_for', ''),
                          'reviewed_by': MODEL, 'reviewed_at': WHEN, 'confidence': '', 'matters_for': m.get('matters_for') or ''})
    entries.append({'dossier': k, 'entry_id': e['id'], 'entry_uid': e['uid'], 'volume': e['volume'], 'date': e['date'], 'n_obs': sum(okc.values()),
                    'ok': okc['ok'], 'wrong': okc['wrong'], 'spurious': okc['spurious'], 'unsure': okc['unsure'], 'missing': len(ans.get('missing') or []),
                    'date_ok': ef.get('date_ok') is not False, 'place_ok': ef.get('place_ok') is not False, 'kind_ok': ef.get('kind_ok') is not False,
                    'scan_legible': ans.get('scan_legible') is not False, 'summary': ans.get('summary') or ''})
wcsv(O / 'graph_checks2.csv', ['entry_id', 'entry_uid', 'obs_index', 'occurrence', 'written', 'taxon', 'sci', 'count', 'verdict', 'fields', 'correction', 'confidence', 'reason'], checks)
wcsv(O / 'graph_checks2_missing.csv', ['entry_id', 'entry_uid', 'kind', 'text', 'species_de', 'sci', 'count', 'note'], missing)
wcsv(O / 'graph_checks2_misreadings.csv', ['entry_id', 'entry_uid', 'transcribed', 'correct', 'matters_for'], misread)
wcsv(O / 'graph_checks2_entries.csv', ['dossier', 'entry_id', 'entry_uid', 'volume', 'date', 'n_obs', 'ok', 'wrong', 'spurious', 'unsure', 'missing', 'date_ok', 'place_ok', 'kind_ok', 'scan_legible', 'summary'], entries)
wcsv(O / 'text_corrections2.csv', ['entry_uid', 'entry_id', 'old_text', 'new_text', 'note', 'reviewed_by', 'reviewed_at', 'confidence', 'matters_for'], textc)

# ---------------------------------------------------------------- places
place_readings = collections.defaultdict(list)
n_place_sheets = 0
missing_place_sheets = []
for m in sorted((W / 'places').glob('sheet_*.json')):
    k = int(m.stem.split('_')[1])
    manifest = jload(m) or []
    ans = jload(W / 'places' / 'answers' / f'sheet_{k:03d}.json')
    if not ans:
        missing_place_sheets.append(k)
        continue
    if isinstance(ans, dict):
        ans = ans.get('crops') or ans.get('answers') or list(ans.values())
    n_place_sheets += 1
    by_n = {int(num(a.get('n'), 0)): a for a in ans if isinstance(a, dict)}
    for mf in manifest:
        a = by_n.get(int(mf['n']))
        if not a:
            continue
        place_readings[mf['item']].append({'reading': a.get('reading') or '', 'legible': a.get('legible') is not False, 'is_place': a.get('is_place'),
                                           'place': a.get('place'), 'region': a.get('region'), 'lat': a.get('lat'), 'lon': a.get('lon'), 'unc': a.get('uncertainty_m'),
                                           'same': a.get('same_as_transcription'), 'conf': round(num(a.get('confidence'), 0), 2), 'note': a.get('note') or '',
                                           'written': mf.get('written'), 'entry': mf.get('entry'), 'mi': None, 'model': 'claude-sonnet-5-5'})
Path(O / 'place_readings.json').write_text(json.dumps(place_readings, ensure_ascii=False, indent=0), encoding='utf-8')

# ---------------------------------------------------------------- class-A taxa
taxa_a = {}
n_a_sheets = 0
missing_a_sheets = []
for m in sorted((W / 'taxa_a').glob('sheet_*.json')):
    k = int(m.stem.split('_')[1])
    manifest = jload(m) or []
    ans = jload(W / 'taxa_a' / 'answers' / f'sheet_{k:03d}.json')
    if not ans:
        missing_a_sheets.append(k)
        continue
    if isinstance(ans, dict):
        ans = ans.get('crops') or ans.get('answers') or list(ans.values())
    n_a_sheets += 1
    by_n = {int(num(a.get('n'), 0)): a for a in ans if isinstance(a, dict)}
    for mf in manifest:
        a = by_n.get(int(mf['n']))
        if not a:
            continue
        taxa_a[mf['mi']] = {'reading': a.get('reading') or '', 'legible': a.get('legible') is not False, 'kind': a.get('kind') or '', 'species_de': a.get('species_de'),
                            'sci': a.get('sci'), 'agrees': a.get('agrees_with_current'), 'conf': round(num(a.get('confidence'), 0), 2), 'note': a.get('note') or '',
                            'written': mf.get('written'), 'current': mf.get('current'), 'entry': mf.get('entry'), 'model': 'claude-sonnet-5-5'}
Path(O / 'taxa_a_readings.json').write_text(json.dumps(taxa_a, ensure_ascii=False, indent=0), encoding='utf-8')

# ---------------------------------------------------------------- report
tot = collections.Counter()
for c in checks:
    tot[c['verdict']] += 1
fields = collections.Counter(f for c in checks for f in c['fields'].split(';') if f)
pr = [r for rs in place_readings.values() for r in rs]
pa = [r for r in taxa_a.values()]
legible_a = [r for r in pa if r['legible']]
agree_a = sum(1 for r in legible_a if r['agrees'] is True)
rep = ['# Maschinelle Prüfung, zweite Bildrunde (claude-sonnet-5-5) — 2026-09-30 nachmittags', '',
       '## Extraktionsprüfung, weitere Einträge', f'- Dossiers: {n_dossiers} (Antworten fehlen: {missing_answers or "keine"})',
       f'- Beobachtungen beurteilt: {sum(tot.values())}: ok {tot["ok"]}, wrong {tot["wrong"]}, spurious {tot["spurious"]}, unsure {tot["unsure"]}',
       f'- falsche Felder: {dict(fields.most_common())}', f'- fehlende Datensätze laut Text: {len(missing)}; Lesevorschläge: {len(textc)}', '',
       '## Ortsnamen am Scan (offene Orte)', f'- Blätter: {n_place_sheets} (Antworten fehlen: {missing_place_sheets or "keine"}); Lesungen: {len(pr)} für {len(place_readings)} Orte',
       f'- lesbar: {sum(1 for r in pr if r["legible"])}, Ortsname: {sum(1 for r in pr if r["is_place"] is True)}, kein Ortsname: {sum(1 for r in pr if r["is_place"] is False)}, mit Koordinaten: {sum(1 for r in pr if r["lat"] is not None)}',
       f'- Lesung weicht von der Transkription ab: {sum(1 for r in pr if r["same"] is False)}', '',
       '## Klasse-A-Artnamen am Scan (Stichprobe)', f'- Blätter: {n_a_sheets} (Antworten fehlen: {missing_a_sheets or "keine"}); Belege: {len(pa)}, lesbar {len(legible_a)}',
       f'- Art stimmt laut Bild: {agree_a} von {len(legible_a)} lesbaren ({(100 * agree_a / len(legible_a)) if legible_a else 0:.1f} %); Wort anders gelesen: {sum(1 for r in legible_a if r["reading"] and r["written"] and r["reading"].strip().lower() != r["written"].strip().lower())}', '']
Path(O / 'report2.md').write_text('\n'.join(rep), encoding='utf-8')
print('\n'.join(rep))
