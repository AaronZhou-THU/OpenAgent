import './devpanel.js';
import './filepanel.js';
import { state, on, emit, resetConversationState } from './state.js';
import * as auth from './auth.js';
import * as api from './api.js';
import * as ws from './websocket.js';
import {
  renderConversationList,
  renderHistory,
  renderToolResultHistory,
  startAssistantMessage,
  appendTextDelta,
  appendToolCall,
  appendToolResult,
  appendSubagentStart,
  appendSubagentEnd,
  appendCompactNotice,
  appendToolApprovalRequest,
  resolveApprovalBlock,
  finishAssistantMessage,
  renderInterruptNotice,
  renderTodos,
  showTodoPanel,
  setConnectionStatus,
  setInputEnabled,
  updateTokenDisplay,
  clearMessages,
} from './renderer.js';

// Track active subagent block IDs (subagent_id → DOM block ID)
let activeSubagents = new Map();

// Track active approval block ID
let activeApprovalId = null;

// Cached presets from API
let _presets = [];

// ===== Initialize =====

async function init() {
  bindUI();
  bindEvents();

  // Check if auth is required
  const authEnabled = await auth.init();
  if (authEnabled) {
    if (!auth.isAuthenticated()) {
      showLoginOverlay();
      return; // Wait for sign-in before loading app
    }
    showUserProfile(auth.getUser());
  }

  await Promise.all([loadConversations(), loadPresets()]);
}

async function loadPresets() {
  try {
    _presets = await api.listPresets();
  } catch (err) {
    console.error('Failed to load presets:', err);
    _presets = [];
  }
}

// ===== UI bindings =====

function bindUI() {
  // New chat
  document.getElementById('new-chat-btn').addEventListener('click', createNewChat);

  // Send message
  document.getElementById('send-btn').addEventListener('click', sendMessage);

  // Textarea: Enter to send, Shift+Enter for newline, auto-resize
  const input = document.getElementById('message-input');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
  });

  // Sidebar toggle (mobile)
  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });

  // Todo close
  document.getElementById('todo-close').addEventListener('click', () => {
    document.getElementById('todo-panel').classList.add('hidden');
  });

  // Teams toggle button
  document.getElementById('teams-btn').addEventListener('click', () => {
    if (!ws.isConnected()) return;
    ws.sendJson({ type: 'toggle_teams', enabled: !state.teamsActive });
  });

  // Approval toggle button
  document.getElementById('approval-btn').addEventListener('click', () => {
    if (!ws.isConnected()) return;
    ws.sendJson({ type: 'toggle_approval', enabled: !state.approvalActive });
  });

  // Plan mode toggle button
  document.getElementById('plan-mode-btn').addEventListener('click', () => {
    if (!ws.isConnected()) return;
    ws.sendJson({ type: 'toggle_plan_mode', enabled: !state.planModeActive });
  });

  // Cancel / stop button
  document.getElementById('cancel-btn').addEventListener('click', () => {
    if (!state.isStreaming || !ws.isConnected()) return;
    ws.sendJson({ type: 'cancel' });
    state.isStreaming = false;
    state.isInterrupting = false;
    finishAssistantMessage();
    setStreamingUI(false);
  });

  // Plan approval buttons
  document.getElementById('plan-approve-btn').addEventListener('click', () => {
    ws.sendJson({ type: 'plan_approval', decision: 'approve' });
    hidePlanApproval();
  });

  document.getElementById('plan-reject-btn').addEventListener('click', () => {
    const feedbackSection = document.getElementById('plan-feedback-section');
    feedbackSection.classList.toggle('hidden');
  });

  document.getElementById('plan-feedback-submit').addEventListener('click', () => {
    const input = document.getElementById('plan-feedback-input');
    const feedback = input.value.trim();
    ws.sendJson({ type: 'plan_approval', decision: 'reject', feedback });
    input.value = '';
    hidePlanApproval();
  });
}

// ===== Event bus bindings =====

