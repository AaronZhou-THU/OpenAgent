import { API_BASE_URL } from './config.js';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// Health
export function getHealth() {
  return request('/health');
}

// Conversations
export function listConversations() {
  return request('/api/conversations');
}

export function getConversation(id) {
  return request(`/api/conversations/${id}`);
}

export function deleteConversation(id) {
  return request(`/api/conversations/${id}`, { method: 'DELETE' });
}

// Chat
export function createChat(systemPrompt = null, preset = null) {
  const body = {};
  if (systemPrompt) body.system_prompt = systemPrompt;
  if (preset) body.preset = preset;
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// Presets
export function listPresets() {
  return request('/api/presets');
}

// Files
export function fileUrl(convId, path) {
  return `${API_BASE_URL}/api/files/${convId}/${path}`;
}

// Workspace file browsing
export function listWorkspaceFiles() {
  return request('/api/workspace/files');
}

export function readWorkspaceFile(path) {
  return request(`/api/workspace/file/${path}`);
}

// Upload files to workspace
export async function uploadWorkspaceFiles(files, subdir = '') {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  const qs = subdir ? `?subdir=${encodeURIComponent(subdir)}` : '';
  const res = await fetch(`${API_BASE_URL}/api/workspace/upload${qs}`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}
