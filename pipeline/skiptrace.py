"""Skip trace owners through Apify (actor one-api/skip-trace) and attach phones and emails to parcels.

  The token is read from the .env file in the project root (APIFY_TOKEN=...), which is gitignored.
  An APIFY_TOKEN environment variable overrides it. To rotate the key, edit .env. Nothing else changes.

  python -m pipeline.skiptrace --dry-run                 show who would be traced and the cost, call nothing
  python -m pipeline.skiptrace --limit 10                trace the first 10, a cheap test
  python -m pipeline.skiptrace                           trace every individual owner of a 3 to 6 unit lot
  python -m pipeline.skiptrace --from-csv outreach.csv   trace exactly the lots in a CSV exported from the app
  python -m pipeline.skiptrace --all                     every private owner in the three zips, LLCs included
  python -m pipeline.skiptrace --refresh                 ignore the cache and trace again

Results are cached per owner in data/contacts.json, so reruns only pay for new owners.
Only phones, emails and match quality are kept. Relatives, age and address history are discarded.
"""
import argparse, csv, json, os, pathlib, re, time
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARCELS = ROOT / "web" / "data" / "parcels.json"
CACHE = ROOT / "data" / "contacts.json"
ACTOR = "one-api~skip-trace"
API = "https://api.apify.com/v2"
COST_PER_RESULT = 0.007   # listed as "from $7 per 1,000 results"; check the actor page for your plan

def token():
    t = os.environ.get("APIFY_TOKEN")
    env = ROOT / ".env"
    if not t and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("APIFY_TOKEN="): t = line.split("=", 1)[1].strip().strip('"\'')
    if not t: raise SystemExit("APIFY_TOKEN is not set. See the top of pipeline/skiptrace.py.")
    return t

def units(a):
    if not a or a < 360: return 0
    return int(min(a, 1440) // 360 + max(a - 1440, 0) // 480)

def owner_key(p):
    return f"{p['owner']}|{p['mzip']}"

def query_for(p):
    """Actor input for one owner: mailing address plus the name to match, or name plus city when there is no street."""
    street = next((l for l in reversed(p["mail"]) if l and not l.lower().startswith("c/o") and l[0].isdigit()), None)
    place = f"{p['mcity']}, {p['mst']} {p['mzip']}".strip()
    if street: return "street_citystatezip", f"{street}; {place} | {p['name']}"
    return "name", f"{p['name']}; {place}"

def select(parcels, a):
    if a.from_csv:
        with open(a.from_csv, newline="", encoding="utf-8-sig") as f:
            ids = {r["opa"].zfill(9) for r in csv.DictReader(f)}
        pool = [p for p in parcels if p["id"] in ids and not p["pub"]]
    else:
        pool = [p for p in parcels if not p["pub"] and a.min_units <= units(p["area"]) <= a.max_units]
    if not a.include_entities: pool = [p for p in pool if not p["ent"]]
    return pool

def run_actor(tok, payload, log=print):
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API}/acts/{ACTOR}/runs", headers=h, json=payload, timeout=60)
    if r.status_code >= 400: raise RuntimeError(f"Apify {r.status_code}: {r.text[:300]}")
    run = r.json()["data"]
    while run["status"] in ("READY", "RUNNING"):
        time.sleep(5)
        run = requests.get(f"{API}/actor-runs/{run['id']}", headers=h, timeout=60).json()["data"]
        log(f"    run {run['id']} {run['status']}")
    if run["status"] != "SUCCEEDED": raise RuntimeError(f"Apify run {run['id']} ended {run['status']}")
    items = requests.get(f"{API}/datasets/{run['defaultDatasetId']}/items", headers=h, params={"format": "json", "clean": "true"}, timeout=120)
    items.raise_for_status()
    return items.json()

def norm(x):
    return re.sub(r"\s+", " ", str(x or "")).strip().lower()

def name_check(owner, found):
    """Our own check that the person found is the owner: any real name token in common."""
    skip = {"jr", "sr", "ii", "iii", "iv", "and", "the", "widow", "est", "estate"}
    a = {t for t in re.findall(r"[a-z]+", owner.lower()) if len(t) >= 3 and t not in skip}
    b = {t for t in re.findall(r"[a-z]+", found.lower()) if len(t) >= 3}
    return "matched" if a & b else "mismatch"

def name_query(p):
    return "name", f"{p['name']}; {p['mcity']}, {p['mst']} {p['mzip']}".strip()