function bindEvents() {
  on('conversation:select', selectConversation);
  on('conversation:delete', deleteConversation);
  on('ws:connecting', () => {
    state.isConnected = false;
    setConnectionStatus('connecting');
  });
  on('ws:connected', () => {
    state.isConnected = true;
    setConnectionStatus('connected');
    setStreamingUI(false);
  });
  on('ws:disconnected', () => {
    state.isConnected = false;
    setConnectionStatus('disconnected');
    if (state.isStreaming) {
      state.isStreaming = false;
      state.isInterrupting = false;
      finishAssistantMessage();
      setStreamingUI(false);
    }
  });
  on('ws:reconnect_failed', ({ message }) => {
    const messagesEl = document.getElementById('messages');
    if (messagesEl) {
      const notice = document.createElement('div');
      notice.className = 'system-message error-message';
      notice.setAttribute('role', 'alert');
      notice.textContent = message;
      messagesEl.appendChild(notice);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  });
  on('ws:event', handleServerEvent);

  // Auth events
  on('auth:changed', async ({ authenticated, user }) => {
    if (authenticated) {
      hideLoginOverlay();
      showUserProfile(user);
      await Promise.all([loadConversations(), loadPresets()]);
    } else {
      showLoginOverlay();
      hideUserProfile();
    }
  });
  on('auth:expired', () => {
    auth.signOut();
    showLoginOverlay();
    hideUserProfile();
  });
}

// ===== Conversation management =====

async function loadConversations() {
  try {
    state.conversations = await api.listConversations();
    // Sort by created_at descending
    state.conversations.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    renderConversationList();
  } catch (err) {
    console.error('Failed to load conversations:', err);
  }
}

async function createNewChat() {
  // Always show the modal so users can toggle teams
  showPresetSelector();
}

let _selectedPreset = null;

function showPresetSelector() {
  const overlay = document.getElementById('preset-overlay');
  const list = document.getElementById('preset-list');
  const teamsToggle = document.getElementById('enable-teams-toggle');
  const tracingToggle = document.getElementById('enable-tracing-toggle');
  const approvalToggle = document.getElementById('enable-approval-toggle');
  const planModeToggle = document.getElementById('enable-plan-mode-toggle');
  const createBtn = document.getElementById('preset-create-btn');
  list.innerHTML = '';
  teamsToggle.checked = false;
  tracingToggle.checked = false;
  approvalToggle.checked = false;
  planModeToggle.checked = false;

  // Default to first preset
  _selectedPreset = _presets.length > 0 ? _presets[0].name : null;

  for (const preset of _presets) {
    const item = document.createElement('button');
    item.className = 'preset-option' + (preset.name === _selectedPreset ? ' selected' : '');
    item.dataset.preset = preset.name;
    item.innerHTML = `
      <span class="preset-option-name">${escapeHtml(preset.name)}</span>
      <span class="preset-option-desc">${escapeHtml(preset.description)}</span>
    `;
    item.addEventListener('click', () => {
      _selectedPreset = preset.name;
      list.querySelectorAll('.preset-option').forEach(el => el.classList.remove('selected'));
      item.classList.add('selected');
    });
    list.appendChild(item);
  }

  // Create button handler
  const handler = async () => {
    createBtn.removeEventListener('click', handler);
    overlay.classList.add('hidden');
    await doCreateChat(_selectedPreset, {
      enableTeams: teamsToggle.checked,
      enableTracing: tracingToggle.checked,
      enableApproval: approvalToggle.checked,
      enablePlanMode: planModeToggle.checked,
    });
  };
  createBtn.addEventListener('click', handler);

  overlay.classList.remove('hidden');

  // Close on backdrop click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.classList.add('hidden');
      createBtn.removeEventListener('click', handler);
    }
  }, { once: true });
}

async function doCreateChat(preset = null, { enableTeams = false, enableTracing = false, enableApproval = false, enablePlanMode = false } = {}) {
  try {
    const { conversation_id } = await api.createChat(null, preset, { enableTeams, enableTracing, enableApproval, enablePlanMode });
    await loadConversations();
    await selectConversation(conversation_id);
  } catch (err) {
    console.error('Failed to create chat:', err);
  }
}

