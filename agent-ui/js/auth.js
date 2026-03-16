/**
 * Google Authentication module for agent-ui.
 *
 * Manages Google Sign-In via Google Identity Services (GIS).
 * Auth is optional — if the backend reports auth disabled, the app
 * works without login (fully backward compatible).
 */

import { API_BASE_URL } from './config.js';
import { emit } from './state.js';

let _credential = null;
let _user = null;
let _authEnabled = false;
let _clientId = null;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Check with the backend whether auth is enabled, and if so,
 * load the GIS library and initialize sign-in.
 * Returns true if auth is enabled, false otherwise.
 */
export async function init() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/config`);
    const config = await res.json();
    _authEnabled = config.enabled;
    _clientId = config.google_client_id;
  } catch (err) {
    console.warn('Could not fetch auth config, assuming auth disabled:', err);
    _authEnabled = false;
    return false;
  }

  if (!_authEnabled) return false;

  // Restore credential from localStorage
  _credential = localStorage.getItem('google_credential');
  if (_credential) {
    _user = _decodeUser(_credential);
  }

  // Load Google Identity Services script
  await _loadGisScript();

  // Initialize GIS
  google.accounts.id.initialize({
    client_id: _clientId,
    callback: _handleCredentialResponse,
    auto_select: true,
  });

  return true;
}

/** Returns the current Google ID token, or null. */
export function getToken() {
  return _credential || localStorage.getItem('google_credential');
}

/** Returns decoded user info {name, email, picture}, or null. */
export function getUser() {
  if (_user) return _user;
  const token = getToken();
  if (!token) return null;
  _user = _decodeUser(token);
  return _user;
}

/** Whether auth is required (backend has it enabled). */
export function isAuthEnabled() {
  return _authEnabled;
}

/** Whether the user is currently signed in. */
export function isAuthenticated() {
  return !!getToken();
}

/** Render the Google Sign-In button into the given container element. */
export function renderSignInButton(container) {
  if (!_authEnabled || typeof google === 'undefined') return;
  google.accounts.id.renderButton(container, {
    theme: 'filled_blue',
    size: 'large',
    shape: 'pill',
    text: 'signin_with',
  });
}

/** Show the One Tap prompt (for returning users). */
export function prompt() {
  if (!_authEnabled || typeof google === 'undefined') return;
  google.accounts.id.prompt();
}

/** Sign out and clear stored credentials. */
export function signOut() {
  if (typeof google !== 'undefined') {
    google.accounts.id.disableAutoSelect();
  }
  _credential = null;
  _user = null;
  localStorage.removeItem('google_credential');
  emit('auth:changed', { authenticated: false, user: null });
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

function _handleCredentialResponse(response) {
  _credential = response.credential;
  localStorage.setItem('google_credential', _credential);
  _user = _decodeUser(_credential);
  emit('auth:changed', { authenticated: true, user: _user });
}

function _decodeUser(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return {
      name: payload.name,
      email: payload.email,
      picture: payload.picture,
    };
  } catch {
    return null;
  }
}

function _loadGisScript() {
  return new Promise((resolve, reject) => {
    if (typeof google !== 'undefined' && google.accounts) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error('Failed to load Google Identity Services'));
    document.head.appendChild(script);
  });
}