def trace_batch(tok, queries, owners, cache, debug):
    """queries: {owner_key: (field, text)}. Runs one actor call and files results into cache. Returns keys that hit."""
    payload = {"max_results": 1}; full, addr, names = {}, {}, {}
    for k, (field, q) in queries.items():
        payload.setdefault(field, []).append(q)
        full[norm(q)] = k; addr[norm(q.split(" | ")[0])] = k
        if " | " in q: names[norm(q.split(" | ")[1])] = k
    items = run_actor(tok, payload)
    hit = set()
    for it in items:
        ig = norm(it.get("Input Given"))
        k = (full.get(ig) or names.get(norm(it.get("Target Name"))) or addr.get(ig) or addr.get(ig.split(" | ")[0])
             or next((v for q, v in addr.items() if ig and (q.startswith(ig) or ig.startswith(q))), None))
        if not k:
            debug.append({f: it.get(f) for f in ("Search Option", "Input Given", "Target Name", "Name Match")} | {"fields": sorted(it)[:60]})
            continue
        c = slim(it)
        if not (c["phones"] or c["emails"]): continue
        c["actor_match"] = c["match"]; c["match"] = name_check(owners[k], c["found_name"]); c["via"] = queries[k][0]
        cache[k] = c; hit.add(k)
    return hit

def slim(item):
    """Keep only what outreach needs."""
    phones = [{"number": item[f"Phone-{i}"], "type": item.get(f"Phone-{i} Type") or "", "last_seen": item.get(f"Phone-{i} Last Reported") or ""}
              for i in range(1, 6) if item.get(f"Phone-{i}")]
    emails = [item[f"Email-{i}"] for i in range(1, 6) if item.get(f"Email-{i}")]
    return {"found_name": f"{item.get('First Name', '')} {item.get('Last Name', '')}".strip(),
            "match": item.get("Name Match") or "unchecked", "phones": phones, "emails": emails,
            "link": item.get("Person Link") or "", "traced": time.strftime("%Y-%m-%d")}

def merge(parcels, cache):
    n = 0
    for p in parcels:
        c = cache.get(owner_key(p))
        if c and (c.get("phones") or c.get("emails")): p["contacts"] = c; n += 1
        else: p.pop("contacts", None)
    return n

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-csv"); ap.add_argument("--limit", type=int); ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--min-units", type=int, default=3); ap.add_argument("--max-units", type=int, default=6)
    ap.add_argument("--include-entities", action="store_true", help="also look up LLC mailing addresses (weak: returns whoever lives or works there)")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--all", action="store_true", help="every private owner in the target zips, any lot size, LLCs included")
    a = ap.parse_args()
    if a.all: a.min_units, a.max_units, a.include_entities = 0, 10**6, True
    parcels = json.loads(PARCELS.read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo, owners, people = {}, {}, {}
    for p in select(parcels, a):
        k = owner_key(p)
        done = k in cache and (cache[k].get("phones") or cache[k].get("emails"))   # empty results are retried
        if k in todo or (done and not a.refresh): continue
        todo[k] = query_for(p); owners[k] = p["owner"]; people[k] = p
    keys = list(todo)[: a.limit] if a.limit else list(todo)
    print(f"{len(keys)} owners to trace ({len(cache)} already cached). Estimated cost about ${len(keys) * COST_PER_RESULT:.2f}.")
    if a.dry_run:
        for k in keys[:15]: print("   ", todo[k][0], "->", todo[k][1])
        if len(keys) > 15: print(f"    ... and {len(keys) - 15} more")
        return
    tok = token(); debug = []
    for i in range(0, len(keys), a.batch):
        chunk = keys[i:i + a.batch]
        print(f"  batch {i // a.batch + 1}: {len(chunk)} owners")
        try:
            hit = trace_batch(tok, {k: todo[k] for k in chunk}, owners, cache, debug)
            # second pass: owners the address lookup missed are retried by name and city
            miss = [k for k in chunk if k not in hit and todo[k][0] != "name" and not people[k]["ent"]]
            if miss:
                print(f"    {len(hit)} found by address, retrying {len(miss)} by name")
                hit |= trace_batch(tok, {k: name_query(people[k]) for k in miss}, owners, cache, debug)
        except Exception as e:
            print(f"  FAILED: {e}"); break
        for k in chunk:
            if k not in hit: cache[k] = {"phones": [], "emails": [], "match": "no result", "traced": time.strftime("%Y-%m-%d")}
        CACHE.parent.mkdir(exist_ok=True); CACHE.write_text(json.dumps(cache, indent=1))
    if debug:
        (ROOT / "data" / "skiptrace_debug.json").write_text(json.dumps(debug, indent=1))
        print(f"  {len(debug)} results could not be tied to an owner. See data/skiptrace_debug.json (no contact data in it).")
    n = merge(parcels, cache)
    PARCELS.write_text(json.dumps(parcels, separators=(",", ":")))
    got = [cache[k] for k in keys if cache.get(k, {}).get("phones") or cache.get(k, {}).get("emails")]
    print(f"Done. {len(got)}/{len(keys)} owners returned a phone or email ({sum(c['match'] == 'matched' for c in got)} with a matching name). {n} lots now carry contacts in web/data/parcels.json.")

if __name__ == "__main__":
    main()
