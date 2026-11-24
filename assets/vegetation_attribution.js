(() => {
  'use strict';

  const dataUrl = 'assets/vegetation_uttarakhand_2015_2025_corrected.csv';
  const names = {
    tree_cover: 'Trees (mapped)',
    grass: 'Grass',
    shrub_scrub: 'Shrub / scrub'
  };
  const colors = {tree_cover: '#71b68a', grass: '#d8c56e', shrub_scrub: '#b78a68'};
  const seasonNames = {
    pre_monsoon: 'Pre-monsoon',
    monsoon: 'Monsoon',
    post_monsoon: 'Post-monsoon'
  };
  let rows = [];

  function parseCsv(text) {
    const records = [];
    let record = [], field = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (quoted) {
        if (char === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (char === '"') quoted = false;
        else field += char;
      } else if (char === '"') quoted = true;
      else if (char === ',') { record.push(field); field = ''; }
      else if (char === '\n' || char === '\r') {
        if (char === '\r' && text[i + 1] === '\n') i++;
        record.push(field); field = '';
        if (record.some(value => value !== '')) records.push(record);
        record = [];
      } else field += char;
    }
    if (field || record.length) { record.push(field); records.push(record); }
    const headers = (records.shift() || []).map((value, index) => index === 0 ? value.replace(/^\uFEFF/, '') : value);
    return records.map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] || ''])));
  }

  function esc(value) {
    return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function render() {
    const season = document.getElementById('veg-attribution-season')?.value || 'post_monsoon';
    const selected = document.getElementById('td-district')?.value || 'all';
    const chosen = rows.filter(row => row.season === season && (selected === 'all' || row.GAUL2_NAME === selected));
    const byClass = Object.fromEntries(Object.keys(names).map(key => [key, {area: 0, greening: 0}]));
    chosen.forEach(row => {
      if (!byClass[row.cover_class]) return;
      byClass[row.cover_class].area += number(row.class_area_ha);
      byClass[row.cover_class].greening += number(row.positive_ndvi_trend_area_ha);
    });

    const totalGreening = Object.values(byClass).reduce((sum, value) => sum + value.greening, 0);
    const areaLabel = selected === 'all' ? 'Uttarakhand' : selected;
    const areaNode = document.getElementById('veg-attribution-area-label');
    const totalNode = document.getElementById('veg-attribution-total-ha');
    const contextNode = document.getElementById('veg-attribution-context');
    if (!areaNode || !totalNode || !contextNode) return;
    areaNode.textContent = `${areaLabel} · ${seasonNames[season] || season}`;
    totalNode.textContent = totalGreening ? `${Math.round(totalGreening).toLocaleString('en-IN')} ha` : 'No data';
    const districtCount = Math.round(chosen.length / 3);
    const qualityNote = chosen.find(row => row.data_quality_note)?.data_quality_note;
    contextNode.textContent = `${districtCount} district${districtCount === 1 ? '' : 's'} · exported 100 m estimates`;
    const qualityNode = document.getElementById('veg-attribution-quality');
    if (qualityNode) qualityNode.textContent = qualityNote ? `Source CSV quality note · ${seasonNames[season] || season}: ${qualityNote}` : '';

    const bars = document.getElementById('veg-attribution-bars');
    const cards = document.getElementById('veg-attribution-cards');
    const order = ['tree_cover', 'grass', 'shrub_scrub'];
    bars.innerHTML = order.map(key => {
      const share = totalGreening ? byClass[key].greening / totalGreening * 100 : 0;
      return `<div class="veg-attribution-bar-row"><span>${esc(names[key])}</span><div class="veg-attribution-bar-track"><i style="width:${share.toFixed(2)}%;background:${colors[key]}"></i></div><strong>${share.toFixed(1)}%</strong></div>`;
    }).join('');
    cards.innerHTML = order.map(key => {
      const item = byClass[key];
      const mixShare = totalGreening ? item.greening / totalGreening * 100 : 0;
      const classTrendShare = item.area ? item.greening / item.area * 100 : 0;
      return `<article class="veg-attribution-card" data-cover="${key}"><small>${esc(names[key])}</small><strong>${Math.round(item.greening).toLocaleString('en-IN')} ha</strong><span>${mixShare.toFixed(1)}% of mapped positive-trend area</span><em>${Math.round(item.area).toLocaleString('en-IN')} ha mapped class · ${classTrendShare.toFixed(1)}% of this class has positive trend</em></article>`;
    }).join('');
  }

  async function init() {
    const status = document.getElementById('veg-attribution-context');
    if (!status) return;
    try {
      const response = await fetch(new URL(dataUrl, document.baseURI));
      if (!response.ok) throw new Error(`CSV request failed (${response.status})`);
      rows = parseCsv(await response.text());
      if (!rows.length) throw new Error('CSV has no data rows');
      document.getElementById('veg-attribution-season')?.addEventListener('change', render);
      document.getElementById('td-district')?.addEventListener('change', render);
      window.addEventListener('trend-page-open', render);
      render();
    } catch (error) {
      status.textContent = 'Could not load the exported district CSV.';
      const cards = document.getElementById('veg-attribution-cards');
      if (cards) cards.textContent = error.message;
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
