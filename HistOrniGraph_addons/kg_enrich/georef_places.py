#!/usr/bin/env python3
"""Georeference Laubmann-KG places via Nominatim (additive enrichment).

Reads Place nodes (dwc:verbatimLocality; ontology 0.4.0 — habitats are skos:Concepts, not places) that lack
geo:lat, filters out labels that are obviously micro-localities, geocodes the rest
Bavaria-biased at <= 1 req/1.1 s (Nominatim usage policy), and emits:

  out/georef_places.ttl   -- geo:lat/long for HIGH-confidence matches
  out/georef_review.csv   -- every geocoded candidate with confidence + decision column
  out/nominatim_cache.json (resumable)

High confidence = settlement-ish OSM type AND the result name matches the label.
Usage: python3 georef_places.py [--limit N] [--endpoint ...] [--outdir out]
"""
import argparse, csv, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from collections import defaultdict

UA = 'laubmann-kg-georef/1.0 (HistOrniGraph; totomail.tp@gmail.com)'
# Bavaria-ish bias box (left,top,right,bottom)
VIEWBOX = '8.5,50.8,14.2,47.0'
SETTLEMENT_TYPES = {'city', 'town', 'village', 'hamlet', 'suburb', 'municipality',
                    'isolated_dwelling', 'locality', 'administrative', 'neighbourhood'}
NATURE_TYPES = {'peak', 'water', 'lake', 'river', 'stream', 'wood', 'forest', 'wetland',
                'bay', 'moor', 'heath', 'ridge', 'saddle', 'glacier', 'valley'}
PREP_RE = re.compile(r'^(bei|beim|an|am|auf|im|in|hinter|vor|unter|über|zwischen|nahe|'
                     r'unweit|entlang|längs|gegen|ober|unterhalb|oberhalb)\b', re.IGNORECASE)
# generic landscape nouns: an exact OSM name match is meaningless ("See" -> village See/Lupburg)
GENERIC = {'see', 'forst', 'wald', 'berg', 'tal', 'au', 'moos', 'heide', 'insel', 'bach',
           'fluss', 'fluß', 'weiher', 'teich', 'ort', 'dorf', 'stadt', 'garten', 'wiese',
           'feld', 'hof', 'alm', 'alpe', 'halde', 'halbinsel', 'park', 'anlagen', 'friedhof',
           'kirche', 'schloss', 'schloß', 'bahnhof', 'brücke', 'mühle', 'turm', 'ufer',
           'frühling', 'sommer', 'herbst', 'winter', 'haus', 'holz', 'graben', 'kanal'}
MICRO_RE = re.compile(r'(garten|fenster|zimmer|terrasse|balkon|nistkasten|futterplatz|'
                      r'käfig|voliere|areal|vkl\.|k\d|w/\d)', re.IGNORECASE)

def sparql(endpoint, query):
    data = urllib.parse.urlencode({'query': query}).encode()
    req = urllib.request.Request(endpoint, data=data, headers={
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=120) as r:
        rows = json.load(r)['results']['bindings']
    return [{k: v['value'] for k, v in b.items()} for b in rows]

def norm(s):
    return unicodedata.normalize('NFC', s).casefold().replace('ß', 'ss').strip()

def geocodable(label):
    if len(label) > 40 or len(label.split()) > 4:
        return False
    if PREP_RE.match(label) or MICRO_RE.search(label):
        return False
    if re.search(r'[\d()\[\]/]', label):
        return False
    if not label[:1].isupper():
        return False
    return True

def geocode(label, cache):
    if label in cache:
        return cache[label]
    url = ('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({
        'q': label, 'format': 'jsonv2', 'countrycodes': 'de', 'limit': 3,
        'viewbox': VIEWBOX, 'accept-language': 'de'}))
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
    except Exception as e:
        print(f'  ! {label}: {e}', file=sys.stderr)
        res = None
    time.sleep(1.1)
    if res is not None:
        cache[label] = res
    return res or []

def in_bavaria(lat, lon):
    return 47.0 <= lat <= 50.8 and 8.5 <= lon <= 14.2

