// API configuration — override via localStorage.setItem('API_BASE_URL', 'http://...')
function getDefaultApiBase() {
  if (typeof window === 'undefined' || !window.location) {
    return 'http://localhost:8000';
  }

  const { protocol, hostname, origin } = window.location;
  if (!/^https?:$/.test(protocol)) {
    return 'http://localhost:8000';
  }

  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000';
  }

  return origin;
}

const stored = localStorage.getItem('API_BASE_URL');
export const API_BASE_URL = stored || getDefaultApiBase();
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');
