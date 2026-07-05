(function () {
  const modal = document.getElementById('ticketStubModal');
  const open = () => modal && modal.classList.add('open');
  const close = () => modal && modal.classList.remove('open');
  document.querySelectorAll('[data-ticket-stub]').forEach(btn => btn.addEventListener('click', event => { event.preventDefault(); open(); }));
  document.querySelectorAll('[data-close-ticket-stub]').forEach(btn => btn.addEventListener('click', close));
  modal?.addEventListener('click', event => { if (event.target === modal) close(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  const current = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.expo-links a').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (href === current || (current === '' && href === 'index.html')) link.classList.add('active');
  });
  const isStandalonePwa = window.matchMedia?.('(display-mode: standalone)')?.matches || window.navigator.standalone === true;
  if (isStandalonePwa) document.documentElement.classList.add('expo-pwa');
  const expoVenueLat = '-33.609232';
  const expoVenueLng = '150.784358';
  const nativeDestination = `${expoVenueLat},${expoVenueLng}`;
  const encodedDestination = encodeURIComponent(nativeDestination);
  const fallbackDirectionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodedDestination}`;
  function nativeNavigationUrl() {
    const ua = navigator.userAgent || '';
    if (/iPad|iPhone|iPod/.test(ua)) return `maps://?daddr=${encodedDestination}`;
    if (/Android/i.test(ua)) return `geo:${expoVenueLat},${expoVenueLng}?q=${encodedDestination}(Hawkesbury%20Showground)`;
    return fallbackDirectionsUrl;
  }
  document.querySelectorAll('[data-native-nav]').forEach(link => {
    if (!isStandalonePwa) {
      link.setAttribute('aria-hidden', 'true');
      link.tabIndex = -1;
      return;
    }
    link.href = nativeNavigationUrl();
    link.target = '_self';
    link.rel = '';
    link.addEventListener('click', () => {
      // Keep href current if the PWA is resumed after device orientation/session changes.
      link.href = nativeNavigationUrl();
    });
  });

})();

(function () {
  const installSection = document.getElementById('expoInstallSection');
  const installModal = document.getElementById('expoInstallModal');
  const installTitle = document.getElementById('expoInstallModalTitle');
  const installBody = document.getElementById('expoInstallModalBody');
  const installActions = document.getElementById('expoInstallModalActions');
  let deferredExpoInstallPrompt = null;

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').catch(() => {});
    });
  }

  // Let Chrome handle its native PWA install prompt. We keep the Expo instructions visible
  // instead of suppressing the browser prompt, which avoids the noisy console warning caused
  // by calling beforeinstallprompt.preventDefault() without immediately prompting.

  function isExpoStandalone() {
    return window.matchMedia?.('(display-mode: standalone)')?.matches || window.navigator.standalone === true;
  }

  function expoPlatform() {
    const ua = navigator.userAgent || '';
    const platform = navigator.platform || '';
    const touchPoints = Number(navigator.maxTouchPoints || 0);
    if (/iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(platform) && touchPoints > 1)) return 'ios';
    if (/Android/i.test(ua)) return 'android';
    return 'other';
  }

  function closeInstallModal() {
    installModal?.classList.remove('open');
  }

  async function tryExpoInstallPrompt() {
    if (!deferredExpoInstallPrompt) return false;
    try {
      await deferredExpoInstallPrompt.prompt();
      await deferredExpoInstallPrompt.userChoice;
      deferredExpoInstallPrompt = null;
      closeInstallModal();
      installSection?.classList.add('hidden');
      return true;
    } catch {
      return false;
    }
  }

  function showInstallInstructions(platformKey) {
    if (!installModal || !installTitle || !installBody || !installActions) return;
    const isIos = platformKey === 'ios';
    installTitle.textContent = isIos ? 'Install Expo on iPhone' : 'Install Expo on Android';
    installBody.innerHTML = isIos ? `
      <ol>
        <li>Open the Expo site in <strong>Safari</strong>.</li>
        <li>Tap the <strong>Share</strong> button.</li>
        <li>Choose <strong>Add to Home Screen</strong>.</li>
        <li>Tap <strong>Add</strong>.</li>
      </ol>
      <p class="muted">The Expo icon will open directly to the Expo guide rather than the main LROC site.</p>` : `
      <ol>
        <li>Open the Expo site in <strong>Chrome</strong>.</li>
        <li>Tap the browser menu.</li>
        <li>Choose <strong>Add to Home screen</strong> or <strong>Install app</strong>.</li>
        <li>Confirm the install prompt.</li>
      </ol>
      <p class="muted">Once installed, the Expo app opens directly to visitor information, location, camping and downloads.</p>`;
    installActions.innerHTML = '<button class="button dark" type="button" data-expo-install-close>Done</button>';
    installModal.classList.add('open');
    installActions.querySelector('[data-expo-install-close]')?.addEventListener('click', closeInstallModal, { once: true });
  }

  if (!installSection || isExpoStandalone()) {
    installSection?.classList.add('hidden');
    return;
  }

  const platform = expoPlatform();
  installSection.querySelectorAll('[data-expo-install-platform]').forEach(button => {
    if (platform === 'ios') button.classList.toggle('hidden', button.dataset.expoInstallPlatform !== 'ios');
    else if (platform === 'android') button.classList.toggle('hidden', button.dataset.expoInstallPlatform !== 'android');
    else button.classList.remove('hidden');
    button.addEventListener('click', () => showInstallInstructions(button.dataset.expoInstallPlatform));
  });
  installModal?.addEventListener('click', event => { if (event.target === installModal) closeInstallModal(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeInstallModal(); });
})();

