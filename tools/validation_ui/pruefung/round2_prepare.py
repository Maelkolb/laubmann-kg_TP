#!/usr/bin/env python3
"""Second visual round (2026-09-30, afternoon): inputs for Sonnet subagents.

  entries/   118 more extraction dossiers (stratified by volume, not in round 1)
  places/    contact sheets of the written place names of every OPEN place
             (machine: wrong without candidate / unsure / unlocatable), 2 crops each
  taxa_a/    contact sheets of 400 random class-A species mentions (never seen at
             the scan in round 1) — residual visual error rate

Pages come from the Drive thumbnails (w2000 JPEG) in <pages>/<page_id>.jpg.
"""
import argparse, collections, hashlib, io, json, pickle, sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
S = Path('/tmp/claude-1002/-home-tobiasperschl/e08f9f56-b2e5-485d-87cc-799261d38dc6/scratchpad')
sys.path.insert(0, str(S / 'repo/tools/validation_ui/machine_review'))
from common import contact_sheet, context, crop_line, write_json  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--out', default=str(Path.home() / 'Laubmann_Maschinenpruefung/arbeit2'))
ap.add_argument('--pages', default=str(S / 'pages'))
ap.add_argument('--plan', default=str(S / 'round2_plan.json'))
ap.add_argument('--triples', default=str(S / 'triples.pkl'))
ap.add_argument('--only', default='', help='entries|places|taxa_a')
args = ap.parse_args()
OUT = Path(args.out); OUT.mkdir(parents=True, exist_ok=True)
PAGES = Path(args.pages)
P = json.loads((HERE / 'payload_v4.json').read_text(encoding='utf-8'))
D = json.loads((HERE / 'data.json').read_text(encoding='utf-8'))
plan = json.loads(Path(args.plan).read_text())
E, PG, TX, PL = P['E'], P['PG'], P['taxon'], P['place']
ITEMS = {it['i']: it for it in D['items']}


def page_file(pidx):
    f = PAGES / (PG[pidx][0] + '.jpg')
    return f if f.exists() else None


def page_jpeg(f, max_w=1400):
    im = Image.open(f).convert('RGB')
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    b = io.BytesIO(); im.save(b, 'JPEG', quality=85); return b.getvalue()


def loc(u):
    u = str(u); return u.rsplit('#', 1)[-1].rsplit('/', 1)[-1]


def sheets(items, sdir, manifest_of, per_sheet=8, width=1200):
    """items: list of (mention box page idx, box, key...) -> sheet_NNN.png/json"""
    sdir.mkdir(parents=True, exist_ok=True); (sdir / 'answers').mkdir(exist_ok=True)
    k = 0
    for s in range(0, len(items), per_sheet):
        chunk = items[s:s + per_sheet]; crops, manifest = [], []
        for n, it in enumerate(chunk, 1):
            box = it['box']; f = page_file(box[0])
            if not f:
                continue
            pg = PG[box[0]]
            try:
                c = crop_line(f, pg[5], pg[6], box[1:5], width - 90)
            except Exception as exc:
                print('crop failed', pg[0], exc); continue
            crops.append((n, c)); manifest.append(dict(manifest_of(it), n=n))
        if not crops:
            continue
        k += 1
        contact_sheet(crops, width).save(sdir / f'sheet_{k:03d}.png', 'PNG', optimize=True)
        write_json(sdir / f'sheet_{k:03d}.json', manifest)
    return k


ROOT = str(OUT)

