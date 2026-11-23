# Jake Effective Land

Finds vacant RM-1 / RM-2 lots in 19104, 19146 and 19125, scores them against Jake's numbers
($20k per by-right unit, $12k with a tax lien, 4 units is the sweet spot), computes a bid ladder,
and drafts the offer letter.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pipeline.probe      # 1. check every source answers and the join columns exist
python -m pipeline.run        # 2. fetch, clean, cross-reference, write web/data/parcels.json
python server.py              # 3. open http://localhost:8000
```

The app works before step 2: `web/data/parcels.json` ships with the 676 lots from Jake's spreadsheet.
The same commands are in VS Code under Terminal > Run Task.

## Layout

| Path | What it is |
|---|---|
| `config.py` | Zips, zoning, land category codes, API hosts |
| `pipeline/fetch.py` | Carto SQL and ArcGIS clients with paging and retry |
| `pipeline/clean.py` | Raw OPA rows to normalized parcel records |
| `pipeline/sources.py` | Registry of cross-reference sources. Add one here and it appears in the app |
| `pipeline/enrich.py` | Joins every source to parcels by OPA number |
| `pipeline/run.py` | The daily job. Also writes a dated snapshot and a change log to `data/snapshots/` |
| `pipeline/probe.py` | Prints each source's real columns |
| `web/score.js` | The scoring and bid logic. Single source of truth, used by the app and by `scripts/score_cli.js` |
| `web/index.html` | The app |
| `scripts/import_xlsx.py` | Streams Jake's 230 MB workbook to CSV (openpyxl chokes on it) |
| `data/Jake_effective_land_clean.xlsx` | The cleaned, scored workbook from the first pass |

## Status: what is tested and what is not

- Tested: cleaning, scoring, the app, CSV export, `--from-csv` rebuild (reproduces the shipped data exactly).
- Confirmed live on 2026-11-11: OPA, violations, unsafe, imm_dang, permits, rtt_summary on Carto.
- **Not confirmed: the two ArcGIS sources (tax delinquencies, vacancy).** Run `python -m pipeline.probe`.
  If one fails, the probe prints the city's ArcGIS services with a similar name so you can fix `sources.py`.
  Also check how fresh the delinquency layer is before trusting it for bids.
  A source that fails is skipped with a log line, it does not stop the run.

## Cross-reference sources

### Wired in (join on OPA number, free, public API)

| Source | Table / layer | What it adds |
|---|---|---|
| Property assessments (OPA) | Carto `opa_properties_public` | The base parcel list |
| Real estate tax delinquencies | ArcGIS `real_estate_tax_delinquencies` (Carto denies access) | Amount owed, years delinquent, payment agreement, sheriff-sale flag. Sets the lien flag, which switches the bid to $12k a unit |
| L&I violations | Carto `violations` | Open and total code violations: pressure on the owner |
| Unsafe / imminently dangerous | Carto `unsafe`, `imm_dang` | City has an open case on a structure |
| Permits | Carto `permits` | A recent zoning or building permit means the owner is developing, not selling |
| Deed and mortgage transfers | Carto `rtt_summary` | Document history: sheriff deeds, mortgages, grantor and grantee names |
| Vacant property indicators | ArcGIS `Vacant_Indicators_Land` | City model agrees the lot is vacant |

### Worth adding next (public, but no clean bulk API)

| Source | Why it matters | Access |
|---|---|---|
| Zoning overlays (ArcGIS `Zoning_Overlays`) | Settles the by-right unit count per lot, the biggest open assumption in the score | ArcGIS, needs a spatial join on lat/lng |
| Sheriff sale listings (Bid4Assets, Philadelphia) | Lots already scheduled for tax or mortgage sale: a deadline for the owner | Web listings, no API |
| Philadelphia civil dockets (First Judicial District) | Tax petitions, foreclosures, estates in litigation, by owner name or address | Web search, has terms of use and bot protection |
| PhilaDox (Records Department) | Full deed, mortgage and lien documents | Web search, paid for images |
| PA Department of State business search | Officers and registered address behind an LLC: the route to a real contact | Web search by entity name |
| Register of Wills | Deceased owners and estates, the classic "can't sell" case | Web search |
| Philadelphia Land Bank / PHDC inventory | Public lots that are actually for sale, with their own application path | Published lists |
| PACER (federal bankruptcy) | Owner in bankruptcy changes who you negotiate with | Paid per page |

Check each site's terms before automating against it. The court and records sites restrict scraping,
and several sit behind bot protection. For those, a link-out from the detail page plus a manual
"I checked this" field is the cheap first version.

## Contacts (skip trace)

`pipeline/skiptrace.py` sends owner name plus mailing address to the Apify actor `one-api/skip-trace` and
attaches phones and emails to each lot. They show in the detail page and in the outreach CSV.

```bash
# the Apify key is already in .env (gitignored). To rotate it, edit that one line.
python -m pipeline.skiptrace --dry-run       # who would be traced, and the cost. Calls nothing
python -m pipeline.skiptrace --limit 10      # cheap live test
python -m pipeline.skiptrace                 # individual owners of 3 to 6 unit lots
python -m pipeline.skiptrace --all           # every private owner in the three zips, LLCs included
python -m pipeline.skiptrace --from-csv jake-land-outreach-2026-11-11.csv   # exactly what you filtered in the app
```

- Results are cached per owner in `data/contacts.json` (gitignored), so reruns only pay for new owners.
- LLC owners are skipped by default: a name search on a company returns nothing useful. Use the PA business search for the people behind it, or `--include-entities` for a weak address-only lookup.
- Each owner is looked up by mailing address first, then by name and city if the address finds nothing. `match: matched` means the person found shares a name with the owner on record; `mismatch` means it is someone else at that address or with a similar search hit. Treat mismatches as unverified. A name-and-city hit can also be a different person with the same name.
- Owners that return nothing are retried on the next run at no cost unless something is found.
- Not tested live: the build sandbox cannot reach Apify. Input and output field names come from the actor's published schema. Start with `--limit 10`.
- Before calling or texting, scrub against the Do Not Call registry and follow TCPA rules; mail has no such restriction.

## Map

The app is map-first: a full-screen map you pan and zoom like Google Maps, with the scored list and filters in a side
panel. Lots are colored by tier and outlined in red when they carry a tax lien. Click a lot on the map or in the list
to fly to it and open its detail page. Zoomed out, lots are dots; from zoom 17 in, they are property outlines.

- Outlines come from `python -m pipeline.outlines` (also run at the end of `python -m pipeline.run`). It writes
  `web/data/outlines.json`. Lots with no outline found show as a dashed circle. Not tested against the live city
  service: the parcel table names (`pwd_parcels`, `dor_parcel`) are from memory, and a failing pass is skipped and logged.
- Basemaps: satellite imagery from Esri, with or without street labels, and a dark street map. No API key needed.
- "Only lots in map view" narrows the list, stats, call desk and email queue to what is on screen.
- Street-level photos: every detail page links to Google Street View. To show the photo inside the detail page,
  add a Google Maps API key (Street View Static API enabled) under Assumptions.

## Buyers (who to sell a lot to)

Each lot's detail panel has a **Buyers** tab listing the five builders most likely to buy it.

- Data: `web/data/builders.json` (ranked builders with score components, LLC names, people, contacts) and
  `web/data/projects.geojson` (their project points, keyed by `builder_id`). Replace both files to refresh.
- Matching is in `web/buyers.js`: `match = score × (0.5 + 0.5 × min(nearby, 5) / 5)`, where `nearby` is the
  builder's projects within 0.75 mi of the lot. Top 5 by match, each with a one-line reason.
- Hover a builder to see its projects on the map (bright = within 0.75 mi, dashed ring = the 0.75 mi radius).
  Tap for score components, track record, nearby projects and who to reach.
- **Call** opens the call desk with a buyer call sheet: script, their median land price next to your target bid,
  and outcome buttons. Outcomes are logged on the lot. The current builders file has no phones or emails, so the
  sheet links out to look the number up; when phones are added to the file, dial buttons appear.
- Works on the static Vercel site as well as with `server.py`.

## Outreach: email queue and call desk

Start the app with `python server.py` (not `http.server`) and open http://localhost:8000.
The server listens on this computer only, keeps shared outreach state in `data/outreach.json`, and sends email.

- **Email queue** (button in the header): lists owners in the current filters who have an email and whose name matched
  the skip trace, one email per owner, best score first. Preview, send a test to yourself, then send. Each email carries
  the opening offer for that lot. The server adds your postal address and an opt-out line, skips anyone already emailed
  or on the do-not-contact list, and stops at `EMAIL_DAILY_CAP`.
- **Call desk**: one owner at a time, best score first. Numbers are ordered most recently seen first; click one to dial
  through whatever handles phone links on your computer (Phone Link, FaceTime, a softphone). The bid ladder, an opening
  script and talking points from the city records are on screen. Log the outcome and it moves to the next owner.
  "Do not contact" and "Bad number" add to the suppression list used by both email and calls.
- Email setup: copy the SMTP lines from `.env.example` into `.env`, fill them in, restart the server.
  Replies arrive in your normal inbox; mark the lot Replied or Not interested by hand for now.
- Check who the skip trace found before contacting: `python -m pipeline.contacts_report`.

## Scoring (see `web/score.js`)

Out of 100: unit fit 30, price reach 30, seller likelihood 30, buildability 10, up to +4 for a next-door lot.
Public owners are capped at 20, tax-exempt orgs lose 10. Ceiling is units × price per unit and is never exceeded.
Open at 70% of the lower of ceiling and OPA value; target that lower figure, or 90% of ceiling when OPA value is higher.
The weights, the 70% and the 90% are defaults to tune, not Jake's numbers.

By-right units use the RM-1 base code (one unit per 360 sf for the first 1,440 sf, one per 480 sf after).
Some overlays cap lower; the app has a conservative setting.

## Next steps

1. Run the probe, fix any column names in `sources.py`.
2. Schedule `python -m pipeline.run` daily (cron, launchd, or a GitHub Action that commits `parcels.json`).
3. Feed the enrichment into the score: violations, sheriff-sale flag and recent permits are fetched but only the lien affects the score today.
4. Outreach state is now shared through `server.py` on one machine. For Jake to use it from his own computer it needs hosting with a login.
5. Zoning overlay join, then contacts.
