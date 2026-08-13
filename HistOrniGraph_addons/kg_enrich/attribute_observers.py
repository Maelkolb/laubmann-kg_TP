#!/usr/bin/env python3
"""Attach an observer to every ObservationEvent (lkg:observedBy, subproperty of
Darwin Core recordedBy).

SUPERSEDED (2026-08): observer/provenance is now LLM-extracted in the core
pipeline (Observation.record_type/observer); keep for reference only.

Rules, most to least certain:
  A. verbatimNotes ends in an attribution tag "(Name)" -> that person
     (auto if the name matches a person mentioned in the same entry, or a
      globally unique surname; otherwise -> review)
  B. verbatimNotes contains "X meldet / berichtet / teilt mit / nach Mitteilung
     von X" -> that person (same confidence logic)
  C. no note-level signal, but the entry mentions 'source'-role persons and its
     raw text has a reporting verb -> review (cannot say WHICH obs are reported)
  D. everything else -> Alfred Laubmann (the diaries are first-person)

Outputs:
  out/observers.ttl         property declaration + auto-applied triples
  out/observer_review.csv   ambiguous cases with candidates + decision column

Usage: python3 attribute_observers.py [--endpoint ...] [--outdir out]
"""
import argparse, csv, json, re, sys, urllib.parse, urllib.request
from collections import defaultdict

LAUBMANN = 'https://lkg.example.org/data/person_c6b2ff6250e5'  # "Alfred Laubmann"

