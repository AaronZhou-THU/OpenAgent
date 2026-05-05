import { renderMarkdown } from './markdown.js';
import { state } from './state.js';

const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');

// Track current streaming state
let currentAssistantGroup = null;
let currentTextBlock = null;
let currentThinkingBlock = null;
let currentThinkingText = '';
let textBuffer = '';
let renderScheduled = false;

// Inline thinking indicator element
let thinkingEl = null;

// Re-show indicator when text stream goes quiet
let staleStreamTimer = null;
const STALE_STREAM_MS = 1500;

// ===== Inline thinking indicator =====

const TOOL_ACTIVITY_MAP = {
  bash: 'Running a command...',
  execute_command: 'Running a command...',
  read_file: 'Reading files...',
  read: 'Reading files...',
  write_file: 'Writing code...',
  edit_file: 'Writing code...',
  write: 'Writing code...',
  edit: 'Writing code...',
  search: 'Searching...',
  grep: 'Searching files...',
  glob: 'Searching files...',
  task: 'Researching...',
  think: 'Thinking...',
  web_search: 'Searching the web...',
  web_fetch: 'Fetching a page...',
};

function getActivityText(toolName) {
  if (!toolName) return 'Working...';
  const lower = toolName.toLowerCase();
  return TOOL_ACTIVITY_MAP[lower] || 'Working...';
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

    const title = conv.title || 'New conversation';
    const date = new Date(conv.created_at).toLocaleDateString();

    item.innerHTML = `
      <div class="conv-info">
        <div class="conv-title">${escapeHtml(title)}</div>
        <div class="conv-meta">${date}</div>
      </div>
      <button class="delete-btn" title="Delete">&times;</button>
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

  document.getElementById('chat-title').textContent = conversation.title || 'New conversation';

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

  // Collect text and provider thinking blocks (skip tool_use)
  let fullText = '';
  const thinkingBlocks = [];
  for (const block of blocks) {
    if (block.type === 'text' && block.text?.trim()) {
      fullText += (fullText ? '\n\n' : '') + block.text;
    } else if (block.type === 'thinking') {
      const thinking = block.thinking || block.text || '';
      if (thinking.trim()) thinkingBlocks.push(thinking);
    }
  }

  if (!fullText.trim() && thinkingBlocks.length === 0) return;

  const group = document.createElement('div');
  group.className = 'message-group assistant';
  for (const thinking of thinkingBlocks) {
    group.appendChild(createThinkingBlock(thinking));
  }
  if (!fullText.trim()) {
    messagesEl.appendChild(group);
    return;
  }
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
  ensureThinkingIndicator('Thinking...');
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
      ensureThinkingIndicator('Thinking...');
    }
  }, STALE_STREAM_MS);
}

export function appendThinking(content, effort = '') {
  removeThinkingIndicator();
  const replyBlock = currentTextBlock;
  finalizeTextBlock();

  if (!currentAssistantGroup) {
    startAssistantMessage();
    removeThinkingIndicator();
  }

  currentThinkingText = content;
  if (!currentThinkingBlock) {
    currentThinkingBlock = createThinkingBlock(content, effort);
    insertThinkingBlock(currentThinkingBlock, replyBlock);
  } else {
    updateThinkingBlock(currentThinkingBlock, currentThinkingText);
  }
  scrollToBottom();
}

export function appendThinkingDelta(content, effort = '') {
  removeThinkingIndicator();

  if (!currentAssistantGroup) {
    startAssistantMessage();
    removeThinkingIndicator();
  }

  currentThinkingText += content;
  if (!currentThinkingBlock) {
    currentThinkingBlock = createThinkingBlock(currentThinkingText, effort);
    insertThinkingBlock(currentThinkingBlock, currentTextBlock);
  } else {
    updateThinkingBlock(currentThinkingBlock, currentThinkingText);
  }
  scrollToBottom();
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
  currentThinkingBlock = null;
  currentThinkingText = '';
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
  notice.textContent = 'Interrupted';
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
    <div class="approval-dialog-title">Permission needed</div>
    <div class="approval-dialog-text">The assistant wants to perform an action.</div>
    <div class="approval-dialog-actions" id="${blockId}-actions">
      <button class="approval-btn allow" data-decision="approve">Allow</button>
      <button class="approval-btn skip" data-decision="deny">Skip</button>
    </div>
  `;

  messagesEl.appendChild(dialog);
  scrollToBottom();
  return blockId;
}

export function resolveApprovalBlock(blockId, decision) {
  const actions = document.getElementById(`${blockId}-actions`);
  if (!actions) return;

  const label = decision === 'approve' || decision === 'auto_approve' ? 'Allowed' : 'Skipped';
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
      <span class="plan-summary-label">Plan approved</span>
      <button class="plan-summary-toggle" aria-label="Toggle plan details">&#9660;</button>
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
  card.innerHTML = '<div class="file-card-header">Files created</div>';

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
    <span>Something went wrong. ${escapeHtml(message || '')}</span>
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
  currentThinkingBlock = null;
  currentThinkingText = '';
  textBuffer = '';
  thinkingEl = null;
}

function insertThinkingBlock(thinkingBlock, replyBlock = null) {
  const firstReplyBlock = replyBlock?.parentNode === currentAssistantGroup
    ? replyBlock
    : currentAssistantGroup.querySelector('.assistant-content, .message-content');
  if (firstReplyBlock) {
    currentAssistantGroup.insertBefore(thinkingBlock, firstReplyBlock);
  } else {
    currentAssistantGroup.appendChild(thinkingBlock);
  }
}

function updateThinkingBlock(block, content) {
  const pre = block.querySelector('pre');
  if (pre) pre.textContent = content;
}

function createThinkingBlock(content, effort = '') {
  const block = document.createElement('div');
  block.className = 'provider-thinking-block';
  const label = effort ? `Thinking · ${effort}` : 'Thinking';
  block.innerHTML = `
    <button class="provider-thinking-header" type="button">
      <span>${escapeHtml(label)}</span>
      <span class="provider-thinking-toggle">&#9654;</span>
    </button>
    <div class="provider-thinking-body">
      <pre>${escapeHtml(content)}</pre>
    </div>
  `;
  block.querySelector('.provider-thinking-header').addEventListener('click', () => {
    block.querySelector('.provider-thinking-body').classList.toggle('open');
    block.querySelector('.provider-thinking-toggle').classList.toggle('open');
  });
  return block;
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
