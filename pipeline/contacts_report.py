"""Who did the skip trace actually find? Run: python -m pipeline.contacts_report"""
import json, pathlib
P = json.loads((pathlib.Path(__file__).resolve().parent.parent / "web" / "data" / "parcels.json").read_text(encoding="utf-8"))
priv = [p for p in P if not p["pub"]]
def line(label, lots):
    c = [p for p in lots if p.get("contacts")]
    m = [p for p in c if p["contacts"]["match"] == "matched"]
    print(f"{label:22} {len(lots):4} lots | {len(c):4} with contacts | {len(m):4} name matches owner | {len(c) - len(m):4} someone else")
    return c
print()
ind = line("Individual owners", [p for p in priv if not p["ent"]])
ent = line("LLC / company owners", [p for p in priv if p["ent"]])
print("\nLLC and company owners: owner on record -> person the skip trace found at the mailing address")
for p in ent[:40]:
    c = p["contacts"]
    print(f"  {'MATCH   ' if c['match'] == 'matched' else 'UNVERIF.'} {p['owner'][:34]:34} -> {c.get('found_name', '')[:26]:26} | {', '.join(p['mail'])[:34]}")
print("\nIndividual owners where the person found is NOT the owner (do not contact as the owner):")
for p in [p for p in ind if p["contacts"]["match"] != "matched"][:25]:
    print(f"  {p['owner'][:34]:34} -> {p['contacts'].get('found_name', '')[:26]}")
