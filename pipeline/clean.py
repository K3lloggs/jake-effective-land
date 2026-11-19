"""Turn raw OPA rows into the compact, normalized parcel records the app reads."""
import re, datetime as dt
from collections import Counter, defaultdict
import config

PUBLIC = re.compile(r'CITY OF PHILA|LAND BANK|REDEVELOP|PHILADELPHIA HOUSING|PHADC|GARDEN|REDEVELOPMENT AUTH|REDEVELOPMENT AUTHORITY|HOUSING AUTH|HOUSING DEVELOPMENT CORP|PHILA HOUSING|COMMONWEALTH OF|SCHOOL DISTRICT|UNITED STATES|SEPTA|DEPT OF|GARDENS TRUST|UNIVERSITY|PHILADELPHIA AUTHORITY|PIDC|AMTRAK')
ENTITY = re.compile(r'\b(LLC|L L C|LL|LP|L P|INC|CORP|CORPORA\w*|CO|COMPANY|TRUST|TR|ASSOC\w*|PARTNERS\w*|HOLDINGS?|PROPERTIES|PROPERTY|INVESTMEN\w*|REALTY|GROUP|CHURCH|MINISTR\w*|FUND\w*|DEVELOP\w*|CONSTRUCTION|ENTERPRISES?|LTD|ESTATE|VENTURES?|CAPITAL|HOMES|ASSN|FOUNDATION|BAPTIST|TEMPLE|MOSQUE|AUTH\w*|BANK|HOUSIN\w*|TABERNACLE|AFFORDABLE|FAMILY|HOLY|CHRIST\w*|GOD|MISSION\w*|CLUB|CENTER|SOCIETY|LEAGUE|INDEPE\w*|SERV\w*|CHURC\w*|COUNCIL|TOWER|COMMUNITY|HUMANITY|ADVE\w*|SEVENTH\S*|BAPTIST|UNITED|TRUSTEES|Y M C A|SQUARE|LOTS|COLLECTIVE|VILLAGE|STREET|ST|AVE)\b')
SMALL = {'Llc':'LLC','Lp':'LP','Inc':'Inc.','Ii':'II','Iii':'III','Jr':'Jr.','Sr':'Sr.','Pa':'PA','Nj':'NJ','Ny':'NY','Ste':'Ste','Po':'PO','Ll':'LLC','Tr':'Trust'}
def tc(s):
    s = re.sub(r'\s+', ' ', s.strip())
    out = []
    for w in s.split(' '):
        t = w.capitalize() if not re.match(r'^\d', w) else w.lower() if re.match(r'^\d+(ST|ND|RD|TH)$', w) else w
        out.append(SMALL.get(t, t))
    return ' '.join(out)
def num(s):
    try:
        x = float(s); return x
    except: return None
def date(s):
    return s[:10] if s else None
def person(raw):
    p = raw.split()
    if len(p) >= 2: p = p[1:] + p[:1]
    return tc(' '.join(p))

def zip5(z):
    """OPA stores zips as numbers, so New Jersey and New England zips lose their leading zero."""
    d = re.sub(r'\D', '', z)
    if len(d) in (4, 8): d = '0' + d
    return d[:5]

def s(v):
    """Carto returns numbers and nulls, the xlsx import returns strings. Normalize to a stripped string."""
    if v is None: return ''
    if isinstance(v, float) and v == int(v): v = int(v)
    return str(v).strip()

def is_target(r):
    return (s(r.get('zip_code'))[:5] in config.ZIPS and s(r.get('zoning')).replace('-', '') in config.ZONING
            and s(r.get('category_code')) in config.LAND_CATEGORY_CODES
            and s(r.get('building_code_description')).upper() not in config.EXCLUDE_DESCRIPTIONS)