def confidence(label, hit):
    lat, lon = float(hit['lat']), float(hit['lon'])
    nl, nh = norm(label), norm(hit.get('name', ''))
    name_ok = nl == nh or nh.startswith(nl + ' ')   # "Hagnau" matches "Hagnau am Bodensee"
    t = hit.get('type', '')
    if nl in GENERIC:
        return 'low' if in_bavaria(lat, lon) else 'reject'
    if name_ok and in_bavaria(lat, lon) and (t in SETTLEMENT_TYPES or t in NATURE_TYPES):
        return 'high'
    if name_ok and (t in SETTLEMENT_TYPES or t in NATURE_TYPES):
        return 'medium'   # exact name but outside the Bavaria box
    if in_bavaria(lat, lon):
        return 'low'
    return 'reject'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--endpoint', default='http://localhost:3030/laubmann/sparql')
    ap.add_argument('--outdir', default='out')
    ap.add_argument('--limit', type=int, default=0, help='max labels to geocode this run (0 = all)')
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    cache_path = f'{args.outdir}/nominatim_cache.json'
    cache = json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}

    P = ('PREFIX lkg: <https://w3id.org/laubmann-kg/ontology#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> '
         'PREFIX dwc: <http://rs.tdwg.org/dwc/terms/>')
    places = sparql(args.endpoint, P + '''
      PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
      SELECT ?p ?l (COUNT(?x) AS ?n) WHERE {
        ?p a lkg:Place ; dwc:verbatimLocality ?vl ; rdfs:label ?l .
        FILTER NOT EXISTS { ?p geo:lat ?lat }
        OPTIONAL { ?x ?rel ?p . FILTER(?rel IN (lkg:observedAt, lkg:departurePlace,
                                                lkg:arrivalPlace, lkg:viaPlace)) }
      } GROUP BY ?p ?l''')
    for p in places:
        p['n'] = int(p['n'])
    # one geocode per distinct label, applied to every node carrying it
    by_label = defaultdict(list)
    for p in places:
        by_label[p['l'].strip()].append(p)
    cands = sorted(((l, ps) for l, ps in by_label.items() if geocodable(l)),
                   key=lambda kv: -sum(p['n'] for p in kv[1]))
    skipped = len(by_label) - len(cands)
    todo = cands[:args.limit] if args.limit else cands
    print(f'{len(by_label)} distinct labels · {len(cands)} geocodable · {skipped} skipped as '
          f'micro-localities · geocoding {len(todo)} (cache: {len(cache)})')

    ttl_rows, review_rows, nomatch = [], [], 0
    for i, (label, nodes) in enumerate(todo):
        hits = geocode(label, cache)
        if i and i % 25 == 0:
            json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f'  …{i}/{len(todo)} ({len(ttl_rows)} high-confidence so far)')
        if not hits:
            nomatch += 1
            continue
        best, conf = None, 'reject'
        for h in hits:
            c = confidence(label, h)
            order = ['reject', 'low', 'medium', 'high']
            if order.index(c) > order.index(conf):
                best, conf = h, c
        if best is None:
            best = hits[0]
        usage = sum(p['n'] for p in nodes)
        review_rows.append([label, usage, conf, best.get('type', ''), best['lat'], best['lon'],
                            best.get('display_name', ''), ';'.join(p['p'] for p in nodes), ''])
        if conf == 'high':
            for p in nodes:
                ttl_rows.append((p['p'], best['lat'], best['lon']))
    json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)

    with open(f'{args.outdir}/georef_places.ttl', 'w', encoding='utf-8') as f:
        f.write('# Nominatim high-confidence matches (settlement/nature type, exact name, Bavaria box)\n'
                '# Data (c) OpenStreetMap contributors, ODbL 1.0\n'
                '@prefix geo: <http://www.w3.org/2003/01/geo/wgs84_pos#> .\n'
                '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n')
        for uri, lat, lon in ttl_rows:
            f.write(f'<{uri}> geo:lat "{lat}"^^xsd:decimal ; geo:long "{lon}"^^xsd:decimal .\n')
    with open(f'{args.outdir}/georef_review.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['label', 'usage', 'confidence', 'osm_type', 'lat', 'lon',
                    'display_name', 'place_uris', 'decision'])
        w.writerows(sorted(review_rows, key=lambda r: -r[1]))
    print(f'done: {len(ttl_rows)} place nodes got high-confidence coordinates '
          f'({len([r for r in review_rows if r[2] == "high"])} labels); '
          f'{len(review_rows)} rows in georef_review.csv; {nomatch} labels without any match')

if __name__ == '__main__':
    main()