# ---------------------------------------------------------------- entries
if args.only in ('', 'entries'):
    print('loading triples …')
    out = collections.defaultdict(lambda: collections.defaultdict(list)); typ = {}
    for s, p, o in pickle.load(open(args.triples, 'rb')):
        pn = loc(p)
        if pn == 'type':
            typ.setdefault(s, set()).add(loc(o))
        else:
            out[s][pn].append(o)
    one = lambda s, p, d='': (str(out[s][p][0]) if s is not None and out[s].get(p) else d)
    many = lambda s, p: [str(x) for x in out[s].get(p, [])]
    label = lambda s: one(s, 'prefLabel') or one(s, 'label') or one(s, 'name') or loc(s)
    entries = {one(s, 'identifier'): s for s, ts in typ.items() if 'DiaryEntry' in ts}

    def obs_index(s, entry_uid, written):
        want = loc(s).replace('obs_', '')
        for i in range(1000):
            if hashlib.sha1(f'{entry_uid}|{written}|{i}'.encode('utf-8')).hexdigest()[:12] == want:
                return i
        return 10 ** 6
    edir = OUT / 'entries'; (edir / 'answers').mkdir(parents=True, exist_ok=True)
    n_ok = 0
    for k, ei in enumerate(plan['entries'], 1):
        e = E[ei]; s = entries.get(e[0])
        if s is None:
            print('no graph entry', e[0]); continue
        d = edir / f'dossier_{k:03d}'; d.mkdir(exist_ok=True); imgs = []
        for pidx in e[8]:
            f = page_file(pidx)
            if not f:
                continue
            pg = PG[pidx]; name = f'page_{len(imgs) + 1}.jpg'
            (d / name).write_bytes(page_jpeg(f)); imgs.append({'file': str(d / name), 'scan': pg[2], 'side': pg[3], 'printed_page': pg[4]})
        observations = []
        for o in out[s].get('containsObservation', []):
            tx = out[o].get('observedTaxon', [None])[0]
            written = one(o, 'verbatimIdentification') or (label(tx) if tx is not None else '')
            rec = {'index': obs_index(o, e[1], written), 'written': written, 'taxon': label(tx) if tx is not None else None, 'sci': one(tx, 'scientificName') or None,
                   'count': one(o, 'individualCount') or None, 'count_qualifier': one(o, 'countQualifier') or None, 'count_min': one(o, 'countMin') or None, 'count_max': one(o, 'countMax') or None,
                   'status': one(o, 'occurrenceStatus') or None, 'locality': one(o, 'verbatimLocality') or None,
                   'evidence': [loc(x) for x in out[o].get('evidenceKind', [])] or None,
                   'vocalisations': [one(v, 'callTranscription') or one(v, 'callType') for v in out[o].get('hasVocalisation', [])] or None,
                   'behaviour': many(o, 'behavior') or None, 'sex': one(o, 'sex') or None, 'life_stage': one(o, 'lifeStage') or None,
                   'breeding': one(o, 'reproductiveCondition') or one(o, 'breedingEvidence') or None, 'record_type': one(o, 'recordType') or None,
                   'observer': (label(out[o]['recordedBy'][0]) if out[o].get('recordedBy') and loc(out[o]['recordedBy'][0]) != 'person_c6b2ff6250e5' else None),
                   'event_date': one(o, 'eventDate') if one(o, 'eventDate') != e[2] else None, 'notes': (one(o, 'verbatimNotes') or None)}
            observations.append({k2: v for k2, v in rec.items() if v not in (None, [], '')})
        observations.sort(key=lambda r: r['index'])
        roles = collections.defaultdict(set)
        for pred, role in {'mentionsCompanion': 'Begleiter', 'mentionsSource': 'Quelle', 'mentionsCollector': 'Sammler', 'mentionsCitedAuthor': 'zitiert', 'mentionsOther': 'sonstige'}.items():
            for p in out[s].get(pred, []):
                roles[p].add(role)
        persons = [{'name': label(p), 'roles': sorted(roles.get(p, {'erwähnt'}))} for p in out[s].get('mentionsPerson', [])]
        travel = []
        for tv in out[s].get('containsTravelEvent', []):
            for leg in out[tv].get('hasLeg', []):
                travel.append({'from': label(out[leg]['departurePlace'][0]) if out[leg].get('departurePlace') else None, 'to': label(out[leg]['arrivalPlace'][0]) if out[leg].get('arrivalPlace') else None,
                               'via': [label(x) for x in out[leg].get('viaPlace', [])] or None, 'mode': one(leg, 'transportMode') or None, 'note': one(leg, 'note') or None})
        weather = [{'verbatim': one(w, 'weatherVerbatim'), 'temperature': one(w, 'temperatureValue') or None, 'unit': one(w, 'temperatureUnit') or None, 'precipitation': one(w, 'precipitation') or None, 'sky': one(w, 'skyCondition') or None} for w in out[s].get('hasWeather', [])]
        habitats = sorted({label(h) for o in out[s].get('containsObservation', []) for h in out[o].get('habitat', []) if str(h).startswith('http')})
        write_json(d / 'dossier.json', {'dossier': k, 'entry': {'id': e[0], 'uid': e[1], 'date': e[2], 'date_verbatim': e[3], 'kind': e[4], 'volume': e[5], 'place': e[6], 'place_verbatim': e[9]},
                                         'pages': imgs, 'transcription': e[7], 'graph': {'observations': observations, 'persons': persons, 'travel': travel, 'weather': weather, 'habitats': habitats}})
        n_ok += 1
    src = (S / 'repo/tools/validation_ui/machine_review/prepare_entries.py').read_text(encoding='utf-8')
    instr = src.split('INSTRUCTIONS = """', 1)[1].split('"""', 1)[0].replace('{root}', ROOT)
    (edir / 'INSTRUCTIONS.md').write_text(instr, encoding='utf-8')
    print('entries: dossiers', n_ok)

