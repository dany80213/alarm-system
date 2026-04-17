'use strict';

// ─── Icone SVG per tipo dispositivo ─────────────────────────────────────────

const ICONE = {
  door: `<svg viewBox="0 0 24 24" fill="none" stroke="#4da3ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="2" width="14" height="20" rx="1"/>
    <circle cx="14" cy="12" r="1.5" fill="#4da3ff"/>
    <line x1="17" y1="2" x2="21" y2="5"/>
    <line x1="17" y1="22" x2="21" y2="19"/>
    <line x1="21" y1="5" x2="21" y2="19"/>
  </svg>`,

  gate: `<svg viewBox="0 0 24 24" fill="none" stroke="#4da3ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="2" y1="2" x2="2" y2="22"/>
    <line x1="22" y1="2" x2="22" y2="22"/>
    <rect x="5" y="6" width="5" height="12" rx="1"/>
    <rect x="14" y="6" width="5" height="12" rx="1"/>
    <line x1="10" y1="12" x2="14" y2="12"/>
  </svg>`,

  window: `<svg viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="1"/>
    <line x1="12" y1="3" x2="12" y2="21"/>
    <line x1="3" y1="12" x2="21" y2="12"/>
  </svg>`,

  motion: `<svg viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M6.3 17.7a8 8 0 0 1 0-11.4"/>
    <path d="M17.7 6.3a8 8 0 0 1 0 11.4"/>
    <path d="M3.5 20.5a13 13 0 0 1 0-17"/>
    <path d="M20.5 3.5a13 13 0 0 1 0 17"/>
  </svg>`,

  controller: `<svg viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="7" width="20" height="14" rx="2"/>
    <circle cx="8" cy="14" r="2"/>
    <line x1="14" y1="11" x2="14" y2="17"/>
    <line x1="11" y1="14" x2="17" y2="14"/>
    <path d="M6 7V5a6 6 0 0 1 12 0v2"/>
  </svg>`,

  bridge: `<svg viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <ellipse cx="12" cy="12" rx="3" ry="3"/>
    <path d="M12 2C6.48 2 2 6.48 2 12"/>
    <path d="M12 2c5.52 0 10 4.48 10 10"/>
    <path d="M12 6c-3.31 0-6 2.69-6 6"/>
    <path d="M12 6c3.31 0 6 2.69 6 6"/>
    <line x1="12" y1="15" x2="12" y2="22"/>
  </svg>`,
};

// ─── Auth state ───────────────────────────────────────────────────────────────

let authToken      = localStorage.getItem('alarm_token') || null;
let userLevel      = 0;
let currentUsername = '';

// ─── App state ────────────────────────────────────────────────────────────────

let statoCorrente  = { mode: 'DISARMED', alarm: false, triggered_device: null };
let dispositiviCache = {};
let bridgesCache   = {};
let isListening    = true;
let activeTab      = 'dashboard';
let lastEventPerDevice = {};   // device_name -> { time, device, zone }

// ─── Modal / placement state ─────────────────────────────────────────────────

let modalActiveCode       = null;
let pendingDeviceInfo     = null;
let pendingBridgeInfo     = null;
let repositioningCode     = null;
let repositioningBridgeTopic = null;
let editingDeviceCode     = null;
let editingBridgeTopic    = null;
let editingUsername       = null;
let unknownBannerCode     = null;
let unknownBridgeBannerTopic = null;

// ─── API wrapper ─────────────────────────────────────────────────────────────

async function api(method, path, body = null) {
  const opts = { method, cache: 'no-store', headers: { 'Authorization': `Bearer ${authToken}` } };
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401) {
    showLogin();
    throw new Error('401');
  }
  return res;
}

// ─── Fullscreen ───────────────────────────────────────────────────────────────

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

document.addEventListener('fullscreenchange', () => {
  const isFs = !!document.fullscreenElement;
  document.getElementById('fs-icon-enter').classList.toggle('hidden', isFs);
  document.getElementById('fs-icon-exit').classList.toggle('hidden', !isFs);
});

// ─── Auth ─────────────────────────────────────────────────────────────────────

function showLogin() {
  authToken = null;
  localStorage.removeItem('alarm_token');
  document.getElementById('login-overlay').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
}

function showApp() {
  document.getElementById('login-overlay').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  applyLevelRestrictions();
}

async function doLogin(e) {
  e.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password  = document.getElementById('login-password').value;
  const errEl     = document.getElementById('login-error');
  errEl.classList.add('hidden');
  try {
    const res = await fetch('/auth/login', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) { errEl.classList.remove('hidden'); return; }
    const data = await res.json();
    authToken       = data.token;
    userLevel       = data.level;
    currentUsername = data.username;
    localStorage.setItem('alarm_token', authToken);
    showApp();
    startPolling();
  } catch (_) {
    errEl.classList.remove('hidden');
  }
}

async function doLogout() {
  try { await api('POST', '/auth/logout'); } catch (_) {}
  showLogin();
}

