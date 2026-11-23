(() => {
  'use strict';
  const rows = window.INTERACTION_DATA || [];
  const byId = {
    LST: {label: 'Temperature', full: 'Land Surface Temperature', color: '#EF6461'},
    NDVI: {label: 'Vegetation', full: 'Vegetation Greenness', color: '#31C48D'},
    SMAP_AM: {label: 'Soil (Morning)', full: 'Morning Soil Moisture', color: '#6C8EE6'},
    SMAP_PM: {label: 'Soil (Evening)', full: 'Evening Soil Moisture', color: '#A78BFA'},
    GPM: {label: 'Rainfall', full: 'Precipitation', color: '#35C9D0'}
  };
  const ids = Object.keys(byId);
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const lagSelect = $('interaction-lag');
  if (!lagSelect || !rows.length) return;
  const lags = [...new Set(rows.map(r => Number(r.lag_months)))].sort((a,b) => a-b);
  lagSelect.innerHTML = lags.map(lag => `<option value="${lag}">${lag === 0 ? 'No lag — same month' : lag > 0 ? `X leads Y by ${lag} month${lag===1?'':'s'}` : `Y leads X by ${Math.abs(lag)} month${lag===-1?'':'s'}`}</option>`).join('');
  if (lags.includes(0)) lagSelect.value = '0';
  $('interaction-kpi-total').textContent = rows.length.toLocaleString();
  $('interaction-kpi-sig').textContent = rows.filter(r => r.fdr_significant).length.toLocaleString();
  $('interaction-kpi-vars').textContent = new Set(rows.flatMap(r => [r.variable_x, r.variable_y])).size;
  $('interaction-kpi-lags').textContent = lags.length;
  const name = id => byId[id]?.label || id;
  const rho = row => Number(row.spearman_rho) || 0;
  const leadPair = row => Number(row.lag_months) > 0 ? [row.variable_x, row.variable_y] : Number(row.lag_months) < 0 ? [row.variable_y, row.variable_x] : null;
  const filteredRows = () => {
    const lag = Number(lagSelect.value);
    const threshold = Number($('interaction-strength').value);
    const sigOnly = $('interaction-significance').value === 'sig';
    return rows.filter(r => Number(r.lag_months) === lag && Math.abs(rho(r)) >= threshold && (!sigOnly || r.fdr_significant))
      .sort((a,b) => Math.abs(rho(b)) - Math.abs(rho(a)));
  };
  function drawNetwork(filtered) {
    const svg = $('network-svg'), box = svg.parentElement.getBoundingClientRect();
    const W = Math.max(360, box.width || 900), H = window.innerWidth < 700 ? 360 : 430;
    const animateGraph = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('height', H);
    if (!filtered.length) { svg.innerHTML = ''; $('interaction-graph-empty').hidden = false; return; }
    $('interaction-graph-empty').hidden = true;
    const activeIds = [...new Set(filtered.flatMap(r => [r.variable_x, r.variable_y]))].sort((a,b) => ids.indexOf(a)-ids.indexOf(b));
    const center = {x: W/2, y: H/2 + 2}, radius = Math.min(W*.34, H*.34, 155);
    const pos = {};
    activeIds.forEach((id,i) => { const angle = -Math.PI/2 + i*2*Math.PI/activeIds.length; pos[id] = {x:center.x+Math.cos(angle)*radius,y:center.y+Math.sin(angle)*radius}; });
    const degree = Object.fromEntries(activeIds.map(id => [id, filtered.filter(r => r.variable_x===id || r.variable_y===id).length]));
    const edges = filtered.map((r,i) => {
      const a=pos[r.variable_x],b=pos[r.variable_y]; if(!a||!b)return '';
      const value=rho(r),positive=value>=0,color=positive?'#31C48D':'#EF6461',significant=Boolean(r.fdr_significant),lag=Number(r.lag_months),direction=leadPair(r);
      const from=direction?pos[direction[0]]:a,to=direction?pos[direction[1]]:b;
      const dx=to.x-from.x,dy=to.y-from.y,len=Math.hypot(dx,dy)||1,ux=dx/len,uy=dy/len,nodeR=34;
      const x1=from.x+ux*nodeR,y1=from.y+uy*nodeR,x2=to.x-ux*nodeR,y2=to.y-uy*nodeR;
      const width=1.4+Math.abs(value)*6,opacity=significant?.78:.27;
      let arrow='';
      if(lag!==0){const tip={x:x2,y:y2},back={x:x2-ux*9,y:y2-uy*9},perp={x:-uy*4,y:ux*4};arrow=`<path d="M${tip.x} ${tip.y}L${back.x+perp.x} ${back.y+perp.y}L${back.x-perp.x} ${back.y-perp.y}Z" fill="${color}" opacity="${opacity}"/>`;}
      const midX=(x1+x2)/2,midY=(y1+y2)/2;
      const edgeFade=animateGraph?'<animate attributeName="opacity" from="0" to="1" begin="0.12s" dur="0.28s" fill="freeze"/>':'';
      const lineDraw=animateGraph?'<animate attributeName="stroke-dashoffset" from="1" to="0" begin="0.12s" dur="0.78s" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.75 0.25 1" fill="freeze"/>':'';
      const labelFade=animateGraph?'<animate attributeName="opacity" from="0" to="1" begin="0.7s" dur="0.28s" fill="freeze"/>':'';
      return `<g class="interaction-edge" opacity="${animateGraph?0:1}">${edgeFade}<title>${direction?`${esc(name(direction[0]))} leads ${esc(name(direction[1]))} by ${Math.abs(lag)} month${Math.abs(lag)===1?'':'s'}`:`${esc(name(r.variable_x))} with ${esc(name(r.variable_y))} in the same month`}; ρ ${value.toFixed(3)}; q ${esc(r.fdr_q_value)}; n=${r.sample_size}; ${significant?'FDR significant':'not FDR significant'}</title><line pathLength="1" stroke-dasharray="${animateGraph?1:'none'}" stroke-dashoffset="${animateGraph?1:0}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${width}" stroke-opacity="${opacity}" stroke-linecap="round">${lineDraw}</line>${arrow}<g class="interaction-edge-label" opacity="${animateGraph?0:1}">${labelFade}<rect x="${midX-27}" y="${midY-10}" width="54" height="19" rx="7"/><text x="${midX}" y="${midY+4}" text-anchor="middle">${value>0?'+':''}${value.toFixed(2)}</text></g></g>`;
    }).join('');
    const nodes = activeIds.map(id => { const p=pos[id],meta=byId[id]||{color:'#82aaa7'},r=34+Math.min(8,(degree[id]-1)*2),startX=((p.x-center.x)*.68).toFixed(1),startY=((p.y-center.y)*.42).toFixed(1),fromX=animateGraph?startX:0,fromY=animateGraph?startY:0;const settle=animateGraph?`<animateTransform attributeName="transform" type="translate" from="${fromX} ${fromY}" to="0 0" begin="0s" dur="0.95s" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.82 0.2 1" fill="freeze"/>`:'';return `<g class="interaction-node" transform="translate(${fromX} ${fromY})">${settle}<title>${esc(name(id))}: ${degree[id]} displayed connection${degree[id]===1?'':'s'}</title><circle class="interaction-node-aura" cx="${p.x}" cy="${p.y}" r="${r+7}" fill="${meta.color}" opacity=".08"/><circle cx="${p.x}" cy="${p.y}" r="${r}" fill="#111e29" stroke="${meta.color}" stroke-width="2.5"/><circle cx="${p.x}" cy="${p.y}" r="${r-7}" fill="${meta.color}" opacity=".11"/><text class="interaction-node-title" x="${p.x}" y="${p.y-2}" text-anchor="middle">${esc(name(id))}</text><text class="interaction-node-sub" x="${p.x}" y="${p.y+14}" text-anchor="middle">${degree[id]} link${degree[id]===1?'':'s'}</text></g>`;}).join('');
    const glowAnimation=animateGraph?'<animate attributeName="opacity" from="0" to="1" begin="0s" dur="0.8s" fill="freeze"/>':'';
    svg.innerHTML=`<defs><radialGradient id="interactionGlow"><stop stop-color="#4fc0b4" stop-opacity=".1"/><stop offset="1" stop-color="#4fc0b4" stop-opacity="0"/></radialGradient></defs><circle class="interaction-core-glow" opacity="${animateGraph?0:1}" cx="${center.x}" cy="${center.y}" r="${radius+85}" fill="url(#interactionGlow)">${glowAnimation}</circle>${edges}${nodes}`;
  }
  function drawMatrix(filtered) {
    const mount=$('interaction-matrix'),lookup=new Map();
    filtered.forEach(r=>{lookup.set(`${r.variable_x}|${r.variable_y}`,rho(r));lookup.set(`${r.variable_y}|${r.variable_x}`,rho(r));});
    const cells=[`<div class="im-cell im-corner"></div>`,...ids.map(id=>`<div class="im-cell im-head">${esc(name(id))}</div>`)].join('');
    const body=ids.map(y=>`<div class="im-cell im-row-head">${esc(name(y))}</div>`+ids.map(x=>{
      if(x===y)return '<div class="im-cell im-value im-diagonal">1.00</div>';
      const value=lookup.get(`${y}|${x}`); if(value===undefined)return '<div class="im-cell im-value im-missing">—</div>';
      const tint=value>=0?'49,196,141':'239,100,97',alpha=.11+Math.abs(value)*.45;
      return `<div class="im-cell im-value" style="background:rgba(${tint},${alpha.toFixed(2)})" title="Spearman ρ = ${value.toFixed(4)}">${value>0?'+':''}${value.toFixed(2)}</div>`;
    }).join('')).join('');
    mount.innerHTML=`<div class="im-grid">${cells}${body}</div>`;
  }
  function drawTable(filtered) {
    const body=$('interaction-table-body');
    body.innerHTML=filtered.map(r=>`<tr><td><span class="interaction-var"><i style="--var-color:${byId[r.variable_x]?.color||'#8ba5b5'}"></i>${esc(name(r.variable_x))}</span></td><td>${Number(r.lag_months)===0?'Same month':`${Math.abs(Number(r.lag_months))} mo · ${Number(r.lag_months)>0?'X leads':'Y leads'}`}</td><td><span class="interaction-var"><i style="--var-color:${byId[r.variable_y]?.color||'#8ba5b5'}"></i>${esc(name(r.variable_y))}</span></td><td class="interaction-rho ${rho(r)>=0?'positive':'negative'}">${rho(r)>0?'+':''}${rho(r).toFixed(4)}</td><td>${Number(r.p_value).toExponential(2)}</td><td>${Number(r.fdr_q_value).toExponential(2)}</td><td>${Number(r.sample_size).toLocaleString()}</td><td><span class="interaction-sig ${r.fdr_significant?'is-sig':'is-nonsig'}">${r.fdr_significant?'Significant':'Not significant'}</span></td></tr>`).join('')||'<tr><td colspan="8" class="interaction-no-rows">No relationships match the selected filters.</td></tr>';
  }
  function drawStrongest(filtered) {
    const mount=$('interaction-strongest');
    if(!filtered.length){mount.innerHTML='<div class="interaction-no-rows">No relationship is available under the current filters.</div>';return;}
    const r=filtered[0],positive=rho(r)>=0,dir=positive?'Positive':'Negative',lag=Number(r.lag_months),direction=leadPair(r),lead=direction?`${name(direction[0])} at t → ${name(direction[1])} at t + ${Math.abs(lag)} month${Math.abs(lag)===1?'':'s'}`:'Both variables measured in the same month';
    mount.innerHTML=`<div class="interaction-strongest-head"><div><span class="anomaly-kicker">${esc(dir.toUpperCase())} ASSOCIATION · ${lag===0?'LAG 0':`LAG +${lag} MONTHS`}</span><h3>${esc(name(r.variable_x))} <span>↔</span> ${esc(name(r.variable_y))}</h3><p>${esc(lead)}</p></div><strong class="interaction-strength-number ${positive?'positive':'negative'}">${rho(r)>0?'+':''}${rho(r).toFixed(3)}<small>Spearman ρ</small></strong></div><div class="interaction-strongest-stats"><div><small>FDR q-value</small><b>${Number(r.fdr_q_value).toExponential(2)}</b></div><div><small>Sample size</small><b>${Number(r.sample_size).toLocaleString()}</b></div><div><small>p-value</small><b>${Number(r.p_value).toExponential(2)}</b></div><div><small>Multiple-test result</small><b>${r.fdr_significant?'Significant':'Not significant'}</b></div></div><p class="interaction-disclaimer">This is the strongest association after the current filters. Statistical association and lead–lag timing do not establish a physical cause.</p>`;
  }
  let explanationTimer = null;
  let activeRequest = null;
  const explanationCache = new Map();
  const apiBase = window.EARTHPULSE_API_BASE || 'http://127.0.0.1:8001';
  const explanationKey = () => `${lagSelect.value}|${$('interaction-significance').value}|${$('interaction-strength').value}`;
  function explanationMarkup(answer) {
    const safe=esc(answer).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
    return `<div class="interaction-ai-answer">${safe.split(/\n\n+/).map(p=>`<p>${p.replace(/\n/g,'<br>')}</p>`).join('')}</div>`;
  }
  function scheduleExplanation(filtered) {
    if (!$('page-network')?.classList.contains('active')) return;
    clearTimeout(explanationTimer);
    const out=$('interaction-ai-output'),status=$('interaction-ai-status'),key=explanationKey();
    if (activeRequest) { activeRequest.abort(); activeRequest=null; }
    if (!filtered.length) {
      out.innerHTML='<p class="interaction-ai-error">No relationships match these filters. Adjust a filter to generate an explanation.</p>';
      status.innerHTML='<i></i> NO MATCHES';
      return;
    }
    if (explanationCache.has(key)) {
      out.innerHTML=explanationMarkup(explanationCache.get(key));
      status.innerHTML='<i></i> UPDATED';
      return;
    }
    status.innerHTML='<i></i> READING GRAPH';
    out.innerHTML='<span class="pred-ai-loading">Reading the filtered graph and checking the statistics…</span>';
    explanationTimer=setTimeout(()=>generateExplanation(filtered,key),650);
  }
  async function generateExplanation(filtered,key) {
    const controller=new AbortController(); activeRequest=controller;
    const out=$('interaction-ai-output'),status=$('interaction-ai-status');
    const degree={}; filtered.forEach(r=>{degree[r.variable_x]=(degree[r.variable_x]||0)+1;degree[r.variable_y]=(degree[r.variable_y]||0)+1;});
    const hubs=Object.entries(degree).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([id,n])=>`${name(id)} (${n} displayed links)`).join(', ')||'None';
    const significant=filtered.filter(r=>r.fdr_significant).length;
    const lagValue=Number(lagSelect.value);
    const lagDescription=lagValue===0?'same-month associations':lagValue>0?`X at month t compared with Y at t+${lagValue} months`:`Y at month t compared with X at t+${Math.abs(lagValue)} months`;
    const graph=filtered.map(r=>{
      const pair=leadPair(r);
      const relation=pair?`${name(pair[0])} at t leads ${name(pair[1])} at t+${Math.abs(Number(r.lag_months))}`:`${name(r.variable_x)} and ${name(r.variable_y)} in the same month`;
      return `${relation}: Spearman rho ${rho(r).toFixed(3)}, FDR q ${Number(r.fdr_q_value).toExponential(2)}, sample n=${r.sample_size}, ${r.fdr_significant?'FDR significant':'not FDR significant'}`;
    }).join('\n');
    const prompt=`Explain this satellite-data relationship graph to a beginner in clear, natural Hinglish. Write 100–150 words in 2–3 short paragraphs, no greeting. Say what the selected graph shows, describe the strongest one or two links using the supplied values, explain positive/negative and lag simply, and report how many displayed links pass FDR correction. Explain the most connected variable only as a count of links in this filtered graph. Association is not cause: never claim one signal caused, predicts, or physically drives another. Call environmental interpretations hypotheses, not proof. Never invent values. For same-month data, do not describe a lead. For lagged data, honor the direction stated. End with one practical takeaway.
Current filter: ${lagDescription}; significance option=${$('interaction-significance').value}; minimum absolute rho=${$('interaction-strength').value}.
Displayed links: ${filtered.length}; FDR-significant links: ${significant}; most connected nodes: ${hubs}.
Actual filtered rows:
${graph}`;
    try {
      const response=await fetch(`${apiBase.replace(/\/$/,'')}/api/explain`,{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({prompt})});
      const payload=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(payload.error||`Explanation service returned ${response.status}`);
      const answer=String(payload.answer||'').trim();
      if(!answer)throw new Error('The model returned an empty explanation.');
      if(key!==explanationKey())return;
      explanationCache.set(key,answer);
      if(explanationCache.size>30)explanationCache.delete(explanationCache.keys().next().value);
      out.innerHTML=explanationMarkup(answer);
      status.innerHTML='<i></i> UPDATED';
    } catch(error) {
      if(error.name==='AbortError')return;
      if(key!==explanationKey())return;
      out.innerHTML=`<p class="interaction-ai-error">Automatic explanation is temporarily unavailable: ${esc(error.message)}.</p>`;
      status.innerHTML='<i></i> UNAVAILABLE';
    } finally { if(activeRequest===controller)activeRequest=null; }
  }
  function render() {
    const filtered=filteredRows();
    $('interaction-filter-count').textContent=`Showing ${filtered.length} of ${rows.length} tested relationships`;
    $('interaction-strength-value').value=Number($('interaction-strength').value).toFixed(2);
    drawNetwork(filtered); drawMatrix(filtered); drawTable(filtered); drawStrongest(filtered);
    scheduleExplanation(filtered);
  }
  lagSelect.addEventListener('change',render);
  $('interaction-significance').addEventListener('change',render);
  $('interaction-strength').addEventListener('input',render);
  window.addEventListener('resize',()=>{if($('page-network')?.classList.contains('active'))drawNetwork(filteredRows());});

  window.renderInteractionNetwork = render;
  render();
})();
