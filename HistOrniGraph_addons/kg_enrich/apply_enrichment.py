#!/usr/bin/env python3
"""Produce an enriched KG export: original TTL + dedup merges + coordinates.

- Rewrites every merged variant URI to its canonical URI (owl:sameAs from the
  dedup TTLs; RDF set-semantics dedupes the resulting duplicate triples on load).
  Variant vernacular names simply become additional lkg:vernacularNameDE values.
- Appends the high-confidence geo:lat/long triples from georeferencing.
- Appends the owl:sameAs triples themselves as provenance.
- Optionally applies human-adjudicated review CSVs: rows whose `decision` column
  is y/yes/merge/1 are treated as additional sameAs merges.

Usage:
  python3 apply_enrichment.py --ttl <export.ttl> [--outdir out] \
      [--reviews out/dedup_persons_review.csv ...] -o laubmann_enriched.ttl
"""
import argparse, csv, re, sys

def load_sameas(paths):
    canon = {}
    pat = re.compile(r'<([^>]+)>\s+owl:sameAs\s+<([^>]+)>')
    for p in paths:
        for line in open(p, encoding='utf-8'):
            m = pat.search(line)
            if m:
                canon[m.group(1)] = m.group(2)
    # path-compress chains a->b->c
    def resolve(u, seen=None):
        seen = seen or set()
        while u in canon and u not in seen:
            seen.add(u)
            u = canon[u]
        return u
    return {v: resolve(v) for v in canon}

def load_reviews(paths):
    pairs = []
    for p in paths:
        with open(p, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('decision', '').strip().lower() in ('y', 'yes', 'merge', '1'):
                    a = row.get('variant_uri') or row.get('unresolved_uri')
                    b = row.get('candidate_uri')
                    if a and b:
                        pairs.append((a, b))
    return pairs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ttl', required=True)
    ap.add_argument('--outdir', default='out')
    ap.add_argument('--reviews', nargs='*', default=[])
    ap.add_argument('-o', '--output', default='laubmann_enriched.ttl')
    args = ap.parse_args()

    sameas_files = [f'{args.outdir}/dedup_taxa_sameas.ttl',
                    f'{args.outdir}/dedup_persons_sameas.ttl',
                    f'{args.outdir}/dedup_places_sameas.ttl']
    canon = load_sameas(sameas_files)
    for a, b in load_reviews(args.reviews):
        canon[a] = canon.get(b, b)
    print(f'{len(canon)} variant URIs will be rewritten to canonicals', file=sys.stderr)

    # token-safe rewrite: the export uses prefixed names data:<uid>; uids are unique hex
    short = {}
    for v, c in canon.items():
        sv = v.replace('https://w3id.org/laubmann-kg/data/', 'data:')
        sc = c.replace('https://w3id.org/laubmann-kg/data/', 'data:')
        short[sv] = sc
    pattern = re.compile('|'.join(re.escape(k) for k in sorted(short, key=len, reverse=True)))

    n_lines = 0
    with open(args.ttl, encoding='utf-8') as fin, open(args.output, 'w', encoding='utf-8') as fout:
        for line in fin:
            fout.write(pattern.sub(lambda m: short[m.group(0)], line))
            n_lines += 1
        fout.write('\n# ---- enrichment: georeferencing (Nominatim, ODbL) ----\n')
        fout.write('@prefix owl: <http://www.w3.org/2002/07/owl#> .\n')
        geo_pat = re.compile(r'^<([^>]+)>(.*)$')
        try:
            for line in open(f'{args.outdir}/georef_places.ttl', encoding='utf-8'):
                if line.startswith('<'):
                    m = geo_pat.match(line.rstrip())
                    uri = canon.get(m.group(1), m.group(1))
                    fout.write(f'<{uri}>{m.group(2)}\n')
                elif line.startswith('@prefix'):
                    fout.write(line)
        except FileNotFoundError:
            print('no georef_places.ttl yet — skipped', file=sys.stderr)
        fout.write('\n# ---- enrichment: provenance of merges ----\n')
        for v, c in sorted(canon.items()):
            fout.write(f'<{v}> owl:sameAs <{c}> .\n')
    print(f'wrote {args.output} ({n_lines} source lines + enrichment)', file=sys.stderr)

if __name__ == '__main__':
    main()
