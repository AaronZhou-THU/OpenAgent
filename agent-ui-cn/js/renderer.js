import { renderMarkdown } from './markdown.js';
import { state, emit } from './state.js';

const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');

// Track current streaming state
let currentAssistantGroup = null;
let currentTextBlock = null;
let textBuffer = '';
let renderScheduled = false;

// ===== Conversation list =====

export function renderConversationList() {
  const listEl = document.getElementById('conversation-list');
  listEl.innerHTML = '';

  for (const conv of state.conversations) {
    const item = document.createElement('div');
    item.className = `conversation-item${conv.id === state.conversationId ? ' active' : ''}`;
    item.dataset.id = conv.id;

    const title = conv.title || '无标题';
    const date = new Date(conv.created_at).toLocaleDateString();
    const count = conv.message_count ?? 0;

    item.innerHTML = `
      <div class="conv-info">
        <div class="conv-title">${escapeHtml(title)}</div>
        <div class="conv-meta">${date} &middot; ${count} 条消息</div>
      </div>
      <button class="delete-btn" title="删除">&times;</button>
    `;

    // Select conversation
    item.querySelector('.conv-info').addEventListener('click', () => {
      emit('conversation:select', conv.id);
    });

    // Delete conversation
    item.querySelector('.delete-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      emit('conversation:delete', conv.id);
    });

    listEl.appendChild(item);
  }
}

// ===== History rendering =====

export function renderHistory(conversation) {
  clearMessages();
  welcomeEl.style.display = 'none';

  document.getElementById('chat-title').textContent = conversation.title || '无标题';
  updateTokenDisplay(conversation.total_input_tokens || 0, conversation.total_output_tokens || 0);

  const messages = conversation.messages || [];

  for (const msg of messages) {
    if (msg.role === 'user') {
      renderUserMessage(msg.content);
    } else if (msg.role === 'assistant') {
      renderAssistantHistory(msg.content);
    }
  }

  scrollToBottom();
}

function renderUserMessage(content) {
  // content can be string or array of content blocks
  let text;
  if (typeof content === 'string') {
    text = content;
  } else if (Array.isArray(content)) {
    // Filter for text blocks (skip tool_result blocks)
    const textBlocks = content.filter(b => typeof b === 'string' || b.type === 'text');
    text = textBlocks.map(b => typeof b === 'string' ? b : b.text).join('\n');
    if (!text) return; // skip pure tool_result messages
  } else {
    text = String(content);
  }

  const group = createMessageGroup('user');
  const contentEl = document.createElement('div');
  contentEl.className = 'message-content user-text';
  contentEl.textContent = text;
  group.appendChild(contentEl);
  messagesEl.appendChild(group);
}

function renderAssistantHistory(content) {
  if (!content) return;

  const group = createMessageGroup('assistant');
  const blocks = Array.isArray(content) ? content : [{ type: 'text', text: String(content) }];

  // Build a map of tool_use_id -> result for correlation
  // Results come as user messages but we get the full conversation with all messages
  // We'll just render what we have in the assistant content

  for (const block of blocks) {
    if (block.type === 'text' && block.text?.trim()) {
      const textEl = document.createElement('div');
      textEl.className = 'message-content';
      textEl.innerHTML = renderMarkdown(block.text);
      group.appendChild(textEl);
    } else if (block.type === 'tool_use') {
      const toolEl = createToolBlock(block.name, block.input, 'tool-call');
      group.appendChild(toolEl);
    }
  }

  messagesEl.appendChild(group);

  // Now render tool results from the next user message (if any exist in history)
  // They appear as separate user messages with role=user, content=[{type: tool_result, ...}]
}

// Also render tool results that appear in user messages (history)
export function renderToolResultHistory(content) {
  if (!Array.isArray(content)) return;

  for (const block of content) {
    if (block.type !== 'tool_result') continue;

    // Find the last assistant group and append result
    const groups = messagesEl.querySelectorAll('.message-group.assistant');
    const lastGroup = groups[groups.length - 1];
    if (!lastGroup) continue;

    // Try to find the matching tool call to get the name
    const toolName = findToolNameById(lastGroup, block.tool_use_id) || 'tool';
    const resultEl = createToolBlock(toolName, block.content, 'tool-result');
    lastGroup.appendChild(resultEl);
  }
}

function findToolNameById(group, toolUseId) {
  // Tool call blocks store the ID in a data attribute
  const calls = group.querySelectorAll('.tool-block.tool-call');
  for (const call of calls) {
    if (call.dataset.toolUseId === toolUseId) {
      return call.dataset.toolName;
    }
  }
  return null;
}