# ---------------------------------------------------------------- places
if args.only in ('', 'places'):
    men = PL['men']; items = []
    for iid, mis in plan['placecrops']:
        it = ITEMS[iid]
        for mi in mis:
            m = men[mi]; e = E[m[1]]
            items.append({'box': m[4], 'item': iid, 'mi': mi, 'written': PL['forms'][m[0]][0], 'context': context(e[7], m[2], m[3], 170) if m[2] >= 0 else e[7][:300],
                          'entry': e[0], 'date': e[3] or e[2], 'entry_place': e[6], 'role': m[5], 'label': it['label'], 'n_mentions': it['n'], 'kind': (it.get('cur') or {}).get('kind'),
                          'graph_location': ({'lat': it['cur']['lat'], 'lon': it['cur']['lon'], 'geonames': (it.get('graph') or {}).get('geonames_name')} if it.get('cur') and it['cur'].get('lat') is not None else None),
                          'anchors': [f"{a['place']} ({a['n']} Einträge)" for a in it.get('anchors', [])[:3]],
                          'machine': {'verdict': it['k'], 'reason': it.get('reason'), 'hint': it.get('hint')}})
    items.sort(key=lambda x: (-x['n_mentions'], x['item']))
    k = sheets(items, OUT / 'places', lambda it: {kk: v for kk, v in it.items() if kk not in ('box', 'mi')})
    (OUT / 'places' / 'INSTRUCTIONS.md').write_text(f"""# Place-name reading — instructions

You are reading handwritten German ornithological diary lines (Alfred Laubmann, Bavaria, 1917–1965; Latin cursive with Kurrent elements; he lived in München and Kaufbeuren, excursions mostly in Upper Bavaria and Swabia: Ismaninger Teichgebiet, Starnberger See, Ammersee, Chiemsee, Isar, Lech, Allgäu, Alps, with travel to Austria, Italy, Switzerland, northern Germany). The machine transcription misreads place names; a text-only check could not locate these places. Your job: read the place name AT THE SCAN and say which place is meant. Work carefully but do not over-deliberate. Read each sheet image ONCE with the Read tool, then its manifest, then write the answer file; no other tools are needed.

Files (N = a sheet number you were given, three digits; you may have been given several sheets — answer each, one file each):
- Image: `{ROOT}/places/sheet_N.png` — up to 8 numbered crops; the orange rectangle marks the line the word stands on. Two crops of the same place name may follow each other (same `label` in the manifest).
- Manifest: `{ROOT}/places/sheet_N.json` — per number `n`: `written` (the transcription's word), `context` (transcribed text around it), `label` (the graph's place name), `n_mentions`, `entry` / `date` / `entry_place` (the entry's own header place — the region the diary is in that day), `role` (Kopfzeile = header place, Beobachtung = locality of an observation, Reise = leg of a journey), `graph_location` (where the graph currently puts it, if anywhere), `anchors` (header places of the entries mentioning this name), `machine` (the text-only verdict and hint).
- Answer: `{ROOT}/places/answers/sheet_N.json`

For each crop, FIRST read the marked line yourself: find the word(s) corresponding to `written` (use `context` to locate it) and transcribe exactly what is written. THEN decide: is it a place name at all (not a bird, a person, a habitat word like Wiese/Moos/Feld)? Which place is meant — today's name and where it is (e.g. "Bregenz, Vorarlberg", "Ortsteil von München", "Bach bei Kaufbeuren")? Use the entry's header place and anchors: a name the diary reaches on a morning walk from München lies near München; typical misreadings turn Ismaning into Ismanning, Pöcking into Pöking, Maisinger See into Mainiger See. Give coordinates only when you know the place well (town, lake, district); otherwise null. If the marked line does not contain the word or is illegible, set `legible` false, confidence 0, and say what you see.

Write the answer as JSON, an array with one object per crop:
`{{"n": <number>, "reading": "the word(s) as written", "legible": true|false, "is_place": true|false|null, "place": "today's name or null", "region": "where it is, short, German, or null", "lat": <float or null>, "lon": <float or null>, "uncertainty_m": <int or null>, "same_as_transcription": true|false, "confidence": 0.0-1.0, "note": "one short sentence, German"}}`

Then reply with only the answer file path(s) and one line per crop `n: reading → place (region)`.
""", encoding='utf-8')
    print('places: crops', len(items), 'sheets', k)

