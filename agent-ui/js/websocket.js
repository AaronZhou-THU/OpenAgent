import { WS_BASE_URL } from './config.js';
import { state, emit } from './state.js';

let ws = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 3;

export function connect(conversationId) {
  disconnect(); // clean up any existing connection
  reconnectAttempts = 0;
  _doConnect(conversationId);
}

function _doConnect(conversationId) {
  emit('ws:connecting');
  const url = `${WS_BASE_URL}/api/chat/${conversationId}/ws`;
  ws = new WebSocket(url);

  ws.onopen = () => {
    reconnectAttempts = 0; // reset on successful connection
    emit('ws:connected');
    emit('dev:status', { state: 'connected', url });
  };

  ws.onmessage = (event) => {
    emit('dev:received', event.data);
    try {
      const data = JSON.parse(event.data);
      emit('ws:event', data);
    } catch (err) {
      console.error('WebSocket parse error:', err, event.data);
    }
  };

  ws.onclose = (event) => {
    emit('dev:status', { state: 'disconnected', code: event.code, reason: event.reason });
    emit('ws:disconnected');

    // Auto-reconnect on abnormal close, up to MAX_RECONNECT_ATTEMPTS
    if (event.code !== 1000 && state.conversationId === conversationId
        && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      const delay = 1000 * reconnectAttempts; // 1s, 2s, 3s backoff
      console.log(`Reconnecting WebSocket (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
      reconnectTimer = setTimeout(() => _doConnect(conversationId), delay);
    } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      emit('dev:status', { state: 'failed', message: 'Max reconnect attempts reached' });
      emit('ws:reconnect_failed', {
        attempts: reconnectAttempts,
        message: `Reconnection failed after ${MAX_RECONNECT_ATTEMPTS} attempts. Please refresh the page.`,
      });
    }
  };

  ws.onerror = (err) => {
    emit('dev:status', { state: 'error', message: 'WebSocket error' });
    console.error('WebSocket error:', err);
  };
}

export function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close(1000, 'switching conversation');
    ws = null;
  }
}

export function send(message) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WebSocket not connected');
    return false;
  }
  const payload = JSON.stringify({ type: 'message', content: message });
  emit('dev:sent', payload);
  ws.send(payload);
  return true;
}

export function sendJson(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WebSocket not connected');
    return false;
  }
  const payload = JSON.stringify(obj);
  emit('dev:sent', payload);
  ws.send(payload);
  return true;
}

export function isConnected() {
  return ws && ws.readyState === WebSocket.OPEN;
}
