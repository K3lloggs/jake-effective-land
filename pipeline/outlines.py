"""Fetch property outlines (parcel polygons) for the map and write web/data/outlines.json.

  python -m pipeline.outlines

Three passes, each only for lots still missing an outline:
  1. Water Department parcels (pwd_parcels) joined on OPA number
  2. Records Department parcels (dor_parcel) containing the lot's map point
  3. Water Department parcels containing the lot's map point
Lots with no outline still show on the map as a dot.
"""
import json, pathlib
from pipeline import fetch

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARCELS = ROOT / "web" / "data" / "parcels.json"
OUT = ROOT / "web" / "data" / "outlines.json"

def to_latlng(geojson):
    """GeoJSON Polygon / MultiPolygon -> nested [lat, lng] rings in the shape Leaflet's L.polygon takes."""
    g = json.loads(geojson) if isinstance(geojson, str) else geojson
    ring = lambda r: [[round(y, 6), round(x, 6)] for x, y, *_ in r]
    if g["type"] == "Polygon": return [ring(r) for r in g["coordinates"]]
    if g["type"] == "MultiPolygon": return [[ring(r) for r in poly] for poly in g["coordinates"]]
    return None

def _norm(v):
    try: return str(int(float(v))).zfill(9)
    except (TypeError, ValueError): return str(v or "").strip().zfill(9)

def build(recs, log=print):
    out = {}
    ids = [r["id"] for r in recs]
    try:
        n0 = len(out)
        for c in fetch.chunks(ids, 200):
            for row in fetch.carto(f"SELECT brt_id AS k, ST_AsGeoJSON(the_geom, 6) AS g FROM pwd_parcels WHERE {fetch.opa_in('brt_id', c)}"):
                k = _norm(row["k"]); shape = to_latlng(row["g"]) if row.get("g") else None
                if shape and k not in out: out[k] = shape
        log(f"  outlines    {len(out) - n0} by OPA number (pwd_parcels)")
    except Exception as e:
        log(f"  outlines    pwd_parcels by OPA number SKIPPED: {str(e)[:160]}")
    for table in ("dor_parcel", "pwd_parcels"):
        todo = [r for r in recs if r["id"] not in out and r.get("lat") and r.get("lng")]
        if not todo: break
        try:
            best = {}
            for c in fetch.chunks(todo, 150):
                vals = ",".join(f"('{r['id']}',{r['lng']},{r['lat']})" for r in c)
                sql = (f"SELECT v.id AS k, ST_AsGeoJSON(p.the_geom, 6) AS g, ST_Area(p.the_geom) AS a "
                       f"FROM (VALUES {vals}) AS v(id, lng, lat) JOIN {table} p "
                       f"ON ST_Contains(p.the_geom, ST_SetSRID(ST_MakePoint(v.lng, v.lat), 4326))")
                for row in fetch.carto(sql):
                    if row.get("g") and (row["k"] not in best or row["a"] < best[row["k"]][0]): best[row["k"]] = (row["a"], row["g"])
            for k, (_, g) in best.items():
                shape = to_latlng(g)
                if shape: out[k] = shape
            log(f"  outlines    {len(best)} by map point ({table})")
        except Exception as e:
            log(f"  outlines    {table} by map point SKIPPED: {str(e)[:160]}")
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    log(f"  outlines    {len(out)}/{len(recs)} lots have an outline. Wrote {OUT.relative_to(ROOT)}")
    return out

if __name__ == "__main__":
    build(json.loads(PARCELS.read_text(encoding="utf-8")))
