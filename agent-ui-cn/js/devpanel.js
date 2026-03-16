// Dev Panel — raw WebSocket traffic viewer
// Self-initializing module: creates DOM, binds events on import

import { on } from './state.js';

const STORAGE_KEY = 'devpanel:open';
const HEIGHT_KEY = 'devpanel:height';
const MAX_ENTRIES = 2000;

let entries = [];
let autoScroll = true;
let filterType = 'all'; // 'all' | 'sent' | 'received' | 'status'
let lastTextDeltaEl = null;
let lastTextDeltaCount = 0;

// ===== DOM Setup =====

const panel = document.createElement('div');
panel.id = 'dev-panel';
panel.className = 'dev-panel collapsed';
panel.innerHTML = `
  <div class="dev-drag-handle"></div>
  <div class="dev-toolbar">
    <span class="dev-toolbar-title">WebSocket 流量</span>
    <div class="dev-toolbar-controls">
      <select id="dev-filter" title="按类型筛选">
        <option value="all">全部</option>
        <option value="sent">已发送</option>
        <option value="received">已接收</option>
        <option value="llm">LLM 追踪</option>
        <option value="status">状态</option>
      </select>
      <label class="dev-autoscroll-label">
        <input type="checkbox" id="dev-autoscroll" checked> 自动滚动
      </label>
      <button id="dev-clear" title="清除日志">清除</button>
    </div>
  </div>
  <div id="dev-log" class="dev-log"></div>
`;
document.body.appendChild(panel);

// Refs
const logEl = panel.querySelector('#dev-log');
const filterEl = panel.querySelector('#dev-filter');
const autoscrollEl = panel.querySelector('#dev-autoscroll');
const clearBtn = panel.querySelector('#dev-clear');
const dragHandle = panel.querySelector('.dev-drag-handle');

// ===== Toggle Button (injected into chat header) =====

const toggleBtn = document.createElement('button');
toggleBtn.id = 'dev-toggle';
toggleBtn.className = 'dev-toggle-btn';
toggleBtn.textContent = '开发';
toggleBtn.title = '切换开发面板';

// Insert into header-right, before existing children
const headerRight = document.querySelector('.header-right');
if (headerRight) {
  headerRight.insertBefore(toggleBtn, headerRight.firstChild);
}

// ===== State Persistence =====

function isOpen() {
  return localStorage.getItem(STORAGE_KEY) === '1';
}

function setOpen(open) {
  localStorage.setItem(STORAGE_KEY, open ? '1' : '0');
  panel.classList.toggle('collapsed', !open);
  toggleBtn.classList.toggle('active', open);
}

// Restore saved height
const savedHeight = localStorage.getItem(HEIGHT_KEY);
if (savedHeight) {
  panel.style.height = savedHeight;
}

// Init open/closed state
setOpen(isOpen());

// ===== Event Handlers =====

toggleBtn.addEventListener('click', () => setOpen(!isOpen()));

clearBtn.addEventListener('click', () => {
  entries = [];
  logEl.innerHTML = '';
  lastTextDeltaEl = null;
  lastTextDeltaCount = 0;
});

filterEl.addEventListener('change', () => {
  filterType = filterEl.value;
  rerenderLog();
});

autoscrollEl.addEventListener('change', () => {
  autoScroll = autoscrollEl.checked;
  if (autoScroll) scrollToBottom();
});

// ===== Drag Resize =====

let isDragging = false;
let startY, startHeight;

dragHandle.addEventListener('mousedown', (e) => {
  isDragging = true;
  startY = e.clientY;
  startHeight = panel.offsetHeight;
  document.body.style.cursor = 'ns-resize';
  document.body.style.userSelect = 'none';
  e.preventDefault();
});

document.addEventListener('mousemove', (e) => {
  if (!isDragging) return;
  const delta = startY - e.clientY;
  const newHeight = Math.max(120, Math.min(window.innerHeight * 0.85, startHeight + delta));
  panel.style.height = newHeight + 'px';
});

document.addEventListener('mouseup', () => {
  if (!isDragging) return;
  isDragging = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  localStorage.setItem(HEIGHT_KEY, panel.style.height);
});

// ===== Log Rendering =====

function timestamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const ms = String(d.getMilliseconds()).padStart(3, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${ms}`;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function prettyJson(raw) {
  try {
    const obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(raw);
  }
}

function extractEventType(raw) {
  try {
    const obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return obj.type || '?';
  } catch {
    return '?';
  }
}

function truncatePreview(raw, maxLen = 120) {
  const oneLine = raw.replace(/\s+/g, ' ').trim();
  return oneLine.length > maxLen ? oneLine.slice(0, maxLen) + '...' : oneLine;
}

function llmPreview(entry) {
  try {
    const obj = typeof entry.raw === 'string' ? JSON.parse(entry.raw) : entry.raw;
    if (obj.type === 'llm_request') {
      const tools = obj.tool_count != null ? `${obj.tool_count} tools` : '';
      return `#${obj.seq} ${obj.model} | ${obj.message_count} msgs | ${tools} | max_tokens=${obj.max_tokens}`;
    }
    if (obj.type === 'llm_response') {
      const u = obj.usage || {};
      const calls = (obj.tool_calls || []).map(tc => tc.name).join(', ');
      return `#${obj.seq} ${obj.done ? 'done' : 'tool_use'} | ${u.input_tokens}in/${u.output_tokens}out${calls ? ' | ' + calls : ''}`;
    }
  } catch { /* fall through */ }
  return null;
}