# ---------------------------------------------------------------- class-A taxa
if args.only in ('', 'taxa_a'):
    men = TX['men']; items = []
    for mi in plan['a_sample']:
        m = men[mi]; e = E[m[1]]; f = TX['forms'][m[0]]; x = TX['ent'][f[2]]
        items.append({'box': m[4], 'mi': mi, 'written': f[0], 'context': context(e[7], m[2], m[3], 170) if m[2] >= 0 else e[7][:300], 'entry': e[0], 'date': e[3] or e[2],
                      'current': {'label': x[0], 'sci': x[1], 'gbif': x[2]}, 'class': 'A', 'form_mentions': f[1]})
    k = sheets(items, OUT / 'taxa_a', lambda it: {kk: v for kk, v in it.items() if kk != 'box'})
    src = (S / 'repo/tools/validation_ui/machine_review/prepare_taxa.py').read_text(encoding='utf-8')
    instr = src.split('SHEET_INSTRUCTIONS = """', 1)[1].split('"""', 1)[0] if 'SHEET_INSTRUCTIONS = """' in src else ''
    if not instr:
        # take the sheet instructions block (second triple-quoted block) of prepare_taxa.py
        blocks = src.split('"""')
        instr = next(b for b in blocks if 'You are reading handwritten German ornithological diary lines' in b)
    instr = instr.replace('{root}/sheets', '{root}/taxa_a').replace('{root}', ROOT)
    instr = instr.replace('to check doubtful species names of a knowledge graph', 'to measure how often the ATTESTED species names of a knowledge graph (class A: the written name is a known German name of the linked taxon; never checked at the scan so far) are nevertheless misread or mis-assigned')
    (OUT / 'taxa_a' / 'INSTRUCTIONS.md').write_text(instr, encoding='utf-8')
    print('taxa_a: crops', len(items), 'sheets', k)
