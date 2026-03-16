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
    reconnectAttempts = 0;
    emit('ws:connected');
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      emit('ws:event', data);
    } catch (err) {
      console.error('WebSocket parse error:', err, event.data);
    }
  };

  ws.onclose = (event) => {
    emit('ws:disconnected');

    // Auto-reconnect on abnormal close, up to MAX_RECONNECT_ATTEMPTS
    if (event.code !== 1000 && state.conversationId === conversationId
        && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      const delay = 1000 * reconnectAttempts;
      console.log(`Reconnecting WebSocket (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
      reconnectTimer = setTimeout(() => _doConnect(conversationId), delay);
    } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      emit('ws:reconnect_failed', {
        attempts: reconnectAttempts,
        message: `连接已断开，请刷新页面。`,
      });
    }
  };

  ws.onerror = (err) => {
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
  ws.send(payload);
  return true;
}

export function sendJson(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WebSocket not connected');
    return false;
  }
  const payload = JSON.stringify(obj);
  ws.send(payload);
  return true;
}

export function isConnected() {
  return ws && ws.readyState === WebSocket.OPEN;
}
