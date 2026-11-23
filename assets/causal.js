/* ═══════════════════════════════════════════════════════════════
   CAUSAL DISCOVERY ENGINE  — EARTHPULSE-X
   Clean, bulletproof implementation
   ═══════════════════════════════════════════════════════════════ */
'use strict';

window.causal = (function () {

  /* ── CONSTANTS ─────────────────────────────────────────────── */
  var VARS = [
    { short: 'GPM',  lines: ['Precipitation'],              color: '#6C8EE6', emoji: '🌧️' },
    { short: 'SMAP', lines: ['Soil moisture', '(morning)'], color: '#2D7DD2', emoji: '💧' },
    { short: 'NDVI', lines: ['Vegetation', 'greenness'],    color: '#31C48D', emoji: '🌿' },
    { short: 'LST',  lines: ['Surface', 'temperature'],     color: '#EF6461', emoji: '🌡️' },
  ];

  var NODE_POS = {
    GPM:  { x: 0.12, y: 0.50 },
    SMAP: { x: 0.40, y: 0.22 },
    NDVI: { x: 0.68, y: 0.22 },
    LST:  { x: 0.88, y: 0.50 },
  };

  var CHAIN_LINKS = [
    { src: 'GPM',  tgt: 'SMAP', desc: 'Rain saturates soil',           expDir: 'positive' },
    { src: 'SMAP', tgt: 'NDVI', desc: 'Wet soil grows vegetation',     expDir: 'positive' },
    { src: 'NDVI', tgt: 'LST',  desc: 'Vegetation cools surface',      expDir: 'negative' },
    { src: 'GPM',  tgt: 'LST',  desc: 'Rain cools surface directly',   expDir: 'negative' },
  ];

  /* ── STATE ─────────────────────────────────────────────────── */
  var _edges = [];
  var _baseEdges = [];
  var _preEdges  = [];
  var _stabilityRows = [];
  var _rawData = null;
  var _districtData = null;
  var _districtEdges = [];
  var _districtRunning = false;
  var _running = false;
  var _animTimer = null;
  var _selectedNode = null;
  var _selectedDistrictNode = null;

  /* ── DATA LOADING ───────────────────────────────────────────── */
  function getData() {
    if (_rawData) return _rawData;
    var pd = window.PREDICTIVE_DATA;
    if (!pd || !pd.regional || !pd.months) {
      setStatus('⚠️ State-wide satellite data is missing. Reload the page and try again.', '#E9A34B');
      return null;
    }
    var reg = pd.regional;
    function extract(key) {
      var value = reg[key];
      if (!value) return [];
      if (Array.isArray(value)) return value.map(Number);
      if (value.values && Array.isArray(value.values)) return value.values.map(Number);
      return [];
    }
    var gpm = extract('GPM');
    var smap = extract('SMAP_AM');
    var ndvi = extract('NDVI');
    var lst = extract('LST');
    var months = pd.months;

    var n = Math.min(gpm.length, smap.length, ndvi.length, lst.length, months.length);
    if (n < 20) {
      setStatus('⚠️ Not enough data points (' + n + '). Need at least 20.', '#E9A34B');
      return null;
    }

    _rawData = {
      gpm: gpm.slice(0, n), smap: smap.slice(0, n),
      ndvi: ndvi.slice(0, n), lst: lst.slice(0, n),
      months: months.slice(0, n), isDistrict: false,
    };
    return _rawData;
  }

  function getDistrictData() {
    var select = document.getElementById('causal-district');
    var district = select ? select.value : '';
    if (_districtData && _districtData.name === district) return _districtData.data;
    var bundle = window.DISTRICT_CAUSAL_DATA;
    var record = bundle && bundle.districts && bundle.districts[district];
    if (!bundle || !record || !bundle.months) return null;
    _districtData = { name: district, data: {
      gpm: record.GPM.map(Number), smap: record.SMAP_AM.map(Number),
      ndvi: record.NDVI.map(Number), lst: record.LST.map(Number), months: bundle.months.slice(), isDistrict: true,
    }};
    return _districtData.data;
  }

  /* ── MATH HELPERS ───────────────────────────────────────────── */
  function mean(a) {
    var s = 0; for (var i = 0; i < a.length; i++) s += a[i];
    return s / a.length;
  }

  function pearson(x, y) {
    var n = Math.min(x.length, y.length);
    if (n < 4) return 0;
    var mx = mean(x.slice(0,n)), my = mean(y.slice(0,n));
    var num = 0, dx = 0, dy = 0;
    for (var i = 0; i < n; i++) {
      var a = x[i] - mx, b = y[i] - my;
      num += a * b; dx += a * a; dy += b * b;
    }
    return (dx > 0 && dy > 0) ? num / Math.sqrt(dx * dy) : 0;
  }

  function laggedPearson(x, y, lag) {
    if (lag === 0) return pearson(x, y);
    var n = Math.min(x.length, y.length) - lag;
    if (n < 4) return 0;
    return pearson(x.slice(0, n), y.slice(lag, lag + n));
  }

  function residuals(dep, ind) {
    var n = Math.min(dep.length, ind.length);
    var d = dep.slice(0, n), ix = ind.slice(0, n);
    var r = pearson(d, ix);
    var sd = stddev(d), si = stddev(ix);
    if (si === 0) return d.slice();
    var b = r * sd / si;
    var a = mean(d) - b * mean(ix);
    var res = [];
    for (var i = 0; i < n; i++) res.push(d[i] - (a + b * ix[i]));
    return res;
  }

  function stddev(a) {
    var m = mean(a), s = 0;
    for (var i = 0; i < a.length; i++) s += (a[i] - m) * (a[i] - m);
    return Math.sqrt(s / a.length);
  }

  function partialCorr(x, y, controls) {
    if (!controls || controls.length === 0) return pearson(x, y);
    var rx = x.slice(), ry = y.slice();
    for (var c = 0; c < controls.length; c++) {
      var ctrl = controls[c];
      var n = Math.min(rx.length, ry.length, ctrl.length);
      rx = residuals(rx.slice(0, n), ctrl.slice(0, n));
      ry = residuals(ry.slice(0, n), ctrl.slice(0, n));
    }
    return pearson(rx, ry);
  }

  function partialTargetShift(x, y, controls) {
    var rx = x.slice(), ry = y.slice();
    for (var c = 0; c < (controls || []).length; c++) {
      var ctrl = controls[c];
      var n = Math.min(rx.length, ry.length, ctrl.length);
      rx = residuals(rx.slice(0, n), ctrl.slice(0, n));
      ry = residuals(ry.slice(0, n), ctrl.slice(0, n));
    }
    return pearson(rx, ry) * stddev(ry);
  }

  function pvalue(r, n) {
    if (n < 4) return 1;
    var t = r * Math.sqrt((n - 2) / Math.max(1 - r * r, 1e-9));
    var absT = Math.abs(t), df = n - 2;
    // Approximation: 2 * (1 - Phi(|t| * sqrt(df/(df+t^2))))
    var z = absT * Math.sqrt(df / (df + absT * absT));
    var p = 2 * (1 - normcdf(z));
    return Math.min(1, Math.max(0, p));
  }

  function normcdf(x) {
    var t = 1 / (1 + 0.2316419 * Math.abs(x));
    var poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    var p = 1 - (1 / Math.sqrt(2 * Math.PI)) * Math.exp(-x * x / 2) * poly;
    return x >= 0 ? p : 1 - p;
  }

  function fdrBH(pvals) {
    var n = pvals.length;
    var indexed = pvals.map(function(p, i) { return { p: p, i: i }; });
    indexed.sort(function(a, b) { return a.p - b.p; });
    var q = new Array(n);
    var runMin = 1;
    for (var k = n - 1; k >= 0; k--) {
      var adj = indexed[k].p * n / (k + 1);
      runMin = Math.min(runMin, adj);
      q[indexed[k].i] = Math.min(1, runMin);
    }
    return q;
  }

  /* ── CAUSAL EDGE COMPUTATION ────────────────────────────────── */
  function computeEdges(data, tauMax, alpha) {
    var seriesMap = { GPM: data.gpm, SMAP: data.smap, NDVI: data.ndvi, LST: data.lst };
    var names = ['GPM', 'SMAP', 'NDVI', 'LST'];
    var rawEdges = [];
    var n = data.gpm.length;

    for (var si = 0; si < names.length; si++) {
      for (var ti = 0; ti < names.length; ti++) {
        if (si === ti) continue;
        var srcName = names[si], tgtName = names[ti];
        for (var tau = 0; tau <= tauMax; tau++) {
          // Same-month partial correlation is symmetric; keep one undirected edge.
          if (tau === 0 && ti < si) continue;
          var nPairs = n - tau;
          if (nPairs < 20) continue;

          var xArr = seriesMap[srcName].slice(0, nPairs);
          var yArr = seriesMap[tgtName].slice(tau, tau + nPairs);

          var controls = [];
          for (var ci = 0; ci < names.length; ci++) {
            if (names[ci] !== srcName && names[ci] !== tgtName) {
              controls.push(seriesMap[names[ci]].slice(tau, tau + nPairs));
            }
          }

          var pc = partialCorr(xArr, yArr, controls);
          var targetShift = partialTargetShift(xArr, yArr, controls);
          var p  = pvalue(pc, nPairs);

          rawEdges.push({
            src: srcName, tgt: tgtName, lag: tau,
            val: pc, strength: Math.abs(pc),
            effectPercent: (data.isDistrict ? targetShift : pc) * 100,
            isDistrict: !!data.isDistrict,
            undirected: tau === 0,
            dir: pc > 0 ? 'positive' : 'negative',
            p: p, q: 1,
          });
        }
      }
    }

    var pvals = rawEdges.map(function(e) { return e.p; });
    var qvals = fdrBH(pvals);
    for (var i = 0; i < rawEdges.length; i++) rawEdges[i].q = qvals[i];

    return rawEdges.filter(function(e) { return e.q < alpha; });
  }

  /* ── RUN ANALYSIS ───────────────────────────────────────────── */
  function runAnalysis() {
    if (_running) return;
    _rawData = null;
    var data = getData();
    if (!data) return;

    _running = true;
    var btn = document.getElementById('causal-run-btn');
    if (btn) btn.disabled = true;
    setStatus('⏳ Calculating Uttarakhand-wide relationships across ' + data.months.length + ' months…', '#35C9D0');

    setTimeout(function() {
      try {
        var tauEl    = document.getElementById('causal-tau-max');
        var alphaEl  = document.getElementById('causal-alpha');
        var minStrEl = document.getElementById('causal-min-strength');

        var tauMax = tauEl  ? parseInt(tauEl.value,  10) : 6;
        var alpha  = alphaEl ? parseFloat(alphaEl.value)  : 0.05;
        var minStr = minStrEl ? parseFloat(minStrEl.value) : 0.05;

        var allEdges = computeEdges(data, tauMax, alpha);
        _edges = allEdges.filter(function(e) { return e.strength >= minStr; });

        // Update KPIs
        setText('kpi-causal-links',  _edges.length);
        setText('kpi-causal-observations', data.months.length);
        var topStr = _edges.length
          ? Math.max.apply(null, _edges.map(function(e){ return e.strength; })).toFixed(3)
          : '—';
        setText('kpi-causal-top', topStr);

        var chainInfo = checkChain(_edges);
        setText('kpi-causal-chain', chainInfo.complete ? '✅ Yes' : '⚠️ Partial');

        hideEl('causal-graph-placeholder');
        drawGraph('causal-graph-canvas', _edges, {});
        setStatus('✅ Uttarakhand-wide — ' + _edges.length + ' significant lagged relationships found', '#31C48D');
        runDistrictAnalysis();
      } catch (err) {
        setStatus('❌ Error: ' + err.message, '#EF6461');
        console.error('Causal analysis error:', err);
      }
      _running = false;
      if (btn) btn.disabled = false;
    }, 60);
  }

  function runDistrictAnalysis() {
    if (_districtRunning) return;
    var data = getDistrictData();
    if (!data) {
      setDistrictStatus('District anomaly data is missing. Reload the page and try again.', '#EF6461');
      return;
    }
    var requestedDistrict = _districtData.name;
    _districtRunning = true;
    setDistrictStatus('Calculating ' + _districtData.name + ' relationships…', '#35C9D0');
    setTimeout(function() {
      try {
        var currentSelect = document.getElementById('causal-district');
        if (currentSelect && currentSelect.value !== requestedDistrict) {
          _districtRunning = false;
          runDistrictAnalysis();
          return;
        }
        var tauEl = document.getElementById('causal-tau-max');
        var alphaEl = document.getElementById('causal-alpha');
        var minEl = document.getElementById('causal-min-strength');
        var tauMax = tauEl ? parseInt(tauEl.value, 10) : 6;
        var alpha = alphaEl ? parseFloat(alphaEl.value) : 0.05;
        var minStrength = minEl ? parseFloat(minEl.value) : 0.05;
        _districtEdges = computeEdges(data, tauMax, alpha).filter(function(edge) { return edge.strength >= minStrength; });
        hideEl('causal-district-graph-placeholder');
        drawGraph('causal-district-graph-canvas', _districtEdges, {});
        populateTable(_districtEdges, data);
        var title = document.getElementById('causal-district-title');
        if (title) title.textContent = requestedDistrict + ' district · lagged relationships';
        setDistrictStatus(_districtEdges.length + ' significant lagged relationships · ' + data.months.length + ' months', '#31C48D');
        renderDistrictMap(requestedDistrict);
      } catch (err) {
        setDistrictStatus('Analysis error: ' + err.message, '#EF6461');
      }
      _districtRunning = false;
    }, 40);
  }

  /* ── DRAW GRAPH ─────────────────────────────────────────────── */
  function drawGraph(canvasId, edges, opts) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.clientWidth || canvas.offsetWidth || 800;
    var H = canvas.clientHeight || 520;
    canvas.width = W;
    canvas.height = H;

    ctx.fillStyle = '#0a1520';
    ctx.fillRect(0, 0, W, H);

    var pad = 60;
    function getXY(name) {
      return {
        x: NODE_POS[name].x * (W - 2 * pad) + pad,
        y: NODE_POS[name].y * (H - 2 * pad) + pad,
      };
    }

    if (!edges || edges.length === 0) {
      ctx.fillStyle = '#4a5a6b';
      ctx.font = '14px Urbanist, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No significant links at current settings — showing variables only.', W/2, 24);
    }

    // Draw edges
    for (var i = 0; i < edges.length; i++) {
      var e = edges[i];
      if (opts.hl && e.src !== opts.hl && e.tgt !== opts.hl) continue;

      var p0 = getXY(e.src), p1 = getXY(e.tgt);
      var color = e.dir === 'positive' ? '#31C48D' : '#EF6461';
      var lw = 1.5 + e.strength * 9;

      var mx = (p0.x + p1.x) / 2;
      var my = (p0.y + p1.y) / 2;
      var dx = p1.x - p0.x, dy = p1.y - p0.y;
      var len = Math.sqrt(dx*dx + dy*dy) || 1;
      var curve = 28 * (e.src < e.tgt ? 1 : -1);
      var cpx = mx - (dy/len) * curve;
      var cpy = my + (dx/len) * curve;

      ctx.save();
      ctx.globalAlpha = 0.9;
      ctx.strokeStyle = color;
      ctx.lineWidth = lw;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.quadraticCurveTo(cpx, cpy, p1.x, p1.y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Same-month lines are undirected; delayed relationships point source → target.
      if (!e.undirected) {
        var angle = Math.atan2(p1.y - cpy, p1.x - cpx);
        var ar = 10;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p1.x - ar*Math.cos(angle-0.4), p1.y - ar*Math.sin(angle-0.4));
        ctx.lineTo(p1.x - ar*Math.cos(angle+0.4), p1.y - ar*Math.sin(angle+0.4));
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
      }

      // Label
      ctx.font = 'bold 9px Urbanist,sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(10,21,32,0.82)';
      var shiftText = (e.effectPercent > 0 ? '+' : '−') + Math.abs(e.effectPercent).toFixed(0) + '% swing';
      var timingText = e.lag === 0 ? 'same mo' : e.lag + ' mo';
      var edgeLabel = timingText + ' · ' + shiftText;
      var labelWidth = Math.max(56, ctx.measureText(edgeLabel).width + 10);
      ctx.fillRect(cpx - labelWidth / 2, cpy - 9, labelWidth, 14);
      ctx.fillStyle = color;
      ctx.fillText(edgeLabel, cpx, cpy + 1);
      ctx.restore();
    }

    // Draw nodes
    for (var v = 0; v < VARS.length; v++) {
      var vr = VARS[v];
      var p  = getXY(vr.short);
      var r  = 42;
      var isHL = opts.hl === vr.short;

      if (isHL) {
        var grad = ctx.createRadialGradient(p.x,p.y,r*0.5,p.x,p.y,r*1.8);
        grad.addColorStop(0, vr.color + '44');
        grad.addColorStop(1, 'transparent');
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(p.x, p.y, r*1.8, 0, Math.PI*2); ctx.fill();
      }

      ctx.fillStyle = vr.color + '22';
      ctx.strokeStyle = vr.color;
      ctx.lineWidth = isHL ? 3 : 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2);
      ctx.fill(); ctx.stroke();

      ctx.fillStyle = '#F1F5FC';
      ctx.font = 'bold 8.5px Urbanist,sans-serif';
      ctx.textAlign = 'center';
      if (vr.lines.length === 1) {
        ctx.fillText(vr.lines[0], p.x, p.y - 2);
      } else {
        ctx.fillText(vr.lines[0], p.x, p.y - 8);
        ctx.fillText(vr.lines[1], p.x, p.y + 2);
      }
      ctx.fillStyle = vr.color;
      ctx.font = '10px sans-serif';
      ctx.fillText(vr.emoji, p.x, p.y + 17);
    }

    var ly = H - 16;
    ctx.font = '9px Urbanist,sans-serif'; ctx.textAlign = 'left';
    ctx.fillStyle = '#31C48D'; ctx.fillRect(pad, ly - 8, 12, 8);
    ctx.fillText('positive · move together', pad + 17, ly);
    ctx.fillStyle = '#EF6461'; ctx.fillRect(pad + 150, ly - 8, 12, 8);
    ctx.fillText('negative · inverse', pad + 167, ly);
  }

  function tauMaxFromUI() {
    var el = document.getElementById('causal-tau-max');
    return el ? parseInt(el.value, 10) : 6;
  }

  /* ── DRAW HEATMAP ───────────────────────────────────────────── */
  function drawHeatmap(canvasId, data, tauMax) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.clientWidth || canvas.offsetWidth || 800;
    var H = canvas.clientHeight || 380;
    canvas.width = W; canvas.height = H;

    ctx.fillStyle = '#0a1520'; ctx.fillRect(0, 0, W, H);

    var names = ['GPM', 'SMAP', 'NDVI', 'LST'];
    var seriesMap = { GPM: data.gpm, SMAP: data.smap, NDVI: data.ndvi, LST: data.lst };
    var n = data.gpm.length;

    var rows = [];
    for (var si = 0; si < names.length; si++)
      for (var ti = 0; ti < names.length; ti++)
        if (si !== ti) rows.push(names[si] + '→' + names[ti]);

    var leftPad = 90, topPad = 36, cellW = (W - leftPad - 20) / (tauMax + 1);
    var cellH = Math.min((H - topPad - 28) / rows.length, 34);

    // Column headers
    ctx.fillStyle = '#8899AA'; ctx.font = '10px Urbanist,sans-serif'; ctx.textAlign = 'center';
    for (var lag = 0; lag <= tauMax; lag++) {
      ctx.fillText('L' + lag, leftPad + lag * cellW + cellW / 2, topPad - 8);
    }

    for (var ri = 0; ri < rows.length; ri++) {
      var parts = rows[ri].split('→');
      var src = parts[0], tgt = parts[1];
      var y = topPad + ri * cellH;

      ctx.fillStyle = '#8899AA'; ctx.font = '9px Urbanist,sans-serif'; ctx.textAlign = 'right';
      ctx.fillText(rows[ri], leftPad - 5, y + cellH / 2 + 3);

      for (var lag2 = 0; lag2 <= tauMax; lag2++) {
        var nP = n - lag2;
        if (nP < 10) continue;
        var xA = seriesMap[src].slice(0, nP);
        var yA = seriesMap[tgt].slice(lag2, lag2 + nP);
        var ctrls = names.filter(function(nm) { return nm !== src && nm !== tgt; })
                         .map(function(nm) { return seriesMap[nm].slice(lag2, lag2 + nP); });
        var pc2 = partialCorr(xA, yA, ctrls);
        var cx2 = leftPad + lag2 * cellW;
        ctx.fillStyle = heatColor(pc2, -0.5, 0.5);
        ctx.fillRect(cx2 + 1, y + 1, cellW - 2, cellH - 2);
        if (Math.abs(pc2) > 0.08) {
          ctx.fillStyle = Math.abs(pc2) > 0.22 ? '#F1F5FC' : '#8899AA';
          ctx.font = '8px Urbanist,sans-serif'; ctx.textAlign = 'center';
          ctx.fillText(pc2.toFixed(2), cx2 + cellW / 2, y + cellH / 2 + 3);
        }
      }
    }

    // Color bar
    var lgX = W - 100, lgY = H - 24;
    for (var ci = 0; ci < 20; ci++) {
      ctx.fillStyle = heatColor(-0.5 + ci / 20, -0.5, 0.5);
      ctx.fillRect(lgX + ci * 4, lgY, 4, 10);
    }
    ctx.fillStyle = '#8899AA'; ctx.font = '8px Urbanist,sans-serif';
    ctx.textAlign = 'left';  ctx.fillText('-0.5', lgX, lgY + 22);
    ctx.textAlign = 'right'; ctx.fillText('+0.5', lgX + 80, lgY + 22);
    ctx.textAlign = 'center';ctx.fillText('Partial Corr', lgX + 40, lgY + 22);
  }

  function heatColor(v, vmin, vmax) {
    var t = Math.max(0, Math.min(1, (v - vmin) / (vmax - vmin)));
    if (t < 0.5) {
      var f = t * 2;
      return 'rgb(' + Math.round(26 + f*(30-26)) + ',' + Math.round(74 + f*(125-74)) + ',' + Math.round(138 + f*(210-138)) + ')';
    } else {
      var f2 = (t - 0.5) * 2;
      return 'rgb(' + Math.round(30 + f2*(239-30)) + ',' + Math.round(125 + f2*(100-125)) + ',' + Math.round(210 + f2*(97-210)) + ')';
    }
  }

  /* ── CHAIN CHECK ────────────────────────────────────────────── */
  function checkChain(edges) {
    var links = CHAIN_LINKS.map(function(cl) {
      var matches = edges.filter(function(e) { return e.src === cl.src && e.tgt === cl.tgt; });
      matches.sort(function(a, b) { return b.strength - a.strength; });
      var best = matches[0];
      return {
        src: cl.src, tgt: cl.tgt, desc: cl.desc, expDir: cl.expDir,
        found: !!best,
        lag: best ? best.lag : null,
        strength: best ? best.strength : 0,
        dir: best ? best.dir : null,
        physicsMatch: best ? best.dir === cl.expDir : false,
      };
    });
    var found = links.filter(function(l) { return l.found; }).length;
    return { links: links, complete: found >= 3, foundCount: found };
  }

  /* ── RENDER CHAIN ───────────────────────────────────────────── */
  function renderChain(chainInfo) {
    var flow = document.getElementById('causal-chain-flow');
    var cards = document.getElementById('causal-chain-cards');
    if (!flow || !cards) return;

    var nodeData = [
      { short: 'GPM',  emoji: '🌧️', color: '#6C8EE6' },
      { short: 'SMAP', emoji: '💧',  color: '#2D7DD2' },
      { short: 'NDVI', emoji: '🌿',  color: '#31C48D' },
      { short: 'LST',  emoji: '🌡️', color: '#EF6461' },
    ];

    var html = '';
    for (var i = 0; i < nodeData.length; i++) {
      var nd = nodeData[i];
      html += '<div style="display:flex;align-items:center;gap:0;">';
      html += '<div id="cnode-' + i + '" style="text-align:center;padding:14px 18px;border:2px solid #293846;border-radius:12px;background:#0f1a2e;min-width:80px;transition:all .4s;">';
      html += '<div style="font-size:1.5rem;">' + nd.emoji + '</div>';
      html += '<div style="font-size:.78rem;font-weight:700;color:#F1F5FC;margin-top:4px;">' + nd.short + '</div>';
      html += '</div>';
      if (i < nodeData.length - 1) {
        html += '<div style="display:flex;flex-direction:column;align-items:center;gap:3px;padding:0 6px;">';
        html += '<span id="carrow-' + i + '" style="font-size:1.3rem;color:#293846;transition:color .4s;">&#10140;</span>';
        html += '<span id="clag-' + i + '" style="font-size:.62rem;color:#4a5a6b;transition:color .4s;"></span>';
        html += '</div>';
      }
      html += '</div>';
    }
    flow.innerHTML = html;

    // Update arrows based on chain results
    var arrowLinks = chainInfo.links.slice(0, 3);
    for (var j = 0; j < arrowLinks.length; j++) {
      var lnk = arrowLinks[j];
      var arrow = document.getElementById('carrow-' + j);
      var lagEl = document.getElementById('clag-' + j);
      if (!arrow) continue;
      if (lnk.found && lnk.physicsMatch) {
        arrow.style.color = '#31C48D';
        if (lagEl) { lagEl.textContent = 'L' + lnk.lag + 'm · ' + lnk.strength.toFixed(2); lagEl.style.color = '#31C48D'; }
      } else if (lnk.found) {
        arrow.style.color = '#E9A34B';
        if (lagEl) { lagEl.textContent = 'L' + lnk.lag + 'm · unexpected'; lagEl.style.color = '#E9A34B'; }
      } else {
        arrow.style.color = '#EF6461';
        if (lagEl) { lagEl.textContent = 'not detected'; lagEl.style.color = '#EF6461'; }
      }
    }

    // Detail cards
    var cardHtml = '';
    for (var k = 0; k < chainInfo.links.length; k++) {
      var cl = chainInfo.links[k];
      var icon = cl.found && cl.physicsMatch ? '✅' : cl.found ? '⚠️' : '❌';
      var col  = cl.found && cl.physicsMatch ? '#31C48D' : cl.found ? '#E9A34B' : '#EF6461';
      var lagStr = cl.found ? 'Lag ' + cl.lag + 'm · strength ' + cl.strength.toFixed(3) : 'Not detected';
      var phStr  = cl.found ? (cl.physicsMatch ? ' · Physics match ✅' : ' · Unexpected direction ⚠️') : '';
      cardHtml += '<div style="padding:14px 16px;border:1px solid #293846;border-left:3px solid ' + col + ';border-radius:10px;background:#111c2d;">';
      cardHtml += '<div style="font-size:.88rem;font-weight:700;color:' + col + ';">' + icon + ' ' + cl.src + ' → ' + cl.tgt + '</div>';
      cardHtml += '<div style="font-size:.75rem;color:#AAB8CC;margin:4px 0;">' + cl.desc + '</div>';
      cardHtml += '<div style="font-size:.7rem;color:#6B7B91;">' + lagStr + phStr + '</div>';
      cardHtml += '</div>';
    }
    cards.innerHTML = cardHtml;
  }

  /* ── ANIMATE CHAIN ──────────────────────────────────────────── */
  function animateChain() {
    if (_animTimer) clearInterval(_animTimer);
    // Reset
    for (var i = 0; i < 4; i++) {
      var nd = document.getElementById('cnode-' + i);
      if (nd) { nd.style.borderColor = '#293846'; nd.style.background = '#0f1a2e'; }
    }
    for (var j = 0; j < 3; j++) {
      var ar = document.getElementById('carrow-' + j);
      if (ar) ar.style.color = '#293846';
    }

    var step = 0;
    var nodeColors = ['#6C8EE6', '#2D7DD2', '#31C48D', '#EF6461'];
    var statusEl = document.getElementById('causal-chain-status');
    if (statusEl) statusEl.textContent = 'Animating…';

    _animTimer = setInterval(function() {
      if (step >= CHAIN_LINKS.length) {
        clearInterval(_animTimer);
        if (statusEl) statusEl.textContent = 'Complete ✅';
        return;
      }
      var srcIdx = ['GPM','SMAP','NDVI','LST'].indexOf(CHAIN_LINKS[step].src);
      var tgtIdx = ['GPM','SMAP','NDVI','LST'].indexOf(CHAIN_LINKS[step].tgt);
      var srcNode = document.getElementById('cnode-' + srcIdx);
      if (srcNode) { srcNode.style.borderColor = nodeColors[srcIdx]; srcNode.style.background = nodeColors[srcIdx] + '22'; }
      var arEl = document.getElementById('carrow-' + step);
      if (arEl) arEl.style.color = '#35C9D0';
      setTimeout(function(ti, tc) {
        return function() {
          var tgtNode = document.getElementById('cnode-' + ti);
          if (tgtNode) { tgtNode.style.borderColor = tc; tgtNode.style.background = tc + '22'; }
        };
      }(tgtIdx, nodeColors[tgtIdx]), 700);
      step++;
    }, 1400);
  }

  function resetChain() {
    if (_animTimer) clearInterval(_animTimer);
    for (var i = 0; i < 4; i++) {
      var nd = document.getElementById('cnode-' + i);
      if (nd) { nd.style.borderColor = '#293846'; nd.style.background = '#0f1a2e'; }
    }
    for (var j = 0; j < 3; j++) {
      var ar = document.getElementById('carrow-' + j);
      if (ar) ar.style.color = '#293846';
    }
    var statusEl = document.getElementById('causal-chain-status');
    if (statusEl) statusEl.textContent = '';
  }

  /* ── CHAMOLI TEST ───────────────────────────────────────────── */
  function runChamoliTest(data, tauMax) {
    var n = data.months.length;
    var preStart = -1, disasterIdx = -1;

    for (var i = 0; i < data.months.length; i++) {
      var m = String(data.months[i]);
      if (preStart < 0 && (m.startsWith('2019-01') || m.startsWith('2019-1'))) preStart = i;
      if (m.startsWith('2021-02') || m.startsWith('2021-2')) disasterIdx = i;
    }
    if (preStart < 0) preStart = Math.round(n * 0.37);
    if (disasterIdx < 0) disasterIdx = Math.round(n * 0.47);

    function sliceData(from, to) {
      return {
        gpm: data.gpm.slice(from, to), smap: data.smap.slice(from, to),
        ndvi: data.ndvi.slice(from, to), lst: data.lst.slice(from, to),
        months: data.months.slice(from, to),
      };
    }

    var baseData = sliceData(0, preStart);
    var preData  = sliceData(preStart, disasterIdx + 1);

    if (baseData.gpm.length < 20 || preData.gpm.length < 8) {
      setText('causal-chamoli-verdict', '<span style="color:var(--t3);">Not enough data for Chamoli split test.</span>');
      return;
    }

    var tau3 = Math.min(3, tauMax);
    _baseEdges = computeEdges(baseData, tau3, 0.10);
    _preEdges  = computeEdges(preData,  tau3, 0.10);

    var baseN   = _baseEdges.length;
    var preN    = _preEdges.length;
    var baseStr = baseN ? _baseEdges.reduce(function(s,e){return s+e.strength;},0)/baseN : 0;
    var preStr  = preN  ? _preEdges.reduce(function(s,e){return s+e.strength;},0)/preN  : 0;
    var lost    = baseN - preN;
    var strDrop = baseStr - preStr;

    var verdict, verdictColor;
    if (lost >= 2 || strDrop > 0.04) {
      verdict = '⚠️ CAUSAL DESTABILISATION DETECTED'; verdictColor = '#EF6461';
    } else if (lost >= 1) {
      verdict = '🔶 PARTIAL SIGNAL — Minor structural change'; verdictColor = '#E9A34B';
    } else {
      verdict = '✅ NO STRUCTURAL CHANGE DETECTED'; verdictColor = '#31C48D';
    }

    var baseStart = data.months[0] ? String(data.months[0]).slice(0,7) : '2015-04';
    var baseEnd   = data.months[preStart-1] ? String(data.months[preStart-1]).slice(0,7) : '';
    var preS      = data.months[preStart]   ? String(data.months[preStart]).slice(0,7)   : '2019-01';
    var preE      = data.months[disasterIdx]? String(data.months[disasterIdx]).slice(0,7): '2021-02';

    var verdictEl = document.getElementById('causal-chamoli-verdict');
    if (verdictEl) verdictEl.innerHTML = '<div style="border-left:4px solid '+verdictColor+';padding:4px 16px;"><div style="font-size:1.1rem;font-weight:800;color:'+verdictColor+';">'+verdict+'</div><div style="font-size:.85rem;color:#AAB8CC;margin-top:6px;">Network '+(lost>0?'lost '+lost+' link(s)':'maintained all links')+' and mean strength '+(strDrop>0?'dropped by '+strDrop.toFixed(3):'remained stable')+' in pre-disaster period '+preS+' → '+preE+'.</div></div>';

    setText('causal-baseline-info', 'Period: '+baseStart+' → '+baseEnd+' &nbsp;·&nbsp; <strong>'+baseN+'</strong> links &nbsp;·&nbsp; Mean strength: <strong>'+baseStr.toFixed(3)+'</strong>');
    setText('causal-predis-info',   'Period: '+preS+' → '+preE+' &nbsp;·&nbsp; <strong>'+preN+'</strong> links &nbsp;·&nbsp; Mean strength: <strong>'+preStr.toFixed(3)+'</strong>');
    setText('kpi-links-lost',    lost);
    setText('kpi-str-drop',      strDrop.toFixed(4));
    setText('kpi-links-compare', baseN + ' → ' + preN);

    drawGraph('causal-baseline-canvas', _baseEdges, {});
    drawGraph('causal-predis-canvas',   _preEdges,  {});
  }

  /* ── ROLLING STABILITY ──────────────────────────────────────── */
  function runRollingStability(data, tauMax) {
    var n = data.gpm.length;
    var winSize = 36, step = 6;
    _stabilityRows = [];

    for (var i = 0; i + winSize <= n; i += step) {
      var slice = {
        gpm: data.gpm.slice(i,i+winSize), smap: data.smap.slice(i,i+winSize),
        ndvi: data.ndvi.slice(i,i+winSize), lst: data.lst.slice(i,i+winSize),
        months: data.months.slice(i,i+winSize),
      };
      var tau3 = Math.min(3, tauMax);
      var wEdges = computeEdges(slice, tau3, 0.10);
      var nLinks = wEdges.length;
      var meanStr = nLinks ? wEdges.reduce(function(s,e){return s+e.strength;},0)/nLinks : 0;
      var gpmSmap = 0, smapNdvi = 0;
      for (var ei = 0; ei < wEdges.length; ei++) {
        if (wEdges[ei].src==='GPM'  && wEdges[ei].tgt==='SMAP') gpmSmap  = Math.max(gpmSmap,  wEdges[ei].strength);
        if (wEdges[ei].src==='SMAP' && wEdges[ei].tgt==='NDVI') smapNdvi = Math.max(smapNdvi, wEdges[ei].strength);
      }
      var midMonth = data.months[i + Math.floor(winSize/2)] || '';
      _stabilityRows.push({ mid: String(midMonth).slice(0,7), nLinks: nLinks, meanStr: meanStr, gpmSmap: gpmSmap, smapNdvi: smapNdvi });
    }

    drawStabilityChart('causal-stability-canvas', _stabilityRows);
  }

  function drawStabilityChart(canvasId, rows) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !rows.length) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.clientWidth || canvas.offsetWidth || 800;
    var H = canvas.clientHeight || 320;
    canvas.width = W; canvas.height = H;

    ctx.fillStyle = '#0a1520'; ctx.fillRect(0,0,W,H);

    var pl = 50, pr = 20, pt = 30, pb = 55;
    var plotW = W - pl - pr, plotH = H - pt - pb;
    var maxStr = 0;
    for (var i = 0; i < rows.length; i++) maxStr = Math.max(maxStr, rows[i].meanStr);
    maxStr = maxStr || 0.3;

    function toX(i) { return pl + (i / (rows.length - 1 || 1)) * plotW; }
    function toY(v) { return pt + (1 - v / maxStr) * plotH; }

    // Grid
    ctx.strokeStyle = '#1E2D4A'; ctx.lineWidth = 1;
    for (var gi = 0; gi <= 4; gi++) {
      var gy = pt + gi / 4 * plotH;
      ctx.beginPath(); ctx.moveTo(pl, gy); ctx.lineTo(pl + plotW, gy); ctx.stroke();
      ctx.fillStyle = '#4a5a6b'; ctx.font = '9px Urbanist,sans-serif'; ctx.textAlign = 'right';
      ctx.fillText((maxStr * (1 - gi/4)).toFixed(3), pl - 4, gy + 3);
    }

    // Chamoli marker
    var chamoliIdx = -1;
    for (var ci = 0; ci < rows.length; ci++) {
      if (rows[ci].mid && rows[ci].mid.startsWith('2020')) { chamoliIdx = ci; break; }
    }
    if (chamoliIdx >= 0) {
      var cx = toX(chamoliIdx);
      ctx.strokeStyle = 'rgba(239,100,97,0.5)'; ctx.lineWidth = 1.5; ctx.setLineDash([4,3]);
      ctx.beginPath(); ctx.moveTo(cx, pt); ctx.lineTo(cx, pt+plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#EF6461'; ctx.font = '9px Urbanist,sans-serif'; ctx.textAlign = 'left';
      ctx.fillText('← Chamoli', cx+4, pt+14);
    }

    // Fill area
    if (rows.length > 1) {
      ctx.beginPath();
      for (var ri = 0; ri < rows.length; ri++) {
        var rx = toX(ri), ry = toY(rows[ri].meanStr);
        ri === 0 ? ctx.moveTo(rx, ry) : ctx.lineTo(rx, ry);
      }
      ctx.lineTo(toX(rows.length-1), pt+plotH);
      ctx.lineTo(toX(0), pt+plotH);
      ctx.closePath();
      ctx.fillStyle = 'rgba(53,201,208,0.08)'; ctx.fill();

      // Lines
      function drawLine(key, color, dash) {
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash(dash || []);
        ctx.beginPath();
        for (var li = 0; li < rows.length; li++) {
          var lx = toX(li), ly2 = toY(rows[li][key]);
          li === 0 ? ctx.moveTo(lx, ly2) : ctx.lineTo(lx, ly2);
        }
        ctx.stroke(); ctx.setLineDash([]);
      }
      drawLine('meanStr',  '#35C9D0', []);
      drawLine('gpmSmap',  '#6C8EE6', [6,3]);
      drawLine('smapNdvi', '#31C48D', [4,4]);
    }

    // X labels
    ctx.fillStyle = '#4a5a6b'; ctx.font = '9px Urbanist,sans-serif'; ctx.textAlign = 'center';
    var xStep = Math.max(1, Math.floor(rows.length / 7));
    for (var xi = 0; xi < rows.length; xi += xStep) {
      ctx.fillText(rows[xi].mid || '', toX(xi), H - pb + 14);
    }

    // Legend
    var items = [['#35C9D0','Overall',[]], ['#6C8EE6','GPM→SMAP',[6,3]], ['#31C48D','SMAP→NDVI',[4,4]]];
    for (var li2 = 0; li2 < items.length; li2++) {
      var itm = items[li2];
      var lxp = pl + li2 * 150;
      ctx.strokeStyle = itm[0]; ctx.lineWidth = 2; ctx.setLineDash(itm[2]);
      ctx.beginPath(); ctx.moveTo(lxp, H-12); ctx.lineTo(lxp+20, H-12); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#8899AA'; ctx.font = '9px Urbanist,sans-serif'; ctx.textAlign = 'left';
      ctx.fillText(itm[1], lxp + 24, H - 9);
    }

    // Trend annotation
    if (rows.length >= 4) {
      var xs = rows.map(function(_,i){return i;});
      var ys = rows.map(function(r){return r.meanStr;});
      var mx2 = mean(xs), my2 = mean(ys);
      var num2 = 0, den2 = 0;
      for (var ti2 = 0; ti2 < xs.length; ti2++) { num2 += (xs[ti2]-mx2)*(ys[ti2]-my2); den2 += (xs[ti2]-mx2)*(xs[ti2]-mx2); }
      var slope2 = den2 > 0 ? num2/den2 : 0;
      var trendEl = document.getElementById('causal-stability-trend');
      if (trendEl) {
        var dir2 = slope2 < -0.0004 ? '📉 DECLINING ↘' : '📈 STABLE / IMPROVING ↗';
        var col2 = slope2 < -0.0004 ? '#EF6461' : '#31C48D';
        trendEl.innerHTML = '<strong>Stability trend:</strong> <span style="color:'+col2+';font-weight:700;">'+dir2+'</span> · slope = '+slope2.toFixed(5)+'/window';
      }
    }
  }

  /* ── EDGE TABLE ─────────────────────────────────────────────── */
  function populateTable(edges, data) {
    var tbody = document.getElementById('causal-edge-tbody');
    if (!tbody) return;
    if (!edges.length) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--t3);text-align:center;padding:20px;">No significant relationships for this district/settings.</td></tr>';
      return;
    }
    var sorted = edges.slice().sort(function(a,b){return b.strength-a.strength;});
    var varColor = { GPM:'#6C8EE6', SMAP:'#2D7DD2', NDVI:'#31C48D', LST:'#EF6461' };
    var varName = { GPM:'Precipitation (GPM)', SMAP:'Soil moisture (morning)', NDVI:'Vegetation greenness', LST:'Surface temperature' };
    tbody.innerHTML = sorted.map(function(e) {
      var swingPercent = Math.abs(e.effectPercent).toFixed(0) + '% of its usual swing';
      var when = e.lag === 0 ? 'In the same month' : e.lag + (e.lag === 1 ? ' month later' : ' months later');
      var movement = e.effectPercent < 0 ? 'lower' : 'higher';
      return '<tr>'
        + '<td><span style="color:' + (varColor[e.src]||'#F1F5FC') + ';font-weight:600;">' + varName[e.src] + '</span> ' + (e.undirected ? '↔' : '→') + ' <span style="color:' + (varColor[e.tgt]||'#F1F5FC') + ';font-weight:600;">' + varName[e.tgt] + '</span></td>'
        + '<td>A usual rise in ' + varName[e.src] + ' is associated with ' + varName[e.tgt] + ' being about ' + swingPercent + ' ' + movement + '.</td>'
        + '<td>' + when + '</td>'
        + '</tr>';
    }).join('');
  }

  /* ── CSV DOWNLOAD ───────────────────────────────────────────── */
  function downloadCSV() {
    if (!_districtEdges.length) { alert('Select a district and run the analysis first.'); return; }
    var rows = ['Source,Target,Lag (months),Partial correlation,Strength,Direction,q-value (FDR)'];
    for (var i = 0; i < _districtEdges.length; i++) {
      var e = _districtEdges[i];
      rows.push(e.src+','+e.tgt+','+e.lag+','+e.val.toFixed(4)+','+e.strength.toFixed(4)+','+e.dir+','+e.q.toFixed(6));
    }
    var blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    var district = document.getElementById('causal-district')?.value || 'district';
    a.download = 'earthpulse_x_' + district.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '_relationships.csv';
    a.click();
  }

  /* ── UTILITIES ──────────────────────────────────────────────── */
  function setStatus(msg, color) {
    var el = document.getElementById('causal-status');
    if (el) { el.textContent = msg; el.style.color = color || '#AAB8CC'; }
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = val;
  }

  function hideEl(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'none';
  }

  function setDistrictStatus(msg, color) {
    var el = document.getElementById('causal-district-status');
    if (el) { el.textContent = msg; el.style.color = color || '#AAB8CC'; }
  }

  function renderDistrictMap(selected) {
    var svg = document.getElementById('causal-district-map');
    var geo = window.ANOMALY_DATA && window.ANOMALY_DATA.districtGeo;
    if (!svg || !geo || !geo.features) return;
    var features = geo.features;
    var minLon = 77.55, maxLon = 81.15, minLat = 28.55, maxLat = 31.55;
    var width = 360, height = 420, pad = 12;
    function point(coord) {
      return [pad + (coord[0] - minLon) / (maxLon - minLon) * (width - pad * 2),
        height - pad - (coord[1] - minLat) / (maxLat - minLat) * (height - pad * 2)];
    }
    var paths = [], labels = [];
    features.forEach(function(feature) {
      var name = feature.properties.district_name;
      var geom = feature.geometry;
      var polygons = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
      var pointsForLabel = [];
      var d = '';
      polygons.forEach(function(poly) {
        (poly[0] || []).forEach(function(coord, index) {
          var p = point(coord);
          pointsForLabel.push(p);
          d += (index ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1);
        });
        d += 'Z';
      });
      var safe = String(name).replace(/[&<>"']/g, function(ch) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]; });
      paths.push('<path data-district="' + safe + '" d="' + d + '" fill="' + (name === selected ? '#35C9D0' : '#20344A') + '" fill-opacity="' + (name === selected ? '.88' : '.72') + '" stroke="' + (name === selected ? '#9AF4E9' : '#7890A7') + '" stroke-width="' + (name === selected ? '2.4' : '1.2') + '"><title>' + safe + '</title></path>');
      if (pointsForLabel.length) {
        var center = pointsForLabel.reduce(function(acc, p) { acc[0] += p[0]; acc[1] += p[1]; return acc; }, [0, 0]);
        center[0] /= pointsForLabel.length; center[1] /= pointsForLabel.length;
        labels.push('<text x="' + center[0].toFixed(1) + '" y="' + center[1].toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" fill="#F1F5FC" font-size="7" pointer-events="none">' + safe + '</text>');
      }
    });
    svg.innerHTML = paths.join('') + labels.join('');
    svg.querySelectorAll('[data-district]').forEach(function(path) {
      path.addEventListener('click', function() {
        var select = document.getElementById('causal-district');
        if (select && select.value !== path.getAttribute('data-district')) {
          select.value = path.getAttribute('data-district');
          select.dispatchEvent(new Event('change'));
        }
      });
    });
  }

  /* ── ON PAGE OPEN ───────────────────────────────────────────── */
  function initializeDistrictSelector() {
    var select = document.getElementById('causal-district');
    var bundle = window.DISTRICT_CAUSAL_DATA;
    if (!select || !bundle || !bundle.districts) return;
    var districts = Object.keys(bundle.districts).sort();
    select.innerHTML = districts.map(function(name) {
      return '<option value="' + name.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;') + '">' + name + '</option>';
    }).join('');
    select.value = districts.indexOf('Chamoli') >= 0 ? 'Chamoli' : districts[0];
    select.addEventListener('change', function() {
      _districtData = null;
      _selectedDistrictNode = null;
      renderDistrictMap(select.value);
      runDistrictAnalysis();
    });
    renderDistrictMap(select.value);
  }

  function onPageOpen() {
    setTimeout(function() {
      if (!_edges.length) runAnalysis();
      if (!_districtEdges.length) runDistrictAnalysis();
    }, 150);
  }

  /* ── CANVAS CLICK ───────────────────────────────────────────── */
  document.addEventListener('click', function(e) {
    var canvas = e.target && e.target.closest ? e.target.closest('canvas') : null;
    if (!canvas || (canvas.id !== 'causal-graph-canvas' && canvas.id !== 'causal-district-graph-canvas')) return;
    var isDistrict = canvas.id === 'causal-district-graph-canvas';
    var edges = isDistrict ? _districtEdges : _edges;
    if (!edges.length) return;
    var rect = canvas.getBoundingClientRect();
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) return;

    var mx = e.clientX - rect.left, my = e.clientY - rect.top;
    var W = canvas.width, H = canvas.height, pad = 60;
    var clicked = null;
    for (var i = 0; i < VARS.length; i++) {
      var v = VARS[i];
      var nx = NODE_POS[v.short].x*(W-2*pad)+pad;
      var ny = NODE_POS[v.short].y*(H-2*pad)+pad;
      if (Math.sqrt((mx-nx)*(mx-nx)+(my-ny)*(my-ny)) < 46) { clicked = v.short; break; }
    }
    if (isDistrict) {
      _selectedDistrictNode = clicked === _selectedDistrictNode ? null : clicked;
      drawGraph(canvas.id, edges, _selectedDistrictNode ? { hl: _selectedDistrictNode } : {});
    } else {
      _selectedNode = clicked === _selectedNode ? null : clicked;
      drawGraph(canvas.id, edges, _selectedNode ? { hl: _selectedNode } : {});
    }
  });

  initializeDistrictSelector();

  /* ── PUBLIC API ─────────────────────────────────────────────── */
  return {
    runAnalysis:    runAnalysis,
    runDistrictAnalysis: runDistrictAnalysis,
    animateChain:   animateChain,
    resetChain:     resetChain,
    downloadCSV:    downloadCSV,
    onPageOpen:     onPageOpen,
  };

}());