function applyLevelRestrictions() {
  document.getElementById('user-info').textContent =
    `${currentUsername} (L${userLevel})`;

  // Arming controls: level 50+
  const ctrl = document.getElementById('controls-card');
  if (userLevel < 50) ctrl.classList.add('hidden');
  else                ctrl.classList.remove('hidden');

  // Listening button: visible to all, clickable only for level 100
  const btnL = document.getElementById('btn-listening');
  btnL.disabled = (userLevel < 100);
  if (userLevel < 100) btnL.title = 'Solo gli amministratori possono modificare questa impostazione';
  else                 btnL.title = '';

  // Users tab: level 100 only
  document.querySelectorAll('.tab-admin-only').forEach(el => {
    if (userLevel >= 100) el.classList.remove('hidden');
    else                  el.classList.add('hidden');
  });
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.remove('hidden');
  document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
  if (tab === 'config')    loadConfigDevices();
  if (tab === 'users')     loadUsers();
  if (tab === 'dashboard') refreshMap();
}

async function refreshMap() {
  try {
    const [dispositivi, bridges] = await Promise.all([
      api('GET', '/devices').then(r => r.json()),
      api('GET', '/bridges').then(r => r.json()),
    ]);
    dispositiviCache = dispositivi;
    bridgesCache     = bridges;
    renderizzaMappa(dispositivi, bridges);
  } catch (_) {}
}

// ─── Listening mode ───────────────────────────────────────────────────────────

async function fetchListening() {
  try {
    const data = await api('GET', '/listening').then(r => r.json());
    isListening = data.active;
    updateListeningButton();
  } catch (_) {}
}

async function toggleListening() {
  if (userLevel < 100) return;
  try {
    const data = await api('POST', '/listening/toggle').then(r => r.json());
    isListening = data.active;
    updateListeningButton();
    if (isListening) hideBanner();
  } catch (_) {}
}

function updateListeningButton() {
  const btn = document.getElementById('btn-listening');
  if (isListening) {
    btn.innerHTML = '&#9679; In ascolto';
    btn.classList.remove('inactive');
  } else {
    btn.innerHTML = '&#9675; Non in ascolto';
    btn.classList.add('inactive');
  }
}

// ─── Unknown device banner ────────────────────────────────────────────────────

function showUnknownBanner(device) {
  if (unknownBannerCode === device.code) return;
  unknownBannerCode = device.code;
  document.getElementById('unknown-banner-code').textContent = device.code;
  document.getElementById('unknown-banner').classList.remove('hidden');
}

function hideBanner() {
  unknownBannerCode = null;
  document.getElementById('unknown-banner').classList.add('hidden');
}

async function dismissUnknownBanner() {
  const code = unknownBannerCode;
  hideBanner();
  if (code) {
    try { await api('POST', '/unknown/dismiss', { code }); } catch (_) {}
  }
}

// ─── Unknown bridge banner ────────────────────────────────────────────────────

function showBridgeBanner(bridge) {
  if (unknownBridgeBannerTopic === bridge.topic) return;
  unknownBridgeBannerTopic = bridge.topic;
  document.getElementById('bridge-banner-topic').textContent = bridge.topic;
  document.getElementById('bridge-banner').classList.remove('hidden');
}

function hideBridgeBanner() {
  unknownBridgeBannerTopic = null;
  document.getElementById('bridge-banner').classList.add('hidden');
}

async function dismissBridgeBanner() {
  const topic = unknownBridgeBannerTopic;
  hideBridgeBanner();
  if (topic) {
    try { await api('POST', '/unknown-bridges/dismiss', { topic }); } catch (_) {}
  }
}

