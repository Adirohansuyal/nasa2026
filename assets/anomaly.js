(() => {
  'use strict';
  const D=window.ANOMALY_DATA;
  if(!D)return;
  const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const HAZARD_ORDER=Object.keys(D.hazards), GEO_WEIGHTED=new Set(['COLD_STRESS','HEAT_WAVE','FLOOD','VEGETATION_LOSS']);
  let selected=HAZARD_ORDER[0], mapHandlers=new Map();
  const monthName=s=>{const d=new Date(`${String(s).slice(0,7)}-01T00:00:00Z`);return Number.isNaN(+d)?String(s):d.toLocaleDateString('en-US',{month:'short',year:'numeric',timeZone:'UTC'});};
  const fullMonth=s=>{const d=new Date(`${String(s).slice(0,7)}-01T00:00:00Z`);return Number.isNaN(+d)?String(s):d.toLocaleDateString('en-US',{month:'long',year:'numeric',timeZone:'UTC'});};
  const num=(v,n=1)=>Number(v||0).toFixed(n);
  function prep(canvas){if(!canvas)return null;const r=canvas.getBoundingClientRect();if(r.width<30)return null;const ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.round(r.width*ratio);canvas.height=Math.round(r.height*ratio);const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);return{ctx,w:r.width,h:r.height};}
  function rgb(hex){const s=String(hex||'#778899').replace('#','');return[parseInt(s.slice(0,2),16),parseInt(s.slice(2,4),16),parseInt(s.slice(4,6),16)];}
  function fillMix(base,color,t){const a=rgb(base),b=rgb(color);return`rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')})`;}
  function project(lon,lat){const R=6378137,c=Math.cos(Math.PI/6);return[R*c*lon*Math.PI/180,R*Math.sin(lat*Math.PI/180)/c];}
  function geometryPolygons(g){if(!g)return[];if(g.type==='Polygon')return[g.coordinates];if(g.type==='MultiPolygon')return g.coordinates;return[];}
  function allDistricts(){return D.districtGeo.features.map(f=>f.properties.district_name).sort((a,b)=>a.localeCompare(b));}

  function renderCatalogue(){
    $('anomaly-kpi-events').textContent=Number(D.spatialEventCount).toLocaleString();
    $('anomaly-kpi-districts').textContent=D.districtCount;
    $('anomaly-hazard-catalogue').innerHTML=HAZARD_ORDER.map(key=>{const h=D.hazards[key];return`<button class="anomaly-catalogue-card" data-hazard="${key}" style="--hazard-color:${h.color}"><span class="anomaly-card-emoji">${h.emoji}</span><span class="anomaly-card-count">${h.monthsTriggered} mo</span><strong>${esc(h.label)}</strong><span>${esc(h.description)}</span><small>Open district analysis <b>↗</b></small></button>`;}).join('');
    $('anomaly-hazard-catalogue').querySelectorAll('[data-hazard]').forEach(el=>el.addEventListener('click',()=>selectHazard(el.dataset.hazard,true)));
    renderFrequency();renderRuleCards();renderLegacy();
  }
  function renderFrequency(){
    const chart=$('anomaly-frequency-chart');if(!chart)return;const rows=HAZARD_ORDER.map(key=>({key,meta:D.hazards[key],value:Number(D.hazards[key].monthsTriggered)})),max=Math.max(1,...rows.map(x=>x.value));
    chart.innerHTML=rows.map(r=>`<div class="anomaly-frequency-row" style="--hazard-color:${r.meta.color}"><div class="anomaly-frequency-label"><span>${r.meta.emoji}</span><strong>${esc(r.meta.label)}</strong></div><div class="anomaly-frequency-track"><i style="width:${Math.max(r.value?3:0,r.value/max*100)}%"></i></div><div class="anomaly-frequency-value"><b>${r.value}</b><small>months</small></div></div>`).join('');
  }
  function selectHazard(key,scroll){if(!D.hazards[key])return;selected=key;document.querySelectorAll('.anomaly-hazard-tab').forEach(b=>{const on=b.dataset.hazard===key;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));});renderHazardPanel();if(scroll)$('anomaly-hazard-panel').scrollIntoView({behavior:'smooth',block:'start'});}
  function renderTabs(){ $('anomaly-hazard-tabs').innerHTML=HAZARD_ORDER.map(key=>{const h=D.hazards[key];return`<button class="anomaly-hazard-tab" role="tab" aria-selected="${key===selected}" data-hazard="${key}" style="--hazard-color:${h.color}">${h.emoji} ${esc(h.label.split('/')[0].trim())}<span>${h.monthsTriggered}</span></button>`;}).join('');$('anomaly-hazard-tabs').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>selectHazard(b.dataset.hazard,false)));}
  function getDistrictRows(key){return(D.districtHazards[key]||[]).slice().sort((a,b)=>Number(b.risk_score)-Number(a.risk_score));}
  function colorValue(key,row){if(GEO_WEIGHTED.has(key))return Number(row.risk_score)||0;if(key==='DROUGHT')return Math.abs(Number(row.mean_intensity_z)||0);return Math.max(0,Number(row.mean_intensity_z)||0);}
  function renderHazardPanel(){
    const key=selected,meta=D.hazards[key],rows=getDistrictRows(key),active=rows.filter(r=>Number(r.months_triggered)>0),freq=Number(meta.monthsTriggered)||0,top=active[0],maxRisk=Math.max(0,...active.map(r=>Number(r.risk_score)||0));
    $('anomaly-hazard-panel').style.setProperty('--hazard-color',meta.color);
    $('anomaly-hazard-panel').innerHTML=`<div class="anomaly-hazard-banner"><span>${meta.emoji}</span><div><h3>${esc(meta.label)}</h3><p>${esc(meta.description)}</p><small>⏱ ${freq} regional months · 🗺 ${active.length} of ${D.districtCount} districts exposed · ${esc(meta.action)}</small></div></div>
      <div class="anomaly-hazard-kpis"><div><small>REGIONAL MONTHS TRIGGERED</small><strong>${freq}</strong></div><div><small>DISTRICTS EXPOSED</small><strong>${active.length} <i>/ ${D.districtCount}</i></strong></div><div><small>HIGHEST-RISK DISTRICT</small><strong>${top?esc(top.district_name):'—'}</strong></div><div><small>RISK SCORE</small><strong>${top?num(top.risk_score,0)+'/100':'—'}</strong></div></div>
      ${freq===0?`<div class="anomaly-empty">No ${esc(meta.label)} events were detected in the 10-year record at the current thresholds.</div>`:`<div class="anomaly-map-heading"><div><span class="anomaly-kicker">DISTRICT EXPOSURE MAP</span><h3>${meta.emoji} ${esc(meta.label)}</h3></div><span class="anomaly-map-legend"><i style="--legend-color:${meta.color}"></i> lower intensity <b>→</b> higher intensity</span></div>
      <div class="anomaly-map-rank-grid"><div class="anomaly-map-wrap"><canvas id="anomaly-hazard-map" class="anomaly-map-canvas" aria-label="${esc(meta.label)} intensity by district"></canvas><div id="anomaly-map-tooltip" class="anomaly-map-tooltip" hidden></div></div><div class="anomaly-rank-wrap"><div class="anomaly-subheading"><div><span class="anomaly-kicker">DISTRICT ORDER</span><h3>Exposure ranking</h3></div><span>${active.length} exposed</span></div><div class="anomaly-ranking">${rows.map((r,i)=>rankRow(r,i,key,meta)).join('')}</div></div></div>
      <section class="anomaly-mini-map-section"><div class="anomaly-subheading"><div><span class="anomaly-kicker">DISTRICT FOOTPRINTS</span><h3>Exposure by district</h3></div><span>Map outlines · score · active months</span></div><div class="anomaly-mini-map-grid">${miniMapCards(rows,key,meta)}</div></section>
      <div class="anomaly-reasons">${buildReasons(active,freq,key)}</div>
      <details class="anomaly-details" open><summary>📅 Month-by-month record · ${esc(meta.label)}</summary><div class="anomaly-table-wrap">${monthTable(rows,key)}</div></details>
      <details class="anomaly-details"><summary>📋 Full district table · ${esc(meta.label)}</summary><div class="anomaly-table-wrap">${districtTable(rows)}</div></details>
      <section class="pred-ai-card anomaly-ai-card"><div class="pred-ai-heading"><span class="pred-ai-icon">✦</span><div><h3>AI hazard briefing</h3><p>RANKING EXPLANATION · GEOGRAPHIC CONTEXT · SOURCED EVENTS</p></div><span class="pred-ai-live"><i></i> READY</span></div><p class="pred-muted">Explains why the leading district ranks first using the displayed score components, then checks for documented events in the flagged months. Past events do not affect the score.</p><button class="pred-ai-refresh" id="anomaly-ai-button">Explain the leading district</button><div class="pred-ai-answer" id="anomaly-ai-output" aria-live="polite"></div></section>`}`;
    if(freq){drawDistrictMap($('anomaly-hazard-map'),rows,key);bindMapTooltip($('anomaly-hazard-map'),rows,key);const b=$('anomaly-ai-button');b?.addEventListener('click',()=>explainHazard(key,rows,meta));}
  }
  function miniMap(name,key,meta,exposed){const f=D.districtGeo.features.find(x=>x.properties.district_name===name);if(!f)return'';const rings=geometryPolygons(f.geometry).flatMap(poly=>poly),pts=rings.flat(),xs=pts.map(p=>p[0]),ys=pts.map(p=>-p[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),w=Math.max(.01,maxX-minX),h=Math.max(.01,maxY-minY),paths=rings.map(r=>r.map((p,i)=>`${i?'L':'M'}${p[0]-minX},${-p[1]-minY}`).join(' ')+' Z').join(' ');return`<svg class="anomaly-mini-map" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${paths}" fill="${exposed?meta.color:'#26333e'}" fill-opacity="${exposed?'.72':'.3'}" stroke="${exposed?meta.color:'#61707b'}" stroke-width=".012" vector-effect="non-scaling-stroke"/></svg>`;}
  function rankRow(row,index,key,meta){const exposed=Number(row.months_triggered)>0,score=Number(row.risk_score)||0,medal={0:'①',1:'②',2:'③'}[index]||String(index+1).padStart(2,'0'),width=exposed?Math.max(2,score):0;return`<div class="anomaly-rank-row${exposed?'':' unexposed'}"><span class="anomaly-rank-num">${medal}</span><div class="anomaly-rank-main"><div><strong>${esc(row.district_name)}</strong><small>${exposed?`${row.months_triggered} months · ${num(row.mean_intensity_z,2)}σ mean`:'No active pixel months'}</small></div><div class="anomaly-rank-track"><i style="width:${width}%;--rank-color:${meta.color}"></i></div></div><b class="anomaly-rank-score" style="color:${exposed?meta.color:'#7b8993'}">${exposed?num(score,0):'—'}</b></div>`;}
  function miniMapCards(rows,key,meta){return rows.map((r,i)=>{const exposed=Number(r.months_triggered)>0;return`<article class="anomaly-mini-map-card${exposed?'':' unexposed'}"><div class="anomaly-mini-map-visual">${miniMap(r.district_name,key,meta,exposed)}</div><div class="anomaly-mini-map-copy"><span class="anomaly-mini-map-rank">${String(i+1).padStart(2,'0')} · ${exposed?num(r.risk_score,0)+'/100':'NO PIXEL EXPOSURE'}</span><strong>${esc(r.district_name)}</strong><small>${exposed?`${r.months_triggered} months · ${num(r.mean_intensity_z,2)}σ mean`:'No active pixel months'}</small></div></article>`;}).join('');}
  function buildReasons(rows,total,key){
    if(!rows.length)return'<p>No districts have pixel records in the active months.</p>';
    const top=rows.slice(0,5),sameFrequency=new Set(top.map(r=>Number(r.months_triggered))).size===1;
    const note=sameFrequency?`Each of the top ${top.length} districts was exposed in ${top[0].months_triggered} of ${total} active months. Exposure frequency is tied, so score differences come from signal intensity and the hazard-specific geographic multiplier.`:`The ranking combines exposure frequency and mean satellite-signal intensity, adjusted by a hazard-specific geographic multiplier.`;
    const cards=top.map((r,i)=>{const next=top[i+1],reasons=[];if(next){if(Number(r.months_triggered)>Number(next.months_triggered))reasons.push(`more exposed months (${r.months_triggered} vs ${next.months_triggered})`);if(Math.abs(Number(r.mean_intensity_z))>Math.abs(Number(next.mean_intensity_z))+.001)reasons.push(`stronger mean signal (${num(r.mean_intensity_z,2)}σ vs ${num(next.mean_intensity_z,2)}σ)`);if(Number(r.geo_weight)>Number(next.geo_weight)+.001)reasons.push(`higher geographic multiplier (${num(r.geo_weight,2)}× vs ${num(next.geo_weight,2)}×)`);}if(!reasons.length)reasons.push('its score components are close to the next district');return`<article class="anomaly-reason-card" style="--hazard-color:${D.hazards[key].color}"><div class="anomaly-reason-card-top"><span class="anomaly-reason-rank">${String(i+1).padStart(2,'0')}</span><strong>${esc(r.district_name)}</strong><b>${num(r.risk_score,1)}<small>/100</small></b></div><p>${esc(reasons.join(' · '))}</p><div class="anomaly-reason-metrics"><span><small>EXPOSURE</small><b>${r.months_triggered}/${total} months</b></span><span><small>MEAN INTENSITY</small><b>${num(r.mean_intensity_z,2)}σ</b></span><span><small>GEO. MULTIPLIER</small><b>${num(r.geo_weight,2)}×</b></span></div><div class="anomaly-reason-score-track"><i style="width:${Math.max(2,Number(r.risk_score)||0)}%"></i></div></article>`;}).join('');
    return`<div class="anomaly-reasons-heading"><div><span class="anomaly-kicker">RANKING DRIVERS</span><h3>Why these districts rank highest</h3></div><span class="anomaly-reason-formula">Frequency · intensity · geographic weighting</span></div><p class="anomaly-shared-note">${esc(note)}</p><div class="anomaly-reasons-grid">${cards}</div><p class="anomaly-reasons-footnote">Historical events are not part of the score. This is a relative monitoring index, not a hazard probability or official warning.</p>`;
  }
  function monthTable(rows,key){const alerts=new Map(D.monthlyAlerts.map(r=>[String(r.month).slice(0,7),r])),monthSet=new Set(rows.flatMap(r=>r.triggered_months||[])),months=[...monthSet].sort();if(!months.length)return'<p class="anomaly-empty">No pixel-level month records for this hazard.</p>';return`<table class="pred-table anomaly-table"><thead><tr><th>Month</th><th>Regional tier</th><th>Districts exposed</th><th>Districts</th><th>Regional pattern</th></tr></thead><tbody>${months.map(m=>{const a=alerts.get(m),districts=rows.filter(r=>(r.triggered_months||[]).includes(m)).map(r=>r.district_name).sort();return`<tr><td>${fullMonth(m)}</td><td><span class="anomaly-tier tier-${String(a?.max_alert_level||'normal').toLowerCase()}">${a?.max_alert_level||'—'}</span></td><td>${districts.length}</td><td>${esc(districts.join(', '))}</td><td>${esc(a?.primary_hazard&&a.primary_hazard!=='NONE'?D.hazards[a.primary_hazard]?.label||a.primary_hazard:a?.alert_message||'—')}</td></tr>`;}).join('')}</tbody></table>`;}
  function districtTable(rows){return`<table class="pred-table anomaly-table"><thead><tr><th>Rank</th><th>District</th><th>Risk level</th><th>Risk score</th><th>Months exposed</th><th>Mean intensity</th><th>Max intensity</th><th>Worst month</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}</td><td><strong>${esc(r.district_name)}</strong></td><td><span class="anomaly-tier tier-${String(r.risk_level||'normal').toLowerCase()}">${r.risk_level}</span></td><td>${Number(r.months_triggered)>0?num(r.risk_score,1):'—'}</td><td>${r.months_triggered}</td><td>${r.months_triggered?`${num(r.mean_intensity_z,3)}σ`:'—'}</td><td>${r.months_triggered?`${num(r.max_intensity_z,3)}σ`:'—'}</td><td>${r.worst_month==='—'?'—':monthName(r.worst_month)}</td></tr>`).join('')}</tbody></table>`;}

  function drawDistrictMap(canvas,rows,key,legacy=false,highlight=''){
    const ready=prep(canvas);if(!ready)return;const{ctx,w,h}=ready;ctx.fillStyle='#0b121a';ctx.fillRect(0,0,w,h);
    const items=D.districtGeo.features.map(f=>({name:f.properties.district_name,geometry:f.geometry,row:rows.find(r=>r.district_name===f.properties.district_name)})),coords=[];
    items.forEach(f=>geometryPolygons(f.geometry).forEach(poly=>poly[0].forEach(p=>coords.push(project(p[0],p[1])))));
    if(!coords.length)return;const xs=coords.map(p=>p[0]),ys=coords.map(p=>p[1]),pad={x:48,y:35},bounds={l:Math.min(...xs),r:Math.max(...xs),b:Math.min(...ys),t:Math.max(...ys)},scale=Math.min((w-pad.x*2)/(bounds.r-bounds.l),(h-pad.y*2)/(bounds.t-bounds.b)),ox=(w-(bounds.r-bounds.l)*scale)/2,oy=(h-(bounds.t-bounds.b)*scale)/2;
    const px=x=>ox+(x-bounds.l)*scale,py=y=>h-oy-(y-bounds.b)*scale,values=items.map(f=>legacy?Number(f.row?.anomaly_pixel_percentage)||0:colorValue(key,f.row||{})),min=legacy?0:Math.min(0,...values),max=Math.max(...values),hazard=D.hazards[key],colors=new Map();
    items.forEach((f,i)=>{const val=values[i],t=max===min?0:Math.max(0,Math.min(1,(val-min)/(max-min))),fill=fillMix('#111b25',legacy?'#d58b58':hazard.color,.12+.83*Math.pow(t,.82));colors.set(f.name,fill);const path=new Path2D();const polygons=geometryPolygons(f.geometry);polygons.forEach(poly=>{poly.forEach(ring=>ring.forEach((pt,j)=>{const [x,y]=project(pt[0],pt[1]);j?path.lineTo(px(x),py(y)):path.moveTo(px(x),py(y));}));});ctx.fillStyle=fill;ctx.strokeStyle=f.name===highlight?'#f0f6f7':'rgba(207,220,228,.72)';ctx.lineWidth=f.name===highlight?2.2:1;ctx.fill(path,'evenodd');ctx.stroke(path);f.path=path;f.value=val;});
    items.forEach(f=>{const polys=geometryPolygons(f.geometry),pts=polys.flatMap(poly=>poly[0]).map(p=>project(p[0],p[1]));if(!pts.length)return;const x=pts.reduce((a,p)=>a+px(p[0]),0)/pts.length,y=pts.reduce((a,p)=>a+py(p[1]),0)/pts.length;ctx.fillStyle='rgba(245,248,250,.85)';ctx.font='600 8px Urbanist,sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(f.name.replace(' Garhwal','').replace('Udham Singh Nagar','US Nagar'),x,y);});
    canvas._anomalyFeatures=items;canvas._anomalyScale={legacy,key,colors};ctx.fillStyle='#9baab4';ctx.font='10px Urbanist,sans-serif';ctx.textAlign='left';ctx.textBaseline='alphabetic';ctx.fillText(legacy?'GPM high-anomaly pixel share (%)':GEO_WEIGHTED.has(key)?'Hazard-weighted district risk score':`${key==='DROUGHT'?'Mean |z|':key==='COMPOUND'?'Positive mean intensity z':'Hazard intensity'} by district`,12,h-10);
  }
  function bindMapTooltip(canvas,rows,key,legacy=false){if(!canvas)return;const tip=legacy?$('anomaly-legacy-tooltip'):$('anomaly-map-tooltip');if(!tip)return;canvas.onpointermove=e=>{const rect=canvas.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;let found=null;for(const f of canvas._anomalyFeatures||[])if(canvas.getContext('2d').isPointInPath(f.path,x,y,'evenodd')){found=f;break;}if(!found){tip.hidden=true;return;}const row=found.row||{},value=legacy?row.anomaly_pixel_percentage:colorValue(key,row);tip.innerHTML=`<b>${esc(found.name)}</b><br>${legacy?`High anomaly: ${num(value,2)}% · ${Number(row.high_anomaly_pixels||0).toLocaleString()} / ${Number(row.valid_pixels||0).toLocaleString()} pixels`:`Risk ${num(row.risk_score,0)}/100 · ${row.months_triggered||0} months · Mean ${num(row.mean_intensity_z,2)}σ · Worst ${row.worst_month==='—'?'—':monthName(row.worst_month)}`}`;tip.hidden=false;tip.style.left=`${Math.min(x+14,rect.width-260)}px`;tip.style.top=`${Math.max(4,y-12)}px`;};canvas.onpointerleave=()=>{tip.hidden=true;};}

  async function explainHazard(key,rows,meta){
    const button=$('anomaly-ai-button'),out=$('anomaly-ai-output');if(!button||!out)return;
    const top=rows.filter(r=>Number(r.months_triggered)>0).slice(0,5).map(r=>({district:r.district_name,months:r.months_triggered,anomalyMonths:r.triggered_months||[],meanIntensitySigma:r.mean_intensity_z,maxIntensitySigma:r.max_intensity_z,frequencyScore:r.frequency_score,intensityScore:r.intensity_score,elevationWeight:r.geo_weight,riskScore:r.risk_score,worstMonth:r.worst_month}));
    if(!top.length){out.innerHTML='<p>No district exposure is available to explain for this hazard.</p>';return;}
    button.disabled=true;button.textContent='Generating briefing…';out.innerHTML='<span class="pred-ai-loading">CHECKING THE RANKING DATA AND HISTORICAL SOURCES…</span>';
    const context=top.map(r=>`${r.district}: anomaly months ${r.anomalyMonths.join(', ')||'not listed'}; months exposed ${r.months}; mean intensity ${num(r.meanIntensitySigma,2)} sigma`).join('\n');
    const leader=top[0],runnerUp=top[1]||null;
    const prompt=`You are the evidence-focused AI analyst for EARTHPULSE-X. Answer in clear, professional English. The supplied application data is the sole authority for ranks and numbers.