async function selectConversation(id) {
  if (state.conversationId === id) return;

  // Disconnect from previous
  ws.disconnect();
  resetConversationState();
  state.conversationId = id;

  // Update sidebar active state
  renderConversationList();

  // Load history
  try {
    const conv = await api.getConversation(id);
    state.planModeActive = conv.enable_plan_mode || false;
    state.teamsActive = conv.enable_teams || false;
    state.approvalActive = conv.enable_approval || false;
    renderHistoryWithToolResults(conv);
    updatePlanModeUI();
    updateTeamsUI();
    updateApprovalUI();
  } catch (err) {
    console.error('Failed to load conversation:', err);
  }

  // Connect WebSocket
  ws.connect(id);

  // Close sidebar on mobile
  document.getElementById('sidebar').classList.remove('open');
}

function renderHistoryWithToolResults(conv) {
  // We need to handle the alternating user/assistant messages and correlate tool results
  const welcomeEl = document.getElementById('welcome');
  const messagesEl = document.getElementById('messages');
  clearMessages();
  welcomeEl.style.display = 'none';

  document.getElementById('chat-title').textContent = conv.title || '无标题';
  updateTokenDisplay(conv.total_input_tokens || 0, conv.total_output_tokens || 0);

  const messages = conv.messages || [];

  for (const msg of messages) {
    if (msg.role === 'user') {
      // Check if this is a tool result message
      if (Array.isArray(msg.content) && msg.content.some(b => b.type === 'tool_result')) {
        renderToolResultHistory(msg.content);
      } else {
        renderUserMessageFromHistory(msg.content);
      }
    } else if (msg.role === 'assistant') {
      renderAssistantFromHistory(msg.content);
    }
  }

  scrollMessagesToBottom();
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

  const messagesEl = document.getElementById('messages');
  const group = document.createElement('div');
  group.className = 'message-group user';
  group.innerHTML = `
    <div class="message-role user">user</div>
    <div class="message-content user-text">${escapeHtml(text)}</div>
  `;
  messagesEl.appendChild(group);
}

function renderAssistantFromHistory(content) {
  if (!content) return;

  const { renderMarkdown } = getMarkdownModule();
  const messagesEl = document.getElementById('messages');
  const group = document.createElement('div');
  group.className = 'message-group assistant';
  group.innerHTML = '<div class="message-role assistant">assistant</div>';

  const blocks = Array.isArray(content) ? content : [{ type: 'text', text: String(content) }];

  for (const block of blocks) {
    if (block.type === 'text' && block.text?.trim()) {
      const textEl = document.createElement('div');
      textEl.className = 'message-content';
      textEl.innerHTML = renderMarkdown(block.text);
      group.appendChild(textEl);
    } else if (block.type === 'tool_use') {
      const toolEl = createHistoryToolBlock(block.name, block.input, 'tool-call', block.id);
      group.appendChild(toolEl);
    }
  }

  messagesEl.appendChild(group);
}

function createHistoryToolBlock(name, content, type, toolUseId) {
  const block = document.createElement('div');
  block.className = `tool-block ${type}`;
  block.dataset.toolName = name;
  if (toolUseId) block.dataset.toolUseId = toolUseId;

  const label = type === 'tool-call' ? `\u25B6 ${name}` : `\u2713 ${name}`;

  block.innerHTML = `
    <div class="tool-header">
      <span class="tool-name">${escapeHtml(label)}</span>
      <span class="tool-toggle">\u25B6</span>
    </div>
    <div class="tool-body">
      <pre>${escapeHtml(formatToolContent(content))}</pre>
    </div>
  `;

  block.querySelector('.tool-header').addEventListener('click', () => {
    block.querySelector('.tool-body').classList.toggle('open');
    block.querySelector('.tool-toggle').classList.toggle('open');
  });

  return block;
}

