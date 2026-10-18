(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const icon = (name) => `<svg><use href="/static/icons.svg#${name}"></use></svg>`;
  const state = {
    period: '24h', deviceId: document.body.dataset.deviceId,
    demoMode: document.body.dataset.demoMode === 'true',
    data: null, busy: false, toastTimer: null,
  };
  const formatter = new Intl.NumberFormat('id-ID');
  const decimal = (v, digits = 1) => new Intl.NumberFormat('id-ID', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(Number(v) || 0);
  const rupiah = (v) => `Rp ${formatter.format(Math.round(Number(v) || 0))}`;
  const htmlEscape = (raw) => String(raw ?? '').replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const displayDateTime = (iso) => iso ? new Date(iso).toLocaleString('id-ID', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  }) : '—';
  const displayTime = (iso) => iso ? new Date(iso).toLocaleTimeString('id-ID', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  }) : '—';

  function toast(message, isError = false) {
    const el = $('toast');
    el.textContent = message;
    el.classList.toggle('error', isError);
    el.classList.add('visible');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => el.classList.remove('visible'), 3400);
  }
  async function api(url, options = {}) {
    const res = await fetch(url, {headers: {'Accept': 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {})}, ...options});
    let payload;
    try { payload = await res.json(); } catch (_) { payload = {}; }
    if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`);
    return payload;
  }
  function setText(id, value) {const el = $(id); if (el) el.textContent = value;}

  function renderOverview(data) {
    if (data.empty) {
      $('apiError').hidden = false;
      setText('apiErrorMessage', data.message);
      return;
    }
    $('apiError').hidden = true;
    const s = data.stats;
    setText('statPower', formatter.format(Math.round(s.power_w)));
    setText('statEnergy', decimal(s.energy_24h_kwh, 2));
    setText('statCost', formatter.format(s.cost_30d));
    setText('statPeak', formatter.format(Math.round(s.peak_24h_w)));
    setText('statAvg', `${formatter.format(Math.round(s.average_24h_w))} W`);
    setText('statVoltage', `${decimal(s.voltage_v, 1)} V`);
    const positive = s.change_24h_percent > 0;
    const change = $('statChange');
    change.textContent = `${positive ? '+' : ''}${decimal(s.change_24h_percent, 1)}%`;
    change.className = `change-chip ${positive ? 'up' : 'down'}`;
    setText('tariffCaption', `${rupiah(data.settings.tariff_per_kwh)} / kWh`);
    setText('liveVoltage', `${decimal(s.voltage_v, 1)} V`);
    setText('liveCurrent', `${decimal(s.current_a, 2)} A`);
    setText('liveFrequency', `${decimal(s.frequency_hz, 2)} Hz`);
    setText('liveFactor', decimal(s.power_factor, 2));
    setText('liveTimestamp', displayDateTime(data.latest.timestamp));
    setText('sidebarDeviceName', data.device.name);
    setText('sidebarDeviceStatus', data.online ? '● Aktif / pembacaan terbaru' : '○ Belum ada pembacaan baru');
    setText('bannerDeviceStatus', data.online ? 'Device online' : 'Device offline');
    setText('bannerDeviceId', data.device_id);
    setText('lastUpdated', `Update ${displayTime(data.generated_at)}`);
    setText('modeLabel', data.mode === 'iot' ? 'IOT DATA CONNECTED' : 'DEMO DATA ACTIVE');
    const onlineBadge = $('onlineBadge');
    onlineBadge.classList.toggle('offline', !data.online);
    onlineBadge.innerHTML = `<i></i> ${data.online ? 'ONLINE' : 'OFFLINE'}`;
    setText('forecastKwh', decimal(data.forecast.total_kwh, 2));
    setText('forecastCost', rupiah(data.forecast.estimated_cost));
    setText('chartPointsLabel', `${formatter.format(data.sample_count)} pembacaan tersimpan`);
    setText('navAlertCount', String(data.unread_alerts));
    setText('alertsCount', `${data.unread_alerts} baru`);
    $('notificationDot').hidden = data.unread_alerts === 0;
    renderForecast(data.forecast.days);
    renderAlerts(data.alerts);
    renderRecommendations(data.recommendations);
    renderHistory(data.history);
    renderCharts();
  }

  function chartLabel(at) {
    if (state.period === '24h') return new Date(at).toLocaleTimeString('id-ID', {hour: '2-digit', minute: '2-digit', hour12: false});
    return new Date(`${at}T12:00:00+07:00`).toLocaleDateString('id-ID', {day: 'numeric', month: 'short'});
  }
  function renderCharts() {
    if (!state.data || state.data.empty) return;
    const data = state.data.series;
    drawChart('powerChart', 'powerChartWrap', 'powerTooltip', data.map(v => v.power_w),
      data.map(v => chartLabel(v.at)), 'line', '#4aac8b', 'W');
    drawChart('energyChart', null, 'energyTooltip', data.map(v => v.energy_kwh),
      data.map(v => chartLabel(v.at)), 'bar', '#b4e68a', 'kWh');
  }

  function drawChart(svgId, wrapId, tooltipId, rawValues, labels, type, color, suffix) {
    const svg = $(svgId);
    const wrap = svg.parentElement;
    const tooltip = $(tooltipId);
    const width = Math.max(330, Math.floor(wrap.clientWidth || 750));
    const height = Math.max(185, Math.floor(wrap.clientHeight || 226));
    const left = 47, right = 13, top = 17, bottom = 36;
    const plotW = width - left - right, plotH = height - top - bottom;
    const values = rawValues.map(v => Number.isFinite(+v) ? Math.max(0, +v) : 0);
    if (!values.length) return;
    const maxVal = Math.max(...values, 0.001);
    const ceiling = maxVal * 1.19;
    const n = values.length;
    const x = i => left + (type === 'bar' ? ((i + 0.5) / n) * plotW : n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const y = v => top + plotH * (1 - v / ceiling);
    let markup = '';
    for (let tick = 0; tick <= 4; tick++) {
      const yy = top + tick / 4 * plotH;
      const tickVal = ceiling * (1 - tick / 4);
      const label = suffix === 'W' ? formatter.format(Math.round(tickVal)) : decimal(tickVal, tickVal < 10 ? 1 : 0);
      markup += `<line x1="${left}" y1="${yy.toFixed(1)}" x2="${(width-right).toFixed(1)}" y2="${yy.toFixed(1)}" stroke="#e9eff0" stroke-width="1" stroke-dasharray="3 5"/>`;
      markup += `<text x="${left-10}" y="${(yy+3).toFixed(1)}" text-anchor="end" fill="#a1b1b9" font-size="9" font-family="Plus Jakarta Sans, sans-serif">${label}</text>`;
    }
    const step = n > 21 ? Math.ceil(n / 6) : n > 10 ? Math.ceil(n / 5) : 1;
    for (let i = 0; i < n; i += step) {
      markup += `<text x="${x(i).toFixed(1)}" y="${height-10}" text-anchor="middle" fill="#a6b3bc" font-size="9" font-family="Plus Jakarta Sans, sans-serif">${htmlEscape(labels[i])}</text>`;
    }
    if (type === 'line') {
      const coords = values.map((v, i) => [x(i), y(v)]);
      let path = `M ${coords[0][0].toFixed(2)} ${coords[0][1].toFixed(2)}`;
      if (coords.length > 1) {
        for (let i = 1; i < coords.length; i++) {
          const prev = coords[i-1], curr = coords[i];
          const mid = (prev[0]+curr[0])/2;
          path += ` C ${mid.toFixed(2)} ${prev[1].toFixed(2)},${mid.toFixed(2)} ${curr[1].toFixed(2)},${curr[0].toFixed(2)} ${curr[1].toFixed(2)}`;
        }
      }
      const area = `${path} L ${x(n-1).toFixed(2)} ${(top+plotH).toFixed(2)} L ${x(0).toFixed(2)} ${(top+plotH).toFixed(2)} Z`;
      markup += `<defs><linearGradient id="${svgId}-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#61c9a3" stop-opacity=".24"/><stop offset="100%" stop-color="#61c9a3" stop-opacity=".005"/></linearGradient></defs>`;
      markup += `<path d="${area}" fill="url(#${svgId}-fill)"/>`;
      markup += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.8" stroke-linecap="round"/>`;
      if (n <= 8) coords.forEach(([xx,yy]) => {markup += `<circle cx="${xx.toFixed(1)}" cy="${yy.toFixed(1)}" r="3.4" fill="white" stroke="${color}" stroke-width="2"/>`;});
    } else {
      const barW = Math.min(35, Math.max(3, plotW / n * .68));
      values.forEach((v, i) => {
        const yy = y(v);
        const barH = Math.max(0, top + plotH - yy);
        markup += `<rect x="${(x(i)-barW/2).toFixed(1)}" y="${yy.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" opacity="${i===n-1 ? 1 : .81}" rx="4"/>`;
      });
    }
    const hitWidth = plotW / Math.max(1, n);
    for (let i = 0; i < n; i++) {
      markup += `<rect data-index="${i}" x="${Math.max(left,x(i)-hitWidth/2).toFixed(1)}" y="${top}" width="${hitWidth.toFixed(1)}" height="${plotH}" fill="transparent" style="cursor:crosshair"/>`;
    }
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.innerHTML = markup;
    // Bind once. Handler reads current dataset through properties to support refresh.
    svg._chartData = {values, labels, suffix, x, y};
    if (!svg._hoverBound) {
      svg.addEventListener('pointermove', (event) => {
        const target = event.target.closest('[data-index]');
        if (!target) {tooltip.hidden = true; return;}
        const i = Number(target.dataset.index);
        const current = svg._chartData;
        const value = current.values[i];
        tooltip.innerHTML = `${htmlEscape(current.labels[i])}<strong>${decimal(value, current.suffix === 'W' ? 0 : 2)} ${current.suffix}</strong>`;
        const bounds = wrap.getBoundingClientRect();
        tooltip.style.left = `${Math.max(55, Math.min(bounds.width-55, event.clientX-bounds.left))}px`;
        tooltip.style.top = `${Math.max(50, event.clientY-bounds.top-5)}px`;
        tooltip.hidden = false;
      });
      svg.addEventListener('pointerleave', () => {tooltip.hidden = true;});
      svg._hoverBound = true;
    }
  }

  function renderForecast(days) {
    if (!days.length) return;
    const high = Math.max(...days.map(d => d.energy_kwh), 0.1);
    $('forecastSpark').innerHTML = days.map(d => {
      const local = new Date(`${d.date}T12:00:00+07:00`);
      const day = local.toLocaleDateString('id-ID', {weekday: 'short'});
      return `<div class="forecast-bar-wrap" title="${htmlEscape(d.date)} · ${decimal(d.energy_kwh, 2)} kWh"><div class="forecast-bar" style="height:${Math.max(3,Math.round(d.energy_kwh/high*74))}px"></div><small>${htmlEscape(day)}</small></div>`;
    }).join('');
  }
  function renderAlerts(alerts) {
    const el = $('alertsList');
    if (!alerts.length) {el.innerHTML = '<div class="empty-data">Belum ada peringatan. Semua terpantau.</div>'; return;}
    el.innerHTML = alerts.slice(0, 4).map(a => `<div class="alert-item ${a.status === 'acknowledged' ? 'acknowledged' : ''}"><span class="alert-icon ${htmlEscape(a.severity)}">${icon(a.severity === 'info' ? 'info' : 'bell')}</span><div class="alert-copy"><h4>${htmlEscape(a.title)}</h4><p>${htmlEscape(a.message)}</p><small>${displayDateTime(a.timestamp)}</small></div>${a.status !== 'acknowledged' ? `<button type="button" class="ack-button" data-ack-id="${htmlEscape(a.id)}" title="Tandai sudah dibaca">✓ Dibaca</button>` : ''}</div>`).join('');
  }
  function renderRecommendations(recommendations) {
    $('recommendationsList').innerHTML = recommendations.map(r => `<div class="rec-item"><span class="rec-icon ${htmlEscape(r.type)}">${icon(r.type === 'warning' ? 'bell' : r.type === 'good' ? 'shield' : 'lightbulb')}</span><div class="rec-copy"><h4>${htmlEscape(r.title)}</h4><p>${htmlEscape(r.description)}</p></div></div>`).join('');
  }
  function renderHistory(history) {
    $('historyRows').innerHTML = history.map(r => `<tr><td>${displayDateTime(r.timestamp)}</td><td>${decimal(r.voltage_v, 1)} V</td><td>${decimal(r.current_a, 2)} A</td><td>${decimal(r.power_w, 1)} W</td><td>${decimal(r.energy_kwh, 3)} kWh</td><td>${decimal(r.frequency_hz, 2)} Hz</td><td><span class="source-tag ${r.source === 'iot' ? 'iot' : ''}">${htmlEscape(r.source.toUpperCase())}</span></td></tr>`).join('') || '<tr><td colspan="7" class="empty-data">Belum ada pembacaan.</td></tr>';
  }

  async function loadDashboard({silent = false} = {}) {
    if (state.busy) return;
    state.busy = true;
    $('refreshButton').disabled = true;
    try {
      const data = await api(`/api/overview?period=${state.period}&device_id=${encodeURIComponent(state.deviceId)}`);
      state.data = data;
      renderOverview(data);
    } catch (error) {
      $('apiError').hidden = false;
      setText('apiErrorMessage', error.message);
      if (!silent) toast(`Gagal memuat: ${error.message}`, true);
    } finally {
      state.busy = false;
      $('refreshButton').disabled = false;
    }
  }

  function setModal(open) {
    $('settingsModal').hidden = !open;
    document.body.style.overflow = open ? 'hidden' : '';
  }
  async function showSettings() {
    try {
      const settings = await api(`/api/settings?device_id=${encodeURIComponent(state.deviceId)}`);
      $('inputTariff').value = settings.tariff_per_kwh;
      $('inputPowerLimit').value = settings.power_limit_w;
      $('inputVoltageMin').value = settings.voltage_min_v;
      $('inputVoltageMax').value = settings.voltage_max_v;
      setModal(true);
    } catch (error) {toast(error.message, true);}
  }
  async function saveSettings(event) {
    event.preventDefault();
    const payload = {
      tariff_per_kwh: Number($('inputTariff').value),
      power_limit_w: Number($('inputPowerLimit').value),
      voltage_min_v: Number($('inputVoltageMin').value),
      voltage_max_v: Number($('inputVoltageMax').value),
    };
    try {
      await api(`/api/settings?device_id=${encodeURIComponent(state.deviceId)}`, {method:'PUT', body:JSON.stringify(payload)});
      setModal(false);
      toast('Pengaturan berhasil disimpan di PostgreSQL.');
      await loadDashboard({silent:true});
    } catch (error) {toast(error.message, true);}
  }
  function toggleSidebar(open) {
    $('sidebar').classList.toggle('is-open', open);
    $('sidebarOverlay').classList.toggle('is-open', open);
  }
  function exportCSV() {
    window.location.href = `/api/export.csv?device_id=${encodeURIComponent(state.deviceId)}&period=${state.period}`;
  }
  async function tickDemo() {
    const btn = $('simulateButton');
    if (!btn) return;
    btn.disabled = true;
    try {
      await api('/api/demo/tick', {method:'POST'});
      toast('Pembacaan dummy baru masuk ke PostgreSQL.');
      await loadDashboard({silent:true});
    } catch (error) {toast(error.message, true);}
    finally {btn.disabled = false;}
  }
  async function resetDemo() {
    if (!window.confirm('Buat ulang semua pembacaan dummy dan peringatan demo untuk perangkat ini? Data IoT asli tidak dihapus.')) return;
    try {
      const result = await api('/api/demo/reset', {method:'POST'});
      toast(`${formatter.format(result.count)} pembacaan demo berhasil dibuat ulang.`);
      setModal(false);
      await loadDashboard({silent:true});
    } catch (error) {toast(error.message, true);}
  }
  function init() {
    setText('todayDate', new Date().toLocaleDateString('id-ID', {day:'2-digit',month:'long',year:'numeric'}));
    document.querySelectorAll('.range-btn').forEach(btn => btn.addEventListener('click', () => {
      if (state.period === btn.dataset.period) return;
      state.period = btn.dataset.period;
      document.querySelectorAll('.range-btn').forEach(b => b.classList.toggle('active', b === btn));
      loadDashboard({silent:true});
    }));
    $('refreshButton').addEventListener('click', () => loadDashboard());
    $('retryButton').addEventListener('click', () => loadDashboard());
    $('scrollToAlerts').addEventListener('click', () => $('alerts').scrollIntoView({behavior:'smooth'}));
    $('openSettings').addEventListener('click', showSettings);
    $('closeSettings').addEventListener('click', () => setModal(false));
    $('cancelSettings').addEventListener('click', () => setModal(false));
    $('settingsModal').addEventListener('click', e => {if (e.target === $('settingsModal')) setModal(false);});
    document.addEventListener('keydown', e => {if (e.key === 'Escape') setModal(false);});
    $('settingsForm').addEventListener('submit', saveSettings);
    $('exportCsv').addEventListener('click', exportCSV);
    $('alertsList').addEventListener('click', async e => {
      const button = e.target.closest('[data-ack-id]');
      if (!button) return;
      button.disabled = true;
      try {await api(`/api/alerts/${encodeURIComponent(button.dataset.ackId)}/ack`, {method:'POST'});toast('Peringatan sudah ditandai dibaca.');await loadDashboard({silent:true});}
      catch (error) {toast(error.message, true);button.disabled = false;}
    });
    if ($('simulateButton')) $('simulateButton').addEventListener('click', tickDemo);
    if ($('resetDemoButton')) $('resetDemoButton').addEventListener('click', resetDemo);
    $('menuToggle').addEventListener('click', () => toggleSidebar(true));
    $('sidebarOverlay').addEventListener('click', () => toggleSidebar(false));
    document.querySelectorAll('.sidebar-link[href^="#"]').forEach(link => link.addEventListener('click', () => {
      document.querySelectorAll('.sidebar-link').forEach(b => b.classList.remove('active'));
      link.classList.add('active'); toggleSidebar(false);
    }));
    let resizeTimer;
    window.addEventListener('resize', () => {clearTimeout(resizeTimer);resizeTimer = setTimeout(renderCharts, 160);});
    loadDashboard();
    // Auto-refresh is read-only; simulator inserts a new point only on user action.
    setInterval(() => {if (!document.hidden && $('settingsModal').hidden) loadDashboard({silent:true});}, 20000);
  }
  document.addEventListener('DOMContentLoaded', init);
})();
