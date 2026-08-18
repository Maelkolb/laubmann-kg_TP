#!/usr/bin/env python3
"""Entity deduplication for the Laubmann KG (additive enrichment).

Reads entities from a SPARQL endpoint and emits:
  out/dedup_taxa_sameas.ttl      -- taxa merged on identical scientificName (auto)
  out/dedup_persons_sameas.ttl   -- persons merged on title-stripped normalized name (auto)
  out/dedup_persons_review.csv   -- initial-vs-fullname / bare-surname candidates (human review)
  out/dedup_taxa_review.csv      -- unresolved-vernacular similarity candidates (human review)
  out/dedup_places_sameas.ttl    -- places merged on normalized label (auto, conservative)

The export itself is never rewritten: canonical node = the variant with the most usage,
variants point to it via owl:sameAs. Load the TTLs next to the export in the triple store.

Usage: python3 dedup_entities.py [--endpoint http://localhost:3030/laubmann/sparql] [--outdir out]
"""
import argparse, csv, difflib, json, re, sys, unicodedata, urllib.parse, urllib.request
from collections import defaultdict

def sparql(endpoint, query):
    data = urllib.parse.urlencode({'query': query}).encode()
    req = urllib.request.Request(endpoint, data=data, headers={
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=120) as r:
        rows = json.load(r)['results']['bindings']
    return [{k: v['value'] for k, v in b.items()} for b in rows]

# academic/professional titles are safe to strip; gendered forms (Frau/Frl./Herr) are
# distinguishing — "Frl. A. Müller" is not the same person as "A. Müller"
TITLE_RE = re.compile(
    r'^(?:(?:Prof|Dr|Dipl|Ing|med|phil|jur|h\.c|Geheimrat|'
    r'Oberst|Major|Pfarrer|Baron|Graf|Freiherr|Forstmeister|Oberförster|Hofrat|Sanitätsrat)\.?\s+)+',
    re.IGNORECASE)
GENDERED_RE = re.compile(r'^(?:Frau|Frl|Fräulein|Herr)\.?\s+', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r'^\W*(\[.*\]|\?+|N\.?N\.?|X|unleserlich|illegible)\W*$', re.IGNORECASE)

def norm_person(name):
    n = unicodedata.normalize('NFC', name.strip())
    n = TITLE_RE.sub('', n)
    n = re.sub(r'\s+', ' ', n).strip(' .,')
    return n

def norm_place(name):
    n = unicodedata.normalize('NFC', name.strip())
    n = re.sub(r'\s+', ' ', n).strip(' .,')
    return n.casefold()

def write_sameas(path, clusters, comment):
    """clusters: list of (canonical_uri, [variant_uris])"""
    n = 0
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {comment}\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n\n')
        for canon, variants in clusters:
            for v in variants:
                f.write(f'<{v}> owl:sameAs <{canon}> .\n')
                n += 1
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--endpoint', default='http://localhost:3030/laubmann/sparql')
    ap.add_argument('--outdir', default='out')
    args = ap.parse_args()
    import os
    os.makedirs(args.outdir, exist_ok=True)
    EP = args.endpoint
    P = 'PREFIX lkg: <https://w3id.org/laubmann-kg/ontology#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>'

    # ---------- taxa: merge on identical scientificName ----------
    taxa = sparql(EP, P + '''
      SELECT ?t ?v ?sci (COUNT(?obs) AS ?n) WHERE {
        ?t a lkg:Taxon ; lkg:vernacularNameDE ?v .
        OPTIONAL { ?t lkg:scientificName ?sci }
        OPTIONAL { ?obs lkg:observedTaxon ?t }
      } GROUP BY ?t ?v ?sci''')
    by_sci = defaultdict(list)
    unresolved = []
    for t in taxa:
        t['n'] = int(t['n'])
        if t.get('sci'):
            by_sci[t['sci'].strip()].append(t)
        else:
            unresolved.append(t)
    tax_clusters = []
    for sci, members in sorted(by_sci.items()):
        if len(members) > 1:
            members.sort(key=lambda m: -m['n'])
            tax_clusters.append((members[0]['t'], [m['t'] for m in members[1:]]))
    n_tax = write_sameas(f'{args.outdir}/dedup_taxa_sameas.ttl', tax_clusters,
                         'taxa with identical lkg:scientificName; canonical = most observations')
    print(f'taxa: {len(tax_clusters)} clusters, {n_tax} sameAs links '
          f'({sum(len(v) for _, v in tax_clusters) + len(tax_clusters)} nodes merged)')

    # unresolved vernaculars: fuzzy-match against resolved ones -> review only
    resolved_vern = {t['v']: t for t in taxa if t.get('sci')}
    with open(f'{args.outdir}/dedup_taxa_review.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['unresolved_uri', 'unresolved_name', 'n_obs', 'candidate_uri',
                    'candidate_name', 'candidate_sci', 'similarity', 'decision'])
        n_rev = 0
        for u in sorted(unresolved, key=lambda x: -x['n']):
            best = difflib.get_close_matches(u['v'], resolved_vern.keys(), n=1, cutoff=0.75)
            if best:
                c = resolved_vern[best[0]]
                sim = difflib.SequenceMatcher(None, u['v'], best[0]).ratio()
                w.writerow([u['t'], u['v'], u['n'], c['t'], c['v'], c['sci'], f'{sim:.2f}', ''])
                n_rev += 1
    print(f'taxa review: {n_rev} unresolved-vernacular candidates -> dedup_taxa_review.csv')

    # ---------- persons ----------
    persons = sparql(EP, P + '''
      SELECT ?p ?l (COUNT(?e) AS ?n) WHERE {
        ?p a lkg:Person ; rdfs:label ?l .
        OPTIONAL { ?e lkg:mentionsPerson ?p }
      } GROUP BY ?p ?l''')
    for p in persons:
        p['n'] = int(p['n'])
        p['norm'] = norm_person(p['l'])
        p['placeholder'] = bool(PLACEHOLDER_RE.match(p['norm']) or PLACEHOLDER_RE.match(p['l']))
        p['gendered'] = bool(GENDERED_RE.match(p['norm']))
    persons = [p for p in persons if not p['placeholder']]

    # high confidence: identical normalized name (title/spacing differences only)
    by_norm = defaultdict(list)
    for p in persons:
        if p['norm']:
            by_norm[p['norm'].casefold()].append(p)
    per_clusters = []
    for _, members in sorted(by_norm.items()):
        if len(members) > 1:
            members.sort(key=lambda m: -m['n'])
            per_clusters.append((members[0]['p'], [m['p'] for m in members[1:]]))
    n_per = write_sameas(f'{args.outdir}/dedup_persons_sameas.ttl', per_clusters,
                         'persons with identical title-stripped name; canonical = most mentions')
    print(f'persons: {len(per_clusters)} clusters, {n_per} sameAs links')

    # review band: initial <-> full first name, and bare surname <-> unique fuller form
    canon_of = {}
    for canon, variants in per_clusters:
        for v in variants:
            canon_of[v] = canon
    reps = {}   # normalized -> representative record (post high-conf merge)
    for p in persons:
        key = p['norm'].casefold()
        if key and (key not in reps or p['n'] > reps[key]['n']):
            reps[key] = p
    by_surname = defaultdict(list)
    for p in reps.values():
        if p['gendered']:
            continue  # too risky for the automatic initial/surname rules
        toks = p['norm'].split()
        if toks:
            by_surname[toks[-1].casefold()].append(p)
    review_rows = []
    for surname, members in by_surname.items():
        if len(members) < 2:
            continue
        fulls = [m for m in members if len(m['norm'].split()) >= 2
                 and not re.match(r'^[A-ZÄÖÜ]\.?$', m['norm'].split()[0])]
        initials = [m for m in members if len(m['norm'].split()) >= 2
                    and re.match(r'^[A-ZÄÖÜ]\.?$', m['norm'].split()[0])]
        bares = [m for m in members if len(m['norm'].split()) == 1]
        for i in initials:
            ini = i['norm'][0]
            matches = [fu for fu in fulls if fu['norm'][0] == ini]
            if len(matches) == 1:
                review_rows.append((i, matches[0], 'initial-vs-full'))
        if bares and len(fulls) + len(initials) == 1:
            other = (fulls + initials)[0]
            for b in bares:
                review_rows.append((b, other, 'bare-surname-unique'))
    with open(f'{args.outdir}/dedup_persons_review.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['variant_uri', 'variant_name', 'variant_mentions', 'candidate_uri',
                    'candidate_name', 'candidate_mentions', 'rule', 'decision'])
        for a, b, rule in sorted(review_rows, key=lambda r: -(r[0]['n'] + r[1]['n'])):
            w.writerow([a['p'], a['l'], a['n'], b['p'], b['l'], b['n'], rule, ''])
    print(f'persons review: {len(review_rows)} candidate pairs -> dedup_persons_review.csv')

    # ---------- places: conservative normalized-label merge ----------
    places = sparql(EP, P + '''
      SELECT ?p ?l (COUNT(?x) AS ?n) WHERE {
        ?p a lkg:Place ; lkg:verbatimLocality ?vl ; rdfs:label ?l .
        OPTIONAL { ?x ?rel ?p . FILTER(?rel IN (lkg:observedAt, lkg:departurePlace,
                                                lkg:arrivalPlace, lkg:viaPlace)) }
      } GROUP BY ?p ?l''')
    by_pl = defaultdict(list)
    for p in places:
        p['n'] = int(p['n'])
        by_pl[norm_place(p['l'])].append(p)
    pl_clusters = []
    for _, members in sorted(by_pl.items()):
        if len(members) > 1:
            members.sort(key=lambda m: -m['n'])
            pl_clusters.append((members[0]['p'], [m['p'] for m in members[1:]]))
    n_pl = write_sameas(f'{args.outdir}/dedup_places_sameas.ttl', pl_clusters,
                        'places with identical case/space-normalized label; canonical = most usage')
    print(f'places: {len(pl_clusters)} clusters, {n_pl} sameAs links')

if __name__ == '__main__':
    main()
