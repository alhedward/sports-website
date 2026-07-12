const cfg = window.SPORTSPOT_CONFIG || {};
const adminCfg = cfg.admin || {};
const API_BASE = (cfg.apiBaseUrl || '').replace(/\/$/, '');
const STORE = 'sports-admin-pwa-state-v1';
const TOKEN_STORE = 'sports-admin-pwa-tokens-v1';

let selectedSuggestion = null;
let selectedRecord = null;
let selectedRecordOriginalId = null;
let selectedCollection = 'sport_bodies';
let recordEditorMode = 'form';
let deferredInstall = null;
let currentActor = null;

const COLLECTION_FIELD_ORDER = {
  sport_bodies: [
    'id', 'name', 'sport', 'level', 'region', 'summary', 'participation_note',
    'tags', 'official_url', 'cta_label', 'source_name', 'last_verified'
  ],
  top_players: [
    'id', 'name', 'sport', 'genre', 'country', 'rank_label', 'summary',
    'why_featured', 'achievements', 'stats_note', 'source_name', 'official_url',
    'related_body_ids', 'tags'
  ],
  pathways: [
    'id', 'name', 'sport', 'nationality', 'rank_label', 'tournament_ids',
    'feature_reason', 'bio', 'career_stats', 'accomplishments', 'source_name',
    'source_url', 'last_verified'
  ],
  tournaments: [
    'id', 'name', 'sport', 'start_date', 'end_date', 'hosts', 'status',
    'summary', 'tags', 'source_name', 'source_url', 'last_verified'
  ],
  events: [
    'id', 'tournament_id', 'name', 'date', 'venue', 'source_name',
    'source_url', 'last_verified'
  ]
};

const LONG_TEXT_FIELDS = new Set([
  'summary', 'participation_note', 'why_featured', 'stats_note', 'feature_reason',
  'bio', 'description', 'submitter_note', 'notes'
]);

const READ_ONLY_FIELDS = new Set([
  'id', 'created_at', 'updated_at', 'submitted_at', 'approved_at', 'rejected_at',
  'created_from_suggestion_id'
]);

const $ = selector => document.querySelector(selector);
const safe = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[character]));
const state = loadState();

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STORE) || '{}');
  } catch {
    return {};
  }
}

function saveState() {
  localStorage.setItem(STORE, JSON.stringify(state));
}

function loadTokens() {
  try {
    return JSON.parse(sessionStorage.getItem(TOKEN_STORE) || localStorage.getItem(TOKEN_STORE) || '{}');
  } catch {
    return {};
  }
}

function saveTokens(tokens) {
  sessionStorage.setItem(TOKEN_STORE, JSON.stringify(tokens));
}

function clearTokens() {
  sessionStorage.removeItem(TOKEN_STORE);
  localStorage.removeItem(TOKEN_STORE);
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function sha256(text) {
  return b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
}

function rand(size = 32) {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return b64url(bytes);
}

function deviceId() {
  if (!state.device_id) {
    state.device_id = `pwa-${rand(18)}`;
    saveState();
  }
  return state.device_id;
}

function deviceLabel() {
  return state.device_label || `${navigator.platform || 'Device'} ${
    navigator.userAgent.includes('Firefox') ? 'Firefox' :
    navigator.userAgent.includes('Edg') ? 'Edge' :
    navigator.userAgent.includes('Chrome') ? 'Chrome' :
    navigator.userAgent.includes('Safari') ? 'Safari' : 'Browser'
  }`;
}

function api(path) {
  return `${API_BASE}${path}`;
}

function setStatus(message) {
  $('#gateStatus').textContent = message || '';
}

function token() {
  const tokens = loadTokens();
  return tokens.id_token || tokens.access_token || '';
}

function parseJwt(jwt) {
  try {
    const [, encodedPayload] = jwt.split('.');
    const padded = encodedPayload.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(encodedPayload.length / 4) * 4, '=');
    return JSON.parse(atob(padded));
  } catch {
    return {};
  }
}

