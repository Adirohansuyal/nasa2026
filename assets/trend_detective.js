/* Trend Detective uses the same monthly satellite-grid bundle as Earth Observation. */
(()=>{
  const data=window.EO_REAL_DATA, $=id=>document.getElementById(id);
  if(!data||!$('td-variable'))return;
  const vars=data.variables, months=data.months, names={lst:'Land surface temperature',ndvi:'Vegetation greenness',smap_am:'Morning soil moisture',smap_pm:'Evening soil moisture',gpm:'Precipitation'};
  const units={lst:'K',ndvi:'index',smap_am:'m³/m³',smap_pm:'m³/m³',gpm:'mm/month'};
  const palette={lst:'#ef6461',ndvi:'#31c48d',smap_am:'#6c8ee6',smap_pm:'#a78bfa',gpm:'#35c9d0'};
  const districtFeatures=data.districts?.features||[], nlon=data.lon.length, nlat=data.lat.length;
  let selectedDistrict='all', lastRows=[];const seriesCache=new Map();
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function source(key,q,mi){const v=vars[key];return key==='gpm'?(v.gpm||[])[mi]:(v[q]||[])[mi];}
  function avg(vals){const a=vals.filter(Number.isFinite);return a.length?a.reduce((s,x)=>s+x,0)/a.length:null;}
  function pointInRing(x,y,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))inside=!inside;}return inside;}
  function pointInPoly(x,y,poly){return pointInRing(x,y,poly[0])&&!poly.slice(1).some(r=>pointInRing(x,y,r));}
  function featuresAt(x,y){for(const f of districtFeatures){const g=f.geometry, polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;if(polys.some(p=>pointInPoly(x,y,p)))return f.properties.district_name||f.properties.shapeName;}return null;}
  const cellDistrict=(()=>{const out=[];for(let r=0;r<nlat;r++)for(let c=0;c<nlon;c++){const idx=r*nlon+c;out[idx]=data.inside[idx]?featuresAt(data.lon[c],data.lat[r]):null;}return out;})();
  function monthlySeries(key,q,district){const cacheKey=`${key}|${q}|${district}`;if(seriesCache.has(cacheKey))return seriesCache.get(cacheKey);const out=[];for(let mi=0;mi<months.length;mi++){const grid=source(key,q,mi)||[];const vals=[];for(let i=0;i<grid.length;i++){if(!Number.isFinite(grid[i]))continue;if(district==='all'?(data.inside[i]===1):(cellDistrict[i]===district))vals.push(grid[i]);}out.push(avg(vals));}seriesCache.set(cacheKey,out);return out;}
  function regression(y){const a=y.map((v,i)=>[i,v]).filter(p=>Number.isFinite(p[1]));if(a.length<3)return {ols:null,sen:null,intercept:null,valid:a.length};const mx=a.reduce((s,p)=>s+p[0],0)/a.length,my=a.reduce((s,p)=>s+p[1],0)/a.length;let num=0,den=0;for(const [x,v] of a){num+=(x-mx)*(v-my);den+=(x-mx)**2;}const ols=den?num/den:0, slopes=[];for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++)slopes.push((a[j][1]-a[i][1])/(a[j][0]-a[i][0]));slopes.sort((x,z)=>x-z);const mid=slopes.length>>1,sen=slopes.length%2?slopes[mid]:(slopes[mid-1]+slopes[mid])/2;return {ols,sen,intercept:my-ols*mx,valid:a.length};}
  function erf(x){const sign=x<0?-1:1,a=Math.abs(x),t=1/(1+.3275911*a),v=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-a*a);return sign*v;}
  function normalP(z){return Math.max(0,Math.min(1,1-erf(Math.abs(z)/Math.SQRT2)));}
  function mmk(values){const y=values.filter(Number.isFinite),n=y.length;if(n<4)return {p:1,tau:0,rho:0,n};let s=0;for(let i=0;i<n-1;i++)for(let j=i+1;j<n;j++)s+=Math.sign(y[j]-y[i]);const counts=new Map();y.forEach(v=>counts.set(v,(counts.get(v)||0)+1));let ties=0;counts.forEach(c=>ties+=c*(c-1)*(2*c+5));const variance=(n*(n-1)*(2*n+5)-ties)/18;if(variance<=0)return {p:1,tau:0,rho:0,n};const pairs=[];for(let i=0;i<n-1;i++)for(let j=i+1;j<n;j++)pairs.push((y[j]-y[i])/(j-i));pairs.sort((a,b)=>a-b);const slope=pairs.length%2?pairs[pairs.length>>1]:(pairs[(pairs.length>>1)-1]+pairs[pairs.length>>1])/2;const residual=y.map((v,i)=>v-slope*i),rank=ranks(residual);const aa=rank.slice(0,-1),bb=rank.slice(1),rho=pearson(aa,bb)||0,correction=rho>0?1+2*(n-1)/n*rho:1,corrected=variance*correction,z=s>0?(s-1)/Math.sqrt(corrected):s<0?(s+1)/Math.sqrt(corrected):0;return {p:normalP(z),tau:s/(.5*n*(n-1)),rho,n};}
  function fdr(results){const sorted=results.map((r,i)=>({p:r.p,i})).sort((a,b)=>a.p-b.p),q=Array(results.length).fill(1);let next=1;for(let k=sorted.length-1;k>=0;k--){next=Math.min(next,sorted[k].p*sorted.length/(k+1));q[sorted[k].i]=Math.min(1,next);}return q;}
  const reportCache=new Map();
  function trendReports(q){if(reportCache.has(q))return reportCache.get(q);const regional=Object.keys(names).map(key=>({key,stats:regression(monthlySeries(key,q,'all')),test:mmk(monthlySeries(key,q,'all'))}));const regionalQ=fdr(regional.map(r=>r.test));regional.forEach((r,i)=>{const official=q==='strict'?window.EP_TREND_REGIONAL_STATS?.[r.key]:null;if(official){r.official=true;r.stats.sen=official.trend_slope_per_year/12;r.stats.valid=official.valid_months;r.test={p:official.modified_mk_p_value,tau:official.modified_mk_tau,rho:official.lag1_autocorrelation,n:official.valid_months};r.q=official.fdr_adjusted_p_value_modified;}else r.q=regionalQ[i];});const districts=[];for(const feature of districtFeatures){const name=feature.properties.district_name||feature.properties.shapeName;for(const key of Object.keys(names)){const raw=monthlySeries(key,q,name),base=Array.from({length:12},(_,m)=>avg(raw.filter((_,i)=>Number(months[i].slice(5,7))===m+1))),anomaly=raw.map((v,i)=>Number.isFinite(v)?v-base[Number(months[i].slice(5,7))-1]:null),valid=anomaly.filter(Number.isFinite),stats=regression(anomaly),test=valid.length>=48?mmk(anomaly):{p:1,tau:0,rho:0,n:valid.length};districts.push({name,key,raw,anomaly,stats,test,n:valid.length});}}const dq=fdr(districts.map(d=>d.test));districts.forEach((d,i)=>d.q=dq[i]);const result={regional,districts};reportCache.set(q,result);return result;}
  function rolling12(y){return y.map((_,i)=>{const a=y.slice(Math.max(0,i-5),Math.min(y.length,i+7)).filter(Number.isFinite);return a.length>=6?avg(a):null;});}
  function fmt(x,d=3){return Number.isFinite(x)?`${x>0?'+':''}${x.toFixed(d)}`:'—';}
  function canvasSetup(id){const c=$(id);if(!c)return null;const rect=c.getBoundingClientRect();if(rect.width<40||rect.height<40)return null;const dpr=window.devicePixelRatio||1;c.width=Math.round(rect.width*dpr);c.height=Math.round(rect.height*dpr);const ctx=c.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);return {c,ctx,w:rect.width,h:rect.height};}
  function drawSeries(key,values,stats){
    const setup=canvasSetup('td-timeseries');if(!setup)return;
    const {c,ctx,w,h}=setup,p={l:58,r:18,t:22,b:34},pw=w-p.l-p.r,ph=h-p.t-p.b,roll=rolling12(values),all=[...values,...roll].filter(Number.isFinite);
    if(!all.length)return;
    let lo=Math.min(...all),hi=Math.max(...all);const pad=(hi-lo)*.12||1;lo-=pad;hi+=pad;
    const X=i=>p.l+i/(values.length-1)*pw,Y=v=>p.t+(hi-v)/(hi-lo)*ph;
    const draw=progress=>{
      const last=Math.max(1,Math.floor((values.length-1)*progress));
      ctx.clearRect(0,0,w,h);ctx.fillStyle='#0f1a2e';ctx.fillRect(0,0,w,h);ctx.font='11px sans-serif';ctx.fillStyle='#8393a7';ctx.strokeStyle='#263752';ctx.textAlign='right';
      for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4,y=Y(v);ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.fillText(v.toFixed(2),p.l-8,y+4);}
      ctx.textAlign='center';for(let i=0;i<months.length;i+=12){const x=X(i);ctx.fillText(months[i].slice(0,4),x,h-10);}
      const line=(arr,color,width,dash=[])=>{ctx.beginPath();let started=false;for(let i=0;i<=last;i++){const v=arr[i];if(!Number.isFinite(v)){started=false;continue;}if(!started){ctx.moveTo(X(i),Y(v));started=true;}else ctx.lineTo(X(i),Y(v));}ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.stroke();ctx.setLineDash([]);};
      line(values,'rgba(160,181,205,.48)',1);line(roll,palette[key],2.8);if(stats.ols!==null)line(values.map((_,i)=>stats.intercept+stats.ols*i),'#e9a34b',1.8,[6,4]);
      const med=avg(values);if(stats.sen!==null)line(values.map((_,i)=>med+stats.sen*(i-(values.length-1)/2)),'#a78bfa',1.8,[2,4]);
      ctx.textAlign='left';ctx.fillStyle='#a0b5cd';ctx.fillText('Monthly observation',p.l,14);ctx.fillStyle=palette[key];ctx.fillText('12-month mean',p.l+135,14);ctx.fillStyle='#e9a34b';ctx.fillText('OLS',p.l+250,14);ctx.fillStyle='#a78bfa';ctx.fillText('Sen slope',p.l+300,14);
    };
    const tooltip=$('td-chart-tooltip');
    c.onmousemove=e=>{const rect=c.getBoundingClientRect(),wrap=c.parentElement,box=wrap.getBoundingClientRect(),x=Math.max(p.l,Math.min(w-p.r,e.clientX-rect.left)),ratio=(x-p.l)/pw,i=Math.max(0,Math.min(values.length-1,Math.round(ratio*(values.length-1))));tooltip.innerHTML=`<strong>${months[i]}</strong><span>Monthly: ${fmt(values[i],3)} ${units[key]}</span><span>12-month mean: ${fmt(roll[i],3)} ${units[key]}</span>`;tooltip.style.left=`${Math.max(12,Math.min(e.clientX-box.left+14,box.width-225))}px`;tooltip.style.top='14px';tooltip.hidden=false;};
    c.onmouseleave=()=>{tooltip.hidden=true;};
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(reduced){draw(1);return;}
    const start=performance.now(),duration=1100;
    const frame=now=>{const t=Math.min(1,(now-start)/duration),ease=1-(1-t)*(1-t);draw(ease);if(t<1)requestAnimationFrame(frame);};
    requestAnimationFrame(frame);
  }
  function ranks(values){const sorted=values.map((v,i)=>({v,i})).sort((a,b)=>a.v-b.v),out=Array(values.length);for(let i=0;i<sorted.length;){let j=i+1;while(j<sorted.length&&sorted[j].v===sorted[i].v)j++;const rank=(i+j-1)/2+1;for(let k=i;k<j;k++)out[sorted[k].i]=rank;i=j;}return out;}
  function pearson(a,b){const ma=avg(a),mb=avg(b);let num=0,da=0,db=0;for(let i=0;i<a.length;i++){const x=a[i]-ma,y=b[i]-mb;num+=x*y;da+=x*x;db+=y*y;}return da&&db?num/Math.sqrt(da*db):null;}
  function drawMultiVar(q,district){
    /* ── 1. Compute standardised departures for every signal ── */
    const signals=Object.keys(names).map(key=>{
      const s=monthlySeries(key,q,district),
        base=Array.from({length:12},(_,m)=>avg(s.filter((_,i)=>Number(months[i].slice(5,7))===m+1))),
        depart=s.map((v,i)=>Number.isFinite(v)?v-base[Number(months[i].slice(5,7))-1]:null),
        valid=depart.filter(Number.isFinite),
        mu=avg(valid),
        sd=Math.sqrt(avg(valid.map(v=>(v-mu)**2))||0);
      return {key,values:depart.map(v=>Number.isFinite(v)&&sd?(v-mu)/sd:null)};
    });

    /* ── 2. Build area charts — one per signal ── */
    const container=$('td-multivar-heatmap');
    container.innerHTML='';
    container.style.cssText='overflow:visible;display:flex;flex-direction:column;gap:6px;';

    const CHART_H=72,EMOJI={LST:'🌡️',NDVI:'🌿',SMAP_AM:'💧',SMAP_PM:'💧',GPM:'🌧️'};
    const dpr=window.devicePixelRatio||1;

    signals.forEach(({key,values})=>{
      const color=palette[key];
      const wrap=document.createElement('div');
      wrap.style.cssText='display:grid;grid-template-columns:148px 1fr;align-items:center;gap:0;';

      /* label */
      const lbl=document.createElement('div');
      lbl.style.cssText=`font-size:11px;font-weight:700;color:${color};line-height:1.3;padding-right:8px;text-align:right;`;
      lbl.innerHTML=`<span style="font-size:16px;display:block;margin-bottom:2px">${EMOJI[key]||'🔵'}</span>${names[key]}`;
      wrap.appendChild(lbl);

      /* canvas */
      const c=document.createElement('canvas');
      const parentW=container.getBoundingClientRect().width||800;
      const W=Math.max(300,parentW-158);
      c.width=W*dpr; c.height=CHART_H*dpr;
      c.style.width=W+'px'; c.style.height=CHART_H+'px';
      c.style.borderRadius='8px';
      c.style.cursor='crosshair';
      wrap.appendChild(c);

      const ctx=c.getContext('2d');
      ctx.scale(dpr,dpr);

      const valid=values.filter(Number.isFinite);
      const maxAbs=Math.max(2.5,...valid.map(v=>Math.abs(v)));
      const PAD={l:4,r:4,t:8,b:14};
      const pw=W-PAD.l-PAD.r, ph=CHART_H-PAD.t-PAD.b;
      const zero=PAD.t+ph/2;
      const xOf=i=>PAD.l+(i/(values.length-1))*pw;
      const yOf=v=>zero-((v||0)/maxAbs)*(ph/2);

      const NORMAL_BAND=0.5; /* ±0.5σ = "normal" zone */

      function draw(){
        ctx.clearRect(0,0,W,CHART_H);
        ctx.fillStyle='rgba(15,26,46,0.72)';
        ctx.beginPath(); ctx.roundRect(0,0,W,CHART_H,8); ctx.fill();

        /* normal band: grey shaded zone ±0.5σ around zero */
        const bandTop=yOf(NORMAL_BAND), bandBot=yOf(-NORMAL_BAND);
        ctx.fillStyle='rgba(180,200,220,0.08)';
        ctx.fillRect(PAD.l, bandTop, pw, bandBot-bandTop);
        /* dashed border lines for the band */
        ctx.setLineDash([3,4]);
        ctx.strokeStyle='rgba(180,200,220,0.22)'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(PAD.l,bandTop); ctx.lineTo(PAD.l+pw,bandTop); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(PAD.l,bandBot); ctx.lineTo(PAD.l+pw,bandBot); ctx.stroke();
        ctx.setLineDash([]);
        /* "Normal" label inside band */
        ctx.fillStyle='rgba(180,200,220,0.35)'; ctx.font='7px Urbanist,sans-serif';
        ctx.textAlign='left'; ctx.fillText('Normal',PAD.l+4,(bandTop+bandBot)/2+2.5);

        /* year gridlines */
        months.forEach((m,i)=>{
          if(m.slice(5,7)==='01'){
            const x=xOf(i);
            ctx.beginPath(); ctx.moveTo(x,PAD.t); ctx.lineTo(x,CHART_H-PAD.b);
            ctx.strokeStyle='rgba(42,63,95,0.6)'; ctx.lineWidth=1; ctx.stroke();
            ctx.fillStyle='#687a90'; ctx.font='8px Urbanist,sans-serif';
            ctx.textAlign='center'; ctx.fillText(m.slice(0,4),x,CHART_H-2);
          }
        });

        /* zero line */
        ctx.beginPath(); ctx.moveTo(PAD.l,zero); ctx.lineTo(PAD.l+pw,zero);
        ctx.strokeStyle='rgba(200,220,255,0.35)'; ctx.lineWidth=1; ctx.stroke();

        /* positive fill — only outside normal band */
        ctx.beginPath();
        let started=false, lastX=PAD.l;
        values.forEach((v,i)=>{
          if(v===null||v<=NORMAL_BAND){if(started){ctx.lineTo(lastX,yOf(NORMAL_BAND));ctx.closePath();ctx.fillStyle='rgba(239,100,97,0.30)';ctx.fill();ctx.beginPath();started=false;}return;}
          const x=xOf(i);lastX=x;
          if(!started){ctx.moveTo(x,yOf(NORMAL_BAND));started=true;}
          ctx.lineTo(x,yOf(v));
        });
        if(started){ctx.lineTo(lastX,yOf(NORMAL_BAND));ctx.closePath();ctx.fillStyle='rgba(239,100,97,0.30)';ctx.fill();}

        /* negative fill — only outside normal band */
        ctx.beginPath();
        started=false;
        values.forEach((v,i)=>{
          if(v===null||v>=-NORMAL_BAND){if(started){ctx.lineTo(lastX,yOf(-NORMAL_BAND));ctx.closePath();ctx.fillStyle='rgba(67,133,197,0.30)';ctx.fill();ctx.beginPath();started=false;}return;}
          const x=xOf(i);lastX=x;
          if(!started){ctx.moveTo(x,yOf(-NORMAL_BAND));started=true;}
          ctx.lineTo(x,yOf(v));
        });
        if(started){ctx.lineTo(lastX,yOf(-NORMAL_BAND));ctx.closePath();ctx.fillStyle='rgba(67,133,197,0.30)';ctx.fill();}

        /* signal line */
        ctx.beginPath();
        let inLine=false;
        values.forEach((v,i)=>{
          if(v===null){inLine=false;return;}
          const x=xOf(i),y=yOf(v);
          inLine?ctx.lineTo(x,y):ctx.moveTo(x,y);
          inLine=true;
        });
        ctx.strokeStyle=color; ctx.lineWidth=1.6; ctx.lineJoin='round'; ctx.stroke();
      }
      draw();

      /* hover tooltip */
      const tip=document.createElement('div');
      tip.style.cssText='position:fixed;background:rgba(7,16,27,.92);border:1px solid rgba(121,170,164,.35);border-radius:7px;padding:6px 10px;font-size:11px;color:#e5edf8;pointer-events:none;display:none;white-space:nowrap;z-index:9999;';
      document.body.appendChild(tip);
      c.addEventListener('mousemove',e=>{
        const rect=c.getBoundingClientRect();
        const mx=(e.clientX-rect.left)*(W/rect.width);
        const idx=Math.round((mx-PAD.l)/pw*(values.length-1));
        const i=Math.max(0,Math.min(values.length-1,idx));
        const v=values[i];
        const mo=months[i]||'';
        tip.style.display='block';
        tip.style.left=(e.clientX+12)+'px';
        tip.style.top=(e.clientY-28)+'px';
        if(v===null){
          tip.innerHTML=`<b>${mo}</b> · ${names[key]}<br><span style="color:#687a90">No data</span>`;
        } else {
          const absV=Math.abs(v);
          let label,col;
          if(absV<=NORMAL_BAND){label='Normal range';col='#b3c8d6';}
          else if(v>NORMAL_BAND){label=`${absV.toFixed(2)}\u03c3 above normal`;col='#ff8c86';}
          else{label=`${absV.toFixed(2)}\u03c3 below normal`;col='#6ec6f5';}
          tip.innerHTML=`<b>${mo}</b> · ${names[key]}<br><span style="color:${col}">${label}</span>`;
        }
      });
      c.addEventListener('mouseleave',()=>{tip.style.display='none';});

      container.appendChild(wrap);
    });


  }

  function drawSeason(key,q,district){
    const setup=canvasSetup('td-season-chart');if(!setup)return;
    const {ctx,w,h}=setup,p={l:48,r:12,t:18,b:28},pw=w-p.l-p.r,ph=h-p.t-p.b,series=monthlySeries(key,q,district),means=Array.from({length:12},(_,m)=>avg(series.filter((_,i)=>Number(months[i].slice(5,7))===m+1))),valid=means.filter(Number.isFinite);
    if(!valid.length)return;
    const lo=Math.min(...valid),hi=Math.max(...valid),range=hi-lo||1,labels=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const draw=progress=>{ctx.clearRect(0,0,w,h);ctx.fillStyle='#0f1a2e';ctx.fillRect(0,0,w,h);ctx.font='10px sans-serif';ctx.textAlign='center';for(let m=0;m<12;m++){const x=p.l+(m+.5)*pw/12,bh=(means[m]-lo)/range*(ph-15),barProgress=Math.max(0,Math.min(1,progress*12-m));ctx.fillStyle=palette[key];ctx.fillRect(x-pw/30,p.t+ph-bh*barProgress,pw/15,bh*barProgress);ctx.fillStyle='#aab8cc';ctx.fillText(labels[m],x,h-7);}ctx.fillStyle='#aab8cc';ctx.textAlign='left';ctx.fillText(`Usual monthly mean (${units[key]})`,p.l,12);};
    if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){draw(1);return;}
    const start=performance.now(),duration=700,frame=now=>{const t=Math.min(1,(now-start)/duration);draw(1-(1-t)*(1-t));if(t<1)requestAnimationFrame(frame);};requestAnimationFrame(frame);
  }
  function strongestPositiveLink(key,q,districtName,rep){
    const target=rep.districts.find(d=>d.key===key&&d.name===districtName)?.anomaly;
    if(!target)return null;
    let best=null;
    for(const otherKey of Object.keys(names)){
      if(otherKey===key)continue;
      const other=rep.districts.find(d=>d.key===otherKey&&d.name===districtName)?.anomaly;
      if(!other)continue;
      const a=[],b=[];
      target.forEach((v,i)=>{if(Number.isFinite(v)&&Number.isFinite(other[i])){a.push(v);b.push(other[i]);}});
      if(a.length<24)continue;
      const score=pearson(ranks(a),ranks(b));
      if(score!==null&&score>=(best?.score??-Infinity))best={key:otherKey,score,n:a.length};
    }
    return best;
  }
  function drawMap(key,q){
    const setup=canvasSetup('td-district-map');if(!setup)return;
    const {c,ctx,w,h}=setup,rep=trendReports(q),tip=$('td-map-tooltip');
    const districts=districtFeatures.map(f=>{const name=f.properties.district_name||f.properties.shapeName,d=rep.districts.find(x=>x.key===key&&x.name===name),slope=d?.stats?.sen,rate=Number.isFinite(slope)?slope*120:null,link=strongestPositiveLink(key,q,name,rep);return {f,name,d,rate,link};});
    ctx.clearRect(0,0,w,h);ctx.fillStyle='#0b1420';ctx.fillRect(0,0,w,h);
    const significant=districts.filter(d=>d.d&&d.d.q<.05),maxIncrease=Math.max(0,...significant.filter(d=>d.rate>0).map(d=>d.rate)),maxDecrease=Math.max(0,...significant.filter(d=>d.rate<0).map(d=>Math.abs(d.rate)));
    const latCenter=(Math.min(...data.lat)+Math.max(...data.lat))/2*Math.PI/180,cosLat=Math.cos(latCenter),coords=[];
    for(const d of districts){const geom=d.f.geometry,polys=geom.type==='Polygon'?[geom.coordinates]:geom.coordinates;for(const poly of polys)for(const ring of poly)for(const [x,y] of ring)coords.push([x*cosLat,y]);}
    if(!coords.length){ctx.fillStyle='#aab8cc';ctx.textAlign='center';ctx.font='14px Urbanist, sans-serif';ctx.fillText('District boundary data is unavailable.',w/2,h/2);return;}
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;for(const [x,y] of coords){if(x<minX)minX=x;if(x>maxX)maxX=x;if(y<minY)minY=y;if(y>maxY)maxY=y;}
    const pad=20,legendH=54,availW=w-pad*2,availH=h-pad*2-legendH,scale=Math.min(availW/(maxX-minX),availH/(maxY-minY));
    const mapW=(maxX-minX)*scale,mapH=(maxY-minY)*scale,left=(w-mapW)/2,top=pad+(availH-mapH)/2;
    const project=(x,y)=>[left+(x*cosLat-minX)*scale,top+(maxY-y)*scale];
    const pathByDistrict=new Map(),centers=[];
    const mix=(a,b,t)=>{const A=parseInt(a.slice(1),16),B=parseInt(b.slice(1),16),ar=(A>>16)&255,ag=(A>>8)&255,ab=A&255,br=(B>>16)&255,bg=(B>>8)&255,bb=B&255;return `rgb(${Math.round(ar+(br-ar)*t)},${Math.round(ag+(bg-ag)*t)},${Math.round(ab+(bb-ab)*t)})`;};
    for(const d of districts){
      const geom=d.f.geometry,polys=geom.type==='Polygon'?[geom.coordinates]:geom.coordinates,path=new Path2D();let cx=0,cy=0,n=0;
      for(const poly of polys)for(const ring of poly){ring.forEach(([x,y],i)=>{const [px,py]=project(x,y);i?path.lineTo(px,py):path.moveTo(px,py);if(i<ring.length-1){cx+=px;cy+=py;n++;}});path.closePath();}
      pathByDistrict.set(d.name,{path,d});const hasSlope=Number.isFinite(d.rate),ok=hasSlope&&d.d&&d.d.q<.05,isUp=hasSlope&&d.rate>0,isDown=hasSlope&&d.rate<0,t=Math.min(1,Math.abs(d.rate||0)/(isUp?maxIncrease:maxDecrease||1));
      const glow=ok?(isUp?'rgba(255,126,99,.76)':'rgba(81,214,229,.78)'):'rgba(98,132,164,.08)';
      ctx.save();ctx.strokeStyle=glow;ctx.lineWidth=ok?7:1.2;ctx.shadowColor=glow;ctx.shadowBlur=ok?15:0;ctx.stroke(path);ctx.restore();
      if(d.link?.score>=0.5){ctx.save();ctx.strokeStyle='rgba(99,224,176,.98)';ctx.lineWidth=3.2;ctx.shadowColor='rgba(99,224,176,.9)';ctx.shadowBlur=10;ctx.stroke(path);ctx.restore();}
      ctx.fillStyle=!hasSlope||(!isUp&&!isDown)?'#263b53':ok?(isUp?mix('#ffb19a','#df5149',.28+.72*t):mix('#a1e9ef','#258ebf',.28+.72*t)):(isUp?'#79594e':'#425d73');
      ctx.fill(path,'evenodd');ctx.strokeStyle=ok?(isUp?'rgba(255,196,175,.94)':'rgba(176,244,247,.94)'):hasSlope?(isUp?'rgba(222,164,142,.78)':'rgba(137,174,199,.78)'):'rgba(164,189,210,.72)';ctx.lineWidth=ok?1.35:1;ctx.stroke(path);
      if(n)centers.push({name:d.name,x:cx/n,y:cy/n});
    }
    ctx.save();ctx.font='600 9px Urbanist, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.lineWidth=3;ctx.strokeStyle='rgba(8,16,28,.88)';ctx.fillStyle='#f3f6fb';
    centers.forEach(pt=>{ctx.strokeText(pt.name,pt.x,pt.y);ctx.fillText(pt.name,pt.x,pt.y);});ctx.restore();
    const reliableUp=districts.filter(d=>Number.isFinite(d.rate)&&d.rate>0&&d.d?.q<.05).length;
    const reliableDown=districts.filter(d=>Number.isFinite(d.rate)&&d.rate<0&&d.d?.q<.05).length;
    const estimatedUp=districts.filter(d=>Number.isFinite(d.rate)&&d.rate>0&&!(d.d?.q<.05)).length;
    const estimatedDown=districts.filter(d=>Number.isFinite(d.rate)&&d.rate<0&&!(d.d?.q<.05)).length;
    const noDirection=districts.length-reliableUp-reliableDown-estimatedUp-estimatedDown;
    const coMoving=districts.filter(d=>d.link?.score>=0.5).length;
    $('td-map-status').textContent=`${names[key]} · Green outlines mark ${coMoving} district${coMoving===1?'':'s'} where this signal moves in the same direction as at least one other signal (score ≥ +0.50; pattern only, not proof of cause). Rising with supporting evidence: ${reliableUp}; falling with supporting evidence: ${reliableDown}. May rise: ${estimatedUp}; may fall: ${estimatedDown} (not confirmed, q ≥ 0.05). No clear direction: ${noDirection}.`;
    const legendItems=[
      {label:`Rising ${reliableUp}`,swatch:'#ff9d82',glow:'#ff7e63'},
      {label:`Falling ${reliableDown}`,swatch:'#72dce8',glow:'#51d6e5'},
      {label:`May rise ${estimatedUp}`,swatch:'#79594e',text:'#dab8a8'},
      {label:`May fall ${estimatedDown}`,swatch:'#425d73',text:'#a9c2d4'},
      {label:`Moves together ≥ +0.50 (${coMoving})`,swatch:'#63e0b0',glow:'#63e0b0'},
      {label:`No clear direction ${noDirection}`,swatch:'#263b53',text:'#aab8cc'}
    ];
    ctx.save();ctx.font='10px Urbanist, sans-serif';ctx.textBaseline='middle';
    const gap=14,itemWidths=legendItems.map(item=>11+7+ctx.measureText(item.label).width),rows=[[]];let rowWidth=0;
    legendItems.forEach((item,i)=>{const width=itemWidths[i];if(rowWidth&&rowWidth+gap+width>w-24){rows.push([]);rowWidth=0;}rows.at(-1).push({item,width});rowWidth+=width+(rows.at(-1).length>1?gap:0);});
    rows.forEach((row,r)=>{const total=row.reduce((sum,entry)=>sum+entry.width,0)+gap*(row.length-1);let x=Math.max(8,(w-total)/2),y=h-12-(rows.length-1-r)*14;row.forEach(({item,width})=>{ctx.shadowBlur=item.glow?8:0;ctx.shadowColor=item.glow||'transparent';ctx.fillStyle=item.swatch;ctx.fillRect(x,y-5,11,10);ctx.shadowBlur=0;ctx.fillStyle=item.text||'#dce5f0';ctx.fillText(item.label,x+18,y);x+=width+gap;});});ctx.restore();
    // Separate magnitude scales match the two independent fills used for
    // statistically supported rises and falls. Keep them in the map's open
    // right margin so they don't cover a district.
    if(w>=700){
      const sx=w-112,sy=Math.max(28,top+(mapH-150)/2),sw=100,sh=150;
      ctx.save();ctx.fillStyle='rgba(7,16,27,.88)';ctx.strokeStyle='rgba(151,180,210,.24)';ctx.lineWidth=1;
      ctx.beginPath();ctx.roundRect(sx,sy,sw,sh,9);ctx.fill();ctx.stroke();
      ctx.font='600 8px Urbanist, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#cbd7e6';ctx.fillText(`Sen / decade · ${units[key]}`,sx+sw/2,sy+13);
      const columns=[
        {x:sx+28,label:'↑',topColor:'#df5149',bottomColor:'#ffb19a',max:maxIncrease,value:maxIncrease?`+${maxIncrease.toPrecision(2)}`:'—'},
        {x:sx+70,label:'↓',topColor:'#258ebf',bottomColor:'#a1e9ef',max:maxDecrease,value:maxDecrease?`−${maxDecrease.toPrecision(2)}`:'—'}
      ];
      for(const col of columns){ctx.fillStyle=col.topColor;ctx.fillText(col.label,col.x+4,sy+28);const gy=sy+39,gh=88,grad=ctx.createLinearGradient(0,gy,0,gy+gh);grad.addColorStop(0,col.topColor);grad.addColorStop(1,col.bottomColor);ctx.fillStyle=grad;ctx.fillRect(col.x,gy,8,gh);ctx.fillStyle='#aab8cc';ctx.font='7px Urbanist, sans-serif';ctx.fillText(col.value,col.x+4,sy+136);ctx.fillText('0',col.x+4,sy+146);}
      ctx.restore();
    }
    c.onmousemove=e=>{
      const rect=c.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;
      // Resolve the pointer in geographic coordinates. Canvas hit testing can
      // disagree with the visible polygons after DPR scaling on Retina displays.
      const px=x*(w/rect.width),py=y*(h/rect.height);
      const lon=(px-left+minX)/(scale*cosLat),lat=maxY-(py-top)/scale;
      const name=featuresAt(lon,lat),hit=name?districts.find(d=>d.name===name):null;
      if(!hit){tip.style.display='none';c.style.cursor='crosshair';return;}
      c.style.cursor='pointer';const good=hit.d&&hit.d.q<.05,dir=Number.isFinite(hit.rate)?(hit.rate>0?'increase':hit.rate<0?'decrease':'no clear direction'):'no slope estimate',certainty=good?'reliable':Number.isFinite(hit.rate)?'not reliable at q < 0.05':'';
      const linkText=hit.link?.score>=0.5?`<br><span>Moves with ${esc(names[hit.link.key])} · score +${hit.link.score.toFixed(2)} (${hit.link.n} months)</span>`:'<br><span>No strong same-direction link found for this signal.</span>';
      tip.innerHTML=`<strong>${esc(hit.name)}</strong>${esc(dir)}${certainty?` · ${esc(certainty)}`:''}<br><span>Sen ${fmt(hit.rate,3)} ${esc(units[key])}/decade · q = ${hit.d?.q?.toPrecision(3)||'—'} · ${hit.d?.n||0} months</span>${linkText}`;
      tip.style.display='block';const box=c.parentElement.getBoundingClientRect(),offsetX=rect.left-box.left,offsetY=rect.top-box.top;
      tip.style.left=`${Math.min(Math.max(12,offsetX+x+18),box.width-250)}px`;tip.style.top=`${Math.min(Math.max(12,offsetY+y+14),box.height-100)}px`;
    };
    c.onmouseleave=()=>{tip.style.display='none';c.style.cursor='crosshair';};
  }
  function render(){const key=$('td-variable').value,q=$('td-quality').value,district=selectedDistrict,meta=vars[key],values=monthlySeries(key,q,district),stats=regression(values),valid=values.filter(Number.isFinite),mean=avg(valid),reports=trendReports(q),regional=reports.regional.find(r=>r.key===key),districtReport=district==='all'?null:reports.districts.find(r=>r.key===key&&r.name===district),result=districtReport||regional,trendSlope=districtReport?districtReport.stats.sen:regional.stats.sen,change=trendSlope===null?null:trendSlope*120,first=valid[0],last=valid[valid.length-1],significant=result.q<.05,direction=significant?(result.test.tau>0?'Increasing':'Decreasing'):'No reliable trend';lastRows=values.map((v,i)=>({month:months[i],value:v}));
    $('td-overview-note').textContent=`${district==='all'?'Uttarakhand':district} · ${q==='strict'?'trend direction adjusted for multiple tests':'trend recalculated with relaxed data quality'} · select a signal to inspect`;
    const activeSignal=$('td-variable').value;
    $('td-overview').innerHTML=reports.regional.map(r=>{
      const rate=Number.isFinite(r.stats.sen)?r.stats.sen*120:null,sig=r.q<.05,dir=sig?(r.test.tau>0?'Increasing':'Decreasing'):'No reliable trend';
      const directionColor=sig?(r.test.tau>0?'#63e0b0':'#ff8c86'):'#b8c6d9',qLabel=r.q<.001?r.q.toExponential(1):r.q.toFixed(3);
      return `<button type="button" class="td-overview-card${r.key===activeSignal?' is-selected':''}" data-var="${r.key}" style="--td-signal-color:${palette[r.key]};--td-direction-color:${directionColor}" aria-pressed="${r.key===activeSignal}"><span class="td-overview-label">${names[r.key]}</span><span class="td-overview-trend"><i aria-hidden="true"></i>${dir}</span><span class="td-overview-rate">${fmt(rate,3)} ${units[r.key]}<small>per decade</small></span><span class="td-overview-meta"><span>q ${qLabel}</span><span>${r.stats.valid||0} months</span></span></button>`;
    }).join('');
    $('td-overview').querySelectorAll('[data-var]').forEach(b=>b.addEventListener('click',()=>{$('td-variable').value=b.dataset.var;render();}));
    $('td-summary').innerHTML=`<b>${esc(district==='all'?'Uttarakhand':district)} · ${esc(meta.label)}</b> · ${valid.length} usable monthly readings from ${months[0]} to ${months.at(-1)}. Choose a signal or district to explore how the pattern changes.`;
    const areaName=district==='all'?'Uttarakhand':district;
    $('td-multivar-title').textContent=`${areaName} · How environmental signals change together`;
    $('td-map-title').textContent=`${meta.label} · Where is it changing?`;
    $('td-chart-title').textContent=`${district==='all'?'Uttarakhand':district} · ${meta.label} through time`;$('td-chart-caption').textContent=`The faint line shows monthly readings; the brighter line smooths short-term ups and downs. The dashed lines show two trend estimates. District evidence uses seasonally adjusted readings.`;
    $('td-kpis').innerHTML=[['Trend signal',direction,`Adjusted trend test · lag-1 autocorrelation ${fmt(result.test.rho,2)}`,'What this means',direction==='Increasing'?'The signal shows a consistent pattern of increasing over time.':'The data does not show a reliable pattern of increase or decrease.'],['Estimated change per decade',fmt(change,3)+' '+meta.unit,'District estimates account for the usual seasonal cycle','In plain English',`This estimates how much the signal changed over 10 years, after accounting for its usual seasonal ups and downs. It is an estimate based on past data, not a prediction.`],['Multiple-test adjusted result',`q = ${result.q.toPrecision(3)}`,'q < 0.05 indicates evidence of a trend after adjustment','How to read this',result.q<0.05?'The trend remains well supported even after checking multiple signals and districts.':'After checking multiple signals and districts, the evidence for a trend is not strong enough to be reliable.'],['Data coverage',`${valid.length} / ${months.length} months`,`Average ${fmt(mean,3)} ${meta.unit}`,'Data used',`${valid.length} of ${months.length} months had usable readings.`]].map(([a,b,c,d,e],i)=>`<div class="td-kpi${i===0?' td-kpi-primary':''}"><small>${a}</small><strong>${b}</strong><p>${c}</p><h4 class="td-kpi-plain-heading">${d}</h4><p class="td-kpi-plain">${e}</p></div>`).join('');
    drawSeries(key,values,stats);drawMultiVar(q,district);drawMap(key,q);drawSeason(key,q,district);renderDistrictTable(key,q);$('td-season-title').textContent=`${areaName} · Usual seasonal cycle`;$('td-season-caption').textContent=`${areaName}: bars show the average for each calendar month across available years; this is the recurring seasonal pattern, not the long-term trend.`;
  }
  function renderDistrictTable(key,q){const rep=trendReports(q),rows=districtFeatures.map(f=>{const name=f.properties.district_name||f.properties.shapeName,d=rep.districts.find(x=>x.key===key&&x.name===name),slope=d?.stats?.sen,sen=Number.isFinite(slope)?slope*120:null,significant=Number.isFinite(sen)&&d.q<.05,direction=sen===null?'No slope estimate':significant?(sen>0?'Reliable increase':sen<0?'Reliable decrease':'No clear direction'):sen>0?'Estimated increase · not reliable':sen<0?'Estimated decrease · not reliable':'No clear direction';return {name,n:d.n,sen,q:d.q,significant,direction};}).sort((a,b)=>(b.sen||0)-(a.sen||0));$('td-district-title').textContent=`Uttarakhand · District comparison · ${names[key]} · seasonally adjusted`;$('td-district-table').innerHTML=`<table class="td-table"><thead><tr><th>District</th><th>Direction</th><th>Sen / decade (${esc(units[key])})</th><th>Adjusted q</th><th>Valid months</th></tr></thead><tbody>${rows.map(r=>`<tr data-district="${esc(r.name)}"><td>${esc(r.name)}</td><td class="${r.significant?(r.sen>0?'td-up':'td-down'):'td-flat'}">${esc(r.direction)}</td><td>${fmt(r.sen,3)}</td><td>${r.q.toPrecision(3)}</td><td>${r.n}</td></tr>`).join('')}</tbody></table>`;$('td-district-table').querySelectorAll('tr[data-district]').forEach(tr=>tr.addEventListener('click',()=>{$('td-district').value=tr.dataset.district;selectedDistrict=tr.dataset.district;render();}));}
  function download(){const key=$('td-variable').value,meta=vars[key],rows=['month,value,unit,selected_region',...lastRows.map(r=>`${r.month},${r.value===null?'':r.value},${meta.unit},${selectedDistrict}`)];const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'}));a.download=`earthpulse-trend-${key}-${selectedDistrict==='all'?'uttarakhand':selectedDistrict}.csv`;a.click();URL.revokeObjectURL(a.href);}
  for(const f of districtFeatures){const o=document.createElement('option');o.value=f.properties.district_name||f.properties.shapeName;o.textContent=o.value;$('td-district').appendChild(o);}
  $('td-variable').addEventListener('change',render);$('td-quality').addEventListener('change',render);$('td-district').addEventListener('change',e=>{selectedDistrict=e.target.value;render();});$('td-download').addEventListener('click',download);window.addEventListener('resize',()=>{clearTimeout(window.__tdResize);window.__tdResize=setTimeout(render,120);});window.addEventListener('trend-page-open',()=>requestAnimationFrame(()=>requestAnimationFrame(render)));render();
})();