def clean(rows, today=None):
    today = today or dt.date.today()
    recs, seen = [], set()
    for raw in rows:
        r = {k: s(v) for k, v in raw.items()}
        pid = r['parcel_number'].zfill(9)
        if pid in seen: continue
        seen.add(pid)
        fr, dp, ar = num(r.get('frontage')), num(r.get('depth')), num(r.get('total_area'))
        notes = []
        if fr == 0: fr = None
        if dp == 0: dp = None
        if not ar or ar <= 0:
            ar = round(fr * dp) if fr and dp else None
            notes.append('Lot size estimated from frontage × depth' if ar else 'Lot size missing in OPA')
        owner = re.sub(r'\s+', ' ', r.get('owner_1', '')); o2 = re.sub(r'\s+', ' ', r.get('owner_2', ''))
        care = r.get('mailing_care_of', '')
        pub = bool(PUBLIC.search(owner)) or bool(PUBLIC.search(care))
        ent = bool(ENTITY.search(owner)) or pub
        sd = date(r.get('sale_date', '')); hold = None
        if sd:
            hold = max(0, round((today - dt.date.fromisoformat(sd)).days / 365.25, 1))
        cs = r.get('mailing_city_state', ''); st = cs.split()[-1] if cs else ''
        a1 = r.get('mailing_address_1', '')
        lines = [x for x in [care and 'c/o ' + tc(care), tc(a1) if a1 and a1 != owner else '',
                             tc(r.get('mailing_address_2', '')), tc(r.get('mailing_street', ''))] if x]
        recs.append(dict(
            id=pid, addr=tc(r.get('location', '')), zip=r['zip_code'][:5], zone=r.get('zoning', ''),
            area=ar, fr=fr, dp=dp, mv=num(r.get('market_value')), sp=num(r.get('sale_price')), sd=sd, hold=hold,
            owner=owner, owner2=o2, name=tc(owner) if ent else person(owner),
            name2=(person(o2) if o2 and not ENTITY.search(o2) else tc(o2)),
            ent=ent, pub=pub, exempt=(num(r.get('exempt_land')) or 0) > 0,
            mail=lines, mcity=tc(' '.join(cs.split()[:-1])), mst=st, mzip=zip5(r.get('mailing_zip', '')),
            oos=(st not in ('PA', '')), ooc=('PHILA' not in cs.upper()),
            cat=tc(r.get('category_code_description', '')), bdesc=tc(r.get('building_code_description', '')),
            shape=r.get('parcel_shape', ''), topo=r.get('topography', ''), view=r.get('view_type', ''),
            tract=r.get('census_tract', ''), ward=r.get('geographic_ward', ''),
            reg=r.get('registry_number', ''), bp=r.get('beginning_point', ''), book=r.get('book_and_page', ''),
            rec=date(r.get('recording_date', '')), tland=num(r.get('taxable_land')), eland=num(r.get('exempt_land')),
            hs=num(r.get('homestead_exemption')), beds=num(r.get('number_of_bedrooms')), baths=num(r.get('number_of_bathrooms')),
            stories=num(r.get('number_stories')), yb=r.get('year_built') if r.get('year_built') not in ('', '0') else None,
            la=num(r.get('total_livable_area')), unit=r.get('unit', ''), pin=r.get('pin', ''),
            assessed=date(r.get('assessment_date', '')), lat=num(r.get('lat')), lng=num(r.get('lng')),
            notes=notes, lien=False, records={},
            _street=r.get('street_name', '') + '|' + r.get('street_direction', '') + '|' + r['zip_code'][:5],
            _hn=int(num(r.get('house_number')) or 0)))
    pc = Counter(x['owner'] for x in recs)
    by = defaultdict(list)
    for x in recs: by[x['_street']].append(x)
    for x in recs:
        x['port'] = pc[x['owner']]
        x['adj'] = [dict(id=y['id'], addr=y['addr'], same=(y['owner'] == x['owner'])) for y in by[x['_street']]
                    if y is not x and y['_hn'] % 2 == x['_hn'] % 2 and 0 < abs(y['_hn'] - x['_hn']) <= 2]
    for x in recs: del x['_street'], x['_hn']
    return recs