function createEntryEl(entry) {
  const el = document.createElement('div');
  el.className = `dev-entry dev-${entry.dir}`;
  el.dataset.dir = entry.dir;

  const arrows = { sent: '&gt;&gt;&gt;', received: '&lt;&lt;&lt;', llm: '&loz;&loz;&loz;', status: '---' };
  const arrow = arrows[entry.dir] || '---';

  const badge = entry.eventType ? `<span class="dev-badge">${escapeHtml(entry.eventType)}</span>` : '';
  const countBadge = entry.coalesceCount > 1
    ? `<span class="dev-coalesce-count">&times;${entry.coalesceCount}</span>` : '';

  const preview = (entry.dir === 'llm' && llmPreview(entry)) || truncatePreview(entry.raw);

  el.innerHTML = `
    <div class="dev-entry-header">
      <span class="dev-ts">${entry.ts}</span>
      <span class="dev-arrow dev-arrow-${entry.dir}">${arrow}</span>
      ${badge}${countBadge}
      <span class="dev-preview">${escapeHtml(preview)}</span>
    </div>
    <div class="dev-entry-body">
      <pre>${escapeHtml(prettyJson(entry.raw))}</pre>
    </div>
  `;

  el.querySelector('.dev-entry-header').addEventListener('click', () => {
    el.classList.toggle('expanded');
  });

  return el;
}

function addEntry(dir, raw) {
  const eventType = extractEventType(raw);

  // Re-tag LLM trace events from 'received' to 'llm' for filtering
  if (dir === 'received' && (eventType === 'llm_request' || eventType === 'llm_response')) {
    dir = 'llm';
  }

  // Coalesce consecutive text_delta received events
  if (dir === 'received' && eventType === 'text_delta' && lastTextDeltaEl) {
    lastTextDeltaCount++;
    const lastEntry = entries[entries.length - 1];
    lastEntry.raw = raw;
    lastEntry.coalesceCount = lastTextDeltaCount;
    lastEntry.ts = timestamp();

    // Update existing DOM element in-place
    const countSpan = lastTextDeltaEl.querySelector('.dev-coalesce-count');
    if (countSpan) {
      countSpan.textContent = `\u00d7${lastTextDeltaCount}`;
    } else {
      const badge = lastTextDeltaEl.querySelector('.dev-badge');
      if (badge) {
        const span = document.createElement('span');
        span.className = 'dev-coalesce-count';
        span.textContent = `\u00d7${lastTextDeltaCount}`;
        badge.after(span);
      }
    }
    // Update preview + body with latest data
    const preview = lastTextDeltaEl.querySelector('.dev-preview');
    if (preview) preview.textContent = truncatePreview(raw);
    const pre = lastTextDeltaEl.querySelector('pre');
    if (pre) pre.textContent = prettyJson(raw);
    const tsEl = lastTextDeltaEl.querySelector('.dev-ts');
    if (tsEl) tsEl.textContent = timestamp();

    if (autoScroll) scrollToBottom();
    return;
  }

  // Reset text_delta coalescing
  if (dir !== 'received' || eventType !== 'text_delta') {
    lastTextDeltaEl = null;
    lastTextDeltaCount = 0;
  }

  const entry = { ts: timestamp(), dir, raw, eventType, coalesceCount: 1 };
  entries.push(entry);

  // Cap entries
  if (entries.length > MAX_ENTRIES) {
    entries.shift();
    if (logEl.firstChild) logEl.removeChild(logEl.firstChild);
  }

  const el = createEntryEl(entry);

  // Track for coalescing
  if (dir === 'received' && eventType === 'text_delta') {
    lastTextDeltaEl = el;
    lastTextDeltaCount = 1;
  }

  // Respect filter
  if (filterType !== 'all' && entry.dir !== filterType) {
    el.style.display = 'none';
  }

  logEl.appendChild(el);
  if (autoScroll) scrollToBottom();
}

function addStatus(info) {
  const raw = JSON.stringify(info);
  addEntry('status', raw);
}

function rerenderLog() {
  for (const el of logEl.children) {
    const dir = el.dataset.dir;
    el.style.display = (filterType === 'all' || dir === filterType) ? '' : 'none';
  }
}

function scrollToBottom() {
  logEl.scrollTop = logEl.scrollHeight;
}

// ===== Event Bus Subscriptions =====

on('dev:sent', (raw) => addEntry('sent', raw));
on('dev:received', (raw) => addEntry('received', raw));
on('dev:status', (info) => addStatus(info));
