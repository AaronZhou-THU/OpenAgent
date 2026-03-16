import { renderMarkdown } from './markdown.js';
import { state } from './state.js';

const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');

// Track current streaming state
let currentAssistantGroup = null;
let currentTextBlock = null;
let textBuffer = '';
let renderScheduled = false;

// Inline thinking indicator element
let thinkingEl = null;

// Re-show indicator when text stream goes quiet
let staleStreamTimer = null;
const STALE_STREAM_MS = 1500;

// ===== Inline thinking indicator =====

const TOOL_ACTIVITY_MAP = {
  bash: '正在执行命令...',
  execute_command: '正在执行命令...',
  read_file: '正在读取文件...',
  read: '正在读取文件...',
  write_file: '正在编写代码...',
  edit_file: '正在编写代码...',
  write: '正在编写代码...',
  edit: '正在编写代码...',
  search: '正在搜索...',
  grep: '正在搜索文件...',
  glob: '正在搜索文件...',
  task: '正在研究...',
  think: '正在思考...',
  web_search: '正在搜索网络...',
  web_fetch: '正在获取页面...',
};

function getActivityText(toolName) {
  if (!toolName) return '正在处理...';
  const lower = toolName.toLowerCase();
  return TOOL_ACTIVITY_MAP[lower] || '正在处理...';
}

function createThinkingIndicator(text) {
  const el = document.createElement('div');
  el.className = 'thinking-indicator';
  el.innerHTML = `
    <span class="thinking-dot"></span>
    <span class="thinking-dot"></span>
    <span class="thinking-dot"></span>
    <span class="thinking-text">${escapeHtml(text)}</span>
  `;
  return el;
}

function ensureThinkingIndicator(text) {
  if (thinkingEl) {
    thinkingEl.querySelector('.thinking-text').textContent = text;
    // Re-attach inside assistant group if detached
    if (!thinkingEl.parentNode && currentAssistantGroup) {
      currentAssistantGroup.appendChild(thinkingEl);
      scrollToBottom();
    }
    return;
  }
  thinkingEl = createThinkingIndicator(text);
  if (currentAssistantGroup) {
    currentAssistantGroup.appendChild(thinkingEl);
  } else {
    messagesEl.appendChild(thinkingEl);
  }
  scrollToBottom();
}

function removeThinkingIndicator() {
  if (thinkingEl && thinkingEl.parentNode) {
    thinkingEl.parentNode.removeChild(thinkingEl);
  }
  thinkingEl = null;
}

export function showActivity(text) {
  state.activityText = text;
  ensureThinkingIndicator(text);
}

export function hideActivity() {
  state.activityText = null;
  removeThinkingIndicator();
}

export function showActivityForTool(toolName) {
  showActivity(getActivityText(toolName));
}

// ===== Conversation list =====

export function renderConversationList() {
  const listEl = document.getElementById('conversation-list');
  listEl.innerHTML = '';

  for (const conv of state.conversations) {
    const item = document.createElement('div');
    item.className = `conversation-item${conv.id === state.conversationId ? ' active' : ''}`;
    item.dataset.id = conv.id;

    const title = conv.title || '新对话';
    const date = new Date(conv.created_at).toLocaleDateString();

    item.innerHTML = `
      <div class="conv-info">
        <div class="conv-title">${escapeHtml(title)}</div>
        <div class="conv-meta">${date}</div>
      </div>
      <button class="delete-btn" title="删除">&times;</button>
    `;

    item.querySelector('.conv-info').addEventListener('click', () => {
      import('./state.js').then(({ emit }) => emit('conversation:select', conv.id));
    });

    item.querySelector('.delete-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      import('./state.js').then(({ emit }) => emit('conversation:delete', conv.id));
    });

    listEl.appendChild(item);
  }
}

// ===== History rendering =====

export function renderHistory(conversation) {
  clearMessages();
  welcomeEl.style.display = 'none';

  document.getElementById('chat-title').textContent = conversation.title || '新对话';

  const messages = conversation.messages || [];

  for (const msg of messages) {
    if (msg.role === 'user') {
      // Skip tool_result user messages
      if (Array.isArray(msg.content) && msg.content.some(b => b.type === 'tool_result')) {
        continue;
      }
      renderUserMessageFromHistory(msg.content);
    } else if (msg.role === 'assistant') {
      renderAssistantFromHistory(msg.content);
    }
  }

  scrollToBottom();
}

function renderUserMessageFromHistory(content) {
  let text;
  if (typeof content === 'string') {
    text = content;
  } else if (Array.isArray(content)) {
    const textBlocks = content.filter(b => typeof b === 'string' || b.type === 'text');
    text = textBlocks.map(b => typeof b === 'string' ? b : b.text).join('\n');
    if (!text) return;
  } else {
    text = String(content);
  }

  const group = document.createElement('div');
  group.className = 'message-group user';
  const bubble = document.createElement('div');
  bubble.className = 'user-bubble';
  bubble.textContent = text;
  group.appendChild(bubble);
  messagesEl.appendChild(group);
}

