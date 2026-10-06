const COLORS = { EXCELENTE:'#10b981', BUENA:'#3b82f6', MEDIA:'#f59e0b', CRITICA:'#ef4444' };
let _audits = [], _alerts = [];

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}

async function loadAll() {
  try {
    const [sumData, mpData, auditData, alertData, healthData, sessionData, seasonData] = await Promise.all([
      fetchJSON('/api/summary'),
      fetchJSON('/api/marketplace'),
      fetchJSON('/api/audits'),
      fetchJSON('/api/alerts?limit=8&unack_only=true'),
      fetchJSON('/api/health'),
      fetchJSON('/api/sessions'),
      fetchJSON('/api/mri/season_products').catch(() => ({items:[]}))
    ]);

    // Stats cards
    document.getElementById('s-mp').textContent = sumData.marketplace_count ?? '...';
    document.getElementById('s-cat').textContent = sumData.category_count ?? '...';
    document.getElementById('s-total').textContent = sumData.total_audits ?? '...';
    document.getElementById('s-avg').textContent = sumData.avg_pct_30 != null ? sumData.avg_pct_30.toFixed(1)+'%' : '...';
    document.getElementById('s-crit').textContent = sumData.critical_count ?? '...';
    
    // Temporada Actual
    if (seasonData && seasonData.items && seasonData.items.length > 0) {
      document.getElementById('s-exc').textContent = "Activa (" + seasonData.items.length + " prods)";
      // Populate Temporada View
      document.getElementById('season-tbody').innerHTML = seasonData.items.map(p => `
        <tr>
          <td><strong>${p.parent_sku}</strong></td>
          <td>${p.title}</td>
          <td><span class="badge ${p.status==='ACTIVO'?'badge-ok':'badge-warn'}">${p.status}</span></td>
          <td>${p.priority}</td>
          <td><a href="${p.url}" target="_blank" style="color:var(--accent)">Ver Catálogo</a></td>
        </tr>
      `).join('');
    } else {
      document.getElementById('s-exc').textContent = "Sin Temporada";
      document.getElementById('season-tbody').innerHTML = `<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--muted)">Sin catálogo de temporada activo.</td></tr>`;
    }

    if (sumData.last_audit) {
      document.getElementById('last-updated').textContent = 'Última: ' + sumData.last_audit.substring(0,16).replace('T',' ');
    }

    // Health badge
    const hbadge = document.getElementById('health-badge');
    const hs = healthData.health?.status ?? 'UNKNOWN';
    hbadge.textContent = '● ' + hs;
    hbadge.className = 'badge ' + (hs==='HEALTHY' ? 'badge-ok' : hs==='DEGRADED' ? 'badge-warn' : 'badge-err');

    // Update Sessions Health
    if (sessionData && sessionData.ripley && sessionData.mercadolibre) {
      const rip = sessionData.ripley;
      const ripBadge = document.getElementById('sess-ripley-badge');
      if (ripBadge) {
        ripBadge.textContent = rip.status;
        ripBadge.className = 'badge ' + rip.status_class;
      }
      const ripCount = document.getElementById('sess-ripley-count');
      if (ripCount) ripCount.textContent = rip.cookie_count + ' cookies';
      const ripUpdated = document.getElementById('sess-ripley-updated');
      if (ripUpdated) {
        ripUpdated.textContent = rip.last_updated && rip.last_updated !== 'No encontrado' && rip.last_updated !== 'Error de lectura'
          ? rip.last_updated.substring(0,16).replace('T',' ')
          : rip.last_updated;
      }

      const ml = sessionData.mercadolibre;
      const mlBadge = document.getElementById('sess-ml-badge');
      if (mlBadge) {
        mlBadge.textContent = ml.status;
        mlBadge.className = 'badge ' + ml.status_class;
      }
      const mlCount = document.getElementById('sess-ml-count');
      if (mlCount) mlCount.textContent = ml.cookie_count + ' cookies';
      const mlUpdated = document.getElementById('sess-ml-updated');
      if (mlUpdated) {
        mlUpdated.textContent = ml.last_updated && ml.last_updated !== 'No encontrado' && ml.last_updated !== 'Error de lectura'
          ? ml.last_updated.substring(0,16).replace('T',' ')
          : ml.last_updated;
      }


    } else {
      console.warn("La información de sesiones no está disponible o no se ha iniciado el servidor actualizado.");
      const ripBadge = document.getElementById('sess-ripley-badge');
      if (ripBadge) {
        ripBadge.textContent = "SIN CONEXIÓN";
        ripBadge.className = "badge badge-err";
      }
      const mlBadge = document.getElementById('sess-ml-badge');
      if (mlBadge) {
        mlBadge.textContent = "SIN CONEXIÓN";
        mlBadge.className = "badge badge-err";
      }
    }

    // Marketplace cards
    renderMpGrid(mpData.marketplaces || []);

    // Alerts
    _alerts = alertData.alerts || [];
    renderAlerts(_alerts);

    // Audit table
    _audits = auditData.audits || [];
    renderTable(_audits);

  } catch(e) {
    console.error('Load error', e);
    showToast('Error cargando datos: ' + e.message, true);
  }
}