HAZARD: ${meta.label}. Detector pattern: ${meta.description}. The score is a monitoring index, not a probability, forecast, or official warning.
AUTHORITATIVE RANKING INPUT (already sorted highest score first; do not reorder or substitute district names):
LEADER: ${JSON.stringify(leader)}
NEXT DISTRICT: ${JSON.stringify(runnerUp)}
OTHER TOP DISTRICTS AND THEIR FLAGGED MONTHS: ${context}
REGIONAL TRIGGERED MONTHS: ${meta.monthsTriggered}

Write exactly these three short sections:
**Why the leading district ranks first** — Name ${leader.district} as #1. Explain its score by comparing only supplied exposure, mean intensity, geographic multiplier, and score with the next district (if present). Use exact values; do not invent or recalculate.
**Geographic context** — Explain only what a reliable source supports about this district's geography and why it may matter to this hazard. Cite the source as a markdown link. The supplied geographic multiplier is a model heuristic, not a measured elevation or proof of terrain effects. If you cannot verify a relevant geographic explanation, say so plainly.
**Historical event check** — Search for at most two documented events matching an exact district and one of its listed anomaly months, relevant to this hazard. Cite each event claim with a markdown link. If no exact match is verified, state once: “No reliable district-and-month event match was found.” Do not write repetitive no-match bullets for every district.

