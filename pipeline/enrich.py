"""Cross-reference each parcel against the other public-record sources in sources.py."""
from collections import defaultdict
from pipeline import fetch
from pipeline.sources import CARTO_SOURCES, ARCGIS_SOURCES

def _norm(v):
    try: return str(int(float(v))).zfill(9)
    except (TypeError, ValueError): return str(v or '').strip().zfill(9)

def enrich(recs, log=print):
    ids = [r['id'] for r in recs]; by_id = {r['id']: r for r in recs}
    def apply(name, col, rows, summarize):
        groups = defaultdict(list)
        for row in rows: groups[_norm(row.get(col))].append(row)
        hit = 0
        for pid, g in groups.items():
            if pid not in by_id: continue
            out = {k: v for k, v in summarize(g).items() if v not in (None, '', False)}
            if out.pop('lien', False): by_id[pid]['lien'] = True
            by_id[pid]['records'][name] = out; hit += 1
        log(f"  {name:11} {len(rows):6} rows, {hit} parcels matched")
    for name, table, col, summarize, extra in CARTO_SOURCES:
        try:
            rows = []
            for c in fetch.chunks(ids):
                where = fetch.opa_in(col, c) + (f" AND {extra}" if extra else "")
                rows += fetch.carto(f"SELECT * FROM {table} WHERE {where}")
            apply(name, col, rows, summarize)
        except Exception as e:
            log(f"  {name:11} SKIPPED: {str(e)[:160]}")
    for name, layer, col, summarize in ARCGIS_SOURCES:
        try:
            rows = []
            for c in fetch.chunks(ids, 100):
                try:     # text column, zero-padded or not
                    vals = ",".join(f"'{v}'" for i in c for v in {i, i.lstrip('0')})
                    rows += fetch.arcgis(layer, f"{col} IN ({vals})")
                except RuntimeError:   # numeric column
                    rows += fetch.arcgis(layer, f"{col} IN ({','.join(i.lstrip('0') for i in c)})")
            apply(name, col.lower(), rows, summarize)
        except Exception as e:
            log(f"  {name:11} SKIPPED: {str(e)[:160]}")
    return recs
