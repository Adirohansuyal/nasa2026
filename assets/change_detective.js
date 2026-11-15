(() => {
  'use strict';
  const D = window.ANOMALY_DATA;
  if (!D) return;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const HAZARD_KEYS = Object.keys(D.hazards);
  const SERIES = [
    ['LST_z', 'LST', '#df8d7c'], ['NDVI_z', 'NDVI', '#8fbf94'],
    ['SMAP_AM_z', 'SMAP AM', '#72b8c2'], ['SMAP_PM_z', 'SMAP PM', '#7794c4'],
    ['GPM_z', 'GPM rain', '#c69ed2']
  ];
  const EXPECTED = {
    FLOOD: [['GPM_z', 1], ['SMAP_AM_z', 1], ['SMAP_PM_z', 1]],
    DROUGHT: [['GPM_z', -1], ['SMAP_AM_z', -1], ['SMAP_PM_z', -1], ['LST_z', 1]],
    HEAT_WAVE: [['LST_z', 1]],
    VEGETATION_LOSS: [['NDVI_z', -1], ['LST_z', 1], ['SMAP_AM_z', -1]],
    COLD_STRESS: [['LST_z', -1]],
    COMPOUND: []
  };
  const state = { ready: false };

  function monthText(value, style = 'short') {
    const date = new Date(`${String(value).slice(0, 7)}-01T00:00:00Z`);
    return Number.isNaN(+date) ? String(value) : date.toLocaleDateString('en-US', {
      month: style === 'long' ? 'long' : 'short', year: 'numeric', timeZone: 'UTC'
    });
  }
  function hazardRows(key) { return D.districtHazards?.[key] || []; }
  function districtRecord(key, name) { return hazardRows(key).find(row => row.district_name === name); }
  function activeDistricts(key, month) {
    return hazardRows(key).filter(row => (row.triggered_months || []).some(value => String(value).slice(0, 7) === month.slice(0, 7)));
  }
  function monthRow(month) {
    const target = month.slice(0, 7);
    return D.monthlyAlerts.find(row => String(row.month).slice(0, 7) === target) || {};
  }
  function monthSignalCount(row) {
    return SERIES.reduce((total, [key]) => total + (Number.isFinite(Number(row[key])) && Math.abs(Number(row[key])) >= 1.5 ? 1 : 0), 0);
  }
  function sensorSupport(key, row) {
    if (key === 'COMPOUND') return { count: monthSignalCount(row), total: 5, text: `${monthSignalCount(row)} sensors at or beyond ±1.5σ (3+ is a compound pattern)` };
    const rules = EXPECTED[key] || [];
    const count = rules.filter(([field, sign]) => Number.isFinite(Number(row[field])) && Number(row[field]) * sign >= 1.5).length;
    return { count, total: rules.length, text: `${count} of ${rules.length} expected signal directions at or beyond 1.5σ` };
  }

  function buildControls() {
    const hazard = $('detective-hazard'), district = $('detective-district'), month = $('detective-month');
    if (!hazard || !district || !month) return false;
    hazard.innerHTML = HAZARD_KEYS.map(key => `<option value="${esc(key)}">${esc(D.hazards[key].emoji)} ${esc(D.hazards[key].label)}</option>`).join('');
    const names = (D.districtGeo?.features || []).map(feature => feature.properties?.district_name).filter(Boolean).sort();
    district.innerHTML = names.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
    month.innerHTML = D.monthlyAlerts.map(row => `<option value="${esc(String(row.month).slice(0, 10))}">${esc(monthText(row.month, 'long'))}</option>`).join('');
    hazard.value = HAZARD_KEYS.includes('FLOOD') ? 'FLOOD' : HAZARD_KEYS[0];
    district.value = names.includes('Chamoli') ? 'Chamoli' : names[0];
    chooseLatestDistrictSignal();
    hazard.addEventListener('change', () => { chooseLatestDistrictSignal(); render(); });
    district.addEventListener('change', render);
    month.addEventListener('change', render);
    state.ready = true;
    return true;
  }
  function chooseLatestDistrictSignal() {
    const rec = districtRecord($('detective-hazard').value, $('detective-district').value);
    if (rec?.triggered_months?.length) $('detective-month').value = `${rec.triggered_months[rec.triggered_months.length - 1].slice(0, 7)}-01`;
  }

  function renderMetrics(key, district, month, districtRec, regional, spread, support) {
    const triggerMonths = districtRec?.triggered_months || [];
    const active = triggerMonths.some(value => String(value).slice(0, 7) === month.slice(0, 7));
    $('detective-metrics').innerHTML = [
      [`District detections`, `${triggerMonths.length} / 126`, `${esc(district)} · ${esc(D.hazards[key].label)}`],
      [`Districts this month`, `${spread.length} / ${D.districtCount}`, `${esc(monthText(month))} with a reported district signal`],
      [`Sensor direction check`, `${support.count} / ${support.total}`, `${esc(support.text)}`]
    ].map(([label, value, note]) => `<div class="detective-metric"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join('');
    const regionalHazards = (regional.hazards || []).map(item => D.hazards[item.hazard_type]?.label || item.hazard_type);
    const eventText = active
      ? `The selected district is listed for this signal in ${monthText(month, 'long')}.`
      : `No district-level ${D.hazards[key].label.toLowerCase()} signal is listed for ${monthText(month, 'long')}.`;
    const contextText = regionalHazards.length ? `The regional monthly analysis also listed: ${regionalHazards.join(', ')}.` : 'The regional monthly alert did not list a named hazard for this month.';
    $('detective-summary').innerHTML = `<strong>${esc(eventText)}</strong> ${esc(contextText)} The district hazard record covers ${triggerMonths.length} months in the study period${districtRec?.worst_month ? `; its largest reported monthly intensity was in ${monthText(districtRec.worst_month, 'long')}` : ''}.`;
  }

  function renderEvidence(key, district, month, row, districtRec) {
    const support = sensorSupport(key, row);
    $('detective-agreement').textContent = support.text;
    $('detective-evidence-title').textContent = `${district} · ${monthText(month, 'long')}`;
    $('detective-sensors').innerHTML = SERIES.map(([field, label, color]) => {
      const value = Number(row[field]);
      const shown = Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}σ` : 'No data';
      const direction = Number.isFinite(value) ? (value > 0 ? 'Above usual' : value < 0 ? 'Below usual' : 'Near baseline') : 'Unavailable';
      const rule = (EXPECTED[key] || []).find(item => item[0] === field);
      const aligned = Number.isFinite(value) && rule && value * rule[1] >= 1.5;
      const css = aligned ? ' support' : '';
      return `<div class="detective-sensor${css}"><span>${esc(label)}</span><strong style="color:${Number.isFinite(value) ? color : 'var(--t3)'}">${esc(shown)}</strong><small>${esc(direction)}</small></div>`;
    }).join('');
    const activeMonths = districtRec?.triggered_months || [];
    const selectedMonthActive = activeMonths.some(value => String(value).slice(0, 7) === month.slice(0, 7));
    const mean = Number(districtRec?.mean_intensity_z);
    const worst = districtRec?.worst_month ? monthText(districtRec.worst_month, 'long') : 'not available';
    $('detective-district-evidence').innerHTML = selectedMonthActive
      ? `<strong>District record:</strong> this month appears in the district's detected-month list. Across all listed months, mean signal intensity was ${Number.isFinite(mean) ? `${mean > 0 ? '+' : ''}${mean.toFixed(2)}σ` : 'not available'}; strongest listed month: ${esc(worst)}. Intensity is a summary of the district record, not a measurement for this selected month.`
      : `<strong>District record:</strong> this month does not appear in ${esc(district)}'s detected-month list for this signal. The district's other listed months: ${activeMonths.length ? activeMonths.map(monthText).join(', ') : 'none'}.`;
    return support;
  }

  function renderTimeline(key, month, districtRec) {
    const canvas = $('detective-timeline');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 80) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.round(rect.width * dpr), height = Math.round(280 * dpr);
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, width, height);
    const pad = { left: 38 * dpr, right: 12 * dpr, top: 15 * dpr, bottom: 31 * dpr };
    const iw = width - pad.left - pad.right, ih = height - pad.top - pad.bottom;
    const rows = D.monthlyAlerts, x = index => pad.left + index / Math.max(1, rows.length - 1) * iw;
    const y = value => pad.top + (3 - Math.max(-3, Math.min(3, value))) / 6 * ih;
    ctx.font = `${10 * dpr}px Urbanist, sans-serif`;
    [-3, -1.5, 0, 1.5, 3].forEach(value => {
      ctx.strokeStyle = value === 0 ? 'rgba(210,220,225,.3)' : 'rgba(210,220,225,.1)';
      ctx.beginPath(); ctx.moveTo(pad.left, y(value)); ctx.lineTo(width - pad.right, y(value)); ctx.stroke();
      ctx.fillStyle = '#81909B'; ctx.textAlign = 'right'; ctx.fillText(`${value}σ`, pad.left - 7 * dpr, y(value) + 3 * dpr);
    });
    const activeMonths = new Set((districtRec?.triggered_months || []).map(value => String(value).slice(0, 7)));
    rows.forEach((record, index) => {
      if (activeMonths.has(String(record.month).slice(0, 7))) {
        ctx.fillStyle = 'rgba(198,161,109,.22)';
        ctx.fillRect(x(index) - Math.max(1, iw / rows.length / 2), pad.top, Math.max(2, iw / rows.length), ih);
      }
    });
    SERIES.forEach(([field, , color]) => {
      ctx.strokeStyle = color; ctx.lineWidth = 1.8 * dpr; ctx.beginPath();
      let started = false;
      rows.forEach((record, index) => {
        const value = Number(record[field]);
        if (!Number.isFinite(value)) { started = false; return; }
        if (!started) { ctx.moveTo(x(index), y(value)); started = true; } else ctx.lineTo(x(index), y(value));
      });
      ctx.stroke();
    });
    const monthIndex = rows.findIndex(record => String(record.month).slice(0, 7) === month.slice(0, 7));
    if (monthIndex >= 0) {
      ctx.strokeStyle = '#f0cf91'; ctx.lineWidth = 1.4 * dpr; ctx.setLineDash([4 * dpr, 4 * dpr]);
      ctx.beginPath(); ctx.moveTo(x(monthIndex), pad.top); ctx.lineTo(x(monthIndex), pad.top + ih); ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.fillStyle = '#81909B'; ctx.textAlign = 'center';
    [0, 24, 48, 72, 96, 120, rows.length - 1].filter((v, i, a) => v < rows.length && a.indexOf(v) === i).forEach(index => {
      const year = String(rows[index].month).slice(0, 4); ctx.fillText(year, x(index), height - 8 * dpr);
    });
    $('detective-legend').innerHTML = SERIES.map(([, label, color]) => `<span><i style="background:${color}"></i>${esc(label)}</span>`).join('') + '<span><i style="background:#c6a16d"></i>District signal month</span>';
  }

  function renderMap(key, month, selectedDistrict, spread) {
    const svg = $('detective-map');
    const features = D.districtGeo?.features || [];
    if (!svg || !features.length) return;
    const lon = [], lat = [];
    features.forEach(feature => {
      const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
      polygons.forEach(poly => poly.forEach(ring => ring.forEach(point => { lon.push(point[0]); lat.push(point[1]); })));
    });
    const bounds = { minX: Math.min(...lon), maxX: Math.max(...lon), minY: Math.min(...lat), maxY: Math.max(...lat) };
    const pad = 24, sx = 520 - pad * 2, sy = 410 - pad * 2;
    const project = point => [pad + (point[0] - bounds.minX) / (bounds.maxX - bounds.minX) * sx, 430 - pad - (point[1] - bounds.minY) / (bounds.maxY - bounds.minY) * sy];
    const active = new Set(spread.map(record => record.district_name));
    const paths = features.map(feature => {
      const name = feature.properties.district_name;
      const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
      const d = polygons.map(poly => poly.map(ring => ring.map((point, index) => {
        const [x, y] = project(point); return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ') + ' Z').join(' ')).join(' ');
      const isActive = active.has(name), selected = name === selectedDistrict;
      const fill = isActive ? '#b77455' : '#273744';
      const center = project([(bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2]);
      const districtBounds = [];
      polygons.forEach(poly => poly.forEach(ring => ring.forEach(point => districtBounds.push(point))));
      const centroid = project([districtBounds.reduce((a, p) => a + p[0], 0) / districtBounds.length, districtBounds.reduce((a, p) => a + p[1], 0) / districtBounds.length]);
      return `<g data-district="${esc(name)}"><title>${esc(name)}${isActive ? ' · signal listed this month' : ''}</title><path d="${d}" fill="${fill}" stroke="${selected ? '#d9c28e' : '#71818d'}" stroke-width="${selected ? 2.6 : 1.1}"/><text x="${centroid[0].toFixed(1)}" y="${centroid[1].toFixed(1)}">${esc(name.length > 13 ? name.replace(' Garhwal', '') : name)}</text></g>`;
    }).join('');
    svg.innerHTML = paths;
    svg.querySelectorAll('g[data-district]').forEach(group => group.addEventListener('click', () => {
      $('detective-district').value = group.dataset.district; render();
    }));
    $('detective-map-month').textContent = monthText(month, 'long');
  }

  function render() {
    if (!state.ready) return;
    const key = $('detective-hazard').value, district = $('detective-district').value;
    const month = $('detective-month').value, row = monthRow(month), record = districtRecord(key, district);
    const spread = activeDistricts(key, month).sort((a, b) => b.months_triggered - a.months_triggered || a.district_name.localeCompare(b.district_name));
    const support = sensorSupport(key, row);
    renderMetrics(key, district, month, record, row, spread, support);
    renderTimeline(key, month, record);
    renderMap(key, month, district, spread);
    renderEvidence(key, district, month, row, record);
    $('detective-month-label').textContent = monthText(month, 'long');
    $('detective-district-rank').innerHTML = hazardRows(key).slice().sort((a, b) => b.months_triggered - a.months_triggered || a.district_name.localeCompare(b.district_name)).map((item, index) => {
      const active = (item.triggered_months || []).some(value => String(value).slice(0, 7) === month.slice(0, 7));
      return `<div class="detective-rank-row${item.district_name === district ? ' selected' : ''}" data-district="${esc(item.district_name)}"><span>${String(index + 1).padStart(2, '0')}</span><span>${esc(item.district_name)}${active ? ' · active this month' : ''}</span><b>${item.months_triggered} mo</b></div>`;
    }).join('');
    $('detective-district-rank').querySelectorAll('[data-district]').forEach(item => item.addEventListener('click', () => {
      $('detective-district').value = item.dataset.district; render();
    }));
  }

  window.renderEarthChangeDetective = function () {
    if (!state.ready && !buildControls()) return;
    render();
  };
  document.addEventListener('DOMContentLoaded', () => window.renderEarthChangeDetective());
  window.addEventListener('resize', () => {
    if ($('page-detective')?.classList.contains('active')) renderTimeline($('detective-hazard').value, $('detective-month').value, districtRecord($('detective-hazard').value, $('detective-district').value));
  });
})();