function isLoggedIn() {
  const claims = parseJwt(token());
  return claims.exp && claims.exp * 1000 > Date.now() + 30000;
}

class ApiError extends Error {
  constructor(message, status, payload = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload.code || '';
    this.payload = payload;
  }
}

async function responsePayload(response) {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); } catch { return { message: text }; }
}

async function adminFetch(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  headers.Authorization = `Bearer ${token()}`;
  headers['X-Admin-Device-Id'] = deviceId();
  const response = await fetch(api(path), { ...options, headers });
  const payload = await responsePayload(response);
  if (!response.ok) {
    throw new ApiError(payload.message || `${options.method || 'GET'} ${path} failed`, response.status, payload);
  }
  return payload;
}

async function publicFetch(path, body) {
  const response = await fetch(api(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  const payload = await responsePayload(response);
  if (!response.ok) {
    throw new ApiError(payload.message || `HTTP ${response.status}`, response.status, payload);
  }
  return payload;
}

async function loginStart(email) {
  if (!adminCfg.cognitoDomain || !adminCfg.clientId || !adminCfg.redirectUri) {
    throw new Error('Missing admin Cognito configuration in config.js');
  }
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
  if (url.searchParams.get('state') !== state.oauth_state) {
    throw new Error('Cognito state check failed. Please start login again.');
  }

  const body = new URLSearchParams();
  body.set('grant_type', 'authorization_code');
  body.set('client_id', adminCfg.clientId);
  body.set('code', code);
  body.set('redirect_uri', adminCfg.redirectUri);
  body.set('code_verifier', state.pkce_verifier || '');

  const response = await fetch(`${adminCfg.cognitoDomain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  });
  if (!response.ok) {
    throw new Error(`Token exchange failed: HTTP ${response.status}: ${await response.text()}`);
  }

  saveTokens(await response.json());
  delete state.pkce_verifier;
  delete state.oauth_state;
  saveState();
  history.replaceState({}, '', '/admin/');
}

async function precheckAndLogin(event) {
  event.preventDefault();
  const email = $('#adminEmail').value.trim().toLowerCase();
  state.admin_email = email;
  state.device_label = $('#deviceLabel').value.trim() || deviceLabel();
  saveState();
  setStatus('Checking admin eligibility and registered device. This intentionally takes a few seconds...');
  try {
    await publicFetch('/admin-precheck', {
      email,
      device_id: deviceId(),
      device_label: state.device_label
    });
    setStatus('Allowed. Opening Cognito login...');
    await loginStart(email);
  } catch (error) {
    if (error.code === 'DEVICE_APPROVAL_PENDING') {
      setStatus('Approval requested. Ask a PrimaryAdmin to approve this device in Admin → Devices, then press Continue again on this device.');
      return;
    }
    setStatus('Access denied. Check your admin account/device or contact a PrimaryAdmin.');
  }
}

async function connect() {
  if (!isLoggedIn()) {
    $('#gatePanel').hidden = false;
    $('#adminPanel').hidden = true;
    $('#logoutButton').hidden = true;
    return;
  }

  const me = await adminFetch('/admin/me');
  currentActor = me.actor || {};
  $('#authSummary').textContent = `${currentActor.email || currentActor.username} · ${(currentActor.groups || []).join(', ')}`;
  try {
    await registerDevice(false);
  } catch (error) {
    clearTokens();
    currentActor = null;
    $('#gatePanel').hidden = false;
    $('#adminPanel').hidden = true;
    $('#logoutButton').hidden = true;
    setStatus(error.message || 'This device is not approved for admin access.');
    return;
  }
  $('#gatePanel').hidden = true;
  $('#adminPanel').hidden = false;
  $('#logoutButton').hidden = false;
  await refreshSuggestions();
}

async function registerDevice(showAlert = true, notificationsEnabled = null, pushSubscription = null) {
  const payload = { device_id: deviceId(), device_label: deviceLabel() };
  if (notificationsEnabled !== null) payload.notifications_enabled = notificationsEnabled;
  if (pushSubscription) payload.push_subscription = pushSubscription;
  await adminFetch('/admin/devices', { method: 'POST', body: JSON.stringify(payload) });
  if (showAlert) alert('Device registered/updated.');
}

function rowClick(table, handler) {
  table.querySelectorAll('tbody tr[data-id]').forEach(row => {
    row.addEventListener('click', () => handler(row.dataset.id));
  });
}

async function refreshSuggestions() {
  const items = await adminFetch('/admin/collections/suggestions');
  const pending = items.filter(item => (item.status || '') === 'pending_review');
  $('#suggestionsTable tbody').innerHTML = pending.map(item => `
    <tr data-id="${safe(item.id)}">
      <td>${safe(item.status)}</td>
      <td>${safe(item.name)}</td>
      <td>${safe(item.sport)}</td>
      <td>${safe(item.suggestion_type)}</td>
    </tr>
  `).join('') || '<tr><td colspan="4">No pending suggestions.</td></tr>';

  rowClick($('#suggestionsTable'), id => {
    selectedSuggestion = pending.find(item => item.id === id);
    $('#suggestionDetails').textContent = JSON.stringify(selectedSuggestion, null, 2);
  });
}

async function suggestionAction(kind) {
  if (!selectedSuggestion) return alert('Select a suggestion first.');
  if (kind === 'delete' && !confirm('Delete this suggestion?')) return;

  const id = encodeURIComponent(selectedSuggestion.id);
  if (kind === 'body') await adminFetch(`/admin/suggestions/${id}/approve-body`, { method: 'POST', body: '{}' });
  if (kind === 'pathway') await adminFetch(`/admin/suggestions/${id}/approve-pathway`, { method: 'POST', body: '{}' });
  if (kind === 'reject') await adminFetch(`/admin/suggestions/${id}/reject`, { method: 'POST', body: '{}' });
  if (kind === 'delete') await adminFetch(`/admin/collections/suggestions/${id}`, { method: 'DELETE' });

  selectedSuggestion = null;
  $('#suggestionDetails').textContent = 'Select a suggestion.';
  await refreshSuggestions();
}

function deepClone(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

function fieldLabel(fieldName) {
  return fieldName
    .replace(/_/g, ' ')
    .replace(/\b\w/g, character => character.toUpperCase());
}

function orderedKeys(record, collection, nested = false) {
  const keys = Object.keys(record || {});
  if (nested) return keys;
  const preferred = COLLECTION_FIELD_ORDER[collection] || [];
  return [
    ...preferred.filter(key => keys.includes(key)),
    ...keys.filter(key => !preferred.includes(key)).sort()
  ];
}

function isDateField(fieldName, value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && (
    fieldName === 'date' || fieldName.endsWith('_date') || fieldName === 'last_verified'
  );
}

function isUrlField(fieldName) {
  return fieldName === 'url' || fieldName.endsWith('_url') || fieldName.includes('website');
}

function listKind(fieldName, value) {
  if (!Array.isArray(value)) return null;
  if (value.length === 0) return 'string-list';
  if (value.every(item => typeof item === 'string')) return 'string-list';
  if (value.every(item => typeof item === 'number')) return 'number-list';
  return 'json';
}

function createHelp(text) {
  const help = document.createElement('small');
  help.className = 'field-help';
  help.textContent = text;
  return help;
}

function createRecordControl(fieldName, value, path) {
  const wrapper = document.createElement('label');
  wrapper.className = 'record-field';
  wrapper.append(document.createTextNode(fieldLabel(fieldName)));

  const pathJson = JSON.stringify(path);
  const readOnly = READ_ONLY_FIELDS.has(fieldName);
  let control;
  let kind;

  if (typeof value === 'boolean') {
    control = document.createElement('input');
    control.type = 'checkbox';
    control.checked = value;
    wrapper.classList.add('record-field-checkbox');
    kind = 'boolean';
  } else if (typeof value === 'number') {
    control = document.createElement('input');
    control.type = 'number';
    control.step = 'any';
    control.value = String(value);
    kind = 'number';
  } else if (Array.isArray(value)) {
    control = document.createElement('textarea');
    control.rows = Math.max(3, Math.min(8, value.length + 1));
    kind = listKind(fieldName, value);
    if (kind === 'string-list' || kind === 'number-list') {
      control.value = value.join('\n');
      wrapper.append(createHelp('One item per line.'));
    } else {
      control.value = JSON.stringify(value, null, 2);
      wrapper.append(createHelp('This complex list is edited as valid JSON.'));
    }
  } else if (value && typeof value === 'object') {
    const fieldset = document.createElement('fieldset');
    fieldset.className = 'record-fieldset';
    const legend = document.createElement('legend');
    legend.textContent = fieldLabel(fieldName);
    fieldset.append(legend);
    for (const childKey of orderedKeys(value, selectedCollection, true)) {
      fieldset.append(createRecordControl(childKey, value[childKey], [...path, childKey]));
    }
    return fieldset;
  } else if (LONG_TEXT_FIELDS.has(fieldName)) {
    control = document.createElement('textarea');
    control.rows = 5;
    control.value = value ?? '';
    kind = value === null ? 'null-text' : 'string';
  } else {
    control = document.createElement('input');
    control.type = isDateField(fieldName, value) ? 'date' : isUrlField(fieldName) ? 'url' : 'text';
    control.value = value ?? '';
    kind = value === null ? 'null-text' : 'string';
  }

  control.dataset.recordField = 'true';
  control.dataset.path = pathJson;
  control.dataset.kind = kind;
  if (readOnly) {
    control.readOnly = true;
    control.classList.add('read-only-field');
    wrapper.append(createHelp('Managed by the system.'));
  }
  wrapper.append(control);
  return wrapper;
}

function renderRecordForm(record) {
  const form = $('#recordForm');
  form.innerHTML = '';
  for (const key of orderedKeys(record, selectedCollection)) {
    form.append(createRecordControl(key, record[key], [key]));
  }
}

function setAtPath(target, path, value) {
  let current = target;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    if (!current[key] || typeof current[key] !== 'object' || Array.isArray(current[key])) {
      current[key] = {};
    }
    current = current[key];
  }
  current[path[path.length - 1]] = value;
}

function parseControlValue(control) {
  const kind = control.dataset.kind;
  if (kind === 'boolean') return control.checked;
  if (kind === 'number') {
    if (control.value.trim() === '') return null;
    const number = Number(control.value);
    if (!Number.isFinite(number)) throw new Error(`Invalid number in ${fieldLabel(JSON.parse(control.dataset.path).slice(-1)[0])}.`);
    return number;
  }
  if (kind === 'string-list') {
    return control.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  }
  if (kind === 'number-list') {
    return control.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean).map(value => {
      const number = Number(value);
      if (!Number.isFinite(number)) throw new Error(`Invalid number-list value: ${value}`);
      return number;
    });
  }
  if (kind === 'json') {
    try {
      return JSON.parse(control.value || '[]');
    } catch (error) {
      throw new Error(`Invalid JSON in ${fieldLabel(JSON.parse(control.dataset.path).slice(-1)[0])}: ${error.message}`);
    }
  }
  if (kind === 'null-text' && control.value === '') return null;
  return control.value;
}

function collectRecordForm() {
  const result = deepClone(selectedRecord) || {};
  $('#recordForm').querySelectorAll('[data-record-field="true"]').forEach(control => {
    setAtPath(result, JSON.parse(control.dataset.path), parseControlValue(control));
  });
  return result;
}

function setRecordEditorMode(mode, sync = true) {
  if (!selectedRecord) return;
  if (mode === recordEditorMode) return;

  try {
    if (sync && recordEditorMode === 'form') {
      selectedRecord = collectRecordForm();
      $('#recordEditor').value = JSON.stringify(selectedRecord, null, 2);
    } else if (sync && recordEditorMode === 'json') {
      selectedRecord = JSON.parse($('#recordEditor').value);
      renderRecordForm(selectedRecord);
    }
  } catch (error) {
    alert(error.message);
    return;
  }

  recordEditorMode = mode;
  $('#recordFormPanel').hidden = mode !== 'form';
  $('#recordJsonPanel').hidden = mode !== 'json';
  $('#showFormEditor').classList.toggle('active', mode === 'form');
  $('#showJsonEditor').classList.toggle('active', mode === 'json');
  $('#showFormEditor').setAttribute('aria-pressed', String(mode === 'form'));
  $('#showJsonEditor').setAttribute('aria-pressed', String(mode === 'json'));
}

function resetRecordEditor(message = 'Select a record to edit.') {
  selectedRecord = null;
  selectedRecordOriginalId = null;
  recordEditorMode = 'form';
  $('#recordEditorStatus').textContent = message;
  $('#recordForm').innerHTML = '';
  $('#recordEditor').value = '';
  $('#recordFormPanel').hidden = false;
  $('#recordJsonPanel').hidden = true;
  $('#showFormEditor').classList.add('active');
  $('#showJsonEditor').classList.remove('active');
  $('#showFormEditor').setAttribute('aria-pressed', 'true');
  $('#showJsonEditor').setAttribute('aria-pressed', 'false');
  $('#showFormEditor').disabled = true;
  $('#showJsonEditor').disabled = true;
  $('#saveRecord').disabled = true;
  $('#deleteRecord').disabled = true;
}

function loadRecordEditor(record) {
  selectedRecord = deepClone(record);
  selectedRecordOriginalId = record.id;
  recordEditorMode = 'form';
  $('#recordEditorStatus').textContent = `Editing ${record.name || record.title || record.id}`;
  renderRecordForm(selectedRecord);
  $('#recordEditor').value = JSON.stringify(selectedRecord, null, 2);
  $('#recordFormPanel').hidden = false;
  $('#recordJsonPanel').hidden = true;
  $('#showFormEditor').classList.add('active');
  $('#showJsonEditor').classList.remove('active');
  $('#showFormEditor').setAttribute('aria-pressed', 'true');
  $('#showJsonEditor').setAttribute('aria-pressed', 'false');
  $('#showFormEditor').disabled = false;
  $('#showJsonEditor').disabled = false;
  $('#saveRecord').disabled = false;
  $('#deleteRecord').disabled = false;
}

async function refreshRecords(selectId = null) {
  selectedCollection = $('#collectionSelect').value;
  const items = await adminFetch(`/admin/collections/${selectedCollection}`);
  $('#recordsTable tbody').innerHTML = items.map(item => `
    <tr data-id="${safe(item.id)}">
      <td>${safe(item.id)}</td>
      <td>${safe(item.name || item.title || '')}</td>
      <td>${safe(item.sport || '')}</td>
    </tr>
  `).join('') || '<tr><td colspan="3">No records.</td></tr>';

  rowClick($('#recordsTable'), async id => {
    const record = await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(id)}`);
    loadRecordEditor(record);
  });

  if (selectId) {
    const record = await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(selectId)}`);
    loadRecordEditor(record);
  } else {
    resetRecordEditor();
  }
}

async function saveRecord() {
  if (!selectedRecord) return alert('Select a record first.');

  let data;
  try {
    data = recordEditorMode === 'form' ? collectRecordForm() : JSON.parse($('#recordEditor').value);
  } catch (error) {
    return alert(error.message);
  }

  if (!data.id) return alert('Record needs an id.');
  if (data.id !== selectedRecordOriginalId) return alert('The record id cannot be changed.');

  const saved = await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(selectedRecordOriginalId)}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  });
  await refreshRecords(saved.id);
}

async function deleteRecord() {
  if (!selectedRecord || !confirm('Delete this record?')) return;
  await adminFetch(`/admin/collections/${selectedCollection}/${encodeURIComponent(selectedRecordOriginalId)}`, {
    method: 'DELETE'
  });
  await refreshRecords();
}

async function refreshActivity() {
  const items = await adminFetch('/admin/activity-log?limit=500');
  $('#activityTable tbody').innerHTML = items.map(item => `
    <tr>
      <td>${safe(item.created_at)}</td>
      <td>${safe(item.action)}</td>
      <td>${safe(item.actor_email || item.actor_username || 'system')}</td>
      <td>${safe(item.summary)}</td>
    </tr>
  `).join('');
}

function isPrimaryAdmin() {
  return (currentActor?.groups || []).includes('PrimaryAdmins');
}

async function refreshDeviceRequests() {
  const panel = $('#pendingDeviceRequests');
  if (!isPrimaryAdmin()) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const items = await adminFetch('/admin/device-requests');
  $('#deviceRequestsTable tbody').innerHTML = items.map(item => `
    <tr>
      <td>${safe(item.email || item.username)}</td>
      <td>${safe(item.device_label || item.device_id)}</td>
      <td>${safe(item.client?.user_agent || '')}</td>
      <td>${safe(item.client?.ip || '')}</td>
      <td>${safe(item.last_requested_at || item.requested_at || '')}</td>
      <td class="button-cell"><button data-approve-request="${safe(item.id)}">Approve</button><button data-reject-request="${safe(item.id)}" class="danger">Reject</button></td>
    </tr>
  `).join('') || '<tr><td colspan="6">No pending device requests.</td></tr>';

  document.querySelectorAll('[data-approve-request]').forEach(button => {
    button.addEventListener('click', async () => {
      if (!confirm('Approve this device to complete Cognito login? Approval expires after 30 minutes if it is not activated.')) return;
      await adminFetch(`/admin/device-requests/${encodeURIComponent(button.dataset.approveRequest)}/approve`, { method: 'POST', body: '{}' });
      await Promise.all([refreshDeviceRequests(), refreshActivity()]);
    });
  });
  document.querySelectorAll('[data-reject-request]').forEach(button => {
    button.addEventListener('click', async () => {
      if (!confirm('Reject this device request?')) return;
      await adminFetch(`/admin/device-requests/${encodeURIComponent(button.dataset.rejectRequest)}/reject`, { method: 'POST', body: '{}' });
      await Promise.all([refreshDeviceRequests(), refreshActivity()]);
    });
  });
}

async function refreshDevices() {
  const items = await adminFetch('/admin/devices');
  $('#devicesTable tbody').innerHTML = items.map(item => `
    <tr>
      <td>${safe(item.device_label || item.device_id)}</td>
      <td>${safe(item.status)}</td>
      <td>${item.notifications_enabled ? 'enabled' : 'disabled'}</td>
      <td>${safe(item.last_seen_at || '')}</td>
      <td><button data-revoke="${safe(item.device_id)}" class="danger">Revoke</button></td>
    </tr>
  `).join('') || '<tr><td colspan="5">No devices.</td></tr>';

  await refreshDeviceRequests();

  document.querySelectorAll('[data-revoke]').forEach(button => {
    button.addEventListener('click', async () => {
      if (confirm('Revoke this admin device?')) {
        await adminFetch(`/admin/devices/${encodeURIComponent(button.dataset.revoke)}`, { method: 'DELETE' });
        await refreshDevices();
      }
    });
  });
}

async function enableAdminNotifications(enabled) {
  if (enabled && !cfg.vapidPublicKey) {
    alert('Push delivery is not configured yet. This admin device can still be registered, but notification delivery will be available after VAPID keys are added.');
    await registerDevice(true, false, null);
    await refreshDevices();
    return;
  }
  if (enabled && !('Notification' in window)) return alert('This browser does not support notifications.');
  if (enabled && (!('serviceWorker' in navigator) || !('PushManager' in window))) {
    return alert('This browser does not support web push notifications.');
  }
  if (enabled && Notification.permission !== 'granted') {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') return alert('Notifications were not enabled.');
  }

  let subscription = null;
  if (enabled) {
    const registration = await navigator.serviceWorker.ready;
    subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: cfg.vapidPublicKey
      });
    }
  }
  await registerDevice(true, enabled, subscription ? subscription.toJSON() : null);
  await refreshDevices();
}

async function exportJson(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(blob);
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
}

async function exportAll() {
  const collections = ['suggestions', 'sport_bodies', 'top_players', 'pathways', 'tournaments', 'events'];
  const output = {};
  for (const collection of collections) {
    output[collection] = await adminFetch(`/admin/collections/${collection}`);
  }
  await exportJson(`sports-admin-export-${new Date().toISOString().slice(0, 10)}.json`, output);
}

function wire() {
  $('#adminEmail').value = state.admin_email || '';
  $('#deviceLabel').value = state.device_label || deviceLabel();
  $('#precheckForm').addEventListener('submit', precheckAndLogin);
  $('#logoutButton').addEventListener('click', () => {
    clearTokens();
    location.assign(`${adminCfg.cognitoDomain}/logout?client_id=${encodeURIComponent(adminCfg.clientId)}&logout_uri=${encodeURIComponent(adminCfg.logoutUri || location.origin + '/admin/')}`);
  });

  document.querySelectorAll('[data-tab]').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-tab]').forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      document.querySelectorAll('.tab-panel').forEach(panel => { panel.hidden = true; });
      $(`#tab-${button.dataset.tab}`).hidden = false;
      if (button.dataset.tab === 'records') refreshRecords().catch(error => alert(error.message));
      if (button.dataset.tab === 'devices') refreshDevices().catch(error => alert(error.message));
    });
  });

  $('#refreshSuggestions').onclick = refreshSuggestions;
  $('#approveBody').onclick = () => suggestionAction('body');
  $('#approvePathway').onclick = () => suggestionAction('pathway');
  $('#rejectSuggestion').onclick = () => suggestionAction('reject');
  $('#deleteSuggestion').onclick = () => suggestionAction('delete');

  $('#refreshRecords').onclick = () => refreshRecords().catch(error => alert(error.message));
  $('#collectionSelect').onchange = () => refreshRecords().catch(error => alert(error.message));
  $('#showFormEditor').onclick = () => setRecordEditorMode('form');
  $('#showJsonEditor').onclick = () => setRecordEditorMode('json');
  $('#saveRecord').onclick = () => saveRecord().catch(error => alert(error.message));
  $('#deleteRecord').onclick = () => deleteRecord().catch(error => alert(error.message));

  $('#refreshActivity').onclick = refreshActivity;
  $('#refreshDevices').onclick = refreshDevices;
  $('#registerThisDevice').onclick = () => registerDevice(true).then(refreshDevices);
  $('#enableAdminNotifications').onclick = () => enableAdminNotifications(true);
  $('#disableAdminNotifications').onclick = () => enableAdminNotifications(false);

  $('#exportAll').onclick = exportAll;
  $('#exportActivity').onclick = async () => exportJson(
    `sports-activity-${new Date().toISOString().slice(0, 10)}.json`,
    await adminFetch('/admin/activity-log?limit=10000')
  );

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    deferredInstall = event;
    $('#installAdmin').hidden = false;
  });
  $('#installAdmin').onclick = () => deferredInstall?.prompt();

  resetRecordEditor();
}

wire();
exchangeCodeIfPresent().then(connect).catch(error => {
  console.error(error);
  setStatus(error.message);
});
