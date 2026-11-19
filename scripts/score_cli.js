// Score web/data/parcels.json with the same code the app uses and write a CSV.
//   node scripts/score_cli.js > data/scored.csv
const { DEFAULTS, scoreParcel } = require('../web/score.js');
const P = require('../web/data/parcels.json');
const q = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
const cols = ['score','tier','id','addr','zip','zone','area','fr','units','lien','mv','open','target','walk','owner','name','mail','mcity','mst','mzip','tags'];
console.log(cols.join(','));
P.map(p => ({ ...p, ...scoreParcel(p, null, DEFAULTS) })).sort((a, b) => b.score - a.score)
  .forEach(r => console.log(cols.map(c => q(Array.isArray(r[c]) ? r[c].join(', ') : r[c])).join(',')));
