#!/usr/bin/env python3
"""Update the Darwin Core Archive with georeferenced coordinates.

- event.txt: fills empty decimalLatitude/decimalLongitude where the event's
  locality label got a high-confidence geocode (existing coordinates are kept).
- occurrence.txt / eml.xml: recordedBy & abstract "Adolf" -> "Alfred Laubmann".
- Rebuilds laubmann_sample_dwca.zip in the output directory.

Usage: python3 update_dwca.py --dwca <dwca_dir> [--outdir out] [--dest <dir>]
"""
import argparse, csv, os, re, shutil, sys, zipfile

def coords_by_label(outdir):
    """label -> (lat, lon) from the high-confidence georef review rows."""
    m = {}
    with open(f'{outdir}/georef_review.csv', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['confidence'] == 'high':
                m[row['label'].strip()] = (row['lat'], row['lon'])
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dwca', required=True)
    ap.add_argument('--outdir', default='out')
    ap.add_argument('--dest', default=None, help='where to write updated dwca (default: <outdir>/dwca)')
    args = ap.parse_args()
    dest = args.dest or f'{args.outdir}/dwca'
    os.makedirs(dest, exist_ok=True)
    coords = coords_by_label(args.outdir)
    print(f'{len(coords)} georeferenced labels available', file=sys.stderr)

    # event core: fill empty coordinates by locality
    filled, total = 0, 0
    with open(f'{args.dwca}/event.txt', newline='', encoding='utf-8') as fin, \
         open(f'{dest}/event.txt', 'w', newline='', encoding='utf-8') as fout:
        r = csv.DictReader(fin, delimiter='\t')
        w = csv.DictWriter(fout, fieldnames=r.fieldnames, delimiter='\t',
                           lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in r:
            total += 1
            if not row.get('decimalLatitude') and row.get('locality', '').strip() in coords:
                row['decimalLatitude'], row['decimalLongitude'] = coords[row['locality'].strip()]
                filled += 1
            w.writerow(row)
    print(f'event.txt: filled coordinates for {filled} of {total} events', file=sys.stderr)

    # other files: copy with the name fix where applicable
    for name in os.listdir(args.dwca):
        if name in ('event.txt',) or name.endswith('.zip'):
            continue
        src = os.path.join(args.dwca, name)
        dst = os.path.join(dest, name)
        if name.endswith(('.txt', '.xml')):
            txt = open(src, encoding='utf-8').read().replace('Adolf Laubmann', 'Alfred Laubmann')
            open(dst, 'w', encoding='utf-8').write(txt)
        else:
            shutil.copy2(src, dst)

    zpath = os.path.join(dest, 'laubmann_dwca_enriched.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(dest)):
            if not name.endswith('.zip'):
                z.write(os.path.join(dest, name), name)
    print(f'wrote {zpath}', file=sys.stderr)

if __name__ == '__main__':
    main()
