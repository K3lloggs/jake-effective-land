"""Daily refresh: fetch OPA, clean, cross-reference, write web/data/parcels.json, log what changed.

  python -m pipeline.run                  full refresh from OpenDataPhilly
  python -m pipeline.run --no-enrich      OPA only, skip the cross-references
  python -m pipeline.run --from-csv FILE  rebuild from a local OPA export (CSV with OPA column names)
"""
import argparse, csv, json, datetime as dt, pathlib
import config
from pipeline import fetch
from pipeline.clean import clean, is_target
from pipeline.enrich import enrich

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "parcels.json"
SNAP = ROOT / "data" / "snapshots"

def fetch_opa():
    zips = " OR ".join(f"zip_code LIKE '{z}%'" for z in config.ZIPS)
    cats = ",".join(f"'{c}'" for c in config.LAND_CATEGORY_CODES)
    sql = (f"SELECT *, ST_Y(the_geom) AS lat, ST_X(the_geom) AS lng FROM opa_properties_public "
           f"WHERE ({zips}) AND CAST(category_code AS text) IN ({cats})")
    rows = fetch.carto_paged(sql, "parcel_number")
    for r in rows:
        for k in ("the_geom", "the_geom_webmercator"): r.pop(k, None)
    return rows

def diff(old, new):
    o = {r["id"]: r for r in old}; n = {r["id"]: r for r in new}
    ch = {"added": sorted(set(n) - set(o)), "removed": sorted(set(o) - set(n)), "changed": []}
    for i in set(o) & set(n):
        d = {k: [o[i].get(k), n[i].get(k)] for k in ("owner", "mv", "sp", "sd", "lien", "zone") if o[i].get(k) != n[i].get(k)}
        if d: ch["changed"].append({"id": i, "addr": n[i]["addr"], **d})
    return ch

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-csv"); ap.add_argument("--no-enrich", action="store_true")
    a = ap.parse_args()
    if a.from_csv:
        with open(a.from_csv, newline="") as f: rows = list(csv.DictReader(f))
        if rows and "_hidden" in rows[0]: rows = [r for r in rows if r["_hidden"] == "0"]
    else:
        print("Fetching OPA..."); rows = fetch_opa()
    rows = [r for r in rows if is_target(r)]
    recs = clean(rows)
    print(f"{len(recs)} target parcels")
    if not a.no_enrich and not a.from_csv:
        print("Cross-referencing..."); enrich(recs)
    cache = ROOT / "data" / "contacts.json"
    if cache.exists():   # keep skip-trace results across refreshes
        from pipeline.skiptrace import merge
        merge(recs, json.loads(cache.read_text()))
    old = json.loads(OUT.read_text()) if OUT.exists() else []
    OUT.parent.mkdir(parents=True, exist_ok=True); SNAP.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(recs, separators=(",", ":")))
    stamp = dt.date.today().isoformat()
    (SNAP / f"{stamp}.json").write_text(json.dumps(recs, separators=(",", ":")))
    if not a.no_enrich and not a.from_csv:
        try:
            from pipeline.outlines import build
            print("Fetching property outlines..."); build(recs)
        except Exception as e: print(f"  outlines    SKIPPED: {str(e)[:160]}")
    ch = diff(old, recs)
    (SNAP / f"{stamp}.changes.json").write_text(json.dumps(ch, indent=1))
    print(f"Wrote {OUT.relative_to(ROOT)}. Since last run: {len(ch['added'])} added, {len(ch['removed'])} removed, "
          f"{len(ch['changed'])} changed. Liened: {sum(r['lien'] for r in recs)}")

if __name__ == "__main__":
    main()
