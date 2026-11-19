"""Thin clients for the city's two open-data backends: Carto SQL and ArcGIS FeatureServer."""
import time, requests
import config

S = requests.Session()
S.headers["User-Agent"] = config.USER_AGENT

def carto(sql, retries=3):
    for i in range(retries):
        r = S.post(config.CARTO, data={"q": sql, "format": "json"}, timeout=120)  # POST: long IN (...) lists overflow a GET URL
        if r.status_code == 200:
            return r.json()["rows"]
        if r.status_code in (429, 500, 502, 503, 504) and i < retries - 1:
            time.sleep(2 ** i * 3); continue
        raise RuntimeError(f"Carto {r.status_code}: {r.text[:300]}\nSQL: {sql[:300]}")

def carto_paged(sql, order_by, page=None):
    page = page or config.PAGE
    out, off = [], 0
    while True:
        rows = carto(f"{sql} ORDER BY {order_by} LIMIT {page} OFFSET {off}")
        out += rows
        if len(rows) < page: return out
        off += page

def arcgis(layer, where, fields="*", limit=None):
    """Query an ArcGIS FeatureServer layer, following its pagination. Keys come back lowercased."""
    url = f"{config.ARCGIS}/{layer}/FeatureServer/0/query"
    out, off = [], 0
    while True:
        r = S.post(url, data={"where": where, "outFields": fields, "returnGeometry": "false", "f": "json",
                              "resultOffset": off, "resultRecordCount": limit or 2000}, timeout=120)
        r.raise_for_status(); j = r.json()
        if "error" in j: raise RuntimeError(f"ArcGIS {layer}: {j['error']}")
        feats = [{k.lower(): v for k, v in f["attributes"].items()} for f in j.get("features", [])]
        out += feats
        if limit or not j.get("exceededTransferLimit") or not feats: return out
        off += len(feats)

def arcgis_services(keywords):
    """Names of the city's ArcGIS services containing any keyword. Use it to find a layer's exact name."""
    r = S.get(config.ARCGIS, params={"f": "json"}, timeout=120); r.raise_for_status()
    names = [s["name"] for s in r.json().get("services", [])]
    return [n for n in names if any(k in n.lower() for k in keywords)]

def chunks(seq, n=None):
    n = n or config.CHUNK
    for i in range(0, len(seq), n): yield seq[i:i + n]

def opa_in(col, ids):
    """WHERE clause that matches OPA numbers whether the column is text or integer, padded or not."""
    vals = set()
    for i in ids: vals.add(i); vals.add(i.lstrip("0"))
    return f"CAST({col} AS text) IN ({','.join(repr(v) for v in sorted(vals))})"
