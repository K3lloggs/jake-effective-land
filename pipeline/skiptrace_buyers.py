"""Skip trace the builders in web/data/builders.json (the Buyers tab) and write their phones and emails back into it.

  python -m pipeline.skiptrace_buyers --dry-run        who would be traced and the cost. Calls nothing
  python -m pipeline.skiptrace_buyers --top 20         cheap live test: the 20 best-scoring builders
  python -m pipeline.skiptrace_buyers                  the top 150 builders by score
  python -m pipeline.skiptrace_buyers --all            every builder that has a named person
  python -m pipeline.skiptrace_buyers --merge-only     re-apply saved results after you replace builders.json

How it looks people up: for each builder, up to --people named people (default 2). Each person is searched at the
builder's registered address first, then by name and city if that finds nothing.
  via "address": the person was found at the registered address. Strong.
  via "name":    found by name and city only. Could be a different person with the same name. Check before calling.
Builders with no named person are skipped: there is nobody to look up.

Results are cached per person in data/buyer_contacts.json (gitignored), so reruns only pay for new people.
Uses the same Apify actor and key (.env) as pipeline/skiptrace.py. Only phones, emails and match quality are kept.
"""
import argparse, json, pathlib, re, time
from pipeline.skiptrace import token, trace_batch, COST_PER_RESULT

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILDERS = ROOT / "web" / "data" / "builders.json"
CACHE = ROOT / "data" / "buyer_contacts.json"
SENIOR = ["president", "owner", "manager", "general partner", "member", "governor", "organizer", "treasurer", "secretary", "vice president", "incorporator"]

def tc(s): return " ".join(w.capitalize() for w in str(s).split())

def split_address(a):
    """'301 Haverford Ave, Narberth, PA, 19072-1922' -> (street, 'Narberth, PA 19072')"""
    parts = [x.strip() for x in str(a or "").split(",") if x.strip()]
    if len(parts) < 3 or not re.match(r"^\d", parts[0]): return None, None
    zip5 = re.sub(r"\D", "", parts[-1])[:5] if re.search(r"\d{5}", parts[-1]) else ""
    state = next((x for x in parts[1:] if re.fullmatch(r"[A-Za-z]{2}", x)), "PA")
    city = parts[-3] if zip5 and len(parts) >= 4 else parts[1]
    return ", ".join(parts[:-3] if zip5 and len(parts) >= 4 else parts[:1]), f"{city}, {state.upper()} {zip5}".strip()

def people_of(b, n):
    seen, out = set(), []
    rank = lambda p: next((i for i, r in enumerate(SENIOR) if r == str(p.get("role", "")).lower()), len(SENIOR))
    for p in sorted(b.get("people") or [], key=rank):
        name = tc(p["name"]); toks = name.split()
        if len(toks) < 2 or name.lower() in seen: continue
        if any((toks[-1] == s.split()[-1] and toks[0][:4] == s.split()[0][:4]) for s in seen): continue   # GIOVANA / GIOVANNA
        seen.add(name.lower()); out.append({"name": name, "role": p.get("role", "")})
        if len(out) >= n: break
    return out

def key(b, person): return f"{b['builder_id']}|{person['name']}"

def merge(builders, cache):
    """Write cached contacts into each builder's phones / emails. Returns how many builders have a contact."""
    n = 0
    for b in builders:
        phones, emails, seen = [], [], set()
        for k, c in cache.items():
            if not k.startswith(b["builder_id"] + "|"): continue
            person = k.split("|", 1)[1]
            for h in c.get("phones", []):
                d = re.sub(r"\D", "", h["number"])[-10:]
                if d in seen: continue
                seen.add(d); phones.append({"number": h["number"], "type": h.get("type", ""), "last_seen": h.get("last_seen", ""),
                                            "person": person, "via": c.get("via", ""), "match": c.get("match", "")})
            for e in c.get("emails", []):
                if e.lower() not in seen: seen.add(e.lower()); emails.append({"email": e, "person": person, "via": c.get("via", "")})
        phones.sort(key=lambda h: (h["match"] != "matched", h["via"] != "address"))
        b["phones"], b["emails"] = phones, emails
        n += bool(phones or emails)
    return n

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=150); ap.add_argument("--all", action="store_true")
    ap.add_argument("--people", type=int, default=2); ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--merge-only", action="store_true"); ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    doc = json.loads(BUILDERS.read_text(encoding="utf-8")); builders = doc["builders"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    def write():
        n = merge(builders, cache)
        BUILDERS.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        return n
    if a.merge_only:
        print(f"{write()} builders now carry a phone or email in web/data/builders.json."); return
    ranked = sorted(builders, key=lambda b: -b["score"])
    pool = ranked if a.all else ranked[: a.top]
    nobody = sum(1 for b in pool if not people_of(b, 1))
    addr_q, name_q, names = {}, {}, {}
    for b in pool:
        street, place = split_address(b.get("registered_address"))
        for person in people_of(b, a.people):
            k = key(b, person)
            done = k in cache and (cache[k].get("phones") or cache[k].get("emails"))
            if done and not a.refresh: continue
            names[k] = person["name"]
            name_q[k] = ("name", f"{person['name']}; {place or 'Philadelphia, PA'}")
            if street: addr_q[k] = ("street_citystatezip", f"{street}; {place} | {person['name']}")
    keys = list(names)
    print(f"{len(pool)} builders in scope, {nobody} skipped (no named person). {len(keys)} people to trace "
          f"({len(addr_q)} have a registered address). Estimated cost up to about ${len(keys) * COST_PER_RESULT:.2f}.")
    if a.dry_run:
        for k in keys[:15]: print("   ", k.split("|")[0][:24].ljust(24), "->", (addr_q.get(k) or name_q[k])[1])
        if len(keys) > 15: print(f"    ... and {len(keys) - 15} more")
        return
    tok = token(); debug = []
    for i in range(0, len(keys), a.batch):
        chunk = keys[i:i + a.batch]
        print(f"  batch {i // a.batch + 1}: {len(chunk)} people")
        try:
            first = {k: addr_q[k] for k in chunk if k in addr_q}
            hit = trace_batch(tok, first, names, cache, debug) if first else set()
            for k in hit:   # someone else at the registered address is not our person
                if cache[k].get("match") != "matched": cache.pop(k); 
            hit = {k for k in hit if k in cache}
            for k in hit: cache[k]["via"] = "address"
            miss = [k for k in chunk if k not in hit]
            if miss:
                print(f"    {len(hit)} found at the registered address, trying {len(miss)} by name")
                got = trace_batch(tok, {k: name_q[k] for k in miss}, names, cache, debug)
                for k in got:
                    if cache[k].get("match") != "matched": cache.pop(k)
                got = {k for k in got if k in cache}
                for k in got: cache[k]["via"] = "name"
                hit |= got
        except Exception as e:
            print(f"  FAILED: {e}"); break
        for k in chunk:
            if k not in hit: cache[k] = {"phones": [], "emails": [], "match": "no result", "traced": time.strftime("%Y-%m-%d")}
        CACHE.parent.mkdir(exist_ok=True); CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    n = write()
    got = [cache[k] for k in keys if cache.get(k, {}).get("phones") or cache.get(k, {}).get("emails")]
    print(f"Done. {len(got)}/{len(keys)} people returned a phone or email "
          f"({sum(c.get('via') == 'address' for c in got)} at the registered address, {sum(c.get('via') == 'name' for c in got)} by name only). "
          f"{n} builders now carry contacts in web/data/builders.json.")

if __name__ == "__main__":
    main()
