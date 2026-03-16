import { API_BASE_URL } from './config.js';
import { getToken } from './auth.js';
import { emit } from './state.js';

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };

  // Attach Google auth token if available
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    ...options,
  });

  if (res.status === 401) {
    emit('auth:expired');
    throw new Error('Authentication required');
  }

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
export function createChat(systemPrompt = null, preset = null, { enableTeams = false, enableTracing = false, enableApproval = false, enablePlanMode = false } = {}) {
  const body = {};
  if (systemPrompt) body.system_prompt = systemPrompt;
  if (preset) body.preset = preset;
  if (enableTeams) body.enable_teams = true;
  if (enableTracing) body.enable_tracing = true;
  if (enableApproval) body.enable_approval = true;
  if (enablePlanMode) body.enable_plan_mode = true;
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// Presets
export function listPresets() {
  return request('/api/presets');
}

// Tools & Skills
export function listTools() {
  return request('/api/tools');
}

export function listSkills() {
  return request('/api/skills');
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
  const headers = {};
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE_URL}/api/workspace/upload${qs}`, {
    method: 'POST',
    headers,
    body: form,
  });
  if (res.status === 401) {
    emit('auth:expired');
    throw new Error('Authentication required');
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}