function renderAssistantFromHistory(content) {
  if (!content) return;

  const blocks = Array.isArray(content) ? content : [{ type: 'text', text: String(content) }];

  // Collect only text blocks (skip tool_use)
  let fullText = '';
  for (const block of blocks) {
    if (block.type === 'text' && block.text?.trim()) {
      fullText += (fullText ? '\n\n' : '') + block.text;
    }
  }

  if (!fullText.trim()) return;

  const group = document.createElement('div');
  group.className = 'message-group assistant';
  const contentEl = document.createElement('div');
  contentEl.className = 'assistant-content';
  contentEl.innerHTML = renderMarkdown(fullText);
  group.appendChild(contentEl);
  messagesEl.appendChild(group);
}

// ===== Streaming rendering =====

export function startAssistantMessage() {
  welcomeEl.style.display = 'none';
  currentAssistantGroup = document.createElement('div');
  currentAssistantGroup.className = 'message-group assistant';
  messagesEl.appendChild(currentAssistantGroup);
  textBuffer = '';
  currentTextBlock = null;
  // Show inline thinking indicator immediately for instant feedback
  ensureThinkingIndicator('正在思考...');
}

export function appendTextDelta(text) {
  // Remove inline thinking indicator — text replaces it
  removeThinkingIndicator();
  state.activityText = null;

  textBuffer += text;

  if (!currentTextBlock) {
    currentTextBlock = document.createElement('div');
    currentTextBlock.className = 'assistant-content streaming-cursor';
    if (currentAssistantGroup) {
      currentAssistantGroup.appendChild(currentTextBlock);
    }
  }

  if (!renderScheduled) {
    renderScheduled = true;
    requestAnimationFrame(flushTextBuffer);
  }

  // Reset stale-stream timer: if no text arrives for STALE_STREAM_MS,
  // re-show the thinking indicator so the user knows we're still working
  clearTimeout(staleStreamTimer);
  staleStreamTimer = setTimeout(() => {
    if (currentAssistantGroup && !thinkingEl) {
      ensureThinkingIndicator('正在思考...');
    }
  }, STALE_STREAM_MS);
}

function flushTextBuffer() {
  renderScheduled = false;
  if (currentTextBlock && textBuffer) {
    currentTextBlock.innerHTML = renderMarkdown(textBuffer);
    scrollToBottom();
  }
}

export function finalizeTextBlock() {
  clearTimeout(staleStreamTimer);
  if (currentTextBlock) {
    currentTextBlock.classList.remove('streaming-cursor');
    if (textBuffer) {
      currentTextBlock.innerHTML = renderMarkdown(textBuffer);
    }
    currentTextBlock = null;
  }
  textBuffer = '';
}

export function finishAssistantMessage() {
  clearTimeout(staleStreamTimer);
  finalizeTextBlock();
  removeThinkingIndicator();
  state.activityText = null;
  currentAssistantGroup = null;
}

// ===== User message (live) =====

export function renderUserMessage(text) {
  welcomeEl.style.display = 'none';
  const group = document.createElement('div');
  group.className = 'message-group user';
  const bubble = document.createElement('div');
  bubble.className = 'user-bubble';
  bubble.textContent = text;
  group.appendChild(bubble);
  messagesEl.appendChild(group);
  scrollToBottom();
}

// ===== Interrupt notice =====

export function renderInterruptNotice() {
  const notice = document.createElement('div');
  notice.className = 'interrupt-notice';
  notice.textContent = '已中断';
  messagesEl.appendChild(notice);
  scrollToBottom();
}

// ===== Tool approval =====

let approvalCounter = 0;

export function showToolApproval() {
  finalizeTextBlock();

  const blockId = `approval-${++approvalCounter}`;
  const dialog = document.createElement('div');
  dialog.className = 'approval-dialog';
  dialog.id = blockId;
  dialog.innerHTML = `
    <div class="approval-dialog-title">需要授权</div>
    <div class="approval-dialog-text">助手想要执行一个操作。</div>
    <div class="approval-dialog-actions" id="${blockId}-actions">
      <button class="approval-btn allow" data-decision="approve">允许</button>
      <button class="approval-btn skip" data-decision="deny">跳过</button>
    </div>
  `;

  messagesEl.appendChild(dialog);
  scrollToBottom();
  return blockId;
}

export function resolveApprovalBlock(blockId, decision) {
  const actions = document.getElementById(`${blockId}-actions`);
  if (!actions) return;

  const label = decision === 'approve' || decision === 'auto_approve' ? '已允许' : '已跳过';
  actions.innerHTML = `<span class="approval-resolved">${label}</span>`;
}

// ===== Plan overlay =====

export function showPlanOverlay(planText) {
  const overlay = document.getElementById('plan-overlay');
  const content = document.getElementById('plan-overlay-content');
  const feedback = document.getElementById('plan-overlay-feedback');
  if (!overlay || !content) return;

  content.innerHTML = renderMarkdown(planText);
  feedback.classList.add('hidden');
  overlay.classList.remove('hidden');
}