async function uploadCookies(mp) {
  const textarea = document.getElementById(mp === 'ripley' ? 'cookies-ripley' : 'cookies-ml');
  const btn = document.getElementById(mp === 'ripley' ? 'btn-upload-ripley' : 'btn-upload-ml');
  const val = textarea.value.trim();
  
  if (!val) {
    showToast('Por favor pega un array JSON válido de cookies.', true);
    return;
  }
  
  let cookiesObj;
  try {
    cookiesObj = JSON.parse(val);
    if (!Array.isArray(cookiesObj)) {
      throw new Error('Debe ser una lista JSON (Array de objetos).');
    }
  } catch(e) {
    showToast('Error de formato JSON: ' + e.message, true);
    return;
  }
  
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.innerHTML = '<span class="spin">⟳</span> Subiendo...';
  
  try {
    const response = await fetch('/api/sessions/upload', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        marketplace: mp,
        cookies: cookiesObj
      })
    });
    
    const resData = await response.json();
    if (response.ok && resData.status === 'success') {
      showToast(resData.message || 'Sesión actualizada con éxito.');
      textarea.value = ''; // limpiar textarea
      loadAll(); // recargar métricas y estados
    } else {
      showToast(resData.message || 'Error al actualizar sesión.', true);
    }
  } catch(e) {
    showToast('Error en la solicitud: ' + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}


function renderMpGrid(mps) {
  const grid = document.getElementById('mp-grid');
  grid.innerHTML = mps.map(mp => {
    const lvl = mp.critical > 0 ? 'c-red' : 'c-green';
    return `<button class="mp-card" style="text-align:left; font-family:inherit; color:inherit" onclick="setMpFilter('${mp.marketplace}')" aria-label="Filtrar por ${mp.marketplace}">
      <div class="mp-name">${mp.marketplace}</div>
      <div class="mp-big ${lvl}">${(mp.avg_pct_30||0).toFixed(1)}<small style="font-size:.9rem;font-weight:400">%</small></div>
      <div class="mp-stat">TOP30 avg • ${mp.categories} categorías</div>
      <div class="mp-stat" style="margin-top:.4rem">
        ${mp.excellent||0} exc / ${mp.critical||0} críticas
      </div>
    </button>`;
  }).join('');
}

function renderAlerts(alerts) {
  const sec = document.getElementById('alerts-section');
  if (!alerts.length) { sec.innerHTML = ''; return; }
  const icons = { DROP:'📉', RECOVERY:'📈', CRITICAL:'🚨', PEAK:'🏆', STALE:'⚠️' };
  sec.innerHTML = `<h2 class="section-title">Alertas Activas (${alerts.length})</h2>` +
    alerts.map(a => `
      <div class="alert-item" id="alert-${a.id}">
        <span class="alert-icon">${icons[a.alert_type]||'ℹ️'}</span>
        <span class="alert-msg">${a.message.replace(/Run '.*?'.*$/i, '')}</span>
        <span class="alert-time">${(a.created_at||'').substring(0,16).replace('T',' ')}</span>
        <button class="ack-btn" onclick="ackAlert(${a.id})">✓ OK</button>
      </div>`).join('');
}

function pctBar(pct, color) {
  const w = Math.min(100, pct || 0);
  return `<div class="bar-wrap">
    <span style="min-width:38px;font-size:.78rem">${(pct||0).toFixed(1)}%</span>
    <div class="bar"><div class="bar-fill" style="width:${w}%;background:${color}"></div></div>
  </div>`;
}

function renderTotals(data) {
  const tfoot = document.getElementById('audit-tfoot');
  if (!data.length) { tfoot.innerHTML = ''; return; }
  const sum = (key) => data.reduce((a, r) => a + (Number(r[key]) || 0), 0);
  const canal   = sum('total_marketplace');
  const nico    = sum('total_nicopoly');
  const t30     = sum('top_30');
  const t60     = sum('top_60');
  const t90     = sum('top_90');
  const t120    = sum('top_120');
  const t240    = sum('top_240');
  const n = data.length;
  // Weighted average percentages
  const wavg = (key) => n > 0 ? (data.reduce((a,r) => a + (Number(r[key])||0), 0) / n) : 0;
  tfoot.innerHTML = `<tr>
    <td class="lbl-col" colspan="2">TOTAL (${n} categorías)</td>
    <td class="sum-col" style="text-align:right">${canal.toLocaleString('es-CL')}</td>
    <td class="sum-col" style="text-align:right">${nico.toLocaleString('es-CL')}</td>
    <td class="sum-col" style="text-align:center">${t30}</td>
    <td class="sum-col" style="text-align:center">${t60}</td>
    <td class="sum-col" style="text-align:center">${t90}</td>
    <td class="sum-col" style="text-align:center">${t120}</td>
    <td class="sum-col" style="text-align:center">${t240}</td>
    <td class="sum-col">${wavg('pct_30').toFixed(1)}%</td>
    <td class="sum-col">${wavg('pct_60').toFixed(1)}%</td>
    <td class="sum-col">${wavg('pct_90').toFixed(1)}%</td>
    <td class="sum-col">${wavg('pct_120').toFixed(1)}%</td>
    <td class="sum-col">${wavg('pct_240').toFixed(1)}%</td>
    <td colspan="4"></td>
  </tr>`;
}

function renderTable(data) {
  const tbody = document.getElementById('audit-tbody');
  tbody.innerHTML = data.map(r => {
    const color = COLORS[r.presence_level] || '#64748b';
    const catLabel = r.category_url
      ? `<a href="${r.category_url}" target="_blank" rel="noopener"
           style="color:var(--text);text-decoration:none;border-bottom:1px dashed var(--border)"
           title="Abrir en marketplace: ${r.category_url}">${r.category}</a>`
      : r.category;
    const brandUrl = r.category_brand_url || r.category_url;
    const linkCell = brandUrl
      ? `<a href="${brandUrl}" target="_blank" rel="noopener"
           title="Abrir Categoría Nicopoly: ${brandUrl}"
           style="color:var(--accent);text-decoration:none;font-size:1rem">↗</a>`
      : '—';
    return `<tr data-mp="${r.marketplace}" data-lvl="${r.presence_level}" data-cat="${r.category}" onclick="selectCategoryRow('${r.marketplace}', '${r.category}', this)">
      <td style="font-weight:500">${r.marketplace}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${r.category}">${catLabel}</td>
      <td style="text-align:right">${(r.total_marketplace||0).toLocaleString('es-CL')}</td>
      <td style="text-align:right">${(r.total_nicopoly||0).toLocaleString('es-CL')}</td>
      <td style="text-align:center">${r.top_30||0}</td>
      <td style="text-align:center">${r.top_60||0}</td>
      <td style="text-align:center">${r.top_90||0}</td>
      <td style="text-align:center">${r.top_120||0}</td>
      <td style="text-align:center">${r.top_240||0}</td>
      <td>${pctBar(r.pct_30, color)}</td>
      <td>${pctBar(r.pct_60, color)}</td>
      <td>${pctBar(r.pct_90, color)}</td>
      <td>${pctBar(r.pct_120, color)}</td>
      <td>${pctBar(r.pct_240, color)}</td>
      <td><span class="lvl lvl-${r.presence_level}">${r.presence_level}</span></td>
      <td style="color:${color};font-weight:500;font-size:.75rem">${r.risk_level||'—'}</td>
      <td style="color:#64748b;font-size:.75rem">${(r.audit_date||'').substring(0,10)}</td>
      <td style="text-align:center">${linkCell}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="18" style="text-align:center;padding:2rem;color:#64748b">Sin datos. Ejecuta una auditoría primero.</td></tr>';
  renderTotals(data);
}

let _currentSort = { col: null, asc: false };

function sortTableBy(col) {
  if (_currentSort.col === col) {
    _currentSort.asc = !_currentSort.asc;
  } else {
    _currentSort.col = col;
    _currentSort.asc = false;
  }
  
  _audits.sort((a, b) => {
    let valA = a[col] || 0;
    let valB = b[col] || 0;
    if (typeof valA === 'string') valA = valA.toLowerCase();
    if (typeof valB === 'string') valB = valB.toLowerCase();
    
    if (valA < valB) return _currentSort.asc ? -1 : 1;
    if (valA > valB) return _currentSort.asc ? 1 : -1;
    return 0;
  });
  filterTable();
}

function filterTable() {
  const q = document.getElementById('search').value.toLowerCase();
  const mp = document.getElementById('mp-filter').value;
  const lvl = document.getElementById('lvl-filter').value;
  const filtered = _audits.filter(r =>
    (!q || r.category.toLowerCase().includes(q)) &&
    (!mp || r.marketplace === mp) &&
    (!lvl || r.presence_level === lvl)
  );
  renderTable(filtered);
}

let _currentChartInstance = null;

function calculateLinearRegression(points, daysToProject = 3) {
  const n = points.length;
  if (n < 2) return { slope: 0, intercept: 0, projections: [] };
  
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += points[i];
    sumXY += i * points[i];
    sumXX += i * i;
  }
  
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  
  const projections = [];
  for (let i = 1; i <= daysToProject; i++) {
    const index = (n - 1) + i;
    const projectedVal = Math.max(0, Math.min(100, slope * index + intercept));
    projections.push(projectedVal);
  }
  return { slope, intercept, projections };
}

function renderFallbackSVG(container, dates, values, projValues) {
  container.innerHTML = '';
  container.style.display = 'flex';
  const canvas = document.getElementById('history-chart');
  if (canvas) canvas.style.display = 'none';

  const w = 700, h = 220, padding = 30;
  const allPoints = [...values];
  const lastVal = values[values.length - 1] || 0;
  let currentVal = lastVal;
  const projPoints = [lastVal, ...projValues];
  
  const minVal = 0;
  const maxVal = 100;
  
  const getX = (i, total) => padding + (i * (w - 2 * padding) / (total - 1));
  const getY = (val) => h - padding - (val * (h - 2 * padding) / 100);

  const totalPoints = values.length + projValues.length;
  let pointsStr = values.map((v, i) => `${getX(i, totalPoints)},${getY(v)}`).join(' ');
  let projStr = projPoints.map((v, i) => `${getX(values.length - 1 + i, totalPoints)},${getY(v)}`).join(' ');

  let svgHTML = `<svg width="100%" height="100%" viewBox="0 0 ${w} ${h}" style="background:transparent; font-family:inherit;">
    <!-- Grid Lines -->
    <line x1="${padding}" y1="${getY(0)}" x2="${w-padding}" y2="${getY(0)}" stroke="#1e2d45" stroke-dasharray="3,3" />
    <line x1="${padding}" y1="${getY(50)}" x2="${w-padding}" y2="${getY(50)}" stroke="#1e2d45" stroke-dasharray="3,3" />
    <line x1="${padding}" y1="${getY(100)}" x2="${w-padding}" y2="${getY(100)}" stroke="#1e2d45" stroke-dasharray="3,3" />
    
    <!-- Axises Text -->
    <text x="${padding - 5}" y="${getY(100) + 4}" fill="#64748b" font-size="9" text-anchor="end">100%</text>
    <text x="${padding - 5}" y="${getY(50) + 4}" fill="#64748b" font-size="9" text-anchor="end">50%</text>
    <text x="${padding - 5}" y="${getY(0) + 4}" fill="#64748b" font-size="9" text-anchor="end">0%</text>

    <!-- Trend Line -->
    <polyline fill="none" stroke="#3b82f6" stroke-width="3" points="${pointsStr}" />
    <!-- Projection Line -->
    <polyline fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-dasharray="5,5" points="${projStr}" />
  `;

  // Draw Dots
  values.forEach((v, i) => {
    svgHTML += `<circle cx="${getX(i, totalPoints)}" cy="${getY(v)}" r="4" fill="#3b82f6" stroke="#0a0d14" stroke-width="1.5" />`;
  });
  projValues.forEach((v, i) => {
    svgHTML += `<circle cx="${getX(values.length + i, totalPoints)}" cy="${getY(v)}" r="4" fill="#06b6d4" stroke="#0a0d14" stroke-width="1.5" />`;
  });

  svgHTML += `</svg>`;
  container.innerHTML = svgHTML;
}

async function renderHistoryChart(mpName) {
  try {
    const res = await fetchJSON(`/api/history/marketplace?marketplace=${encodeURIComponent(mpName)}&days=7`);
    const history = res.history || [];
    const panel = document.getElementById('history-panel');
    
    if (history.length < 2) {
      panel.style.display = 'none';
      return;
    }
    
    panel.style.display = 'block';
    document.getElementById('history-title').innerHTML = `Historial y Proyección de Visibilidad — <span>${mpName}</span>`;
    
    // Sort and compile
    const sorted = [...history].sort((a,b) => a.dia.localeCompare(b.dia));
    const dates = sorted.map(h => h.dia.substring(5)); // MM-DD
    const values = sorted.map(h => h.avg_pct_30);
    
    // Calculate Regression for 3 projected days
    const { slope, projections } = calculateLinearRegression(values, 3);
    const lastDateObj = new Date(sorted[sorted.length - 1].dia + 'T12:00:00');
    
    const projDates = [];
    for (let i = 1; i <= 3; i++) {
      const nextDate = new Date(lastDateObj);
      nextDate.setDate(lastDateObj.getDate() + i);
      const m = String(nextDate.getMonth() + 1).padStart(2, '0');
      const d = String(nextDate.getDate()).padStart(2, '0');
      projDates.push(`${m}-${d}`);
    }

    // Trend calculation vs 7-day average of previous days
    const lastVal = values[values.length - 1];
    const prevValues = values.slice(0, -1);
    const avgVal = prevValues.length > 0 ? (prevValues.reduce((a,c) => a + c, 0) / prevValues.length) : lastVal;
    const diff = lastVal - avgVal;
    
    const trendValueSpan = document.getElementById('history-trend-value');
    const trendBadgeSpan = document.getElementById('history-trend-badge');
    
    trendValueSpan.textContent = (lastVal).toFixed(1) + '%';
    
    if (diff > 0.05) {
      trendBadgeSpan.textContent = `+${diff.toFixed(1)}% ↑`;
      trendBadgeSpan.className = 'badge badge-ok';
      trendBadgeSpan.style.background = 'rgba(16,185,129,0.15)';
      trendBadgeSpan.style.color = '#10b981';
    } else if (diff < -0.05) {
      trendBadgeSpan.textContent = `${diff.toFixed(1)}% ↓`;
      trendBadgeSpan.className = 'badge badge-err';
      trendBadgeSpan.style.background = 'rgba(239,68,68,0.15)';
      trendBadgeSpan.style.color = '#ef4444';
      
      // Dynamic Alert Trigger (Plan B): Alert on drops higher than 15% from weekly average
      if (diff <= -15.0) {
        injectDynamicAlert(mpName, lastVal, avgVal);
      }
    } else {
      trendBadgeSpan.textContent = '= Estable';
      trendBadgeSpan.className = 'badge badge-warn';
      trendBadgeSpan.style.background = 'rgba(245,158,11,0.15)';
      trendBadgeSpan.style.color = '#f59e0b';
    }

    // Draw using Chart.js if loaded, otherwise SVG fallback
    if (window.Chart) {
      const canvas = document.getElementById('history-chart');
      const fallback = document.getElementById('history-fallback-svg');
      canvas.style.display = 'block';
      fallback.style.display = 'none';

      if (_currentChartInstance) {
        _currentChartInstance.destroy();
      }

      // Combine historical and projected data for Chart.js rendering
      const chartLabels = [...dates, ...projDates];
      const historyDataset = [...values];
      const projectionDataset = Array(values.length - 1).fill(null);
      projectionDataset.push(values[values.length - 1]); // bridge the gap
      projectionDataset.push(...projections);

      _currentChartInstance = new Chart(canvas, {
        type: 'line',
        data: {
          labels: chartLabels,
          datasets: [
            {
              label: 'Presencia TOP30 (Real)',
              data: historyDataset,
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              borderWidth: 3,
              tension: 0.3,
              fill: true,
              pointBackgroundColor: '#3b82f6',
              pointHoverRadius: 6
            },
            {
              label: 'Proyección (3 días)',
              data: projectionDataset,
              borderColor: '#06b6d4',
              borderWidth: 2.5,
              borderDash: [6, 6],
              tension: 0.1,
              fill: false,
              pointBackgroundColor: '#06b6d4'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: '#e2e8f0', font: { family: 'Inter' } }
            },
            tooltip: {
              callbacks: {
                label: (ctx) => ` Visibilidad: ${ctx.raw.toFixed(1)}%`
              }
            }
          },
          scales: {
            x: {
              ticks: { color: '#64748b' },
              grid: { color: '#1e2d45' }
            },
            y: {
              min: 0,
              max: 100,
              ticks: { color: '#64748b', callback: (v) => v + '%' },
              grid: { color: '#1e2d45' }
            }
          }
        }
      });
    } else {
      const fallback = document.getElementById('history-fallback-svg');
      renderFallbackSVG(fallback, dates, values, projections);
    }
  } catch (err) {
    console.error('History chart error', err);
  }
}

let _currentSelectedMp = '';
let _currentSelectedCat = '';

async function selectCategoryRow(mp, cat, element) {
  _currentSelectedMp = mp;
  _currentSelectedCat = cat;
  
  // Clear other selected row styles
  document.querySelectorAll('#audit-tbody tr').forEach(r => {
    r.style.background = '';
    r.style.borderLeft = '';
  });
  if (element) {
    element.style.background = 'var(--surface2)';
    element.style.borderLeft = '3px solid var(--accent)';
  }
  
  const filterSel = document.getElementById('snapshots-filter-select');
  const onlyNico = filterSel ? (filterSel.value === 'true') : true;

  // Render history chart & category products with prices
  await renderCategoryHistoryChart(mp, cat);
  await renderCategoryProductsTable(mp, cat, onlyNico);
}

async function toggleSnapshotsFilter() {
  const filterSel = document.getElementById('snapshots-filter-select');
  const onlyNico = filterSel ? (filterSel.value === 'true') : true;
  if (_currentSelectedMp && _currentSelectedCat) {
    await renderCategoryProductsTable(_currentSelectedMp, _currentSelectedCat, onlyNico);
  }
}

async function renderCategoryProductsTable(mpName, catName, onlyNico = true) {
  try {
    const res = await fetchJSON(`/api/snapshots?marketplace=${encodeURIComponent(mpName)}&category=${encodeURIComponent(catName)}&limit=1000&only_nicopoly=${onlyNico}`);
    const products = res.products || [];
    const container = document.getElementById('snapshots-table-container');
    const countSpan = document.getElementById('snapshots-count');
    const titleHeader = document.getElementById('snapshots-table-title');
    
    const modeBadge = onlyNico ? '<span style="color:var(--success); font-weight:600;">(Solo Marca Nicopoly)</span>' : '<span style="color:var(--accent2); font-weight:500;">(Todos los Productos del Canal)</span>';
    if (titleHeader) titleHeader.innerHTML = `Detalle de Productos, SKUs & Precios — <span style="color:var(--accent)">${mpName} / ${catName}</span> ${modeBadge}`;
    if (countSpan) countSpan.textContent = `${products.length} productos en vista`;
    
    if (!container) return;

    if (!products.length) {
      const msg = onlyNico
        ? `No hay productos de <strong>Nicopoly</strong> registrados aún en la captura de <strong>${mpName} / ${catName}</strong>.`
        : `Sin capturas registradas para <strong>${mpName} / ${catName}</strong>. Ejecuta una auditoría (▶ Audit All) para generar los snapshots.`;
      container.innerHTML = `<div style="padding: 1rem; color: var(--muted); font-size: 0.82rem; text-align: center; border: 1px dashed var(--border); border-radius: 8px;">
        ${msg}
      </div>`;
      return;
    }
    
    let html = `<table style="width:100%; border-collapse:collapse; font-size:0.8rem; margin-top:0.4rem;">
      <thead>
        <tr style="border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 0.7rem;">
          <th style="padding: 0.55rem; text-align: center;">Posición</th>
          <th style="padding: 0.55rem; text-align: left;">Producto</th>
          <th style="padding: 0.55rem; text-align: left;">SKU Máster (Multivende)</th>
          <th style="padding: 0.55rem; text-align: left;">Código Marketplace</th>
          <th style="padding: 0.55rem; text-align: right;">Precio Publicado</th>
          <th style="padding: 0.55rem; text-align: right;">Precio Multivende</th>
          <th style="padding: 0.55rem; text-align: center;">Estado Alerta</th>
        </tr>
      </thead>
      <tbody>`;
      
    products.forEach(p => {
      const priceStr = p.price > 0 ? `$${p.price.toLocaleString('es-CL')}` : '—';
      const priceMvStr = p.price_multivende > 0 ? `$${p.price_multivende.toLocaleString('es-CL')}` : '—';
      
      let priceAlertBadge = '<span class="badge badge-ok">✓ Alineado</span>';
      
      const hasMvPrice = (p.price_multivende > 0) || (p.price_multivende_offer > 0);

      // Stock check first
      if (p.stock_multivende === 0) {
        priceAlertBadge = `<span class="badge badge-warn" style="background:rgba(239,68,68,0.2); color:#ef4444;" title="Publicado pero sin stock en Multivende">⚠️ SIN STOCK MV</span>`;
      } 
      // Missing Multivende link entirely
      else if (!hasMvPrice) {
        priceAlertBadge = `<span class="badge badge-warn" style="background:rgba(107,114,128,0.2); color:var(--muted);" title="Sin Precio Multivende">⚠️ Sin Precio MV</span>`;
      }
      // Missing Published Price
      else if (p.price == 0 && hasMvPrice) {
        priceAlertBadge = `<span class="badge badge-warn" title="Precio no detectado">⚠️ Sin Precio Pub.</span>`;
      } 
      // Compare prices (base and offer)
      else if (p.price > 0 && hasMvPrice) {
        const p_mv_base = p.price_multivende || 0;
        const p_mv_offer = p.price_multivende_offer || 0;
        
        // If base is 0, we only compare against offer
        const diffBase = p_mv_base > 0 ? p.price - p_mv_base : null;
        const diffOffer = p_mv_offer > 0 ? p.price - p_mv_offer : null;
        
        let alignedBase = (diffBase !== null && Math.abs(diffBase) < 1.0);
        let alignedOffer = (diffOffer !== null && Math.abs(diffOffer) < 1.0);
        
        if (alignedOffer) {
          priceAlertBadge = '<span class="badge badge-ok" style="background:rgba(16,185,129,0.2); color:#10b981;" title="Coincide con precio oferta Multivende">🏷️ Oferta Activa</span>';
        } else if (alignedBase) {
          priceAlertBadge = '<span class="badge badge-ok">✓ Alineado</span>';
        } else {
          // It doesn't match base or offer. Use the closest diff for the badge.
          let diffToUse = diffBase !== null ? diffBase : diffOffer;
          if (diffBase !== null && diffOffer !== null) {
              diffToUse = Math.abs(diffOffer) < Math.abs(diffBase) ? diffOffer : diffBase;
          }
          const sign = diffToUse > 0 ? '+' : '';
          priceAlertBadge = `<span class="badge badge-warn" style="background:rgba(245,158,11,0.2); color:#f59e0b;" title="Discrepancia con precio(s) de Multivende">⚠️ ${sign}$${diffToUse.toLocaleString('es-CL')}</span>`;
        }
      }

      const isNico = p.is_nicopoly ? 'color: var(--success); font-weight: 600;' : '';
      const skuMasterStr = p.sku_master ? `<strong style="color:var(--accent)">${p.sku_master}</strong>` : '<span style="color:var(--muted)">Sin match</span>';
      const mktSkuStr = p.marketplace_sku ? `<code>${p.marketplace_sku}</code>` : '—';
      
      html += `<tr style="border-bottom: 1px solid var(--border);">
        <td style="padding: 0.55rem; text-align: center; font-weight: 600; color: var(--accent2);">#${p.position_absolute}</td>
        <td style="padding: 0.55rem; ${isNico}">${p.product_title}</td>
        <td style="padding: 0.55rem;">${skuMasterStr}</td>
        <td style="padding: 0.55rem;">${mktSkuStr}</td>
        <td style="padding: 0.55rem; text-align: right; color: var(--success); font-weight: 600;">${priceStr}</td>
        <td style="padding: 0.55rem; text-align: right; color: var(--accent2); font-weight: 500;">${priceMvStr}</td>
        <td style="padding: 0.55rem; text-align: center;">${priceAlertBadge}</td>
      </tr>`;
    });
    
    html += `</tbody></table>`;
    container.innerHTML = html;
  } catch (e) {
    console.error('Error rendering category products table', e);
  }
}

async function renderCategoryHistoryChart(mpName, catName) {
  try {
    const res = await fetchJSON(`/api/history?marketplace=${encodeURIComponent(mpName)}&category=${encodeURIComponent(catName)}&days=7`);
    const history = res.history || [];
    const panel = document.getElementById('history-panel');
    
    if (history.length < 2) {
      showToast(`Sin historial suficiente para la categoría: ${catName}`, true);
      return;
    }
    
    panel.style.display = 'block';
    document.getElementById('history-title').innerHTML = `Historial de Visibilidad y Catálogo — <span>${mpName} / ${catName}</span>`;
    
    // Sort and compile
    const sorted = [...history].sort((a,b) => a.audit_date.localeCompare(b.audit_date));
    const dates = sorted.map(h => h.audit_date.substring(5, 10)); // MM-DD
    const values = sorted.map(h => h.pct_30);
    const nicoCounts = sorted.map(h => h.total_nicopoly || 0);
    
    // Calculate Regression for 3 projected days of pct_30
    const { slope, projections } = calculateLinearRegression(values, 3);
    const lastDateObj = new Date(sorted[sorted.length - 1].audit_date.substring(0, 10) + 'T12:00:00');
    
    const projDates = [];
    for (let i = 1; i <= 3; i++) {
      const nextDate = new Date(lastDateObj);
      nextDate.setDate(lastDateObj.getDate() + i);
      const m = String(nextDate.getMonth() + 1).padStart(2, '0');
      const d = String(nextDate.getDate()).padStart(2, '0');
      projDates.push(`${m}-${d}`);
    }

    // Trend calculation vs 7-day average of previous days for pct_30
    const lastVal = values[values.length - 1];
    const prevValues = values.slice(0, -1);
    const avgVal = prevValues.length > 0 ? (prevValues.reduce((a,c) => a + c, 0) / prevValues.length) : lastVal;
    const diff = lastVal - avgVal;
    
    const trendValueSpan = document.getElementById('history-trend-value');
    const trendBadgeSpan = document.getElementById('history-trend-badge');
    
    trendValueSpan.textContent = (lastVal).toFixed(1) + '%';
    
    if (diff > 0.05) {
      trendBadgeSpan.textContent = `+${diff.toFixed(1)}% ↑`;
      trendBadgeSpan.className = 'badge badge-ok';
      trendBadgeSpan.style.background = 'rgba(16,185,129,0.15)';
      trendBadgeSpan.style.color = '#10b981';
    } else if (diff < -0.05) {
      trendBadgeSpan.textContent = `${diff.toFixed(1)}% ↓`;
      trendBadgeSpan.className = 'badge badge-err';
      trendBadgeSpan.style.background = 'rgba(239,68,68,0.15)';
      trendBadgeSpan.style.color = '#ef4444';
    } else {
      trendBadgeSpan.textContent = '= Estable';
      trendBadgeSpan.className = 'badge badge-warn';
      trendBadgeSpan.style.background = 'rgba(245,158,11,0.15)';
      trendBadgeSpan.style.color = '#f59e0b';
    }

    // Update sub text to represent category-specific analytics
    document.getElementById('history-trend-sub').innerHTML = `Presencia TOP30 vs promedio semanal.`;
    document.getElementById('history-projection-sub').innerHTML = `Proyección de visibilidad para los próximos 3 días.`;

    // Draw using Chart.js if loaded, otherwise SVG fallback
    if (window.Chart) {
      const canvas = document.getElementById('history-chart');
      const fallback = document.getElementById('history-fallback-svg');
      canvas.style.display = 'block';
      fallback.style.display = 'none';

      if (_currentChartInstance) {
        _currentChartInstance.destroy();
      }

      const chartLabels = [...dates, ...projDates];
      const historyDataset = [...values];
      const projectionDataset = Array(values.length - 1).fill(null);
      projectionDataset.push(values[values.length - 1]); // bridge
      projectionDataset.push(...projections);
      
      const nicoDataset = [...nicoCounts, ...Array(3).fill(null)]; // no projection for catalog size, just show historical

      _currentChartInstance = new Chart(canvas, {
        type: 'line',
        data: {
          labels: chartLabels,
          datasets: [
            {
              label: 'Presencia TOP30 (%)',
              data: historyDataset,
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.05)',
              borderWidth: 3,
              tension: 0.3,
              fill: true,
              yAxisID: 'y_vis',
              pointBackgroundColor: '#3b82f6',
              pointHoverRadius: 6
            },
            {
              label: 'Proyección (%)',
              data: projectionDataset,
              borderColor: '#06b6d4',
              borderWidth: 2,
              borderDash: [6, 6],
              tension: 0.1,
              fill: false,
              yAxisID: 'y_vis',
              pointBackgroundColor: '#06b6d4'
            },
            {
              label: 'Total Nico (Productos)',
              data: nicoDataset,
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.05)',
              borderWidth: 2.5,
              tension: 0.2,
              fill: false,
              yAxisID: 'y_nico',
              pointBackgroundColor: '#f59e0b',
              pointHoverRadius: 5
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: '#e2e8f0', font: { family: 'Inter' } }
            }
          },
          scales: {
            x: {
              ticks: { color: '#64748b' },
              grid: { color: '#1e2d45' }
            },
            y_vis: {
              type: 'linear',
              position: 'left',
              min: 0,
              max: 100,
              ticks: { color: '#3b82f6', callback: (v) => v + '%' },
              grid: { color: '#1e2d45' },
              title: { display: true, text: 'Visibilidad (%)', color: '#3b82f6' }
            },
            y_nico: {
              type: 'linear',
              position: 'right',
              min: 0,
              ticks: { color: '#f59e0b', stepSize: 10 },
              grid: { drawOnChartArea: false }, // avoid grid overlap
              title: { display: true, text: 'Total Productos Nico (U)', color: '#f59e0b' }
            }
          }
        }
      });
    } else {
      const fallback = document.getElementById('history-fallback-svg');
      renderFallbackSVG(fallback, dates, values, projections); // fallback uses vis values only
    }
  } catch (err) {
    console.error('History chart error', err);
  }
}

function injectDynamicAlert(mpName, currentVal, avgVal) {
  const alertId = 'dyn-' + mpName.toLowerCase().replace(' ', '-');
  if (document.getElementById('alert-' + alertId)) return; // already alert visible

  const sec = document.getElementById('alerts-section');
  const alertMsg = `Alerta de Caída Crítica: La presencia de <strong>${mpName}</strong> ha caído a un <strong>${currentVal.toFixed(1)}%</strong> (caída de ${(avgVal - currentVal).toFixed(1)}% bajo el promedio semanal de ${avgVal.toFixed(1)}%). Revisa si hay deactivaciones o quiebres de stock.`;
  
  const alertsHeader = sec.querySelector('.section-title');
  if (!alertsHeader) {
    sec.innerHTML = `<h2 class="section-title">Alertas Activas</h2>`;
  }
  
  const alertHTML = `
    <div class="alert-item" id="alert-${alertId}" style="border-color: var(--danger); background: rgba(239, 68, 68, 0.05); animation: fadeIn 0.4s ease;">
      <span class="alert-icon">🚨</span>
      <span class="alert-msg">${alertMsg}</span>
      <span class="alert-time">Hace un momento</span>
      <button class="ack-btn" onclick="document.getElementById('alert-${alertId}').remove(); showToast('Alerta descartada ✓');">✓ OK</button>
    </div>
  `;
  
  // Prepend alert item
  const container = document.createElement('div');
  container.innerHTML = alertHTML;
  sec.appendChild(container.firstElementChild);
  
  showToast(`🚨 Alerta de caída en ${mpName} detectada`, true);
}

function setMpFilter(mp) {
  document.getElementById('mp-filter').value = mp;
  filterTable();
  document.querySelectorAll('.mp-card').forEach(c => {
    c.classList.toggle('active', c.querySelector('.mp-name').textContent === mp);
  });
  renderHistoryChart(mp);
}

async function ackAlert(id) {
  await fetch(`/api/alerts/${id}/ack`, {method:'POST'});
  document.getElementById('alert-'+id)?.remove();
  showToast('Alerta confirmada ✓');
}

let _auditStatusTimer = null;
let _lastAuditStatus = 'IDLE';

async function checkAuditStatus() {
  try {
    const data = await fetchJSON('/api/audit/status');
    const btn = document.getElementById('trigger-btn');
    const currentStatus = data?.status || 'IDLE';

    if (currentStatus === 'RUNNING') {
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spin">⟳</span> Auditando...';
      }
      _lastAuditStatus = 'RUNNING';
      if (_auditStatusTimer) clearTimeout(_auditStatusTimer);
      _auditStatusTimer = setTimeout(checkAuditStatus, 2000);
    } else {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '▶ Audit All';
      }
      // When backend transitions RUNNING -> IDLE: refresh dashboard once
      if (_lastAuditStatus === 'RUNNING') {
        _lastAuditStatus = 'IDLE';
        showToast('Auditoría completada exitosamente');
        await loadAll();
      }
      _lastAuditStatus = 'IDLE';
      if (_auditStatusTimer) clearTimeout(_auditStatusTimer);
      _auditStatusTimer = setTimeout(checkAuditStatus, 5000);
    }
  } catch (err) {
    console.warn('Error al verificar estado de auditoría:', err);
    if (_auditStatusTimer) clearTimeout(_auditStatusTimer);
    _auditStatusTimer = setTimeout(checkAuditStatus, 5000);
  }
}

async function triggerAudit(mp, btnEl) {
  const btn = btnEl || document.getElementById('trigger-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spin">⟳</span> Auditando...';
  }
  _lastAuditStatus = 'RUNNING';

  try {
    const r = await fetch(`/api/audit/trigger?marketplace=${mp}`, {
      method: 'POST'
    });
    const d = await r.json();
    if (r.status === 409 || d.status === 'already_running') {
      showToast(d.message || 'Una auditoría ya está en curso', true);
    } else if (r.ok) {
      showToast(d.message || 'Auditoría iniciada en segundo plano');
    } else {
      showToast(d.detail || d.message || 'Error al iniciar auditoría', true);
    }
  } catch(e) {
    showToast('Error de comunicación con el servidor', true);
  } finally {
    if (_auditStatusTimer) clearTimeout(_auditStatusTimer);
    _auditStatusTimer = setTimeout(checkAuditStatus, 1000);
  }
}

async function lookupMultivendeSKU() {
  const query = document.getElementById('mv-sku-input').value.trim();
  const mkt = document.getElementById('mv-mkt-select').value;
  if (!query) return showToast('Ingresa un SKU o nombre para buscar', true);

  try {
    const res = await fetch(`/api/multivende/lookup?marketplace=${encodeURIComponent(mkt)}&query=${encodeURIComponent(query)}`);
    const data = await res.json();
    const resultCard = document.getElementById('mv-result-card');
    
    if (data.result) {
      resultCard.style.display = 'block';
      document.getElementById('res-sku-master').textContent = data.result.sku_master || '-';
      document.getElementById('res-sku-details').textContent = `${data.result.sku_hijo || '-'} / ${data.result.sku_padre || '-'}`;
      document.getElementById('res-product-name').textContent = data.result.product_name || '-';
      document.getElementById('res-brand').textContent = data.result.brand || 'Nicopoly';

      if (data.result.sku_master) {
        fetchPriceHistory(data.result.sku_master);
      }
    } else {
      resultCard.style.display = 'block';
      document.getElementById('res-sku-master').textContent = 'No Encontrado';
      document.getElementById('res-sku-details').textContent = '-';
      document.getElementById('res-product-name').textContent = `Sin coincidencia exacta en matriz de Multivende para "${query}"`;
      document.getElementById('res-brand').textContent = '-';
      document.getElementById('mv-price-history-table').innerHTML = '<span style="color: var(--warn);">Sin registros de precio.</span>';
    }
  } catch (e) {
    showToast('Error al consultar matriz de Multivende', true);
  }
}

async function fetchPriceHistory(skuMaster) {
  try {
    const res = await fetch(`/api/price-history?sku_master=${encodeURIComponent(skuMaster)}`);
    const data = await res.json();
    const tableContainer = document.getElementById('mv-price-history-table');
    
    if (data.history && data.history.length > 0) {
      let html = '<table style="width:100%; border-collapse:collapse; margin-top:0.4rem;"><thead><tr><th>Fecha</th><th>Marketplace</th><th>Categoría</th><th>Precio Publicado</th><th>Posición</th></tr></thead><tbody>';
      data.history.forEach(h => {
        html += `<tr><td>${h.audit_date.split('T')[0]}</td><td>${h.marketplace}</td><td>${h.category}</td><td style="color: var(--success); font-weight:600;">$${h.price.toLocaleString('es-CL')}</td><td>#${h.position_absolute}</td></tr>`;
      });
      html += '</tbody></table>';
      tableContainer.innerHTML = html;
    } else {
      tableContainer.innerHTML = '<span style="color: var(--muted);">Sin capturas de precio registradas aún para este SKU.</span>';
    }
  } catch (e) {
    console.error('Error fetching price history', e);
  }
}

function showToast(msg, err=false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  const announcer = document.getElementById('sr-announcer');
  if (announcer) announcer.textContent = msg;
  t.style.borderColor = err ? '#ef4444' : '#3b82f6';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.display = 'none'; }, 4000);
}

// Init
loadAll();
checkAuditStatus();
// Auto-refresh every 2 minutes
setInterval(loadAll, 120000);