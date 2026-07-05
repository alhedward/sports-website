(function () {
  const storageKey = 'lroc_auth_tokens';
  const returnToKey = 'lroc_auth_return_to';
  const defaultScopes = ['openid', 'email', 'profile', 'phone', 'aws.cognito.signin.user.admin'];
  let refreshPromise = null;

  function getCfg() {
    return window.LROC_AUTH || {};
  }

  function getTokens() {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || '{}');
    } catch {
      return {};
    }
  }

  function emitAuthChanged(reason = 'updated') {
    try {
      window.dispatchEvent(new CustomEvent('lroc:auth-changed', {
        detail: {
          authenticated: isAuthenticated(),
          reason
        }
      }));
    } catch {}
  }

  function setTokens(tokens, reason = 'updated') {
    localStorage.setItem(storageKey, JSON.stringify(tokens));
    emitAuthChanged(reason);
  }

  function clearTokens(reason = 'cleared') {
    localStorage.removeItem(storageKey);
    emitAuthChanged(reason);
  }

  function parseJwt(token) {
    if (!token) return null;
    const [, payload] = token.split('.');
    if (!payload) return null;
    try {
      return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    } catch {
      return null;
    }
  }

  function isExpired(token) {
    const payload = parseJwt(token);
    if (!payload || !payload.exp) return true;
    return Date.now() / 1000 > payload.exp - 30;
  }

  function getTokenExpiryMs(token) {
    const payload = parseJwt(token);
    return payload?.exp ? Number(payload.exp) * 1000 : 0;
  }

  function getRegion() {
    const cfg = getCfg();
    if (cfg.region) return cfg.region;
    const match = String(cfg.cognitoDomain || '').match(/\.auth\.([^.]+)\.amazoncognito\.com$/);
    return match ? match[1] : 'ap-southeast-2';
  }

  function getCognitoApiBase() {
    return `https://cognito-idp.${getRegion()}.amazonaws.com/`;
  }

  function getMembersPageUrl() {
    const url = new URL(window.location.href);
    url.pathname = url.pathname.replace(/[^/]*$/, 'members.html');
    url.search = '';
    url.hash = '';
    return url.toString();
  }

  function saveReturnTo(url) {
    try {
      sessionStorage.setItem(returnToKey, url || window.location.href);
    } catch {}
  }

  function peekReturnTo() {
    try {
      return sessionStorage.getItem(returnToKey) || '';
    } catch {
      return '';
    }
  }

  function consumeReturnTo() {
    const value = peekReturnTo();
    try {
      sessionStorage.removeItem(returnToKey);
    } catch {}
    return value;
  }

  function login(returnToUrl) {
    const fallback = peekReturnTo() || window.location.href;
    const target = new URL(returnToUrl || fallback, window.location.origin);
    target.search = '';
    saveReturnTo(target.toString());
    window.dispatchEvent(new CustomEvent('lroc:open-login-modal', {
      detail: { returnTo: target.toString() }
    }));
  }

  async function cognitoJsonRequest(target, body) {
    const response = await fetch(getCognitoApiBase(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': target
      },
      body: JSON.stringify(body)
    });
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {}
    if (!response.ok) {
      const message = data.message || data.__type || text || `Request failed with ${response.status}`;
      const err = new Error(String(message).replace(/^.*#/, ''));
      err.status = response.status;
      err.code = data.__type || data.code || '';
      throw err;
    }
    return data;
  }

  function normaliseAuthResult(result, existing = {}, reason = 'updated') {
    if (!result) throw new Error('Authentication result was empty.');
    const next = {
      access_token: result.AccessToken || result.access_token || existing.access_token || '',
      id_token: result.IdToken || result.id_token || existing.id_token || '',
      refresh_token: result.RefreshToken || result.refresh_token || existing.refresh_token || '',
      token_type: result.TokenType || result.token_type || existing.token_type || 'Bearer',
      expires_in: Number(result.ExpiresIn || result.expires_in || existing.expires_in || 3600),
      issued_at: Date.now()
    };
    setTokens(next, reason);
    return next;
  }

  async function refreshTokens() {
    if (refreshPromise) return refreshPromise;
    const current = getTokens();
    if (!current.refresh_token) throw new Error('Please sign in again.');
    refreshPromise = (async () => {
      try {
        const data = await cognitoJsonRequest('AWSCognitoIdentityProviderService.InitiateAuth', {
          AuthFlow: 'REFRESH_TOKEN_AUTH',
          ClientId: getCfg().clientId,
          AuthParameters: {
            REFRESH_TOKEN: current.refresh_token
          }
        });
        return normaliseAuthResult(data.AuthenticationResult || {}, current, 'refreshed');
      } catch (err) {
        clearTokens('expired');
        throw err;
      } finally {
        refreshPromise = null;
      }
    })();
    return refreshPromise;
  }

  async function ensureFreshTokens() {
    const current = getTokens();
    if (current.access_token && !isExpired(current.access_token)) return current;
    if (current.refresh_token) {
      try {
        return await refreshTokens();
      } catch {
        return {};
      }
    }
    return current;
  }

  async function getValidAccessToken() {
    const tokens = await ensureFreshTokens();
    return tokens.access_token || '';
  }

  async function handleRedirect() {
    await ensureFreshTokens();
  }

  async function signIn(username, password) {
    const trimmedUsername = String(username || '').trim().toLowerCase();
    const valuePassword = String(password || '');
    if (!trimmedUsername || !valuePassword) throw new Error('Enter your email address and password.');
    const data = await cognitoJsonRequest('AWSCognitoIdentityProviderService.InitiateAuth', {
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: getCfg().clientId,
      AuthParameters: {
        USERNAME: trimmedUsername,
        PASSWORD: valuePassword
      }
    });
    if (data.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
      return {
        challenge: 'NEW_PASSWORD_REQUIRED',
        challengeName: 'NEW_PASSWORD_REQUIRED',
        username: trimmedUsername,
        session: data.Session || ''
      };
    }
    if (!data.AuthenticationResult) throw new Error('Sign-in did not return tokens.');
    normaliseAuthResult(data.AuthenticationResult, {}, 'signed_in');
    return { authenticated: true };
  }

  async function completeNewPassword(username, newPassword, session) {
    const trimmedUsername = String(username || '').trim().toLowerCase();
    const valuePassword = String(newPassword || '');
    if (!trimmedUsername || !valuePassword || !session) throw new Error('Missing password-reset challenge details.');
    const data = await cognitoJsonRequest('AWSCognitoIdentityProviderService.RespondToAuthChallenge', {
      ClientId: getCfg().clientId,
      ChallengeName: 'NEW_PASSWORD_REQUIRED',
      Session: session,
      ChallengeResponses: {
        USERNAME: trimmedUsername,
        NEW_PASSWORD: valuePassword
      }
    });
    if (!data.AuthenticationResult) throw new Error('Could not complete the password update challenge.');
    normaliseAuthResult(data.AuthenticationResult, {}, 'signed_in');
    return { authenticated: true };
  }


  async function forgotPassword(username) {
    const trimmedUsername = String(username || '').trim().toLowerCase();
    if (!trimmedUsername) throw new Error('Enter your member email address.');
    await cognitoJsonRequest('AWSCognitoIdentityProviderService.ForgotPassword', {
      ClientId: getCfg().clientId,
      Username: trimmedUsername
    });
    return { started: true };
  }

  async function confirmForgotPassword(username, code, newPassword) {
    const trimmedUsername = String(username || '').trim().toLowerCase();
    const confirmationCode = String(code || '').trim();
    const nextPassword = String(newPassword || '');
    if (!trimmedUsername || !confirmationCode || !nextPassword) throw new Error('Missing password reset details.');
    await cognitoJsonRequest('AWSCognitoIdentityProviderService.ConfirmForgotPassword', {
      ClientId: getCfg().clientId,
      Username: trimmedUsername,
      ConfirmationCode: confirmationCode,
      Password: nextPassword
    });
    return { completed: true };
  }

  async function logout() {
    const tokens = getTokens();
    clearTokens('logged_out');
    try {
      sessionStorage.removeItem(returnToKey);
    } catch {}
    try {
      if (tokens.access_token) {
        await cognitoJsonRequest('AWSCognitoIdentityProviderService.GlobalSignOut', {
          AccessToken: tokens.access_token
        });
      }
    } catch {}
    const homeUrl = new URL('index.html', window.location.origin).toString();
    const current = new URL(window.location.href).toString();
    if (homeUrl !== current) {
      window.location.assign(homeUrl);
      return;
    }
    window.location.reload();
  }

  function isAuthenticated() {
    const tokens = getTokens();
    return Boolean((tokens.access_token && !isExpired(tokens.access_token)) || tokens.refresh_token);
  }

  function getAccessToken() {
    return getTokens().access_token;
  }

  function getIdToken() {
    return getTokens().id_token;
  }

  function getAccessTokenExpiryMs() {
    return getTokenExpiryMs(getAccessToken());
  }

  function getClaims() {
    return parseJwt(getIdToken()) || parseJwt(getAccessToken()) || {};
  }

  function getGroups() {
    const claims = getClaims();
    const raw = claims['cognito:groups'] || claims.groups || [];

    if (Array.isArray(raw)) {
      return raw.map(x => String(x).trim()).filter(Boolean);
    }

    if (typeof raw === 'string') {
      let text = raw.trim();
      if (text.startsWith('[') && text.endsWith(']')) text = text.slice(1, -1).trim();
      if (!text) return [];
      return text.split(/[\s,]+/).map(x => x.trim()).filter(Boolean);
    }

    return [];
  }

  function hasAnyGroup(groups) {
    const wanted = new Set((groups || []).map(x => String(x).trim()).filter(Boolean));
    return getGroups().some(group => wanted.has(group));
  }

  function canAccessAdmin() {
    return isAuthenticated() && hasAnyGroup(['admins', 'committee', 'webmaster']);
  }

  function getUserLabel() {
    const payload = getClaims();
    return payload?.name || payload?.given_name || payload?.email || payload?.['cognito:username'] || 'member';
  }

  function getAvatarInitials() {
    const claims = getClaims();
    const source = claims.name || claims.given_name || claims.email || getUserLabel();
    const parts = String(source || '').trim().split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return String(source || 'M').slice(0, 2).toUpperCase();
  }

  const AVATAR_CACHE_KEY = 'lroc_profile_avatar_data_url';

  function getAvatarUrl() {
    const cached = (() => { try { return localStorage.getItem(AVATAR_CACHE_KEY) || ''; } catch { return ''; } })();
    if (/^data:image\//i.test(String(cached || ''))) return cached;
    const claims = getClaims();
    const value = claims.picture || claims.avatar_url || claims.profile_picture || claims['custom:avatar_url'] || claims['custom:profile_picture'] || '';
    const text = String(value || '').trim();
    return /^https?:\/\//i.test(text) || text.startsWith('/') || text.startsWith('assets/') ? text : '';
  }

  function cacheAvatarUrl(value) {
    try {
      const text = String(value || '').trim();
      if (text) localStorage.setItem(AVATAR_CACHE_KEY, text);
      else localStorage.removeItem(AVATAR_CACHE_KEY);
    } catch {}
  }

  async function redirectAfterLogin(defaultUrl = getMembersPageUrl()) {
    const returnTo = consumeReturnTo() || defaultUrl;
    const current = new URL(window.location.href).toString();
    const target = new URL(returnTo, window.location.origin).toString();
    if (target !== current) {
      window.location.replace(target);
      return { redirected: true, target };
    }
    return { redirected: false, target };
  }

  async function handleUnauthorized(returnToUrl) {
    clearTokens('expired');
    login(returnToUrl || window.location.href);
  }

  async function getProfile() {
    const token = await getValidAccessToken();
    if (!token) throw new Error('Please sign in again.');
    const response = await fetch(getCognitoApiBase(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.GetUser'
      },
      body: JSON.stringify({ AccessToken: token })
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch {}
    if (!response.ok) throw new Error(data.message || data.__type || 'Profile request failed.');
    const attrs = {};
    for (const item of (data.UserAttributes || [])) attrs[item.Name] = item.Value;
    const claims = getClaims();
    return {
      email: attrs.email || claims.email || '',
      name: attrs.name || claims.name || '',
      phone_number: attrs.phone_number || claims.phone_number || '',
      'custom:callsign': attrs['custom:callsign'] || claims['custom:callsign'] || ''
    };
  }

  async function updateProfile(profile) {
    const token = await getValidAccessToken();
    if (!token) throw new Error('Please sign in again.');
    const writable = [
      ['name', profile.name],
      ['phone_number', profile.phone_number],
      ['custom:callsign', profile['custom:callsign']]
    ];
    const UserAttributes = writable
      .filter(([, value]) => value !== undefined && value !== null)
      .map(([Name, Value]) => ({ Name, Value: String(Value).trim() }));
    const response = await fetch(getCognitoApiBase(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.UpdateUserAttributes'
      },
      body: JSON.stringify({ AccessToken: token, UserAttributes })
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch {}
    if (!response.ok) throw new Error(data.message || data.__type || 'Profile request failed.');
    return data;
  }

  window.lrocAuth = {
    login,
    handleRedirect,
    logout,
    signIn,
    completeNewPassword,
    redirectAfterLogin,
    handleUnauthorized,
    peekReturnTo,
    getMembersPageUrl,
    isAuthenticated,
    getAccessToken,
    getValidAccessToken,
    refreshSession: refreshTokens,
    getIdToken,
    getAccessTokenExpiryMs,
    getClaims,
    getGroups,
    hasAnyGroup,
    canAccessAdmin,
    getUserLabel,
    getAvatarInitials,
    getAvatarUrl,
    cacheAvatarUrl,
    getProfile,
    updateProfile,
    clearTokens
  };
})();