// ===== Streaming rendering =====

export function startAssistantMessage() {
  welcomeEl.style.display = 'none';
  currentAssistantGroup = createMessageGroup('assistant');
  messagesEl.appendChild(currentAssistantGroup);
  textBuffer = '';
  currentTextBlock = null;
}

export function appendTextDelta(text) {
  textBuffer += text;

  if (!currentTextBlock) {
    currentTextBlock = document.createElement('div');
    currentTextBlock.className = 'message-content streaming-cursor';
    currentAssistantGroup.appendChild(currentTextBlock);
  }

  if (!renderScheduled) {
    renderScheduled = true;
    requestAnimationFrame(flushTextBuffer);
  }
}

function flushTextBuffer() {
  renderScheduled = false;
  if (currentTextBlock && textBuffer) {
    currentTextBlock.innerHTML = renderMarkdown(textBuffer);
    scrollToBottom();
  }
}

export function finalizeTextBlock() {
  if (currentTextBlock) {
    currentTextBlock.classList.remove('streaming-cursor');
    // Final render
    if (textBuffer) {
      currentTextBlock.innerHTML = renderMarkdown(textBuffer);
    }
    currentTextBlock = null;
  }
  textBuffer = '';
}

export function appendToolCall(toolName, input) {
  // Finalize any open text block first
  finalizeTextBlock();

  if (!currentAssistantGroup) {
    startAssistantMessage();
  }

  const block = createToolBlock(toolName, input, 'tool-call');
  block.classList.add('pending');
  currentAssistantGroup.appendChild(block);
  scrollToBottom();
}

export function appendToolResult(toolName, result) {
  if (!currentAssistantGroup) return;

  // Find the first pending tool call with matching name
  const pending = currentAssistantGroup.querySelector(`.tool-block.tool-call.pending[data-tool-name="${toolName}"]`);
  if (pending) {
    pending.classList.remove('pending');
    // Remove spinner
    const spinner = pending.querySelector('.tool-spinner');
    if (spinner) spinner.remove();
  }

  const block = createToolBlock(toolName, result, 'tool-result');
  // Insert after the matching call, or at end
  if (pending && pending.nextSibling) {
    currentAssistantGroup.insertBefore(block, pending.nextSibling);
  } else {
    currentAssistantGroup.appendChild(block);
  }
  scrollToBottom();
}

