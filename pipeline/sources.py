"""Registry of public-record sources that join to a parcel by OPA number.

Each source: where it lives, the join column, and a summarize() that turns that
parcel's rows into a few flat fields for the app. Add a source here and it shows
up in the detail page under City records and in parcels.json.

The Carto sources were confirmed by a live probe on 2026-11-11. The two ArcGIS
sources were not: run `python -m pipeline.probe` and fix names if it reports a miss.
"""
def _n(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def tax(rows):
    r = max(rows, key=lambda x: _n(x.get("total_due")) or 0)
    return {
        "lien": True,
        "Tax owed": _n(r.get("total_due")),
        "Tax principal": _n(r.get("principal_due")),
        "Years delinquent": r.get("num_years_owed"),
        "Oldest unpaid year": r.get("oldest_year_owed"),
        "Payment agreement": r.get("payment_agreement"),
        "Sheriff sale flag": r.get("sheriff_sale"),
        "Bankruptcy flag": r.get("bankruptcy"),
        "Liens sold": r.get("liens_sold_1990s") or r.get("liens_sold_2015"),
    }

def violations(rows):
    open_ = [r for r in rows if str(r.get("violationstatus", "")).upper() in ("OPEN", "IN VIOLATION")]
    last = max((str(r.get("violationdate") or r.get("casecreateddate") or "")[:10] for r in rows), default="")
    return {"L&I violations": len(rows), "Open violations": len(open_), "Latest violation": last or None}

def unsafe(rows):  return {"Unsafe structure case": True}
def imm_dang(rows): return {"Imminently dangerous case": True}

def permits(rows):
    last = max(rows, key=lambda r: str(r.get("permitissuedate") or ""))
    return {"Permits on file": len(rows), "Latest permit": str(last.get("permitissuedate") or "")[:10] or None,
            "Latest permit type": last.get("permitdescription") or last.get("permittype")}

def transfers(rows):
    rows = sorted(rows, key=lambda r: str(r.get("recording_date") or ""), reverse=True)
    r = rows[0]
    sheriff = [x for x in rows if "SHERIFF" in str(x.get("document_type", "")).upper()]
    mort = [x for x in rows if "MORTGAGE" in str(x.get("document_type", "")).upper() and "SATISF" not in str(x.get("document_type", "")).upper()]
    return {"Recorded documents": len(rows), "Latest document": r.get("document_type"),
            "Latest document date": str(r.get("recording_date") or "")[:10] or None,
            "Latest grantor": r.get("grantors"), "Latest grantee": r.get("grantees"),
            "Mortgages recorded": len(mort), "Sheriff deeds": len(sheriff)}

def vacancy(rows):
    return {"City vacancy model": "Flagged as likely vacant land"}

CARTO_SOURCES = [
    # name,        table,                          join column,        summarizer, extra WHERE
    ("violations", "violations",                    "opa_account_num",  violations, "violationdate >= '2018-01-01'"),
    ("unsafe",     "unsafe",                        "opa_account_num",  unsafe,     None),
    ("imm_dang",   "imm_dang",                      "opa_account_num",  imm_dang,   None),
    ("permits",    "permits",                       "opa_account_num",  permits,    "permitissuedate >= '2020-01-01'"),
    ("transfers",  "rtt_summary",                   "opa_account_num",  transfers,  None),
]
ARCGIS_SOURCES = [
    # name,     layer,                    join column, summarizer
    # Carto denies public access to the delinquency table; the same dataset is published on ArcGIS.
    # If the layer name is wrong, `python -m pipeline.probe` lists every service with "tax" in its name.
    ("tax",     "real_estate_tax_delinquencies", "opa_number", tax),
    ("vacancy", "Vacant_Indicators_Land",        "opa_id",     vacancy),
]