async function deleteConversation(id) {
  try {
    await api.deleteConversation(id);
    if (state.conversationId === id) {
      ws.disconnect();
      resetConversationState();
      state.conversationId = null;
      clearMessages();
      document.getElementById('welcome').style.display = '';
      document.getElementById('chat-title').textContent = '请选择一个对话';
      setInputEnabled(false);
      setConnectionStatus('disconnected');
      updateTokenDisplay(0, 0);
    }
    await loadConversations();
  } catch (err) {
    console.error('Failed to delete conversation:', err);
  }
}

// ===== Send message =====

function sendMessage() {
  const input = document.getElementById('message-input');
  const text = input.value.trim();
  if (!text || !ws.isConnected()) return;

  if (state.isStreaming) {
    // INTERRUPT MODE — send feedback while agent is running
    state.isInterrupting = true;
    // Dismiss any pending overlays
    if (activeApprovalId) {
      resolveApprovalBlock(activeApprovalId, 'interrupted');
      activeApprovalId = null;
    }
    hidePlanApproval();
    finishAssistantMessage();
    renderInterruptNotice();
    renderUserMessage(text);
    ws.sendJson({ type: 'interrupt', content: text });
    startAssistantMessage();
    input.value = '';
    input.style.height = 'auto';
    return;
  }

  // NORMAL MODE
  renderUserMessage(text);

  // Send via WebSocket
  ws.send(text);

  // Clear input
  input.value = '';
  input.style.height = 'auto';

  // Enter streaming state
  state.isStreaming = true;
  setStreamingUI(true);
  startAssistantMessage();
}

function renderUserMessage(text) {
  const messagesEl = document.getElementById('messages');
  document.getElementById('welcome').style.display = 'none';
  const group = document.createElement('div');
  group.className = 'message-group user';
  group.innerHTML = `
    <div class="message-role user">user</div>
    <div class="message-content user-text">${escapeHtml(text)}</div>
  `;
  messagesEl.appendChild(group);
  scrollMessagesToBottom();
}

