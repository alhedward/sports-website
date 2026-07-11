const cfg = window.SPORTSPOT_CONFIG || {};
const adminCfg = cfg.admin || {};
const API_BASE = (cfg.apiBaseUrl || '').replace(/\/$/, '');
const STORE = 'sports-admin-pwa-state-v1';
const TOKEN_STORE = 'sports-admin-pwa-tokens-v1';
let selectedSuggestion = null;
let selectedRecord = null;
let selectedCollection = 'sport_bodies';
let deferredInstall = null;

const $ = sel => document.querySelector(sel);
const safe = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const state = loadState();

function loadState() { try { return JSON.parse(localStorage.getItem(STORE) || '{}'); } catch { return {}; } }
function saveState() { localStorage.setItem(STORE, JSON.stringify(state)); }
function loadTokens() { try { return JSON.parse(sessionStorage.getItem(TOKEN_STORE) || localStorage.getItem(TOKEN_STORE) || '{}'); } catch { return {}; } }
function saveTokens(tokens) { sessionStorage.setItem(TOKEN_STORE, JSON.stringify(tokens)); }
function clearTokens() { sessionStorage.removeItem(TOKEN_STORE); localStorage.removeItem(TOKEN_STORE); }
function b64url(bytes) { return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,''); }
async function sha256(txt) { return b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(txt))); }
function rand(size = 32) { const bytes = new Uint8Array(size); crypto.getRandomValues(bytes); return b64url(bytes); }
function deviceId() { if (!state.device_id) { state.device_id = `pwa-${rand(18)}`; saveState(); } return state.device_id; }
function deviceLabel() { return state.device_label || `${navigator.platform || 'Device'} ${navigator.userAgent.includes('Firefox') ? 'Firefox' : navigator.userAgent.includes('Edg') ? 'Edge' : navigator.userAgent.includes('Chrome') ? 'Chrome' : navigator.userAgent.includes('Safari') ? 'Safari' : 'Browser'}`; }
function api(path) { return `${API_BASE}${path}`; }
function setStatus(msg) { $('#gateStatus').textContent = msg || ''; }
function token() { const t = loadTokens(); return t.id_token || t.access_token || ''; }
function parseJwt(jwt) { try { const [, p] = jwt.split('.'); return JSON.parse(atob(p.replace(/-/g,'+').replace(/_/g,'/'))); } catch { return {}; } }
function isLoggedIn() { const claims = parseJwt(token()); return claims.exp && claims.exp * 1000 > Date.now() + 30000; }
async function adminFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  headers.Authorization = `Bearer ${token()}`;
  const res = await fetch(api(path), { ...opts, headers });
  if (!res.ok) throw new Error(`${opts.method || 'GET'} ${path} failed: HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}
async function publicFetch(path, body) {
  const res = await fetch(api(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}
async function loginStart(email) {
  if (!adminCfg.cognitoDomain || !adminCfg.clientId || !adminCfg.redirectUri) throw new Error('Missing admin Cognito configuration in config.js');
  const verifier = rand(48);
  const challenge = await sha256(verifier);
  state.pkce_verifier = verifier;
  state.oauth_state = rand(18);
  state.admin_email = email;
  saveState();
  const url = new URL(`${adminCfg.cognitoDomain}/oauth2/authorize`);
  url.searchParams.set('client_id', adminCfg.clientId);
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('scope', 'openid email profile');
  url.searchParams.set('redirect_uri', adminCfg.redirectUri);
  url.searchParams.set('code_challenge_method', 'S256');
  url.searchParams.set('code_challenge', challenge);
  url.searchParams.set('state', state.oauth_state);
  location.assign(url.toString());
}
async function exchangeCodeIfPresent() {
  const url = new URL(location.href);
  const code = url.searchParams.get('code');
  if (!code) return;
  if (url.searchParams.get('state') !== state.oauth_state) throw new Error('Cognito state check failed. Please start login again.');
  const body = new URLSearchParams();
  body.set('grant_type', 'authorization_code');
  body.set('client_id', adminCfg.clientId);
  body.set('code', code);
  body.set('redirect_uri', adminCfg.redirectUri);
  body.set('code_verifier', state.pkce_verifier || '');
  const res = await fetch(`${adminCfg.cognitoDomain}/oauth2/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
  if (!res.ok) throw new Error(`Token exchange failed: HTTP ${res.status}: ${await res.text()}`);
  saveTokens(await res.json());
  delete state.pkce_verifier; delete state.oauth_state; saveState();
  history.replaceState({}, '', '/admin/');
}
async function precheckAndLogin(evt) {
  evt.preventDefault();
  const email = $('#adminEmail').value.trim().toLowerCase();
  state.admin_email = email;
  state.device_label = $('#deviceLabel').value.trim() || deviceLabel();
  saveState();
  setStatus('Checking admin eligibility and registered device. This intentionally takes a few seconds...');
  try {
    await publicFetch('/admin-precheck', { email, device_id: deviceId(), device_label: state.device_label });
    setStatus('Allowed. Opening Cognito login...');
    await loginStart(email);
  } catch (err) {
    setStatus('Access denied. Check your admin account/device or contact a PrimaryAdmin.');
  }
}
async function connect() {
  if (!isLoggedIn()) { $('#gatePanel').hidden = false; $('#adminPanel').hidden = true; $('#logoutButton').hidden = true; return; }
  const me = await adminFetch('/admin/me');
  $('#authSummary').textContent = `${me.actor.email || me.actor.username} · ${(me.actor.groups || []).join(', ')}`;
  $('#gatePanel').hidden = true; $('#adminPanel').hidden = false; $('#logoutButton').hidden = false;
  await registerDevice(false);
  await refreshSuggestions();
}
async function registerDevice(showAlert = true, notificationsEnabled = null, pushSub = null) {
  const payload = { device_id: deviceId(), device_label: deviceLabel() };
  if (notificationsEnabled !== null) payload.notifications_enabled = notificationsEnabled;
  if (pushSub) payload.push_subscription = pushSub;
  await adminFetch('/admin/devices', { method: 'POST', body: JSON.stringify(payload) });
  if (showAlert) alert('Device registered/updated.');
}
function rowClick(table, handler) { table.querySelectorAll('tbody tr').forEach(row => row.addEventListener('click', () => handler(row.dataset.id))); }
async function refreshSuggestions() {
  const items = await adminFetch('/admin/collections/suggestions');
  const pending = items.filter(i => (i.status || '') === 'pending_review');
  $('#suggestionsTable tbody').innerHTML = pending.map(i => `<tr data-id="${safe(i.id)}"><td>${safe(i.status)}</td><td>${safe(i.name)}</td><td>${safe(i.sport)}</td><td>${safe(i.suggestion_type)}</td></tr>`).join('') || '<tr><td colspan="4">No pending suggestions.</td></tr>';
  rowClick($('#suggestionsTable'), id => { selectedSuggestion = pending.find(i => i.id === id); $('#suggestionDetails').textContent = JSON.stringify(selectedSuggestion, null, 2); });
}
async function suggestionAction(kind) {
  if (!selectedSuggestion) return alert('Select a suggestion first.');
  if (kind === 'delete' && !confirm('Delete this suggestion?')) return;
  const id = encodeURIComponent(selectedSuggestion.id);
  if (kind === 'body') await adminFetch(`/admin/suggestions/${id}/approve-body`, { method: 'POST', body: '{}' });
  if (kind === 'pathway') await adminFetch(`/admin/suggestions/${id}/approve-pathway`, { method: 'POST', body: '{}' });
  if (kind === 'reject') await adminFetch(`/admin/suggestions/${id}/reject`, { method: 'POST', body: '{}' });
  if (kind === 'delete') await adminFetch(`/admin/collections/suggestions/${id}`, { method: 'DELETE' });
  selectedSuggestion = null; $('#suggestionDetails').textContent = 'Select a suggestion.'; await refreshSuggestions();
}
async function refreshRecords() {
  selectedCollection = $('#collectionSelect').value;
  const items = await adminFetch(`/admin/collections/${selectedCollection}`);
  $('#recordsTable tbody').innerHTML = items.map(i => `<tr data-id="${safe(i.id)}"><td>${safe(i.id)}</td><td>${safe(i.name || i.title || '')}</td><td>${safe(i.sport || '')}</td></tr>`).join('') || '<tr><td colspan="3">No records.</td></tr>';
  rowClick($('#recordsTable'), async id => { selectedRecord = await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(id)}`); $('#recordEditor').value = JSON.stringify(selectedRecord, null, 2); });
}
async function saveRecord() { const data = JSON.parse($('#recordEditor').value); if (!data.id) return alert('Record JSON needs id.'); await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(data.id)}`, { method: 'PUT', body: JSON.stringify(data) }); await refreshRecords(); }
async function deleteRecord() { if (!selectedRecord || !confirm('Delete this record?')) return; await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(selectedRecord.id)}`, { method: 'DELETE' }); selectedRecord=null; $('#recordEditor').value=''; await refreshRecords(); }
async function refreshActivity() { const items = await adminFetch('/admin/activity-log?limit=500'); $('#activityTable tbody').innerHTML = items.map(i => `<tr><td>${safe(i.created_at)}</td><td>${safe(i.action)}</td><td>${safe(i.actor_email || i.actor_username || 'system')}</td><td>${safe(i.summary)}</td></tr>`).join(''); }
async function refreshDevices() { const items = await adminFetch('/admin/devices'); $('#devicesTable tbody').innerHTML = items.map(i => `<tr><td>${safe(i.device_label || i.device_id)}</td><td>${safe(i.status)}</td><td>${i.notifications_enabled ? 'enabled' : 'disabled'}</td><td>${safe(i.last_seen_at || '')}</td><td><button data-revoke="${safe(i.device_id)}" class="danger">Revoke</button></td></tr>`).join('') || '<tr><td colspan="5">No devices.</td></tr>'; document.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => { if(confirm('Revoke this admin device?')) { await adminFetch(`/admin/devices/${encodeURIComponent(b.dataset.revoke)}`, { method: 'DELETE' }); await refreshDevices(); } })); }
async function enableAdminNotifications(enabled) {
  if (enabled && !cfg.vapidPublicKey) {
    alert('Push delivery is not configured yet. This admin device can still be registered, but notification delivery will be available after VAPID keys are added.');
    await registerDevice(true, false, null);
    await refreshDevices();
    return;
  }
  if (enabled && !('Notification' in window)) return alert('This browser does not support notifications.');
  if (enabled && (!('serviceWorker' in navigator) || !('PushManager' in window))) return alert('This browser does not support web push notifications.');
  if (enabled && Notification.permission !== 'granted') {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') return alert('Notifications were not enabled.');
  }
  let sub = null;
  if (enabled) {
    const reg = await navigator.serviceWorker.ready;
    sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: cfg.vapidPublicKey });
  }
  await registerDevice(true, enabled, sub ? sub.toJSON() : null);
  await refreshDevices();
}
async function exportJson(name, data) { const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href), 1000); }
async function exportAll() { const cols = ['suggestions','sport_bodies','top_players','pathways','tournaments','events']; const out = {}; for (const c of cols) out[c] = await adminFetch(`/admin/collections/${c}`); await exportJson(`sports-admin-export-${new Date().toISOString().slice(0,10)}.json`, out); }
function wire() {
  $('#adminEmail').value = state.admin_email || '';
  $('#deviceLabel').value = state.device_label || deviceLabel();
  $('#precheckForm').addEventListener('submit', precheckAndLogin);
  $('#logoutButton').addEventListener('click', () => { clearTokens(); location.assign(`${adminCfg.cognitoDomain}/logout?client_id=${encodeURIComponent(adminCfg.clientId)}&logout_uri=${encodeURIComponent(adminCfg.logoutUri || location.origin + '/admin/')}`); });
  document.querySelectorAll('[data-tab]').forEach(btn => btn.addEventListener('click', () => { document.querySelectorAll('[data-tab]').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); document.querySelectorAll('.tab-panel').forEach(p=>p.hidden=true); $(`#tab-${btn.dataset.tab}`).hidden=false; }));
  $('#refreshSuggestions').onclick = refreshSuggestions; $('#approveBody').onclick = () => suggestionAction('body'); $('#approvePathway').onclick = () => suggestionAction('pathway'); $('#rejectSuggestion').onclick = () => suggestionAction('reject'); $('#deleteSuggestion').onclick = () => suggestionAction('delete');
  $('#refreshRecords').onclick = refreshRecords; $('#collectionSelect').onchange = refreshRecords; $('#saveRecord').onclick = saveRecord; $('#deleteRecord').onclick = deleteRecord;
  $('#refreshActivity').onclick = refreshActivity; $('#refreshDevices').onclick = refreshDevices; $('#registerThisDevice').onclick = () => registerDevice(true).then(refreshDevices); $('#enableAdminNotifications').onclick = () => enableAdminNotifications(true); $('#disableAdminNotifications').onclick = () => enableAdminNotifications(false);
  $('#exportAll').onclick = exportAll; $('#exportActivity').onclick = async () => exportJson(`sports-activity-${new Date().toISOString().slice(0,10)}.json`, await adminFetch('/admin/activity-log?limit=10000'));
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferredInstall = e; $('#installAdmin').hidden = false; });
  $('#installAdmin').onclick = () => deferredInstall?.prompt();
}

wire();
exchangeCodeIfPresent().then(connect).catch(err => { console.error(err); setStatus(err.message); });
