// Buyer matching: which builders are most likely to buy a given lot.
// Used by the app (Buyers tab) and runnable in Node for checks.
//
//   match = builder score × (0.5 + 0.5 × min(nearby, 5) / 5)
//   nearby = the builder's projects within RADIUS_MI of the lot
//
// Half of a builder's score always counts; the other half is earned by having up to 5 projects close by.
const RADIUS_MI = 0.75, NEARBY_CAP = 5, TOP_N = 5;

function milesBetween(lat1, lng1, lat2, lng2) {
  const R = 3958.8, k = Math.PI / 180;
  const dLat = (lat2 - lat1) * k, dLng = (lng2 - lng1) * k;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * k) * Math.cos(lat2 * k) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// GeoJSON FeatureCollection of project points -> { builder_id: [{lat, lng, ...properties}] }
function indexProjects(geojson) {
  const idx = {};
  for (const f of (geojson && geojson.features) || []) {
    if (!f.geometry || f.geometry.type !== 'Point') continue;
    const [lng, lat] = f.geometry.coordinates, id = f.properties.builder_id;
    (idx[id] = idx[id] || []).push(Object.assign({ lat, lng }, f.properties));
  }
  return idx;
}

function buyerReason(b, nearby, subject) {
  const parts = [];
  if (nearby.length) parts.push(nearby.length + ' project' + (nearby.length > 1 ? 's' : '') + ' within ' + RADIUS_MI + ' mi, nearest ' + nearby[0].miles.toFixed(2) + ' mi');
  else parts.push('No projects within ' + RADIUS_MI + ' mi');
  const zips = String(b.focus_zips || '').split(',').filter(Boolean);
  if (subject.zip && zips.includes(subject.zip)) parts.push('buys in ' + subject.zip);
  if (b.acq_12m) parts.push(b.acq_12m + ' buy' + (b.acq_12m > 1 ? 's' : '') + ' in 12 mo');
  else if (b.last_activity) parts.push('last active ' + b.last_activity.slice(0, 7));
  return parts.join(' · ');
}

// subject: {lat, lng, zip}. Returns the top builders, best match first.
function rankBuyers(subject, builders, projectIndex, opts) {
  const radius = (opts && opts.radius) || RADIUS_MI, top = (opts && opts.top) || TOP_N;
  if (!subject || subject.lat == null || subject.lng == null) return [];
  const out = [];
  for (const b of builders) {
    const nearby = [];
    for (const pr of projectIndex[b.builder_id] || []) {
      const mi = milesBetween(subject.lat, subject.lng, pr.lat, pr.lng);
      if (mi <= radius) nearby.push(Object.assign({ miles: mi }, pr));
    }
    nearby.sort((x, y) => x.miles - y.miles);
    const factor = 0.5 + 0.5 * Math.min(nearby.length, NEARBY_CAP) / NEARBY_CAP;
    out.push({ builder: b, nearby, factor, match: Math.round(b.score * factor * 10) / 10, reason: buyerReason(b, nearby, subject) });
  }
  out.sort((x, y) => y.match - x.match || y.nearby.length - x.nearby.length || y.builder.score - x.builder.score);
  return out.slice(0, top);
}

if (typeof module !== 'undefined') module.exports = { RADIUS_MI, NEARBY_CAP, TOP_N, milesBetween, indexProjects, rankBuyers };