Never claim a past event caused the satellite anomaly or affected the score. No generic climate explanations, unsourced causal claims, invented citations, repeated ranking summary, or extra sections. DATA: ${JSON.stringify({regionalMonths:meta.monthsTriggered,record:D.source,topDistricts:top})}`;
    try {
      const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer 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',
          'Content-Type': 'application/json',
          'HTTP-Referer': location.href,
          'X-Title': 'EARTHPULSE-X Anomaly Intelligence'
        },
        body: JSON.stringify({
          model: 'meta-llama/llama-3.3-70b-instruct',
          tools: [{ type: 'openrouter/web_search' }],
          messages: [{ role: 'user', content: prompt }],
          temperature: .1,
          max_tokens: 700
        })
      });
      if (!response.ok) throw new Error(`OpenRouter returned ${response.status}`);
      const payload = await response.json();
      const answer = payload.choices?.[0]?.message?.content;
      if (!answer) throw new Error('The model returned an empty answer');
      const safe = esc(answer)
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      const blocks = safe.split(/\n\s*\n/).map(block => {
        const lines = block.split('\n').filter(Boolean);
        if (lines.length && lines.every(line => /^[-*]\s/.test(line))) {
          return `<ul>${lines.map(line => `<li>${line.replace(/^[-*]\s/, '')}</li>`).join('')}</ul>`;
        }
        return `<p>${lines.join('<br>')}</p>`;
      }).join('');
      out.innerHTML = `<div class="anomaly-ai-answer-text">${blocks}</div>`;
    } catch (error) {
      out.innerHTML = `<p class="anomaly-ai-error">Could not generate the AI briefing: ${esc(error.message)}. Check the OpenRouter connection and try again.</p>`;
    } finally {
      button.disabled = false;
      button.textContent = 'Explain the leading district';
    }
  }


  function renderLegacy(){
    const rows=D.legacyGpmAug2025||[],select=$('anomaly-legacy-district');if(!rows.length){$('anomaly-legacy-kpis').innerHTML='<p>Legacy GPM district data is unavailable in this export.</p>';return;}
    const districtKey=r=>r.district_name||r.DISTRICT||r.district||'',valueKey=r=>Number(r.anomaly_pixel_percentage??r.high_anomaly_pct??r.high_anomaly_percent??0);
    rows.sort((a,b)=>valueKey(b)-valueKey(a));select.innerHTML=rows.map(r=>`<option value="${esc(districtKey(r))}">${esc(districtKey(r))}</option>`).join('');
    const draw=()=>{const chosen=rows.find(r=>districtKey(r)===select.value)||rows[0],name=districtKey(chosen),share=valueKey(chosen),high=Number(chosen.high_anomaly_pixels||chosen.high_anomaly_count||0),valid=Number(chosen.valid_pixels||chosen.total_pixels||0),totalHigh=rows.reduce((a,r)=>a+Number(r.high_anomaly_pixels||r.high_anomaly_count||0),0),totalValid=rows.reduce((a,r)=>a+Number(r.valid_pixels||r.total_pixels||0),0);$('anomaly-legacy-kpis').innerHTML=`<div><small>DISTRICTS</small><b>${rows.length}</b></div><div><small>VALID PIXELS</small><b>${totalValid.toLocaleString()}</b></div><div><small>HIGH-ANOMALY PIXELS</small><b>${totalHigh.toLocaleString()}</b></div><div><small>REGION HIGH-ANOMALY SHARE</small><b>${num(totalValid?100*totalHigh/totalValid:0,1)}%</b></div>`;$('anomaly-legacy-selected').innerHTML=`<h3>${esc(name)} · GPM August 2025</h3><dl class="anomaly-legacy-stats"><div><dt>High anomaly</dt><dd>${num(share,2)}%</dd></div><div><dt>Flagged pixels</dt><dd>${high.toLocaleString()}</dd></div><div><dt>Valid pixels</dt><dd>${valid.toLocaleString()}</dd></div><div><dt>Mean precipitation</dt><dd>${num(chosen.mean_precipitation_mm,2)} mm</dd></div><div><dt>Mean |z|</dt><dd>${num(chosen.mean_absolute_robust_z,2)}</dd></div><div><dt>Maximum |z|</dt><dd>${num(chosen.maximum_absolute_robust_z,2)}</dd></div></dl><p>Original GPM-only single-sensor summary, separate from the six-hazard detector.</p>`;drawDistrictMap($('anomaly-legacy-map'),rows,'GPM',true,name);bindMapTooltip($('anomaly-legacy-map'),rows,'GPM',true);};select.onchange=draw;draw();
  }
  function renderRuleCards(){
    const rules={FLOOD:'GPM high + SMAP soil moisture high',DROUGHT:'GPM low + SMAP low + LST high',HEAT_WAVE:'LST high while GPM and SMAP are near normal',VEGETATION_LOSS:'NDVI low + LST high + SMAP low',COLD_STRESS:'LST unusually low during warm-season months (Apr–Sep)',COMPOUND:'Three or more satellite signals anomalous together'};
    $('anomaly-rule-grid').innerHTML=HAZARD_ORDER.map(key=>{const h=D.hazards[key];return`<article style="--hazard-color:${h.color}"><b>${h.emoji} ${esc(h.label)}</b><span>${esc(rules[key]||h.description)}</span><small>${Number(h.monthsTriggered)} regional months · ${esc(h.action)}</small></article>`;}).join('');
  }
  function renderAll(){renderCatalogue();renderTabs();renderHazardPanel();}
  window.renderAnomalyPage=()=>{renderFrequency();const canvas=$('anomaly-hazard-map');if(canvas)drawDistrictMap(canvas,getDistrictRows(selected),selected);const legacy=$('anomaly-legacy-map');if(legacy&&legacy.offsetWidth)renderLegacy();};
  renderAll();
  document.querySelector('.anomaly-method')?.addEventListener('toggle',e=>{if(e.currentTarget.open)renderLegacy();});
  let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{renderFrequency();window.renderAnomalyPage();},120);});
})();
