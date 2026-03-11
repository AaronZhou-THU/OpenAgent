// API configuration — override via localStorage.setItem('API_BASE_URL', 'http://...')
const stored = localStorage.getItem('API_BASE_URL');
export const API_BASE_URL = stored || 'http://localhost:8000';
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');
