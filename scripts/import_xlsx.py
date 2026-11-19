import sys, re, zipfile, csv, html
"""One-off: stream Jake's 230 MB OPA workbook into a CSV of the target zips.
  python scripts/import_xlsx.py Jake_effective_list.xlsx data/raw/opa_zips.csv
Then: python -m pipeline.run --from-csv data/raw/opa_zips.csv
"""
src, out = sys.argv[1], sys.argv[2]
ZIPS = ('19104','19146','19125')
z = zipfile.ZipFile(src)
# shared strings
ss = []
si_re = re.compile(rb'<si>(.*?)</si>', re.S)
t_re = re.compile(rb'<t[^>]*>(.*?)</t>', re.S)
buf = b''
with z.open('xl/sharedStrings.xml') as f:
    while True:
        chunk = f.read(1<<24)
        if not chunk: break
        buf += chunk
        last = buf.rfind(b'</si>')
        if last < 0: continue
        part, buf = buf[:last+5], buf[last+5:]
        for m in si_re.finditer(part):
            ss.append(html.unescape(b''.join(t_re.findall(m.group(1))).decode('utf8')))
print('strings', len(ss), flush=True)
row_re = re.compile(rb'<row ([^>]*)>(.*?)</row>', re.S)
c_re = re.compile(rb'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
v_re = re.compile(rb'<v>(.*?)</v>', re.S)
def colnum(s):
    n = 0
    for ch in s: n = n*26 + (ch-64)
    return n-1
def parse(rowxml):
    vals = {}
    for m in c_re.finditer(rowxml):
        inner = m.group(3)
        if not inner: continue
        v = v_re.search(inner)
        if not v:
            t = t_re.search(inner)
            if t: vals[colnum(m.group(1))] = html.unescape(t.group(1).decode())
            continue
        val = v.group(1).decode()
        if b't="s"' in m.group(2): val = ss[int(val)]
        else: val = html.unescape(val)
        vals[colnum(m.group(1))] = val
    return vals
hdr = None; n = 0; kept = 0; hidden_kept = 0
w = csv.writer(open(out, 'w', newline=''))
buf = b''
with z.open('xl/worksheets/sheet1.xml') as f:
    while True:
        chunk = f.read(1<<24)
        if not chunk: break
        buf += chunk
        last = buf.rfind(b'</row>')
        if last < 0: continue
        part, buf = buf[:last+6], buf[last+6:]
        for m in row_re.finditer(part):
            n += 1
            vals = parse(m.group(2))
            if hdr is None:
                hdr = [vals.get(i, '') for i in range(max(vals)+1)]
                zi = hdr.index('zip_code')
                w.writerow(hdr + ['_hidden']); continue
            zc = str(vals.get(zi, ''))
            if zc[:5] in ZIPS:
                hid = 1 if b'hidden="1"' in m.group(1) else 0
                kept += 1; hidden_kept += hid
                w.writerow([vals.get(i, '') for i in range(len(hdr))] + [hid])
        if n % 50000 < 3000: print(n, kept, flush=True)
print('done', n, kept, 'hidden', hidden_kept)
