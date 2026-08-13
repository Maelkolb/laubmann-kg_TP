#!/usr/bin/env python3
"""Fill per-occurrence recordedBy in the DwC-A from the observer attribution.

SUPERSEDED (2026-08): observer/provenance is now LLM-extracted in the core
pipeline (Observation.record_type/observer); keep for reference only.

Reads out/observers.ttl + person labels from the endpoint, rewrites recordedBy
in occurrence.txt (default stays "Alfred Laubmann"), and refreshes the zip.

Usage: python3 patch_dwca_observers.py [--dwca out/dwca] [--outdir out]
"""
import argparse, csv, json, os, re, sys, urllib.parse, urllib.request, zipfile

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dwca', default='out/dwca')
    ap.add_argument('--outdir', default='out')
    ap.add_argument('--endpoint', default='http://localhost:3030/laubmann/sparql')
    args = ap.parse_args()

    data = urllib.parse.urlencode({'query':
        'SELECT ?p ?l WHERE { ?p a <https://lkg.example.org/ontology#Person> ; '
        '<http://www.w3.org/2000/01/rdf-schema#label> ?l }'}).encode()
    req = urllib.request.Request(args.endpoint, data=data, headers={
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'})
    labels = {}
    for b in json.load(urllib.request.urlopen(req))['results']['bindings']:
        labels.setdefault(b['p']['value'], b['l']['value'])

    observer = {}
    pat = re.compile(r'<https://lkg\.example\.org/data/(obs_\w+)> lkg:observedBy <([^>]+)>')
    for line in open(f'{args.outdir}/observers.ttl', encoding='utf-8'):
        m = pat.match(line)
        if m and 'person_c6b2ff6250e5' not in m.group(2):
            observer[m.group(1)] = labels.get(m.group(2), 'Alfred Laubmann')

    path = os.path.join(args.dwca, 'occurrence.txt')
    rows, patched = [], 0
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f, delimiter='\t')
        fields = r.fieldnames
        for row in r:
            if row['occurrenceID'] in observer:
                row['recordedBy'] = observer[row['occurrenceID']]
                patched += 1
            rows.append(row)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t',
                           lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
        w.writeheader(); w.writerows(rows)
    zpath = os.path.join(args.dwca, 'laubmann_dwca_enriched.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(args.dwca)):
            if not name.endswith('.zip'):
                z.write(os.path.join(args.dwca, name), name)
    print(f'recordedBy patched for {patched} occurrences; zip refreshed', file=sys.stderr)

if __name__ == '__main__':
    main()