(function () {
  const drawer = document.getElementById('expoDrawer');
  const backdrop = document.querySelector('.expo-drawer-backdrop');
  const toggle = document.querySelector('.expo-menu-toggle');
  if (!drawer || !toggle) return;
  function setDrawer(open) {
    drawer.classList.toggle('open', open);
    backdrop?.classList.toggle('open', open);
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    document.body.classList.toggle('expo-menu-open', open);
  }
  toggle.addEventListener('click', () => setDrawer(!drawer.classList.contains('open')));
  document.querySelectorAll('[data-expo-menu-close]').forEach(btn => btn.addEventListener('click', () => setDrawer(false)));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setDrawer(false); });
  const current = location.pathname.split('/').pop() || 'index.html';
  drawer.querySelectorAll('a[href]').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (href === current || (current === '' && href === 'index.html')) link.classList.add('active');
  });
})();

(function () {
  function mainSiteUrl(path) {
    const cleanPath = String(path || 'index.html').replace(/^\/+/, '');
    const host = window.location.hostname || '';
    if (host.toLowerCase().startsWith('expo.')) {
      return `${window.location.protocol}//${host.replace(/^expo\./i, '')}/${cleanPath}`;
    }
    return `/${cleanPath}`;
  }
  document.querySelectorAll('[data-main-site-link]').forEach(link => {
    link.href = mainSiteUrl(link.getAttribute('data-main-site-link') || 'index.html');
    link.target = '_self';
  });

  const defaults = {
    event_name: 'Land Rover Owners Expo 2026',
    hero_title: 'Share the passion at the Expo',
    hero_lead: 'Old, new, classic, modern, restored, original, modified, off-road, camping or urban — if it has a Land Rover badge or spirit, this is the day to see it, display it, explore it and talk about it.',
    event_date: 'Sunday 19 July 2026',
    event_time: '9:00 AM – 4:00 PM',
    venue_name: 'Hawkesbury Showground',
    venue_address: 'Racecourse Road, Clarendon NSW 2756',
    ticket_summary: 'Pre-purchase $10 · Gate price $15 · Under 16s free',
    contact_name: 'Jon Robinson',
    contact_email: 'vicepresident@lroc.com.au',
    ticket_status: 'Online ticket purchase is being prepared for the Expo microsite. For now this button is a placeholder while the new site is tested.'
  };
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
  }
  function pageKey() {
    const file = (location.pathname.split('/').pop() || 'index.html').replace(/\.html$/i, '');
    return file || 'index';
  }
  function replaceTextNodes(root, from, to) {
    if (!from || !to || from === to) return;
    const walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return node.nodeValue && node.nodeValue.includes(from) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => { node.nodeValue = node.nodeValue.split(from).join(to); });
  }
  function cardHtml(card) {
    const url = String(card.url || '').trim();
    const label = String(card.label || '').trim() || 'More details';
    return `<article class="card expo-managed-card">${card.icon ? `<span class="expo-managed-icon">${escapeHtml(card.icon)}</span>` : ''}<h3>${escapeHtml(card.title || card.label || 'Expo item')}</h3>${card.text ? `<p>${escapeHtml(card.text)}</p>` : ''}${url ? `<a class="button secondary" href="${escapeHtml(url)}">${escapeHtml(label)}</a>` : ''}</article>`;
  }
  function downloadHtml(item) {
    const url = String(item.url || '').trim();
    const label = String(item.label || item.title || 'Expo download').trim();
    return `<li>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>` : `<strong>${escapeHtml(label)}</strong>`}${item.text ? `<span>${escapeHtml(item.text)}</span>` : ''}</li>`;
  }
  function applyPageContent(content) {
    const key = pageKey();
    const page = content?.pages?.[key];
    if (!page) return;
    const hero = document.querySelector('.expo-hero');
    const eyebrow = hero?.querySelector('.expo-eyebrow');
    const title = hero?.querySelector('h1');
    const lead = hero?.querySelector('.expo-lead');
    if (eyebrow && page.eyebrow) eyebrow.textContent = page.eyebrow;
    if (title && page.title) title.textContent = page.title;
    if (lead && page.lead) lead.textContent = page.lead;
    const main = document.querySelector('main.container');
    if (!main) return;
    const body = String(page.body || '').trim();
    const cards = Array.isArray(page.cards) ? page.cards.filter(x => x && (x.title || x.text || x.url)) : [];
    const downloads = Array.isArray(page.downloads) ? page.downloads.filter(x => x && (x.label || x.title || x.url)) : [];
    if (!body && !cards.length && !downloads.length) return;
    document.querySelector('.expo-managed-content')?.remove();
    const section = document.createElement('section');
    section.className = 'expo-managed-content';
    section.innerHTML = `<div class="section-head"><div class="expo-eyebrow">${escapeHtml(page.label || 'Expo update')}</div><h2>${escapeHtml(page.title || 'Expo information')}</h2>${body ? `<p>${escapeHtml(body)}</p>` : ''}</div>${cards.length ? `<div class="card-grid expo-managed-grid">${cards.map(cardHtml).join('')}</div>` : ''}${downloads.length ? `<div class="card expo-managed-downloads"><h3>Downloads and links</h3><ul>${downloads.map(downloadHtml).join('')}</ul></div>` : ''}`;
    main.insertBefore(section, main.firstChild);
  }
  function applyExpoContent(content) {
    const data = { ...defaults, ...(content || {}) };
    Object.keys(defaults).forEach(key => replaceTextNodes(document.body, defaults[key], String(data[key] || defaults[key])));
    applyPageContent(data);
    if (data.event_name) document.title = document.title.replace(defaults.event_name, data.event_name).replace('Land Rover Owners Expo', data.event_name);
  }
  fetch('/expo/content.json', { cache: 'no-store' })
    .then(resp => resp.ok ? resp.json() : null)
    .then(data => data && applyExpoContent(data))
    .catch(() => {});
})();