function setStreamingUI(streaming) {
  const input = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const cancelBtn = document.getElementById('cancel-btn');

  if (streaming) {
    input.placeholder = '输入内容以打断智能体...';
    sendBtn.classList.add('hidden');
    cancelBtn.classList.remove('hidden');
    // Keep input enabled so user can type interrupts
    input.disabled = false;
    sendBtn.disabled = true;
    input.focus();
  } else {
    input.placeholder = '输入消息...';
    sendBtn.classList.remove('hidden');
    cancelBtn.classList.add('hidden');
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

// ===== Handle server events =====

function handleServerEvent(event) {
  switch (event.type) {
    case 'text_delta':
      appendTextDelta(event.content);
      break;

    case 'tool_call':
      appendToolCall(event.tool, event.input);
      break;

    case 'tool_result':
      appendToolResult(event.tool, event.result);
      break;

    case 'subagent_start': {
      const blockId = appendSubagentStart(event.task, event.agent_type);
      const sid = event.subagent_id || blockId;
      activeSubagents.set(sid, blockId);
      break;
    }

    case 'subagent_end': {
      const sid = event.subagent_id;
      const blockId = sid ? activeSubagents.get(sid) : activeSubagents.values().next().value;
      appendSubagentEnd(blockId, event.summary, event.tool_count, event.elapsed, event.usage);
      if (sid) activeSubagents.delete(sid);
      else if (activeSubagents.size) activeSubagents.delete(activeSubagents.keys().next().value);
      break;
    }

    case 'todo_update':
      state.todos = event.todos || [];
      renderTodos(state.todos);
      showTodoPanel();
      break;

    case 'task_update':
      // Persistent task system — render in todo panel
      state.todos = (event.tasks || []).map(t => ({
        content: `#${t.id} ${t.subject}`,
        status: t.status === 'completed' ? 'completed' : t.status === 'in_progress' ? 'in_progress' : 'pending',
        activeForm: t.active_form || '',
      }));
      renderTodos(state.todos);
      showTodoPanel();
      break;

    case 'background_result':
      // Show background task completions as compact notices
      for (const n of (event.notifications || [])) {
        appendCompactNotice(`后台任务 [${n.task_id}] ${n.status}：${(n.result || '').slice(0, 200)}`);
      }
      break;

    case 'teammate_status':
      appendCompactNotice(`队友 "${event.name}"（${event.role || '?'}）：${event.status}`);
      break;

    case 'tool_approval_request':
      activeApprovalId = appendToolApprovalRequest(event.tools);
      // Bind button handlers
      if (activeApprovalId) {
        const actionsEl = document.getElementById(`${activeApprovalId}-actions`);
        if (actionsEl) {
          actionsEl.addEventListener('click', (e) => {
            const btn = e.target.closest('.approval-btn');
            if (!btn) return;
            const decision = btn.dataset.decision;
            ws.sendJson({ type: 'tool_approval_response', decision });
            resolveApprovalBlock(activeApprovalId, decision);
            activeApprovalId = null;
          });
        }
      }
      break;

    case 'tool_approval_result':
      // Server denied tools — update UI if approval block still active
      if (activeApprovalId) {
        resolveApprovalBlock(activeApprovalId, event.decision || 'denied');
        activeApprovalId = null;
      }
      break;

    case 'teams_changed':
      state.teamsActive = event.enabled;
      updateTeamsUI();
      appendCompactNotice(event.enabled ? '团队已启用' : '团队已禁用');
      break;

    case 'approval_changed':
      state.approvalActive = event.enabled;
      updateApprovalUI();
      appendCompactNotice(event.enabled ? '工具审批已启用' : '工具审批已禁用');
      break;

    case 'plan_mode_changed':
      state.planModeActive = event.enabled;
      updatePlanModeUI();
      appendCompactNotice(event.enabled ? '规划模式已启用' : '规划模式已禁用');
      break;

    case 'plan_ready':
      showPlanApproval(event.plan);
      break;

    case 'plan_approved':
      hidePlanApproval();
      state.planModeActive = false;
      updatePlanModeUI();
      appendCompactNotice('方案已批准 — 切换到执行模式');
      break;

    case 'plan_rejected':
      hidePlanApproval();
      if (event.feedback) {
        appendCompactNotice(`方案被驳回：${event.feedback}`);
      }
      break;

    case 'compact':
      appendCompactNotice(event.message);
      break;

    case 'phase':
      appendCompactNotice(event.message);
      break;

    case 'interrupted':
      // Turn was interrupted — update tokens but keep streaming
      // (next turn starts automatically via pending_content on server)
      state.isInterrupting = false;
      if (event.usage) {
        state.totalInputTokens += event.usage.input_tokens || 0;
        state.totalOutputTokens += event.usage.output_tokens || 0;
        updateTokenDisplay(state.totalInputTokens, state.totalOutputTokens);
      }
      if (event.files && event.files.length > 0) {
        renderFileCards(event.files, state.conversationId);
      }
      // Don't set isStreaming=false — the next turn is already starting
      break;

    case 'done':
      state.isStreaming = false;
      state.isInterrupting = false;
      finishAssistantMessage();
      setStreamingUI(false);
      // Update token usage
      if (event.usage) {
        state.totalInputTokens += event.usage.input_tokens || 0;
        state.totalOutputTokens += event.usage.output_tokens || 0;
        updateTokenDisplay(state.totalInputTokens, state.totalOutputTokens);
      }
      // Render file download cards if agent created files
      if (event.files && event.files.length > 0) {
        renderFileCards(event.files, state.conversationId);
      }
      // Refresh conversation list (title may have updated)
      loadConversations();
      break;

    case 'error':
      // If we're interrupting, suppress "Cancelled" errors from the interrupted turn
      if (state.isInterrupting && event.message === 'Cancelled') {
        break;
      }
      state.isStreaming = false;
      state.isInterrupting = false;
      finishAssistantMessage();
      setStreamingUI(false);
      // Show error inline
      appendErrorMessage(event.message);
      break;

    default:
      console.log('Unknown event:', event);
  }
}

function appendErrorMessage(message) {
  const messagesEl = document.getElementById('messages');
  const el = document.createElement('div');
  el.className = 'compact-notice';
  el.style.borderColor = 'var(--accent-red)';
  el.style.color = 'var(--accent-red)';
  el.textContent = `错误：${message}`;
  messagesEl.appendChild(el);
  scrollMessagesToBottom();
}

// ===== File download cards =====

function renderFileCards(files, convId) {
  const messagesEl = document.getElementById('messages');
  const card = document.createElement('div');
  card.className = 'file-card';
  card.innerHTML = `<div class="file-card-header">已创建文件</div>`;
  const list = document.createElement('div');
  list.className = 'file-card-list';

  for (const f of files) {
    const size = formatFileSize(f.size);
    const url = api.fileUrl(convId, f.path);
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
  scrollMessagesToBottom();
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ===== Plan Mode =====

function updatePlanModeUI() {
  const btn = document.getElementById('plan-mode-btn');
  if (!state.conversationId) {
    btn.classList.add('hidden');
    return;
  }
  btn.classList.remove('hidden');
  if (state.planModeActive) {
    btn.classList.add('active');
    btn.title = '规划模式已开启（点击关闭）';
  } else {
    btn.classList.remove('active');
    btn.title = '规划模式已关闭（点击开启）';
  }
}

function updateTeamsUI() {
  const btn = document.getElementById('teams-btn');
  if (!state.conversationId) {
    btn.classList.add('hidden');
    return;
  }
  btn.classList.remove('hidden');
  if (state.teamsActive) {
    btn.classList.add('active');
    btn.title = '团队已开启（点击关闭）';
  } else {
    btn.classList.remove('active');
    btn.title = '团队已关闭（点击开启）';
  }
}

function updateApprovalUI() {
  const btn = document.getElementById('approval-btn');
  if (!state.conversationId) {
    btn.classList.add('hidden');
    return;
  }
  btn.classList.remove('hidden');
  if (state.approvalActive) {
    btn.classList.add('active');
    btn.title = '审批已开启（点击关闭）';
  } else {
    btn.classList.remove('active');
    btn.title = '审批已关闭（点击开启）';
  }
}

function showPlanApproval(planText) {
  const overlay = document.getElementById('plan-approval-overlay');
  const contentEl = document.getElementById('plan-content');
  const feedbackSection = document.getElementById('plan-feedback-section');
  feedbackSection.classList.add('hidden');

  const { renderMarkdown } = getMarkdownModule();
  contentEl.innerHTML = renderMarkdown(planText);

  state.pendingPlan = planText;
  overlay.classList.remove('hidden');
}

function hidePlanApproval() {
  document.getElementById('plan-approval-overlay').classList.add('hidden');
  state.pendingPlan = null;
}

// ===== Helpers =====

function scrollMessagesToBottom() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(str) {
  if (typeof str !== 'string') str = String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatToolContent(content) {
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

// Lazy import markdown module
let _markdownModule = null;
function getMarkdownModule() {
  if (!_markdownModule) {
    // We import synchronously since marked is loaded as a global
    _markdownModule = {
      renderMarkdown(text) {
        const raw = marked.parse(text);
        if (typeof DOMPurify !== 'undefined') {
          return DOMPurify.sanitize(raw);
        }
        return raw;
      }
    };
  }
  return _markdownModule;
}

// ===== Auth UI =====

function showLoginOverlay() {
  const overlay = document.getElementById('login-overlay');
  overlay.classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
  auth.renderSignInButton(document.getElementById('google-signin-btn'));
}

function hideLoginOverlay() {
  document.getElementById('login-overlay').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
}

function showUserProfile(user) {
  if (!user) return;
  const profile = document.getElementById('user-profile');
  const avatar = document.getElementById('user-avatar');
  const name = document.getElementById('user-name');
  avatar.src = user.picture || '';
  avatar.alt = user.name || '用户';
  name.textContent = user.name || user.email || '';
  profile.classList.remove('hidden');

  // Bind sign-out (only once)
  const signOutBtn = document.getElementById('sign-out-btn');
  signOutBtn.onclick = () => auth.signOut();
}

function hideUserProfile() {
  document.getElementById('user-profile').classList.add('hidden');
}

// ===== Boot =====
init();