export function appendSubagentStart(task, agentType) {
  finalizeTextBlock();

  if (!currentAssistantGroup) {
    startAssistantMessage();
  }

  const block = document.createElement('div');
  block.className = 'subagent-block';
  block.id = `subagent-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  block.setAttribute('role', 'status');
  block.setAttribute('aria-busy', 'true');
  block.setAttribute('aria-label', `子智能体正在处理：${task}`);
  const typeBadge = agentType ? `<span class="subagent-type subagent-type--${escapeHtml(agentType)}">${escapeHtml(agentType)}</span>` : '';
  block.innerHTML = `
    <div class="subagent-header">
      <span>子智能体</span>
      ${typeBadge}
      <span class="tool-spinner"></span>
    </div>
    <div class="subagent-task">${escapeHtml(task)}</div>
  `;
  currentAssistantGroup.appendChild(block);
  scrollToBottom();

  return block.id;
}

export function appendSubagentEnd(blockId, summary, toolCount, elapsed, usage) {
  const block = blockId ? document.getElementById(blockId) : null;
  if (!block) return;
  block.setAttribute('aria-busy', 'false');

  const spinner = block.querySelector('.tool-spinner');
  if (spinner) spinner.remove();

  const summaryEl = document.createElement('div');
  summaryEl.className = 'subagent-summary';
  summaryEl.textContent = summary;
  block.appendChild(summaryEl);

  const statsEl = document.createElement('div');
  statsEl.className = 'subagent-stats';
  const elapsedStr = elapsed ? `${elapsed.toFixed(1)}s` : '?';
  const tokensStr = usage ? `${usage.input_tokens + usage.output_tokens} tokens` : '';
  statsEl.textContent = `${toolCount ?? 0} 次工具调用 \u00b7 ${elapsedStr}${tokensStr ? ' \u00b7 ' + tokensStr : ''}`;
  block.appendChild(statsEl);

  scrollToBottom();
}

// ===== Tool approval =====

let approvalCounter = 0;

export function appendToolApprovalRequest(tools) {
  finalizeTextBlock();

  if (!currentAssistantGroup) {
    startAssistantMessage();
  }

  const blockId = `approval-${++approvalCounter}`;
  const block = document.createElement('div');
  block.className = 'tool-block tool-approval';
  block.id = blockId;
  block.setAttribute('role', 'alertdialog');
  block.setAttribute('aria-label', '需要工具审批');

  const toolListHtml = tools.map(t => {
    const inputPreview = typeof t.input === 'string'
      ? t.input.slice(0, 120)
      : JSON.stringify(t.input || {}).slice(0, 120);
    return `<div class="approval-tool-item">
      <span class="approval-tool-name">${escapeHtml(t.name)}</span>
      <span class="approval-tool-input">${escapeHtml(inputPreview)}</span>
    </div>`;
  }).join('');

  block.innerHTML = `
    <div class="approval-header">需要工具审批</div>
    <div class="approval-tool-list">${toolListHtml}</div>
    <div class="approval-actions" id="${blockId}-actions">
      <button class="approval-btn approve-btn" data-decision="approve">批准</button>
      <button class="approval-btn deny-btn" data-decision="deny">拒绝</button>
      <button class="approval-btn auto-approve-btn" data-decision="auto_approve">自动批准后续</button>
    </div>
  `;

  currentAssistantGroup.appendChild(block);
  scrollToBottom();
  return blockId;
}

export function resolveApprovalBlock(blockId, decision) {
  const actions = document.getElementById(`${blockId}-actions`);
  if (!actions) return;

  const labels = { approve: '已批准', deny: '已拒绝', auto_approve: '已自动批准' };
  const classes = { approve: 'approved', deny: 'denied', auto_approve: 'approved' };

  actions.innerHTML = `<span class="approval-resolved ${classes[decision] || ''}">${labels[decision] || decision}</span>`;
  scrollToBottom();
}

export function appendCompactNotice(message) {
  if (!currentAssistantGroup) return;
  const notice = document.createElement('div');
  notice.className = 'compact-notice';
  notice.textContent = message;
  currentAssistantGroup.appendChild(notice);
  scrollToBottom();
}

export function finishAssistantMessage() {
  finalizeTextBlock();
  currentAssistantGroup = null;
}

export function renderInterruptNotice() {
  const notice = document.createElement('div');
  notice.className = 'interrupt-notice';
  notice.textContent = '已中断';
  messagesEl.appendChild(notice);
  scrollToBottom();
}

// ===== Todo panel =====

export function renderTodos(todos) {
  const listEl = document.getElementById('todo-list');
  listEl.innerHTML = '';

  if (!todos || todos.length === 0) {
    listEl.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">暂无任务。</p>';
    return;
  }

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
}

export function showTodoPanel() {
  document.getElementById('todo-panel').classList.remove('hidden');
}

export function hideTodoPanel() {
  document.getElementById('todo-panel').classList.add('hidden');
}

// ===== Token display =====

export function updateTokenDisplay(input, output) {
  state.totalInputTokens = input;
  state.totalOutputTokens = output;
  const el = document.getElementById('token-usage');
  const total = input + output;
  if (total > 0) {
    el.textContent = `${formatNumber(input)}/${formatNumber(output)} tokens`;
  } else {
    el.textContent = '';
  }
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

// ===== Helpers =====

function createMessageGroup(role) {
  const group = document.createElement('div');
  group.className = `message-group ${role}`;
  const label = document.createElement('div');
  label.className = `message-role ${role}`;
  const roleLabels = { user: '用户', assistant: '助手' };
  label.textContent = roleLabels[role] || role;
  group.appendChild(label);
  return group;
}

function createToolBlock(name, content, type) {
  const block = document.createElement('div');
  block.className = `tool-block ${type}`;
  block.dataset.toolName = name;

  const label = type === 'tool-call' ? `\u25B6 ${name}` : `\u2713 ${name}`;
  const spinner = type === 'tool-call' ? '<span class="tool-spinner"></span>' : '';

  block.innerHTML = `
    <div class="tool-header">
      <span class="tool-name">${escapeHtml(label)}</span>
      <span>${spinner}<span class="tool-toggle">\u25B6</span></span>
    </div>
    <div class="tool-body">
      <pre>${escapeHtml(formatToolContent(content))}</pre>
    </div>
  `;

  // Toggle collapse
  block.querySelector('.tool-header').addEventListener('click', () => {
    const body = block.querySelector('.tool-body');
    const toggle = block.querySelector('.tool-toggle');
    body.classList.toggle('open');
    toggle.classList.toggle('open');
  });

  return block;
}

function formatToolContent(content) {
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

export function clearMessages() {
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  currentAssistantGroup = null;
  currentTextBlock = null;
  textBuffer = '';
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHtml(str) {
  if (typeof str !== 'string') str = String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatNumber(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return String(n);
}