def sparql(endpoint, query):
    data = urllib.parse.urlencode({'query': query}).encode()
    req = urllib.request.Request(endpoint, data=data, headers={
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return [{k: v['value'] for k, v in b.items()}
                for b in json.load(r)['results']['bindings']]

TAG_RE = re.compile(r'\(([A-ZÄÖÜ][^()]{0,28})\)[.\s"“”]*$')
TAG_SKIP = re.compile(r'^(vgl|p\.|\d|Nr|ca|etwa|siehe|II|III|IV|V\.|VI)', re.IGNORECASE)
VERB_RE = re.compile(
    r'([A-ZÄÖÜ][\wäöüß.\-]+(?: [A-ZÄÖÜ][\wäöüß.\-]+){0,2})\s*(?:,[^,]{0,50},)?\s*'
    r'(?:meldet|berichtet|teilte? mit|schreibt|beobachtete)')
VERB2_RE = re.compile(r'(?:nach Mitteilung von|mitgeteilt von|nach Angabe von)\s+'
                      r'([A-ZÄÖÜ][\wäöüß.\- ]{2,35})')
STOPWORDS = {'Vormittags', 'Nachmittags', 'Morgens', 'Abends', 'Heute', 'Gestern'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--endpoint', default='http://localhost:3030/laubmann/sparql')
    ap.add_argument('--outdir', default='out')
    args = ap.parse_args()
    EP = args.endpoint
    P = ('PREFIX lkg: <https://lkg.example.org/ontology#> '
         'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> '
         'PREFIX skos: <http://www.w3.org/2004/02/skos/core#>')

    persons = sparql(EP, P + 'SELECT ?p ?l WHERE { ?p a lkg:Person ; rdfs:label ?l }')
    plabels = defaultdict(set)          # uri -> labels
    for r in persons:
        plabels[r['p']].add(r['l'])
    surname_index = defaultdict(set)    # surname -> uris
    label_index = {}                    # exact label -> uri
    for uri, labels in plabels.items():
        for l in labels:
            label_index[l.strip()] = uri
            toks = re.sub(r'^(Prof|Dr|Frau|Herr|Frl)\.?\s+', '', l).split()
            if toks and len(toks[-1]) >= 3 and toks[-1][0].isupper():
                surname_index[toks[-1]].add(uri)

    ementions = defaultdict(set)
    for r in sparql(EP, P + 'SELECT ?e ?p WHERE { ?e lkg:mentionsPerson ?p }'):
        ementions[r['e']].add(r['p'])
    esources = defaultdict(set)
    for r in sparql(EP, P + '''SELECT ?e ?p WHERE {
        ?e lkg:mentionsPerson ?p . ?p skos:note ?n . FILTER(?n IN ("source", "collector")) }'''):
        esources[r['e']].add(r['p'])
    ereport = set(r['e'] for r in sparql(EP, P + '''SELECT DISTINCT ?e WHERE {
        ?e a lkg:DiaryEntry ; lkg:rawText ?t .
        FILTER(REGEX(?t, "meldet|berichtet|teilt mit|mitgeteilt|nach Mitteilung")) }'''))

    obs = sparql(EP, P + '''SELECT ?o ?e ?v WHERE {
        ?o a lkg:ObservationEvent ; lkg:derivedFromEntry ?e ; lkg:verbatimNotes ?v }''')
    print(f'{len(obs)} observations, {len(plabels)} persons, '
          f'{len(ereport)} entries with reporting verbs', file=sys.stderr)

    def match_name(cand, entry):
        """-> (uri, confidence) or (None, None). Entry-mentioned persons win."""
        cand = cand.strip(' .,')
        if not cand or cand in STOPWORDS:
            return None, None
        local = ementions.get(entry, set())
        if cand in label_index and label_index[cand] in local:
            return label_index[cand], 'high'
        surname = cand.split()[-1]
        hits = surname_index.get(surname, set())
        local_hits = hits & local
        if len(local_hits) == 1:
            return next(iter(local_hits)), 'high'
        if cand in label_index:
            return label_index[cand], 'medium'
        if len(hits) == 1:
            return next(iter(hits)), 'medium'
        return None, None

    auto, review = [], []
    entry_report = defaultdict(list)
    n_default = n_tag = n_verb = 0
    for r in obs:
        o, e, v = r['o'], r['e'], r['v']
        uri = conf = rule = cand = None
        m = TAG_RE.search(v)
        if m and not TAG_SKIP.match(m.group(1)):
            cand = m.group(1); rule = 'paren-tag'
            uri, conf = match_name(cand, e)
        if uri is None:
            m = VERB_RE.search(v) or VERB2_RE.search(v)
            # "an X schreibt" names the recipient, not the observer -> review only
            if m and re.search(r'\ban\s*$', v[:m.start(1)]):
                review.append([e, o, v[:120], m.group(1), '', '', 'verb-recipient', ''])
                m = None
            if m:
                cand2 = m.group(1); rule = rule or 'verb'
                u2, c2 = match_name(cand2, e)
                if u2: uri, conf, cand = u2, c2, cand2
                elif cand is None: cand = cand2
        if uri:
            auto.append((o, uri))
            n_tag += rule == 'paren-tag'; n_verb += rule != 'paren-tag'
            if conf == 'medium':
                review.append([e, o, v[:120], cand, uri, ';'.join(plabels[uri]), rule + ' (auto-applied, medium)', ''])
        elif cand:
            review.append([e, o, v[:120], cand, '', '', rule or 'unmatched-tag', ''])
            auto.append((o, LAUBMANN))   # keep default until reviewed
            n_default += 1
        elif e in ereport and esources.get(e):
            entry_report[e].append(o)    # one review row per ENTRY, not per obs
            auto.append((o, LAUBMANN))
            n_default += 1
        else:
            auto.append((o, LAUBMANN))
            n_default += 1

    with open(f'{args.outdir}/observers.ttl', 'w', encoding='utf-8') as f:
        f.write('# observer attribution: paren-tag / reporting-verb rules, default = diarist\n'
                '@prefix lkg: <https://lkg.example.org/ontology#> .\n'
                '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
                '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
                '@prefix dwciri: <http://rs.tdwg.org/dwc/iri/> .\n\n'
                'lkg:observedBy a owl:ObjectProperty ;\n'
                '    rdfs:subPropertyOf dwciri:recordedBy ;\n'
                '    rdfs:domain lkg:ObservationEvent ; rdfs:range lkg:Person ;\n'
                '    rdfs:label "observed by"@en .\n\n')
        for o, uri in auto:
            f.write(f'<{o}> lkg:observedBy <{uri}> .\n')
    for e, olist in entry_report.items():
        cands = ';'.join(sorted(l for p in esources[e] for l in plabels[p]))
        review.append([e, f'{len(olist)} observations', '', '', '', cands,
                       'entry-level-report', ''])
    with open(f'{args.outdir}/observer_review.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['entry_uri', 'obs_uri_or_count', 'note_excerpt', 'name_in_text',
                    'matched_uri', 'candidate_persons', 'rule', 'decision'])
        w.writerows(review)
    others = len(auto) - n_default
    print(f'observedBy: {others} attributed to third parties '
          f'({n_tag} paren-tag, {n_verb} verb), {n_default} default Laubmann; '
          f'{len(review)} rows -> observer_review.csv', file=sys.stderr)

if __name__ == '__main__':
    main()