export function hidePlanOverlay() {
  const overlay = document.getElementById('plan-overlay');
  if (!overlay) return;
  overlay.classList.add('hidden');
  // Reset feedback area
  const feedback = document.getElementById('plan-overlay-feedback');
  if (feedback) feedback.classList.add('hidden');
  const input = document.getElementById('plan-change-input');
  if (input) input.value = '';
}

export function renderPlanSummaryCard(planText) {
  const card = document.createElement('div');
  card.className = 'plan-summary-card';
  card.innerHTML = `
    <div class="plan-summary-header">
      <span class="plan-summary-check">&#10003;</span>
      <span class="plan-summary-label">方案已批准</span>
      <button class="plan-summary-toggle" aria-label="展开/收起方案详情">&#9660;</button>
    </div>
    <div class="plan-summary-body">${renderMarkdown(planText)}</div>
  `;

  const toggle = card.querySelector('.plan-summary-toggle');
  const body = card.querySelector('.plan-summary-body');
  toggle.addEventListener('click', () => {
    body.classList.toggle('open');
    toggle.textContent = body.classList.contains('open') ? '\u25B2' : '\u25BC';
  });

  messagesEl.appendChild(card);
  scrollToBottom();
}

// ===== File cards =====

export function renderFileCards(files, convId) {
  const { fileUrl } = getApiModule();

  const card = document.createElement('div');
  card.className = 'file-card';
  card.innerHTML = '<div class="file-card-header">已创建文件</div>';

  const list = document.createElement('div');
  list.className = 'file-card-list';

  for (const f of files) {
    const size = formatFileSize(f.size);
    const url = fileUrl(convId, f.path);
    const item = document.createElement('a');
    item.className = 'file-card-item';
    item.href = url;
    item.download = f.name;
    item.target = '_blank';
    item.rel = 'noopener';
    item.innerHTML = `
      <span class="file-icon">&#128196;</span>
      <span class="file-info">
        <span class="file-name">${escapeHtml(f.name)}</span>
        <span class="file-size">${escapeHtml(size)}</span>
      </span>
      <span class="file-download-icon">&#8595;</span>
    `;
    list.appendChild(item);
  }

  card.appendChild(list);
  messagesEl.appendChild(card);
  scrollToBottom();
}

// ===== Error card =====

export function renderError(message) {
  const card = document.createElement('div');
  card.className = 'error-card';
  card.innerHTML = `
    <span class="error-card-icon">&#9888;</span>
    <span>出错了。${escapeHtml(message || '')}</span>
  `;
  messagesEl.appendChild(card);
  scrollToBottom();
}

// ===== Connection status =====

export function setConnectionStatus(status) {
  const el = document.getElementById('connection-status');
  el.className = `status-indicator ${status}`;
  el.title = status.charAt(0).toUpperCase() + status.slice(1);
}

// ===== Input state =====

export function setInputEnabled(enabled) {
  const input = document.getElementById('message-input');
  const btn = document.getElementById('send-btn');
  input.disabled = !enabled;
  btn.disabled = !enabled;
  if (enabled) input.focus();
}

// ===== Clear / scroll =====

export function clearMessages() {
  clearTimeout(staleStreamTimer);
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  currentAssistantGroup = null;
  currentTextBlock = null;
  textBuffer = '';
  thinkingEl = null;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ===== Floating todo panel =====

export function renderTodoPanel(todos) {
  const panel = document.getElementById('todo-panel');
  const listEl = document.getElementById('todo-list');
  const headerProgress = document.getElementById('todo-progress');
  const barFill = document.getElementById('todo-bar-fill');

  if (!todos || todos.length === 0) {
    panel.classList.add('hidden');
    return;
  }

  // Count stats
  const done = todos.filter(t => t.status === 'completed').length;
  const total = todos.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  headerProgress.textContent = `${done}/${total}`;
  barFill.style.width = `${pct}%`;

  // Build items
  listEl.innerHTML = '';
  for (const todo of todos) {
    const item = document.createElement('div');
    item.className = `todo-item ${todo.status}`;
    item.innerHTML = `
      <div class="todo-status ${todo.status}"></div>
      <div>
        <div class="todo-content">${escapeHtml(todo.content)}</div>
        ${todo.status === 'in_progress' && todo.activeForm
          ? `<div class="todo-active-form">${escapeHtml(todo.activeForm)}</div>`
          : ''}
      </div>
    `;
    listEl.appendChild(item);
  }

  panel.classList.remove('hidden');
}

// ===== Helpers =====

function escapeHtml(str) {
  if (typeof str !== 'string') str = String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Lazy import to avoid circular dependency
let _apiModule = null;
function getApiModule() {
  if (!_apiModule) {
    const origin = typeof window !== 'undefined' && window.location
      && /^https?:$/.test(window.location.protocol)
      ? window.location.origin
      : 'http://localhost:8000';
    const apiBase = localStorage.getItem('API_BASE_URL')
      || ((typeof window !== 'undefined' && window.location
        && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'))
        ? 'http://localhost:8000'
        : origin);
    _apiModule = { fileUrl: (convId, path) => `${apiBase}/api/files/${convId}/${path}` };
  }
  return _apiModule;
}