function addBridgeFromBanner() {
  const topic = unknownBridgeBannerTopic;
  hideBridgeBanner();
  if (topic) {
    try { api('POST', '/unknown-bridges/dismiss', { topic }); } catch (_) {}
    openBridgeModal(topic);
  }
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

const tooltip = document.getElementById('tooltip');

function mostraTooltip(e, testo) {
  tooltip.textContent = testo;
  tooltip.classList.remove('hidden');
  posizionaTooltip(e);
}
function nascondiTooltip() { tooltip.classList.add('hidden'); }
function posizionaTooltip(e) {
  tooltip.style.left = (e.clientX + 12) + 'px';
  tooltip.style.top  = (e.clientY - 28) + 'px';
}
document.addEventListener('mousemove', (e) => {
  if (!tooltip.classList.contains('hidden')) posizionaTooltip(e);
});

// ─── Mappa ───────────────────────────────────────────────────────────────────

function renderizzaMappa(dispositivi, bridges) {
  const mappa = document.getElementById('mappa');
  mappa.querySelectorAll('.device-pin').forEach(el => el.remove());
  dispositiviCache = dispositivi;
  bridgesCache     = bridges || {};

  // Sensori e controller
  Object.entries(dispositivi).forEach(([codice, dev]) => {
    if (dev.type === 'controller') return;
    _aggiungiPin(mappa, codice, dev, 'device');
  });

  // Bridge RF
  Object.entries(bridgesCache).forEach(([topic, bridge]) => {
    _aggiungiPin(mappa, topic, {
      name: bridge.client,
      type: 'bridge',
      zone: null,
      position: bridge.position || { x: 5, y: 5 },
      enabled: bridge.enabled !== false,
      _bridgeTopic: topic,
    }, 'bridge');
  });
}

function _aggiungiPin(mappa, id, dev, kind) {
  const pos     = dev.position || { x: 100, y: 100 };
  const enabled = dev.enabled !== false;
  const pin     = document.createElement('div');
  pin.className = 'device-pin' + (enabled ? '' : ' disabled');
  pin.id        = `pin-${CSS.escape(id)}`;
  pin.style.left = pos.x + '%';
  pin.style.top  = pos.y + '%';

  const icona = document.createElement('div');
  icona.className = `device-icon ${dev.type}`;
  icona.innerHTML = ICONE[dev.type] || ICONE.motion;

  const label = document.createElement('div');
  label.className = 'device-label';
  label.textContent = dev.name.replace(/_/g, ' ');

  pin.appendChild(icona);
  pin.appendChild(label);

  pin.addEventListener('mouseenter', (e) => {
    const statoTxt = enabled ? 'attivo' : 'disattivato';
    if (kind === 'bridge') {
      mostraTooltip(e, `${dev.name} · bridge · ${dev._bridgeTopic} · ${statoTxt}`);
    } else {
      mostraTooltip(e, `${dev.name} · ${dev.type} · ${dev.zone} · ${statoTxt}`);
    }
  });
  pin.addEventListener('mouseleave', nascondiTooltip);
  pin.addEventListener('click', (e) => {
    nascondiTooltip();
    if (kind === 'bridge') showBridgePopup(id, e);
    else                   showDevicePopup(id, e);
  });

  mappa.appendChild(pin);
}

function aggiornaMappa(triggerDevice) {
  document.querySelectorAll('.device-pin.triggered').forEach(el => {
    el.classList.remove('triggered');
  });
  if (!triggerDevice) return;
  Object.entries(dispositiviCache).forEach(([codice, dev]) => {
    if (dev.name === triggerDevice) {
      const pin = document.getElementById(`pin-${CSS.escape(codice)}`);
      if (pin) pin.classList.add('triggered');
    }
  });
}

// ─── Status panel ────────────────────────────────────────────────────────────

function aggiornaBadgeModalita(mode) {
  const badge = document.getElementById('badge-mode');
  badge.textContent = mode;
  badge.className = `badge ${mode}`;
}

function aggiornaBadgeAllarme(alarm) {
  const badge = document.getElementById('badge-alarm');
  badge.classList.toggle('hidden', !alarm);
}

function aggiornaStato(stato) {
  statoCorrente = stato;
  aggiornaBadgeModalita(stato.mode);
  aggiornaBadgeAllarme(stato.alarm);
  aggiornaMappa(stato.triggered_device);
}

// ─── Log eventi ──────────────────────────────────────────────────────────────

function formattaOra(timestamp) {
  const d = new Date(timestamp * 1000);
  return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function aggiornaEventi(eventi) {
  lastEventPerDevice = {};
  eventi.forEach(ev => {
    if (!lastEventPerDevice[ev.device] || ev.time > lastEventPerDevice[ev.device].time) {
      lastEventPerDevice[ev.device] = ev;
    }
  });

  const tbody   = document.getElementById('event-tbody');
  const counter = document.getElementById('event-count');
  counter.textContent = eventi.length;

  if (eventi.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty">Nessun evento</td></tr>';
    return;
  }

  tbody.innerHTML = eventi.map(ev => {
    const triggered = statoCorrente.triggered_device === ev.device ? 'triggered' : '';
    return `<tr class="${triggered}">
      <td>${formattaOra(ev.time)}</td>
      <td>${ev.device.replace(/_/g, ' ')}</td>
      <td>${ev.zone}</td>
    </tr>`;
  }).join('');
}

// ─── Comandi ─────────────────────────────────────────────────────────────────

async function inviaComando(action) {
  if (userLevel < 50) return;
  try {
    const data = await api('POST', '/command', { action }).then(r => r.json());
    if (data.state) aggiornaStato(data.state);
  } catch (_) {}
}

// ─── Polling ─────────────────────────────────────────────────────────────────

async function poll() {
  try {
    const [statoRes, eventiRes] = await Promise.all([
      api('GET', '/state').then(r => r.json()),
      api('GET', '/events?limit=30').then(r => r.json()),
    ]);
    aggiornaStato(statoRes);
    aggiornaEventi(eventiRes);
  } catch (_) {}
}

// ─── Unknown device onboarding ───────────────────────────────────────────────

async function pollUnknown() {
  if (modalActiveCode || pendingDeviceInfo || repositioningCode) return;
  try {
    const list = await api('GET', '/unknown').then(r => r.json());
    if (list.length === 0) { hideBanner(); return; }
    const device = list[0];
    if (isListening && userLevel >= 100) {
      hideBanner();
      showUnknownModal(device);
    } else {
      showUnknownBanner(device);
    }
  } catch (_) {}
}

// ─── Unknown bridge polling ───────────────────────────────────────────────────

async function pollUnknownBridges() {
  if (pendingBridgeInfo || repositioningBridgeTopic) return;
  try {
    const list = await api('GET', '/unknown-bridges').then(r => r.json());
    if (list.length === 0) { hideBridgeBanner(); return; }
    showBridgeBanner(list[0]);
  } catch (_) {}
}

function showUnknownModal(device) {
  modalActiveCode = device.code;
  document.getElementById('modal-device-code').textContent = device.code;
  document.getElementById('modal-name').value  = '';
  document.getElementById('modal-type').value  = 'door';
  document.getElementById('modal-zone').value  = 'perimeter';
  document.getElementById('modal-overlay').classList.remove('hidden');
  document.getElementById('modal-name').focus();
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  modalActiveCode = null;
}

function ignoreUnknownDevice() {
  const code = modalActiveCode;
  closeModal();
  api('POST', '/unknown/dismiss', { code }).catch(() => {});
}

function proceedToPlacement() {
  const name = document.getElementById('modal-name').value.trim();
  const type = document.getElementById('modal-type').value;
  const zone = document.getElementById('modal-zone').value;
  const nameEl = document.getElementById('modal-name');

  if (!name) { nameEl.focus(); nameEl.classList.add('input-error'); return; }
  nameEl.classList.remove('input-error');

  pendingDeviceInfo = { code: modalActiveCode, name, type, zone };
  closeModal();

  if (type === 'controller') {
    submitNewDevice(0, 0);
    return;
  }

  document.getElementById('placement-hint').classList.remove('hidden');
  initPlacementMode(false);
}

// ─── Bridge modal ─────────────────────────────────────────────────────────────

function openBridgeModal(preFillTopic) {
  document.getElementById('bridge-modal-topic').value  = preFillTopic || '';
  document.getElementById('bridge-modal-client').value = '';
  document.getElementById('bridge-modal').classList.remove('hidden');
  document.getElementById(preFillTopic ? 'bridge-modal-client' : 'bridge-modal-topic').focus();
}

function closeBridgeModal() {
  document.getElementById('bridge-modal').classList.add('hidden');
  pendingBridgeInfo = null;
}

function proceedToBridgePlacement() {
  const topic  = document.getElementById('bridge-modal-topic').value.trim();
  const client = document.getElementById('bridge-modal-client').value.trim();
  const topicEl  = document.getElementById('bridge-modal-topic');
  const clientEl = document.getElementById('bridge-modal-client');

  if (!topic)  { topicEl.focus();  topicEl.classList.add('input-error');  return; }
  if (!client) { clientEl.focus(); clientEl.classList.add('input-error'); return; }
  topicEl.classList.remove('input-error');
  clientEl.classList.remove('input-error');

  pendingBridgeInfo = { topic, client };
  document.getElementById('bridge-modal').classList.add('hidden');

  document.getElementById('placement-hint').classList.remove('hidden');
  initBridgePlacementMode();
}

// ─── Bridge edit modal ────────────────────────────────────────────────────────

function openEditBridgeModal(topic) {
  const bridge = bridgesCache[topic];
  if (!bridge) return;
  editingBridgeTopic = topic;
  document.getElementById('edit-bridge-topic-label').textContent = topic;
  document.getElementById('edit-bridge-client').value = bridge.client || '';
  document.getElementById('edit-bridge-modal').classList.remove('hidden');
}

function closeEditBridgeModal() {
  editingBridgeTopic = null;
  document.getElementById('edit-bridge-modal').classList.add('hidden');
}

async function saveBridgeEdit() {
  const topic  = editingBridgeTopic;
  const client = document.getElementById('edit-bridge-client').value.trim();
  const clientEl = document.getElementById('edit-bridge-client');

  if (!client) { clientEl.classList.add('input-error'); clientEl.focus(); return; }
  clientEl.classList.remove('input-error');
  closeEditBridgeModal();

  try {
    await api('PUT', `/bridges/${encodeURIComponent(topic)}`, { client });
    const bridges = await api('GET', '/bridges').then(r => r.json());
    bridgesCache = bridges;
    renderizzaMappa(dispositiviCache, bridges);
    if (activeTab === 'config') loadConfigDevices();
  } catch (_) { alert('Errore durante il salvataggio'); }
}

// ─── Bridge placement mode ────────────────────────────────────────────────────

function initBridgePlacementMode() {
  const mappa = document.getElementById('mappa');
  mappa.classList.add('placement-mode');

  const ghost = document.createElement('div');
  ghost.id = 'placement-ghost';
  ghost.className = 'placement-ghost hidden';
  ghost.innerHTML = `<div class="device-icon bridge">${ICONE.bridge}</div>`;
  mappa.appendChild(ghost);

  function onMouseMove(e) {
    const rect = mappa.getBoundingClientRect();
    ghost.style.left = ((e.clientX - rect.left) / rect.width  * 100) + '%';
    ghost.style.top  = ((e.clientY - rect.top)  / rect.height * 100) + '%';
    ghost.classList.remove('hidden');
  }

  function onMapClick(e) {
    if (e.target.closest('.btn-cancel-placement')) return;
    const rect = mappa.getBoundingClientRect();
    const x = parseFloat(((e.clientX - rect.left) / rect.width  * 100).toFixed(1));
    const y = parseFloat(((e.clientY - rect.top)  / rect.height * 100).toFixed(1));
    exitBridgePlacementMode();
    if (repositioningBridgeTopic) submitBridgeReposition(x, y);
    else                          submitNewBridge(x, y);
  }

  mappa.addEventListener('mousemove', onMouseMove);
  mappa.addEventListener('click', onMapClick);

  mappa._bridgePlacementCleanup = () => {
    mappa.removeEventListener('mousemove', onMouseMove);
    mappa.removeEventListener('click', onMapClick);
    ghost.remove();
    mappa.classList.remove('placement-mode');
    delete mappa._bridgePlacementCleanup;
  };
}

function exitBridgePlacementMode() {
  const mappa = document.getElementById('mappa');
  if (mappa._bridgePlacementCleanup) mappa._bridgePlacementCleanup();
  document.getElementById('placement-hint').classList.add('hidden');
}

function cancelBridgePlacement() {
  pendingBridgeInfo        = null;
  repositioningBridgeTopic = null;
  exitBridgePlacementMode();
}

async function submitNewBridge(x, y) {
  const body = { ...pendingBridgeInfo, position: { x, y } };
  pendingBridgeInfo = null;

  try {
    const res = await api('POST', '/bridges', body);
    if (!res.ok) { const err = await res.json(); alert('Errore: ' + (err.detail || '')); return; }
    const bridges = await api('GET', '/bridges').then(r => r.json());
    bridgesCache = bridges;
    renderizzaMappa(dispositiviCache, bridges);
    if (activeTab === 'config') loadConfigDevices();
  } catch (_) {}
}

async function submitBridgeReposition(x, y) {
  const topic = repositioningBridgeTopic;
  repositioningBridgeTopic = null;
  pendingBridgeInfo        = null;
  try {
    await api('PUT', `/bridges/${encodeURIComponent(topic)}`, { position: { x, y } });
    const bridges = await api('GET', '/bridges').then(r => r.json());
    bridgesCache = bridges;
    renderizzaMappa(dispositiviCache, bridges);
    if (activeTab === 'config') loadConfigDevices();
  } catch (_) {}
}

function startBridgeReposition(topic) {
  const bridge = bridgesCache[topic];
  if (!bridge) return;
  repositioningBridgeTopic = topic;
  pendingBridgeInfo = { topic, client: bridge.client };
  switchTab('dashboard');
  document.getElementById('placement-hint').classList.remove('hidden');
  initBridgePlacementMode();
}

async function toggleBridgeEnabled(topic, enabled) {
  try {
    const res = await api('PUT', `/bridges/${encodeURIComponent(topic)}`, { enabled });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert('Errore: ' + (err.detail || res.status));
      loadConfigDevices();
      return;
    }
    const bridges = await api('GET', '/bridges').then(r => r.json());
    bridgesCache = bridges;
    renderizzaMappa(dispositiviCache, bridges);
  } catch (_) {
    alert('Errore di rete durante l\'aggiornamento');
    loadConfigDevices();
  }
}

async function deleteBridge(topic) {
  const bridge = bridgesCache[topic];
  const label  = bridge ? bridge.client : topic;
  if (!confirm(`Eliminare il bridge "${label}"?\nTopic: ${topic}`)) return;
  try {
    const res = await api('DELETE', `/bridges/${encodeURIComponent(topic)}`);
    if (!res.ok) { const e = await res.json(); alert('Errore: ' + e.detail); return; }
    const bridges = await api('GET', '/bridges').then(r => r.json());
    bridgesCache = bridges;
    renderizzaMappa(dispositiviCache, bridges);
    loadConfigDevices();
  } catch (_) {}
}

// ─── Placement mode (device) ──────────────────────────────────────────────────

function initPlacementMode(isRepositioning) {
  const mappa = document.getElementById('mappa');
  mappa.classList.add('placement-mode');

  const ghost = document.createElement('div');
  ghost.id = 'placement-ghost';
  ghost.className = 'placement-ghost hidden';
  const type = pendingDeviceInfo ? pendingDeviceInfo.type : 'motion';
  ghost.innerHTML = `<div class="device-icon ${type}">${ICONE[type] || ICONE.motion}</div>`;
  mappa.appendChild(ghost);

  function onMouseMove(e) {
    const rect = mappa.getBoundingClientRect();
    ghost.style.left = ((e.clientX - rect.left) / rect.width  * 100) + '%';
    ghost.style.top  = ((e.clientY - rect.top)  / rect.height * 100) + '%';
    ghost.classList.remove('hidden');
  }

  function onMapClick(e) {
    if (e.target.closest('.btn-cancel-placement')) return;
    const rect = mappa.getBoundingClientRect();
    const x = parseFloat(((e.clientX - rect.left) / rect.width  * 100).toFixed(1));
    const y = parseFloat(((e.clientY - rect.top)  / rect.height * 100).toFixed(1));
    exitPlacementMode();
    if (isRepositioning) submitReposition(x, y);
    else                  submitNewDevice(x, y);
  }

  mappa.addEventListener('mousemove', onMouseMove);
  mappa.addEventListener('click', onMapClick);

  mappa._placementCleanup = () => {
    mappa.removeEventListener('mousemove', onMouseMove);
    mappa.removeEventListener('click', onMapClick);
    ghost.remove();
    mappa.classList.remove('placement-mode');
    delete mappa._placementCleanup;
  };
}

function exitPlacementMode() {
  const mappa = document.getElementById('mappa');
  if (mappa._placementCleanup) mappa._placementCleanup();
  document.getElementById('placement-hint').classList.add('hidden');
}

function cancelPlacement() {
  const code            = pendingDeviceInfo ? pendingDeviceInfo.code : null;
  const wasRepositioning = repositioningCode !== null;
  pendingDeviceInfo  = null;
  repositioningCode  = null;
  exitPlacementMode();
  if (!wasRepositioning && code) {
    api('POST', '/unknown/dismiss', { code }).catch(() => {});
  }
}

async function submitNewDevice(x, y) {
  const body = { ...pendingDeviceInfo, position: { x, y } };
  pendingDeviceInfo = null;

  try {
    const res = await api('POST', '/devices/add', body);
    if (!res.ok) { const err = await res.json(); alert('Errore: ' + (err.detail || '')); return; }
    const data = await res.json();
    const dispositivi = await api('GET', '/devices').then(r => r.json());
    dispositiviCache = dispositivi;
    renderizzaMappa(dispositivi, bridgesCache);
    const newPin = document.getElementById(`pin-${CSS.escape(data.code)}`);
    if (newPin) {
      newPin.classList.add('device-new');
      setTimeout(() => newPin.classList.remove('device-new'), 4000);
    }
  } catch (_) {}
}

async function submitReposition(x, y) {
  const code = repositioningCode;
  repositioningCode = null;
  pendingDeviceInfo  = null;
  try {
    await api('PUT', `/devices/${code}`, { position: { x, y } });
    const dispositivi = await api('GET', '/devices').then(r => r.json());
    dispositiviCache = dispositivi;
    renderizzaMappa(dispositivi, bridgesCache);
    if (activeTab === 'config') loadConfigDevices();
  } catch (_) {}
}

// ─── Device popup (click su mappa) ───────────────────────────────────────────

function showDevicePopup(code, clickEvent) {
  const dev = dispositiviCache[code];
  if (!dev) return;

  const enabled = dev.enabled !== false;
  const lastEv  = lastEventPerDevice[dev.name];
  let lastEvText;
  if (lastEv) {
    const d = new Date(lastEv.time * 1000);
    lastEvText = d.toLocaleDateString('it-IT') + ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } else {
    lastEvText = 'Nessun rilevamento';
  }

  document.getElementById('device-popup-name').textContent = dev.name.replace(/_/g, ' ');
  document.getElementById('device-popup-code').textContent = code;
  document.getElementById('device-popup-type').textContent = _typeLabel(dev.type);
  document.getElementById('device-popup-zone').textContent = _zoneLabel(dev.zone);
  const statusEl = document.getElementById('device-popup-status');
  statusEl.textContent = enabled ? 'Attivo' : 'Disattivato';
  statusEl.className   = 'device-popup-val ' + (enabled ? 'popup-active' : 'popup-inactive');
  document.getElementById('device-popup-last').textContent = lastEvText;

  const popup = document.getElementById('device-popup');
  popup.classList.remove('hidden');

  const pw = popup.offsetWidth  || 230;
  const ph = popup.offsetHeight || 150;
  let left = clickEvent.clientX + 14;
  let top  = clickEvent.clientY - 20;
  if (left + pw > window.innerWidth  - 10) left = clickEvent.clientX - pw - 14;
  if (top  + ph > window.innerHeight - 10) top  = window.innerHeight - ph - 10;
  if (top < 10) top = 10;
  popup.style.left = left + 'px';
  popup.style.top  = top  + 'px';
}

function closeDevicePopup() {
  document.getElementById('device-popup').classList.add('hidden');
}

// ─── Bridge popup (click su mappa) ───────────────────────────────────────────

function showBridgePopup(topic, clickEvent) {
  const bridge = bridgesCache[topic];
  if (!bridge) return;

  const enabled = bridge.enabled !== false;

  document.getElementById('device-popup-name').textContent = bridge.client;
  document.getElementById('device-popup-code').textContent = topic;
  document.getElementById('device-popup-type').textContent = 'Bridge RF';
  document.getElementById('device-popup-zone').textContent = '—';
  const statusEl = document.getElementById('device-popup-status');
  statusEl.textContent = enabled ? 'Attivo' : 'Disattivato';
  statusEl.className   = 'device-popup-val ' + (enabled ? 'popup-active' : 'popup-inactive');
  document.getElementById('device-popup-last').textContent = '—';

  const popup = document.getElementById('device-popup');
  popup.classList.remove('hidden');

  const pw = popup.offsetWidth  || 230;
  const ph = popup.offsetHeight || 150;
  let left = clickEvent.clientX + 14;
  let top  = clickEvent.clientY - 20;
  if (left + pw > window.innerWidth  - 10) left = clickEvent.clientX - pw - 14;
  if (top  + ph > window.innerHeight - 10) top  = window.innerHeight - ph - 10;
  if (top < 10) top = 10;
  popup.style.left = left + 'px';
  popup.style.top  = top  + 'px';
}

// ─── Config tab ───────────────────────────────────────────────────────────────

function _typeLabel(t) {
  return { door: 'Porta', window: 'Finestra', motion: 'PIR', gate: 'Cancello', controller: 'Controller', bridge: 'Bridge RF' }[t] || t;
}
function _zoneLabel(z) {
  return { perimeter: 'Perimetrale', internal: 'Interna' }[z] || z;
}

async function loadConfigDevices() {
  try {
    const [dispositivi, bridges] = await Promise.all([
      api('GET', '/devices').then(r => r.json()),
      api('GET', '/bridges').then(r => r.json()),
    ]);
    dispositiviCache = dispositivi;
    bridgesCache     = bridges;
    renderizzaMappa(dispositivi, bridges);

    // ── Tabella sensori ─────────────────────────────────────────────────────
    const tbody   = document.getElementById('config-device-tbody');
    const entries = Object.entries(dispositivi);
    const canEdit = userLevel >= 100;

    if (entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Nessun dispositivo</td></tr>';
    } else {
      tbody.innerHTML = entries.map(([code, dev]) => {
        const enabled = dev.enabled !== false;
        return `
        <tr>
          <td><code class="code-badge">${code}</code></td>
          <td>${dev.name.replace(/_/g, ' ')}</td>
          <td>${_typeLabel(dev.type)}</td>
          <td>${_zoneLabel(dev.zone)}</td>
          <td>
            ${canEdit
              ? `<label class="toggle-switch" title="${enabled ? 'Clicca per disattivare' : 'Clicca per attivare'}">
                  <input type="checkbox" ${enabled ? 'checked' : ''} onchange="toggleDeviceEnabled('${code}', this.checked)">
                  <span class="toggle-slider"></span>
                 </label>`
              : `<span class="${enabled ? 'status-active' : 'status-inactive'}">${enabled ? 'Attivo' : 'Disatt.'}</span>`}
          </td>
          <td class="action-cell">
            ${canEdit ? `
              <button class="btn-action btn-edit"       onclick="openEditDevice('${code}')">Modifica</button>
              ${dev.type !== 'controller' ? `<button class="btn-action btn-reposition" onclick="startReposition('${code}')">Sposta</button>` : ''}
              <button class="btn-action btn-delete"     onclick="deleteDevice('${code}')">Elimina</button>
            ` : '<span class="muted">—</span>'}
          </td>
        </tr>
      `}).join('');
    }

    // ── Tabella bridge ──────────────────────────────────────────────────────
    const bridgeTbody   = document.getElementById('config-bridge-tbody');
    const bridgeEntries = Object.entries(bridges);

    if (bridgeEntries.length === 0) {
      bridgeTbody.innerHTML = '<tr><td colspan="4" class="empty">Nessun bridge registrato</td></tr>';
    } else {
      bridgeTbody.innerHTML = bridgeEntries.map(([topic, bridge]) => {
        const enabled = bridge.enabled !== false;
        const safeTopic = topic.replace(/'/g, "\\'");
        return `
        <tr>
          <td><code class="code-badge">${topic}</code></td>
          <td>${bridge.client || '—'}</td>
          <td>
            ${canEdit
              ? `<label class="toggle-switch">
                  <input type="checkbox" ${enabled ? 'checked' : ''} onchange="toggleBridgeEnabled('${safeTopic}', this.checked)">
                  <span class="toggle-slider"></span>
                 </label>`
              : `<span class="${enabled ? 'status-active' : 'status-inactive'}">${enabled ? 'Attivo' : 'Disatt.'}</span>`}
          </td>
          <td class="action-cell">
            ${canEdit ? `
              <button class="btn-action btn-edit"        onclick="openEditBridgeModal('${safeTopic}')">Modifica</button>
              <button class="btn-action btn-reposition"  onclick="startBridgeReposition('${safeTopic}')">Sposta</button>
              <button class="btn-action btn-delete"      onclick="deleteBridge('${safeTopic}')">Elimina</button>
            ` : '<span class="muted">—</span>'}
          </td>
        </tr>
      `}).join('');
    }

    // Bottone "Aggiungi Bridge" visibile solo a L100
    const addBtnWrap = document.getElementById('add-bridge-btn-wrap');
    if (addBtnWrap) addBtnWrap.classList.toggle('hidden', !canEdit);

  } catch (_) {}
}

async function toggleDeviceEnabled(code, enabled) {
  try {
    const res = await api('PUT', `/devices/${code}`, { enabled });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert('Errore: ' + (err.detail || res.status));
      loadConfigDevices();
      return;
    }
    const dispositivi = await api('GET', '/devices').then(r => r.json());
    dispositiviCache  = dispositivi;
    renderizzaMappa(dispositivi, bridgesCache);
  } catch (_) {
    alert('Errore di rete durante l\'aggiornamento');
    loadConfigDevices();
  }
}

function openEditDevice(code) {
  const dev = dispositiviCache[code];
  if (!dev) return;
  editingDeviceCode = code;
  document.getElementById('edit-device-code').textContent = code;
  document.getElementById('edit-device-name').value = dev.name.replace(/_/g, ' ');
  document.getElementById('edit-device-type').value = dev.type;
  document.getElementById('edit-device-zone').value = dev.zone;
  document.getElementById('edit-device-modal').classList.remove('hidden');
}

function closeEditDeviceModal() {
  editingDeviceCode = null;
  document.getElementById('edit-device-modal').classList.add('hidden');
}

async function saveDeviceEdit() {
  const code   = editingDeviceCode;
  const name   = document.getElementById('edit-device-name').value.trim();
  const type   = document.getElementById('edit-device-type').value;
  const zone   = document.getElementById('edit-device-zone').value;
  const nameEl = document.getElementById('edit-device-name');

  if (!name) { nameEl.classList.add('input-error'); nameEl.focus(); return; }
  nameEl.classList.remove('input-error');
  closeEditDeviceModal();

  try {
    await api('PUT', `/devices/${code}`, { name, type, zone });
    const dispositivi = await api('GET', '/devices').then(r => r.json());
    dispositiviCache  = dispositivi;
    renderizzaMappa(dispositivi, bridgesCache);
    loadConfigDevices();
  } catch (_) { alert('Errore durante il salvataggio'); }
}

async function deleteDevice(code) {
  const dev = dispositiviCache[code];
  const label = dev ? dev.name.replace(/_/g, ' ') : code;
  if (!confirm(`Eliminare il dispositivo "${label}" (${code})?`)) return;
  try {
    const res = await api('DELETE', `/devices/${code}`);
    if (!res.ok) { const e = await res.json(); alert('Errore: ' + e.detail); return; }
    const dispositivi = await api('GET', '/devices').then(r => r.json());
    dispositiviCache  = dispositivi;
    renderizzaMappa(dispositivi, bridgesCache);
    loadConfigDevices();
  } catch (_) {}
}

function startReposition(code) {
  const dev = dispositiviCache[code];
  if (!dev) return;
  repositioningCode = code;
  pendingDeviceInfo = { code, name: dev.name, type: dev.type, zone: dev.zone };
  switchTab('dashboard');
  document.getElementById('placement-hint').classList.remove('hidden');
  initPlacementMode(true);
}

// ─── Users tab ────────────────────────────────────────────────────────────────

function _levelDesc(l) {
  return {
    10:  'Solo visualizzazione',
    50:  'Visualizzazione + Arming',
    100: 'Accesso completo',
  }[l] || String(l);
}

async function loadUsers() {
  try {
    const users = await api('GET', '/users').then(r => r.json());
    const tbody = document.getElementById('users-tbody');

    if (!users.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">Nessun utente</td></tr>';
      return;
    }

    tbody.innerHTML = users.map(u => `
      <tr>
        <td>${u.username}${u.username === currentUsername ? ' <span class="badge-you">(tu)</span>' : ''}</td>
        <td><span class="level-badge level-${u.level}">${u.level}</span></td>
        <td class="muted">${_levelDesc(u.level)}</td>
        <td class="action-cell">
          <button class="btn-action btn-edit" onclick="openEditUser('${u.username}', ${u.level})">Modifica</button>
          ${u.username !== currentUsername
            ? `<button class="btn-action btn-delete" onclick="deleteUser('${u.username}')">Elimina</button>`
            : ''}
        </td>
      </tr>
    `).join('');
  } catch (_) {}
}

async function addUser() {
  const username = document.getElementById('new-user-username').value.trim();
  const password  = document.getElementById('new-user-password').value;
  const level     = parseInt(document.getElementById('new-user-level').value, 10);
  if (!username || !password) { alert('Username e password obbligatori'); return; }
  try {
    const res = await api('POST', '/users', { username, password, level });
    if (!res.ok) { const e = await res.json(); alert('Errore: ' + e.detail); return; }
    document.getElementById('new-user-username').value = '';
    document.getElementById('new-user-password').value = '';
    loadUsers();
  } catch (_) {}
}

function openEditUser(username, level) {
  editingUsername = username;
  document.getElementById('edit-user-name-label').textContent = username;
  document.getElementById('edit-user-password').value = '';
  document.getElementById('edit-user-level').value    = level;
  document.getElementById('edit-user-modal').classList.remove('hidden');
}

function closeEditUserModal() {
  editingUsername = null;
  document.getElementById('edit-user-modal').classList.add('hidden');
}

async function saveUserEdit() {
  const username = editingUsername;
  const pwd      = document.getElementById('edit-user-password').value;
  const level    = parseInt(document.getElementById('edit-user-level').value, 10);
  const body     = { level };
  if (pwd) body.password = pwd;
  closeEditUserModal();
  try {
    const res = await api('PUT', `/users/${username}`, body);
    if (!res.ok) { const e = await res.json(); alert('Errore: ' + e.detail); return; }
    loadUsers();
  } catch (_) {}
}

async function deleteUser(username) {
  if (!confirm(`Eliminare l'utente "${username}"?`)) return;
  try {
    const res = await api('DELETE', `/users/${username}`);
    if (!res.ok) { const e = await res.json(); alert('Errore: ' + e.detail); return; }
    loadUsers();
  } catch (_) {}
}

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (!document.getElementById('device-popup').classList.contains('hidden')) {
      closeDevicePopup();
    } else if (!document.getElementById('bridge-modal').classList.contains('hidden')) {
      closeBridgeModal();
    } else if (!document.getElementById('edit-bridge-modal').classList.contains('hidden')) {
      closeEditBridgeModal();
    } else if (!document.getElementById('modal-overlay').classList.contains('hidden')) {
      ignoreUnknownDevice();
    } else if (!document.getElementById('edit-device-modal').classList.contains('hidden')) {
      closeEditDeviceModal();
    } else if (!document.getElementById('edit-user-modal').classList.contains('hidden')) {
      closeEditUserModal();
    } else if (pendingBridgeInfo || repositioningBridgeTopic) {
      cancelBridgePlacement();
    } else if (pendingDeviceInfo) {
      cancelPlacement();
    }
  }
});

// ─── Init ─────────────────────────────────────────────────────────────────────

async function startPolling() {
  try {
    const [dispositivi, bridges] = await Promise.all([
      api('GET', '/devices').then(r => r.json()),
      api('GET', '/bridges').then(r => r.json()),
    ]);
    dispositiviCache = dispositivi;
    bridgesCache     = bridges;
    renderizzaMappa(dispositivi, bridges);
  } catch (_) {}

  await fetchListening();
  await poll();
  setInterval(poll,                3000);
  setInterval(pollUnknown,         3000);
  setInterval(pollUnknownBridges,  3000);
  setInterval(fetchListening,     15000);
}

async function initApp() {
  if (authToken) {
    try {
      const res = await fetch('/auth/me', {
        cache: 'no-store',
        headers: { 'Authorization': `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data  = await res.json();
        userLevel       = data.level;
        currentUsername = data.username;
        showApp();
        startPolling();
        return;
      }
    } catch (_) {}
  }
  showLogin();
}

initApp();
