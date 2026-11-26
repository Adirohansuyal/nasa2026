(() => {
  'use strict';

  const ROOT = 'assets/data/landcover/';
  const FILES = {
    annual: 'uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv',
    trends: 'uttarakhand_dynamic_world_class_trends_2016_2025.csv',
    highlights: 'uttarakhand_dynamic_world_trend_highlights_2016_2025.csv',
    worldcover: 'uttarakhand_worldcover_2021_districtwise.csv'
  };
  const COLORS = {
    Water:'#005A9C','Tree cover':'#006B3C',Grassland:'#A6BF00',
    'Flooded vegetation':'#8C4FA3',Cropland:'#D88700',Shrubland:'#88532D',
    'Built-up':'#C13728','Bare / sparse vegetation':'#777777','Snow / ice':'#A4CFE3',
    'Herbaceous wetland':'#439B8B',Mangroves:'#287A70','Moss / lichen':'#A1A84A',
    'Permanent water':'#005A9C'
  };
  const DYNAMIC_WORLD_CLASSES = ['Water','Tree cover','Grassland','Flooded vegetation','Cropland','Shrubland','Built-up','Bare / sparse vegetation','Snow / ice'];
  const CLASS_LABELS = {
    tree_cover:'Tree cover',trees:'Tree cover',shrubland:'Shrubland',shrub_and_scrub:'Shrubland',
    grassland:'Grassland',grass:'Grassland',cropland:'Cropland',crops:'Cropland',built_up:'Built-up',built:'Built-up',
    bare_sparse_vegetation:'Bare / sparse vegetation',bare:'Bare / sparse vegetation',snow_ice:'Snow / ice',
    snow_and_ice:'Snow / ice',permanent_water:'Permanent water',water:'Water',herbaceous_wetland:'Herbaceous wetland',
    flooded_vegetation:'Flooded vegetation',mangroves:'Mangroves',moss_lichen:'Moss / lichen'
  };
  const $ = id => document.getElementById(id);
  const getPref = key => { try { return sessionStorage.getItem(`landcover:${key}`); } catch { return null; } };
  const savePref = (key,value) => { try { sessionStorage.setItem(`landcover:${key}`,value); } catch {} };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const number = value => { const n = Number(value); return Number.isFinite(n) ? n : null; };
  const fmt = (value, digits=0) => number(value) === null ? '—' : Number(value).toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const signed = (value,digits=1) => number(value) === null ? '—' : `${Number(value)>0?'+':''}${fmt(value,digits)}`;
  const parseCSV = text => {
    const rows=[]; let row=[], field='', quoted=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(quoted){ if(c==='"'&&text[i+1]==='"'){field+='"';i++;} else if(c==='"')quoted=false; else field+=c; }
      else if(c==='"')quoted=true;
      else if(c===','){row.push(field);field='';}
      else if(c==='\n'){row.push(field.replace(/\r$/,''));rows.push(row);row=[];field='';}
      else field+=c;
    }
    if(field.length||row.length){row.push(field.replace(/\r$/,''));rows.push(row);}
    const headers=rows.shift()||[];
    return rows.filter(r=>r.length>1).map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]??''])));
  };
  const load = async name => {
    const response=await fetch(ROOT+FILES[name]);
    if(!response.ok) throw new Error(`Could not load ${FILES[name]} (${response.status})`);
    return parseCSV(await response.text());
  };
  let DATA=null, resizeTimer=null, playback=null, distributionPlayback=null, mapState=null, mapRequest=0, districtBoundariesPromise=null,districtMiniMapPromise=null,districtMiniMapMarkup='',labelCacheDistrict=null,labelCacheFrames=null,labelCacheWidth=0,labelCacheHeight=0;

  function districtSlug(value){return String(value).toLowerCase().trim().replace(/\s+/g,'-');}
  function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error(`Could not load ${url}`));image.src=url;});}
  async function loadStaticLabels(district,years,frames){
    if(labelCacheDistrict===district&&labelCacheFrames?.length===years.length)return {labels:labelCacheFrames,width:labelCacheWidth,height:labelCacheHeight};
    const images=await Promise.all(years.map(year=>loadImage(`assets/landcover_frames/${district}/${frames[String(year)].file}`)));
    const width=images[0].naturalWidth,height=images[0].naturalHeight;
    if(images.some(image=>image.naturalWidth!==width||image.naturalHeight!==height))throw new Error('Annual map frames have inconsistent dimensions.');
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const context=canvas.getContext('2d',{willReadFrequently:true});
    const labels=images.map(image=>{context.clearRect(0,0,width,height);context.drawImage(image,0,0);const pixels=context.getImageData(0,0,width,height).data;const values=new Uint8Array(width*height);for(let i=0;i<values.length;i++)values[i]=pixels[i*4];return values;});
    labelCacheDistrict=district;labelCacheFrames=labels;labelCacheWidth=width;labelCacheHeight=height;
    return {labels,width,height};
  }
  function colorStaticFrames(labels,width,height,classIndex,classColors){
    const years=Array.from({length:labels.length},(_,i)=>2015+i),canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const context=canvas.getContext('2d'),image=context.createImageData(width,height),maps={};
    const palette=[...classColors.map(hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16))),[236,0,140],[0,214,107],[0,207,255]];
    for(let frame=0;frame<labels.length;frame++){
      const current=labels[frame],previous=frame?labels[frame-1]:null,pixels=image.data;
      for(let i=0;i<current.length;i++){
        const value=current[i];let colorIndex=value;
        if(value>=9){pixels[i*4]=0;pixels[i*4+1]=0;pixels[i*4+2]=0;pixels[i*4+3]=0;continue;}
        if(frame===0){if(value===classIndex)colorIndex=9;}
        else if(previous[i]<9){if(value===classIndex&&previous[i]===classIndex)colorIndex=9;else if(value===classIndex)colorIndex=10;else if(previous[i]===classIndex)colorIndex=11;}
        const color=palette[colorIndex];pixels[i*4]=color[0];pixels[i*4+1]=color[1];pixels[i*4+2]=color[2];pixels[i*4+3]=255;
      }
      context.putImageData(image,0,0);maps[String(years[frame])]=canvas.toDataURL('image/png');
    }
    return maps;
  }

  function setOptions(node, values, selected){
    node.innerHTML=values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
    if(values.includes(selected))node.value=selected;
  }
  function setControlOptions(){
    const source=$('lc-source').value, annual=source==='annual';
    $('lc-year-wrap').hidden=!annual; $('lc-year').disabled=!annual;
    const years=annual?[...new Set(DATA.annual.map(r=>Number(r.year)))].sort((a,b)=>a-b):[2021];
    $('lc-year').innerHTML=years.map(y=>`<option value="${y}">${y}${y===2015?' · partial':''}</option>`).join('');
    $('lc-year').value=String(annual?2025:2021);
    const rows=annual?DATA.annual:DATA.worldcover;
    setOptions($('lc-district'),['Uttarakhand (statewide)',...new Set(rows.map(r=>r.district).filter(d=>d!=='Uttarakhand').sort())],'Uttarakhand (statewide)');
  }
  function activeRows(){
    const source=$('lc-source').value, year=Number($('lc-year').value), district=$('lc-district').value;
    const annual=source==='annual';
    let base=annual?DATA.annual.filter(r=>Number(r.year)===year):DATA.worldcover;
    const isState=district==='Uttarakhand (statewide)';
    const chosen=annual&&isState?base.filter(r=>r.district==='Uttarakhand'):isState?base:base.filter(r=>r.district===district);
    const districts=base.filter(r=>r.district!=='Uttarakhand');
    let composition=chosen;
    if(!annual&&isState){
      const groups=new Map();
      chosen.forEach(r=>{const key=r.cover_class;const g=groups.get(key)||{...r,area_ha:0,area_sqkm:0,pixel_count:0};g.area_ha+=Number(r.area_ha)||0;g.area_sqkm+=Number(r.area_sqkm)||0;g.pixel_count+=Number(r.pixel_count)||0;groups.set(key,g);});
      composition=[...groups.values()];
      const sum=composition.reduce((a,r)=>a+r.area_ha,0), pixels=composition.reduce((a,r)=>a+r.pixel_count,0);
      composition.forEach(r=>{r.pct_of_district=sum?100*r.area_ha/sum:0;r.pct_of_valid_area=pixels?100*r.pixel_count/pixels:0;delete r.data_coverage_pct;});
    }
    return {source,annual,year,district,isState,base,chosen,districts,composition};
  }
  function svgBars(target, rows, xField, title, pctField='pct_of_district'){
    if(!rows.length){target.innerHTML='<p class="lc-empty">No rows are available for this selection.</p>';return;}
    const width=680,rowH=34,left=180,right=140,top=12,height=top+rows.length*rowH+28;
    const max=Math.max(1,...rows.map(r=>Number(r[xField])||0)), plotW=width-left-right;
    const bars=rows.map((r,i)=>{
      const y=top+i*rowH, val=Number(r[xField])||0, w=Math.max(val?2:0,plotW*val/max), label=xField==='area_ha'?`${fmt(r.area_ha)} ha · ${fmt(r[pctField],1)}% district`:`${fmt(val,1)}% mapped · ${fmt(r.area_ha)} ha`;
      return `<g><text x="${left-10}" y="${y+17}" text-anchor="end" class="lc-axis-label">${esc(r.district||r.class_label||r.cover_class)}</text><rect x="${left}" y="${y+3}" width="${w.toFixed(2)}" height="20" rx="4" fill="${COLORS[r.class_label||r.cover_class]||'#79aaa4'}"><title>${esc(r.district||r.class_label)}: ${label}</title></rect><text x="${left+w+7}" y="${y+17}" class="lc-value-label">${esc(label)}</text></g>`;
    }).join('');
    target.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}"><text x="${left}" y="${height-6}" class="lc-axis-title">${esc(title)}</text>${bars}</svg>`;
  }
  function renderDistrictClassCharts(d,xField,area){
    const rows=d.districts.map(r=>({...r,class_label:r.class_label||r.cover_class})),present=[...new Set(rows.map(r=>r.class_label))],classes=[...DYNAMIC_WORLD_CLASSES.filter(c=>present.includes(c)),...present.filter(c=>!DYNAMIC_WORLD_CLASSES.includes(c)).sort()];
    $('lc-district-classes-title').textContent=`Every land-cover class by district · ${d.year}`;$('lc-district-classes-year').textContent=String(d.year);
    $('lc-class-district-grid').innerHTML=classes.map(cls=>{
      const data=rows.filter(r=>r.class_label===cls).sort((a,b)=>Number(b[xField])-Number(a[xField])),width=680,rowH=24,left=168,right=105,top=7,height=top+data.length*rowH+17,max=Math.max(1,...data.map(r=>Number(r[xField])||0)),plot=width-left-right,color=COLORS[cls]||'#79aaa4';
      const bars=data.map((r,i)=>{const value=Number(r[xField])||0,y=top+i*rowH,w=Math.max(value?1.5:0,plot*value/max),label=area?`${fmt(value,0)} ha`:`${fmt(value,1)}%`;return `<g><text x="${left-9}" y="${y+16}" text-anchor="end" class="lc-axis-label">${esc(r.district)}</text><rect x="${left}" y="${y+4}" width="${plot}" height="15" rx="4" fill="rgba(151,173,189,.075)"/><rect x="${left}" y="${y+4}" width="${w.toFixed(1)}" height="15" rx="4" fill="${color}" opacity=".94"><title>${esc(r.district)} · ${esc(cls)} · ${label}</title></rect><text x="${width-5}" y="${y+16}" text-anchor="end" class="lc-value-label">${label}</text></g>`;}).join('');
      return `<article class="lc-class-district-card" style="--class-accent:${color}"><h4><i></i>${esc(cls)}<span>${data.length} districts</span></h4><div class="lc-svg-chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(cls)} area by district in ${d.year}">${bars}</svg></div></article>`;
    }).join('')||'<p class="lc-empty">No district class records are available for this year.</p>';
  }
  function renderDistribution(){
    const d=activeRows(), annual=d.annual, key=$('lc-metric').value, area=key==='area';
    const composition=d.composition.map(r=>({...r,class_label:r.class_label||r.cover_class})).sort((a,b)=>Number(b[area?'area_ha':'pct_of_valid_area'])-Number(a[area?'area_ha':'pct_of_valid_area']));
    const metrics=annual?d.chosen[0]||{}:d.chosen[0]||{};
    let reference=0, coverage=0;
    if(annual){reference=Number(metrics.district_area_ha)||0;coverage=Number(metrics.data_coverage_pct)||0;}
    else if(d.isState){reference=d.chosen.reduce((s,r)=>s+(Number(r.area_ha)||0),0);coverage=d.chosen.reduce((s,r)=>s+(Number(r.data_coverage_pct)||0),0)/Math.max(1,new Set(d.chosen.map(r=>r.district)).size);}
    else {reference=d.chosen.reduce((s,r)=>s+(Number(r.area_ha)||0),0);coverage=Number(metrics.data_coverage_pct)||0;}
    const classes=[...new Set((annual?d.base:d.base).map(r=>r.class_label||r.cover_class))];
    $('lc-kpis').innerHTML=[['Districts',13],['Land-cover classes',classes.length],['Reference area',`${fmt(reference/100)} km²`],['Mapped coverage',`${fmt(coverage,1)}%`]].map(([a,b])=>`<div class="lc-kpi"><small>${esc(a)}</small><strong>${esc(b)}</strong></div>`).join('');
    $('lc-snapshot-note').textContent=annual?(d.year===2015?'2015 is a partial year: Dynamic World observations begin on 27 June.':'Annual Dynamic World · 500 m grid-sample estimates.'):'Baseline snapshot · ESA WorldCover v200 · 2021 · 10 m';
    $('lc-dist-year-slider').value=String(d.year);$('lc-dist-year-slider').disabled=!annual;$('lc-dist-play').disabled=!annual;$('lc-dist-year-label').textContent=annual?String(d.year):'2021';$('lc-dist-timeline-subtitle').textContent=`${d.district} · ${area?'area (ha)':'valid mapped area (%)'}`;
    if(!annual)stopDistributionPlayback();
    const validMetric=area?'area_ha':'pct_of_valid_area';
    svgBars($('lc-annual-class-chart'),composition.map(r=>({...r,district:r.class_label})),validMetric,area?'Class area (ha)':'Share of valid mapped area (%)');
    renderDistrictClassCharts(d,validMetric,area);
    const tableRows=d.composition.map(r=>({...r,class_label:r.class_label||r.cover_class}));
    $('lc-distribution-table').innerHTML=`<table class="lc-table"><thead><tr><th>District</th><th>Class</th><th>Area (ha)</th><th>Area (km²)</th><th>Valid mapped area (%)</th><th>District area (%)</th><th>Coverage (%)</th></tr></thead><tbody>${tableRows.map(r=>`<tr><td>${esc(d.district)}</td><td><i class="lc-swatch" style="--swatch:${COLORS[r.class_label]||'#79aaa4'}"></i>${esc(r.class_label)}</td><td>${fmt(r.area_ha,1)}</td><td>${fmt(Number(r.area_ha)/100,2)}</td><td>${fmt(r.pct_of_valid_area,2)}</td><td>${fmt(r.pct_of_district,2)}</td><td>${fmt(r.data_coverage_pct,1)}</td></tr>`).join('')}</tbody></table>`;
    const downloadRows=d.annual?d.base.filter(r=>r.district!=='Uttarakhand'):d.base;
    $('lc-download-selected').onclick=()=>downloadCSV(downloadRows,`uttarakhand_${d.annual?'dynamic_world_'+d.year:'worldcover_2021'}_district_classes.csv`);
    $('lc-download-current').onclick=()=>downloadCSV(d.annual?DATA.annual:DATA.worldcover,d.annual?'uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv':'uttarakhand_worldcover_2021_districtwise.csv');
  }
  function stopDistributionPlayback(){if(distributionPlayback){clearInterval(distributionPlayback);distributionPlayback=null;}const button=$('lc-dist-play');if(button){button.textContent='▶ Play';button.setAttribute('aria-label','Play annual timeline');}}
  function startDistributionPlayback(){
    if(distributionPlayback||$('lc-source').value!=='annual'||$('lc-view-distribution').hidden)return;
    if(Number($('lc-year').value)>=2025){$('lc-year').value='2015';$('lc-dist-year-slider').value='2015';renderDistribution();}
    const button=$('lc-dist-play');button.textContent='Ⅱ Pause';button.setAttribute('aria-label','Pause annual timeline');
    distributionPlayback=setInterval(()=>{const current=Number($('lc-year').value),next=current>=2025?2015:current+1;$('lc-year').value=String(next);$('lc-dist-year-slider').value=String(next);renderDistribution();},900);
  }
  function downloadCSV(rows,name){
    if(!rows?.length)return;
    const headers=Object.keys(rows[0]), csv=[headers.join(','),...rows.map(r=>headers.map(h=>`"${String(r[h]??'').replace(/"/g,'""')}"`).join(','))].join('\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);
  }
  function renderMapTimeline(districtName,classLabel){
    const panel=$('lt-map-panel');
    if(!panel||$('lc-view-trends').hidden||!panel.getClientRects().length)return;
    const classIndex={'Water':0,'Tree cover':1,'Grassland':2,'Flooded vegetation':3,'Cropland':4,'Shrubland':5,'Built-up':6,'Bare / sparse vegetation':7,'Snow / ice':8}[classLabel];
    if(classIndex===undefined){$('lt-map-status').textContent='This class is not available in Dynamic World.';return;}
    const request=++mapRequest;
    if(playback){clearTimeout(playback);playback=null;}
    $('lt-map-play').textContent='▶ Play';$('lt-map-play').setAttribute('aria-label','Play timeline');
    $('lt-map-status').textContent='Loading pre-generated annual maps from Netlify…';
    $('lt-map-area').textContent='Loading static map frames…';
    const district=districtName==='Uttarakhand (statewide)'?'Uttarakhand':districtName;
    const classColors=['#005A9C','#006B3C','#A6BF00','#8C4FA3','#D88700','#88532D','#C13728','#777777','#A4CFE3'];
    if(!window.L){$('lt-map-status').textContent='Leaflet did not load. Check the network connection and refresh.';return;}
    if(!mapState){
      const map=L.map('lt-map',{zoomControl:true,scrollWheelZoom:true});
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,className:'basemap-tiles',attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
      mapState={map,group:L.layerGroup().addTo(map),currentLayer:null,currentIndex:null,request:0,frameRequest:0,fadeFrame:null,fadePrevious:null,focusDistrict:null};
    }
    const state=mapState;
    state.request++;
    if(state.fadeFrame)cancelAnimationFrame(state.fadeFrame);
    if(state.fadePrevious)state.group.removeLayer(state.fadePrevious);
    state.fadeFrame=null;state.fadePrevious=null;
    state.group.clearLayers();state.currentLayer=null;state.currentIndex=null;state.focusDistrict=null;
    const focusSelectedDistrict=featureCollection=>{
      if(request!==mapRequest||state.focusDistrict===district)return;
      state.group.clearLayers();
      const focus=L.geoJSON(featureCollection,{interactive:false,style:{color:'transparent',weight:0,fillColor:'#10241b',fillOpacity:.28}}).addTo(state.group);
      L.geoJSON(featureCollection,{interactive:false,style:{color:'#101713',weight:7,opacity:.9,fill:false}}).addTo(state.group);
      const outline=L.geoJSON(featureCollection,{interactive:false,style:{color:'#ffe08a',weight:3,opacity:1,fill:false,dashArray:'8 5'}}).addTo(state.group);
      state.focusDistrict=district;
      state.map.invalidateSize(false);
      state.map.fitBounds(outline.getBounds(),{padding:[24,24],maxZoom:12});
    };
    if(!districtBoundariesPromise){
      districtBoundariesPromise=fetch('research/data/dynamic_world_maps/districts.geojson')
        .then(response=>{if(!response.ok)throw new Error('Local district boundaries could not be loaded.');return response.json();});
    }
    districtBoundariesPromise
      .then(collection=>{
        const features=district==='Uttarakhand'
          ?collection.features
          :collection.features.filter(feature=>feature.properties?.GAUL2_NAME===district);
        if(!features.length)throw new Error(`Boundary not found for ${district}.`);
        focusSelectedDistrict({type:'FeatureCollection',features});
      })
      .catch(error=>{if(request===mapRequest)$('lt-map-status').textContent=error.message;});
    const staticDistrict=districtSlug(district),manifestUrl=`assets/landcover_frames/${staticDistrict}/manifest.json`;
    fetch(manifestUrl)
      .then(async response=>{if(!response.ok)throw new Error(`Could not load static map manifest (${response.status}).`);return response.json();})
      .then(async manifest=>{
        const years=manifest.years||Array.from({length:11},(_,i)=>2015+i);
        const raster=await loadStaticLabels(staticDistrict,years,manifest.frames);
        return {years,maps:colorStaticFrames(raster.labels,raster.width,raster.height,classIndex,classColors),bounds:Object.fromEntries(years.map(year=>[String(year),manifest.frames[String(year)].bounds])),outline:null,stableColor:'#EC008C'};
      })
      .then(async data=>{
        if(!data.outline){
          const collection=await districtBoundariesPromise;
          const features=district==='Uttarakhand'?collection.features:collection.features.filter(feature=>feature.properties?.GAUL2_NAME===district);
          if(!features.length)throw new Error(`Boundary not found for ${district}.`);
          data.outline={type:'FeatureCollection',features};
        }
        return data;
      })
      .then(data=>{
        if(request!==mapRequest)return;
        const years=data.years||Array.from({length:11},(_,i)=>2015+i);
        const areas=new Map(DATA.annual.filter(r=>r.district===district&&r.class_label===classLabel).map(r=>[Number(r.year),number(r.area_ha)]));
        const slider=$('lt-map-slider'),yearLabel=$('lt-map-year'),areaLabel=$('lt-map-area'),button=$('lt-map-play');
        slider.min='0';slider.max=String(years.length-1);slider.value='0';
        const otherClasses=DYNAMIC_WORLD_CLASSES.filter(label=>label!==classLabel);
        $('lt-map-legend').innerHTML=`<span><i style="background:${data.stableColor||'#EC008C'}"></i><span id="lt-map-stable-label">Class in baseline year</span></span><span><i style="background:#00D66B"></i>New this year</span><span><i style="background:#00CFFF"></i>No longer this class</span>${otherClasses.map(label=>`<span><i style="background:${COLORS[label]}"></i>${esc(label)}</span>`).join('')}`;
        state.request++;
        const districtAlreadyFocused=state.focusDistrict===district;
        state.group.clearLayers();state.currentLayer=null;state.currentIndex=null;
        const districtFocus=L.geoJSON(data.outline,{interactive:false,style:{color:'transparent',weight:0,fillColor:'#10241b',fillOpacity:.28}}).addTo(state.group);
        const casing=L.geoJSON(data.outline,{interactive:false,style:{color:'#101713',weight:7,opacity:.9,fill:false}}).addTo(state.group);
        const outline=L.geoJSON(data.outline,{interactive:false,style:{color:'#ffe08a',weight:3,opacity:1,fill:false,dashArray:'8 5'}}).addTo(state.group);
        const bounds=outline.getBounds();
        const fit=()=>{state.map.invalidateSize(false);state.map.fitBounds(bounds,{padding:[24,24],maxZoom:12});};
        state.focusDistrict=district;
        if(!districtAlreadyFocused){requestAnimationFrame(()=>requestAnimationFrame(fit));setTimeout(fit,250);}
        const mapAreas=years.map(year=>areas.get(Number(year))??null);
        const showYear=index=>new Promise(resolve=>{
          if(index===state.currentIndex&&state.currentLayer){resolve(true);return;}
          const frameRequest=++state.frameRequest;
          if(state.fadeFrame)cancelAnimationFrame(state.fadeFrame);
          if(state.fadePrevious&&state.fadePrevious!==state.currentLayer)state.group.removeLayer(state.fadePrevious);
          state.fadeFrame=null;state.fadePrevious=null;
          if(state.currentLayer)state.currentLayer.setOpacity(.98);
          const prior=state.currentIndex;
          const previousLayer=state.currentLayer;
          const incoming=L.imageOverlay(data.maps[String(years[index])],data.bounds[String(years[index])],{opacity:0});
          let settled=false;
          const finish=ready=>{if(settled)return;settled=true;resolve(ready);};
          incoming.once('load',()=>{
            if(request!==mapRequest||frameRequest!==state.frameRequest){state.group.removeLayer(incoming);return finish(false);}
            state.group.addLayer(incoming);incoming.setOpacity(0);
            state.currentLayer=incoming;state.currentIndex=index;slider.value=String(index);
            state.fadePrevious=previousLayer&&previousLayer!==incoming?previousLayer:null;
            const year=Number(years[index]);yearLabel.textContent=year===2015?'2015 · partial':String(year);
            const label=$('lt-map-stable-label');if(label)label.textContent=year===2015?'Class in baseline year':'Present in both years';
            const area=mapAreas[index],previous=index>0?mapAreas[index-1]:null;
            areaLabel.textContent=area===null?'area estimate unavailable':previous===null?`${fmt(area)} ha · baseline`:`${fmt(area)} ha · ${area-previous>0?'+':''}${fmt(area-previous)} ha vs prev year`;
            casing.bringToFront();outline.bringToFront();
            const fadeStarted=performance.now(),fadeDuration=240;
            const crossfade=now=>{
              if(request!==mapRequest||frameRequest!==state.frameRequest){state.group.removeLayer(incoming);return finish(false);}
              const progress=Math.min(1,(now-fadeStarted)/fadeDuration);
              incoming.setOpacity(.98*progress);
              if(previousLayer&&previousLayer!==incoming)previousLayer.setOpacity(.98*(1-progress));
              if(progress<1)state.fadeFrame=requestAnimationFrame(crossfade);
              else{state.fadeFrame=null;if(previousLayer&&previousLayer!==incoming)state.group.removeLayer(previousLayer);state.fadePrevious=null;finish(true);}
            };
            state.fadeFrame=requestAnimationFrame(crossfade);
          });
          incoming.once('error',()=>{
            state.group.removeLayer(incoming);
            if(prior!==null){slider.value=String(prior);yearLabel.textContent=prior===0?'2015 · partial':String(years[prior]);}
            areaLabel.textContent=`${years[index]} image failed; keeping the last loaded map visible.`;
            $('lt-map-status').textContent=`The local ${years[index]} map image failed to render; playback stopped on the last loaded frame.`;
            finish(false);
          });
          state.group.addLayer(incoming);
          if(prior===null){yearLabel.textContent=`Loading ${years[index]}…`;areaLabel.textContent='Loading first annual map…';}
        });
        const stop=()=>{if(playback){clearTimeout(playback);playback=null;}button.textContent='▶ Play';button.setAttribute('aria-label','Play timeline');};
        const advance=async()=>{if(!playback)return;const next=state.currentIndex===null?0:(state.currentIndex+1)%years.length;const ready=await showYear(next);if(!ready){stop();return;}if(playback)playback=setTimeout(advance,900);};
        slider.oninput=()=>{stop();showYear(Number(slider.value));};
        button.onclick=()=>{if(playback){stop();return;}button.textContent='Ⅱ Pause';button.setAttribute('aria-label','Pause timeline');playback=setTimeout(advance,0);};
        state.map.off('resize',fit);state.map.on('resize',fit);window.addEventListener('resize',fit,{once:true});
        $('lt-map-status').textContent=`Pre-generated 100 m Dynamic World V1 map · ${districtName} · same-class pixels stay in the class color, new pixels turn green, and pixels that leave the class turn blue.`;
        button.textContent='Ⅱ Pause';button.setAttribute('aria-label','Pause timeline');playback=setTimeout(advance,0);
      })
      .catch(error=>{if(request!==mapRequest)return;$('lt-map-status').textContent=`${error.message} Static map frames could not be loaded from this deployment.`;});
  }
  function rowsForDistrict(name){return DATA.trends.filter(r=>r.district===name);}
  function renderTrends(){
    const district=$('lt-district').value, cls=$('lt-class').value, measure=$('lt-measure').value;
    const selected=rowsForDistrict(district), state=rowsForDistrict('Uttarakhand');
    const areaKey='sen_slope_ha_per_year',shareKey='sen_slope_share_percentage_points_per_year',key=measure==='area'?areaKey:shareKey,unit=measure==='area'?'ha/year':'percentage points/year';
    const chosen=selected.find(r=>r.class_label===cls)||{},stateClass=state.find(r=>r.class_label===cls)||{};
    const highlights=DATA.highlights.filter(r=>r.district===district),up=highlights.find(r=>r.highlight==='largest increase')||{},down=highlights.find(r=>r.highlight==='largest decrease')||{};
    $('lt-kpis').innerHTML=[['District',district],['Class',cls],['District trend',`${signed(chosen[key],1)} ${unit}`],['Uttarakhand trend',`${signed(stateClass[key],1)} ${unit}`]].map(([a,b],i)=>{const trendValue=i===2?Number(chosen[key]):i===3?Number(stateClass[key]):null;return `<div class="lc-kpi lc-trend-kpi lc-trend-kpi-${i+1}"><small>${esc(a)}</small><strong${trendValue===null?'':` class="${trendValue>0?'is-positive':trendValue<0?'is-negative':'is-neutral'}"`}>${esc(b)}</strong></div>`;}).join('');
    $('lt-fastest').innerHTML=[['Fastest estimated increase',up],['Fastest estimated decrease',down]].map(([title,r])=>`<article class="lc-highlight"><small>${title}</small><strong>${esc(r.class_label||'—')}</strong><b>${signed(r.sen_slope_ha_per_year,1)} ha/year</b><span>FDR q = ${number(r.fdr_q_value)?.toFixed(3)||'—'} · ${esc(r.trend_evidence||'')}</span></article>`).join('');
    const upState=state.slice().sort((a,b)=>(Number(b[areaKey])||0)-(Number(a[areaKey])||0))[0]||{},downState=state.slice().sort((a,b)=>(Number(a[areaKey])||0)-(Number(b[areaKey])||0))[0]||{};
    $('lt-state-summary').innerHTML=`<b>Uttarakhand overall:</b> largest estimated increase is <b>${esc(upState.class_label||'—')}</b> (${signed(upState[areaKey],1)} ha/year); largest decrease is <b>${esc(downState.class_label||'—')}</b> (${signed(downState[areaKey],1)} ha/year).`;
    const annualRows=DATA.annual.filter(r=>r.district===district&&r.class_label===cls).sort((a,b)=>Number(a.year)-Number(b.year));
    const stateAnnual=DATA.annual.filter(r=>r.district==='Uttarakhand'&&r.class_label===cls),latestShared=[...annualRows].reverse().find(r=>stateAnnual.some(s=>Number(s.year)===Number(r.year))),stateYear=latestShared&&stateAnnual.find(r=>Number(r.year)===Number(latestShared.year)),districtShare=latestShared&&Number(stateYear.area_ha)>0?100*Number(latestShared.area_ha)/Number(stateYear.area_ha):null,slopeValue=Number(chosen[areaKey]),trendDirection=slopeValue>0?'Increasing':slopeValue<0?'Decreasing':'No clear trend',trendClass=slopeValue>0?'is-positive':slopeValue<0?'is-negative':'is-neutral';
    $('lt-line-summary').innerHTML=`<div class="lc-line-stat ${trendClass}"><small>${esc(cls)} trend · 2016–2025</small><strong>${trendDirection}</strong><span>${signed(slopeValue,1)} ha/year Sen slope</span></div><div class="lc-line-stat"><small>${esc(district)} contribution to Uttarakhand</small><strong>${districtShare===null?'—':`${fmt(districtShare,1)}%`}</strong><span>${latestShared?`${fmt(latestShared.area_ha,0)} of ${fmt(stateYear.area_ha,0)} ha in ${latestShared.year}`:'Latest shared year unavailable'}</span></div>`;
    $("lt-map-title").textContent=`${cls} map timeline · ${district}`;
    renderMapTimeline(district,cls);
    drawLineChart(annualRows,chosen[areaKey]);
    drawTrendBars(selected,key,unit);
    drawTrendBars(state,key,unit,true);
    $('lt-district-table').innerHTML=trendTable(selected,key);
    $('lt-state-table').innerHTML=trendTable(state,key,true);
    $('lt-download-annual').onclick=()=>downloadCSV(DATA.annual,FILES.annual);
    $('lt-download-trends').onclick=()=>downloadCSV(DATA.trends,FILES.trends);
  }
  function drawLineChart(rows,slope){
    const canvas=$('lt-line'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;
    canvas.width=Math.max(1,rect.width*ratio);canvas.height=Math.max(1,rect.height*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);
    const w=rect.width,h=rect.height,p={l:62,r:22,t:22,b:38};ctx.clearRect(0,0,w,h);
    const vals=rows.map(r=>Number(r.area_ha)).filter(Number.isFinite);if(!vals.length)return;
    const years=rows.map(r=>Number(r.year)),x0=Math.min(...years),x1=Math.max(...years),lo=Math.min(...vals),hi=Math.max(...vals),span=Math.max(1,hi-lo),y0=lo-span*.1,y1=hi+span*.16;
    const X=x=>p.l+(x-x0)/(x1-x0||1)*(w-p.l-p.r),Y=y=>h-p.b-(y-y0)/(y1-y0)*(h-p.t-p.b);
    ctx.strokeStyle='rgba(160,180,193,.2)';ctx.fillStyle='#9eacba';ctx.font='11px system-ui';
    for(let i=0;i<=4;i++){const v=y0+(y1-y0)*i/4,y=Y(v);ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.fillText(fmt(v),4,y+4);}
    ctx.beginPath();rows.forEach((r,i)=>{const x=X(Number(r.year)),y=Y(Number(r.area_ha));if(!i)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.strokeStyle='#43bf94';ctx.lineWidth=2.8;ctx.stroke();
    rows.forEach(r=>{const x=X(Number(r.year)),y=Y(Number(r.area_ha));ctx.beginPath();ctx.arc(x,y,3.8,0,Math.PI*2);ctx.fillStyle='#9de1bf';ctx.fill();ctx.fillStyle='#9eacba';ctx.font='10px system-ui';ctx.fillText(String(r.year)+(Number(r.year)===2015?'*':''),x-13,h-13);});
    const trendRows=rows.filter(r=>Number(r.year)>=2016),intercept=trendRows.length?trendRows.map(r=>Number(r.area_ha)-Number(slope)*(Number(r.year))).sort((a,b)=>a-b)[Math.floor(trendRows.length/2)]:null;
    if(Number.isFinite(intercept)&&Number.isFinite(Number(slope))){ctx.setLineDash([6,5]);ctx.beginPath();ctx.moveTo(X(2016),Y(intercept+Number(slope)*2016));ctx.lineTo(X(2025),Y(intercept+Number(slope)*2025));ctx.strokeStyle='#ed9c66';ctx.lineWidth=2;ctx.stroke();ctx.setLineDash([]);}
  }
  function drawTrendBars(rows,key,unit,statewide=false){
    const target=$(statewide?'lt-state-chart':'lt-trend-chart'),data=rows.slice().sort((a,b)=>Number(a[key])-Number(b[key]));
    const width=900,rowH=32,left=280,right=132,top=10,height=top+data.length*rowH+20,lo=Math.min(0,...data.map(r=>Number(r[key])||0)),hi=Math.max(0,...data.map(r=>Number(r[key])||0)),span=Math.max(1,hi-lo),plot=width-left-right,x0=left+plot*(0-lo)/span,valueX=width-8;
    target.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Sen slopes by land-cover class"><line x1="${x0}" y1="0" x2="${x0}" y2="${height-15}" stroke="rgba(180,200,210,.35)"/>${data.map((r,i)=>{const v=Number(r[key])||0,x=left+plot*(v-lo)/span,y=top+i*rowH,color=v>0?'#29a879':v<0?'#df6b64':'#8994a6',barX=Math.min(x,x0),barW=Math.max(2,Math.abs(x-x0)),baseline=DATA.annual.filter(a=>a.district===r.district&&a.class_label===r.class_label&&Number(a.year)>=2016).map(a=>Number(a.area_ha)).sort((a,b)=>a-b),base=baseline.length?baseline[Math.floor(baseline.length/2)]:0,rate=base?(Number(r.sen_slope_ha_per_year)||0)/base*100:null;return `<g><text x="${left-12}" y="${y+17}" text-anchor="end" class="lc-axis-label">${esc(r.class_label)}</text><rect x="${barX}" y="${y+3}" width="${barW}" height="18" rx="3" fill="${color}"><title>${esc(r.class_label)} · ${signed(v,2)} ${esc(unit)} · q=${Number(r.fdr_q_value).toFixed(4)}</title></rect><text x="${valueX}" y="${y+17}" text-anchor="end" class="lc-value-label">${rate===null?'n/a':`${signed(rate,2)}%/yr`}</text></g>`;}).join('')}</svg>`;
  }
  function renderDistrictRanking(){
    if(!DATA)return;
    const classOrder=['Built-up','Cropland','Tree cover','Grassland','Shrubland','Bare / sparse vegetation','Water','Flooded vegetation','Snow / ice'],available=[...new Set(DATA.trends.filter(r=>r.district!=='Uttarakhand').map(r=>r.class_label))],classes=[...available].sort((a,b)=>{const ai=classOrder.indexOf(a),bi=classOrder.indexOf(b);return (ai<0?99:ai)-(bi<0?99:bi)||a.localeCompare(b);});
    $('lt-rank-all').innerHTML=classes.map(cls=>{
      const ranked=DATA.trends.filter(r=>r.district!=='Uttarakhand'&&r.class_label===cls&&Number.isFinite(Number(r.sen_slope_ha_per_year))).sort((a,b)=>Number(b.sen_slope_ha_per_year)-Number(a.sen_slope_ha_per_year));
      if(!ranked.length)return '';
      const mapIcon=name=>`<svg class="lc-district-map" viewBox="0 0 100 72" role="img" aria-label="${esc(name)} district outline"><use href="#district-shape-${name.toLowerCase().replace(/[^a-z0-9]+/g,'-')}"></use></svg>`,high=ranked[0],low=ranked[ranked.length-1],highValue=Number(high.sen_slope_ha_per_year),lowValue=Number(low.sen_slope_ha_per_year),highLabel=highValue>0?'Largest increase':highValue<0?'Least decline':'No change',lowLabel=lowValue<0?'Largest decrease':lowValue>0?'Smallest increase':'No change',highKind=highValue<0?'is-down':'is-up',lowKind=lowValue<0?'is-down':'is-up',color=COLORS[cls]||'#79aaa4',stat=(label,row,kind)=>`<div class="lc-class-rank-stat ${kind}"><small>${label}</small><div class="lc-class-rank-district">${mapIcon(row.district)}<strong>${esc(row.district)}</strong></div><b>${signed(row.sen_slope_ha_per_year,1)} <small>ha/year</small></b><span>${signed(row.relative_change_pct_2016_2025,1)}% fitted · q ${number(row.fdr_q_value)?.toFixed(2)||'—'}</span></div>`,table=`<table class="lc-table lc-ranking-table"><thead><tr><th>Rank</th><th>District</th><th>Sen slope</th><th>Share slope</th><th>Fitted change</th><th>FDR q</th></tr></thead><tbody>${ranked.map((r,i)=>{const q=number(r.fdr_q_value);return `<tr><td><span class="lc-rank-number">${String(i+1).padStart(2,'0')}</span></td><td class="lc-rank-district"><span class="lc-rank-district-inner">${mapIcon(r.district)}<span>${esc(r.district)}</span></span></td><td class="${Number(r.sen_slope_ha_per_year)>0?'lc-rank-up':'lc-rank-down'}">${signed(r.sen_slope_ha_per_year,1)} <small>ha/yr</small></td><td>${signed(r.sen_slope_share_percentage_points_per_year,2)} <small>pp/yr</small></td><td>${signed(r.relative_change_pct_2016_2025,1)}%</td><td><span class="lc-evidence ${q!==null&&q<.05?'is-supported':''}">${q===null?'—':q.toPrecision(3)}</span></td></tr>`;}).join('')}</tbody></table>`;
      return `<article class="lc-class-rank-card" style="--class-accent:${color}"><header><span class="lc-class-rank-swatch"></span><h3>${esc(cls)}</h3><small>2016—2025</small></header><div class="lc-class-rank-stats">${stat(highLabel,high,highKind)}${stat(lowLabel,low,lowKind)}</div><details class="lc-class-rank-details" open><summary>All ${ranked.length} district rankings</summary><div class="lc-table-wrap">${table}</div></details></article>`;
    }).join('');
    if(districtMiniMapMarkup){$('lt-rank-all').insertAdjacentHTML('afterbegin',districtMiniMapMarkup);}
    else if(!districtMiniMapPromise){districtMiniMapPromise=fetch('research/data/dynamic_world_maps/districts.geojson').then(response=>{if(!response.ok)throw new Error('District outlines unavailable');return response.json();}).then(collection=>{
      districtMiniMapMarkup=`<svg class="lc-map-symbol-library" aria-hidden="true" focusable="false"><defs>${collection.features.map(feature=>{const name=feature.properties?.GAUL2_NAME,geometry=feature.geometry;if(!name||!geometry)return '';let rings=[];if(geometry.type==='Polygon')rings=geometry.coordinates;else if(geometry.type==='MultiPolygon')rings=geometry.coordinates.flat();const points=rings.flat(),lons=points.map(p=>Number(p[0])*Math.cos(30*Math.PI/180)),lats=points.map(p=>Number(p[1])),minX=Math.min(...lons),maxX=Math.max(...lons),minY=Math.min(...lats),maxY=Math.max(...lats),scale=Math.min(88/Math.max(1e-9,maxX-minX),58/Math.max(1e-9,maxY-minY)),midX=(minX+maxX)/2,midY=(minY+maxY)/2,d=rings.map(ring=>{const step=Math.max(1,Math.ceil(ring.length/120)),sampled=ring.filter((_,i)=>i%step===0);if(sampled.at(-1)!==ring.at(-1))sampled.push(ring.at(-1));return sampled.map((p,i)=>`${i?'L':'M'}${(50+(Number(p[0])*Math.cos(30*Math.PI/180)-midX)*scale).toFixed(1)} ${(36-(Number(p[1])-midY)*scale).toFixed(1)}`).join(' ')+' Z';}).join(' '),id=name.toLowerCase().replace(/[^a-z0-9]+/g,'-');return `<symbol id="district-shape-${id}" viewBox="0 0 100 72"><path d="${d}" fill="currentColor" fill-rule="evenodd" stroke="rgba(220,235,242,.68)" stroke-width="1.4" stroke-linejoin="round"/></symbol>`;}).join('')}</defs></svg>`;
      if(DATA&&!$('lc-view-all-districts').hidden)renderDistrictRanking();
    }).catch(()=>{});}
  }
  function trendTable(rows,key,statewide=false){
    const sorted=rows.slice().sort((a,b)=>(Number(b[key])||0)-(Number(a[key])||0));
    return `<table class="lc-table"><thead><tr><th>Class</th><th>Sen slope (ha/year)</th><th>Share slope (pp/year)</th><th>Fitted change (%)</th>${statewide?'':'<th>Mann–Kendall p</th>'}<th>FDR q</th><th>Trend evidence</th><th>Mean coverage (%)</th></tr></thead><tbody>${sorted.map(r=>`<tr><td><i class="lc-swatch" style="--swatch:${COLORS[r.class_label]||'#79aaa4'}"></i>${esc(r.class_label)}</td><td>${signed(r.sen_slope_ha_per_year,2)}</td><td>${signed(r.sen_slope_share_percentage_points_per_year,3)}</td><td>${signed(r.relative_change_pct_2016_2025,2)}</td>${statewide?'':`<td>${number(r.mann_kendall_p_value)?.toPrecision(3)||'—'}</td>`}<td>${number(r.fdr_q_value)?.toPrecision(3)||'—'}</td><td>${esc(r.trend_evidence)}</td><td>${fmt(r.mean_data_coverage_pct,1)}</td></tr>`).join('')}</tbody></table>`;
  }
  function renderAll(){if(!DATA)return;renderDistribution();renderTrends();}
  async function init(){
    try{
      const [annual,trends,highlights,worldcover]=await Promise.all([load('annual'),load('trends'),load('highlights'),load('worldcover')]);
      worldcover.forEach(r=>{r.class_label=CLASS_LABELS[r.cover_class]||r.cover_class;});
      DATA={annual,trends,highlights,worldcover};
      const districtNames=[...new Set(trends.map(r=>r.district).filter(d=>d!=='Uttarakhand'))].sort();
      setOptions($('lt-district'),districtNames,districtNames.includes(getPref('district'))?getPref('district'):districtNames.includes('Nainital')?'Nainital':districtNames[0]);
      const trendClasses=[...new Set(trends.map(r=>r.class_label))].sort();
      setOptions($('lt-class'),trendClasses,trendClasses.includes(getPref('class'))?getPref('class'):'Tree cover');
      if(['area','share'].includes(getPref('measure'))) $('lt-measure').value=getPref('measure');
      $('lc-source').addEventListener('change',()=>{stopDistributionPlayback();setControlOptions();renderAll();if($('lc-source').value==='annual')startDistributionPlayback();});
      ['lc-year','lc-district','lc-metric'].forEach(id=>$(id).addEventListener('change',renderAll));
      $('lc-dist-year-slider').addEventListener('input',()=>{stopDistributionPlayback();$('lc-year').value=$('lc-dist-year-slider').value;renderDistribution();});
      $('lc-dist-play').addEventListener('click',()=>{if(distributionPlayback)stopDistributionPlayback();else startDistributionPlayback();});
      [['lt-district','district'],['lt-class','class'],['lt-measure','measure']].forEach(([id,key])=>$(id).addEventListener('change',()=>{savePref(key,$(id).value);renderTrends();}));
      document.querySelectorAll('[data-lc-view]').forEach(btn=>btn.addEventListener('click',()=>{
        if(btn.dataset.lcView!=='distribution')stopDistributionPlayback();
        document.querySelectorAll('[data-lc-view]').forEach(b=>{b.classList.toggle('active',b===btn);b.setAttribute('aria-selected',String(b===btn));});
        savePref('view',btn.dataset.lcView);
        $('lc-view-distribution').hidden=btn.dataset.lcView!=='distribution';$('lc-view-trends').hidden=btn.dataset.lcView!=='trends';$('lc-view-all-districts').hidden=btn.dataset.lcView!=='all-districts';
        if(btn.dataset.lcView==='trends')renderTrends();else if(btn.dataset.lcView==='all-districts')renderDistrictRanking();else renderDistribution();
        if(btn.dataset.lcView==='distribution')startDistributionPlayback();
      }));
      setControlOptions();
      const initialView=['trends','all-districts'].includes(getPref('view'))?getPref('view'):'distribution';
      document.querySelectorAll('[data-lc-view]').forEach(btn=>{const active=btn.dataset.lcView===initialView;btn.classList.toggle('active',active);btn.setAttribute('aria-selected',String(active));});
      $('lc-view-distribution').hidden=initialView!=='distribution';$('lc-view-trends').hidden=initialView!=='trends';$('lc-view-all-districts').hidden=initialView!=='all-districts';
      renderAll();
      if(initialView==='all-districts')renderDistrictRanking();
      if(initialView==='distribution')startDistributionPlayback();
      window.renderLandcoverPage=()=>requestAnimationFrame(()=>{renderAll();if(!$('lc-view-trends').hidden)renderTrends();if(!$('lc-view-distribution').hidden)startDistributionPlayback();});
      window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{renderDistribution();drawLineChart(DATA.annual.filter(r=>r.district===$('lt-district').value&&r.class_label===$('lt-class').value),rowsForDistrict($('lt-district').value).find(r=>r.class_label===$('lt-class').value)?.sen_slope_ha_per_year);},120);});
    }catch(error){$('lc-load-error').hidden=false;$('lc-load-error').textContent=`Land-cover data could not be loaded: ${error.message}. Open this page through the project web server so the CSV files can be fetched.`;}
  }
  document.addEventListener('DOMContentLoaded',init,{once:true});
})();
