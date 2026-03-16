import './filepanel.js';
import { state, on, emit, resetConversationState } from './state.js';
import * as api from './api.js';
import * as ws from './websocket.js';
import {
  renderConversationList,
  renderHistory,
  startAssistantMessage,
  appendTextDelta,
  showActivityForTool,
  showActivity,
  hideActivity,
  finishAssistantMessage,
  renderUserMessage,
  renderInterruptNotice,
  showToolApproval,
  resolveApprovalBlock,
  showPlanOverlay,
  hidePlanOverlay,
  renderPlanSummaryCard,
  renderFileCards,
  renderError,
  setConnectionStatus,
  setInputEnabled,
  clearMessages,
  finalizeTextBlock,
  renderTodoPanel,
} from './renderer.js';

// Track active approval block ID
let activeApprovalId = null;

// Track number of concurrently running subagents
let activeSubagentCount = 0;

// Cached presets
let _presets = [];

// ===== Initialize =====

async function init() {
  bindUI();
  bindEvents();
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
    document.getElementById('sidebar-backdrop').classList.toggle('visible');
  });

  // Sidebar backdrop click to close
  document.getElementById('sidebar-backdrop').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebar-backdrop').classList.remove('visible');
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

  // Todo panel close
  document.getElementById('todo-close').addEventListener('click', () => {
    document.getElementById('todo-panel').classList.add('hidden');
  });

  // Prompt chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt) {
        const input = document.getElementById('message-input');
        input.value = prompt;
        input.focus();
        // Auto-resize
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 200) + 'px';
      }
    });
  });

  // Plan overlay buttons
  document.getElementById('plan-go-ahead-btn').addEventListener('click', () => {
    ws.sendJson({ type: 'plan_approval', decision: 'approve' });
    const planText = state.pendingPlan || '';
    hidePlanOverlay();
    finishAssistantMessage();
    renderPlanSummaryCard(planText);
    state.pendingPlan = null;
    state.planModeActive = false;
    // Start fresh group so implementation progress appears below the card
    startAssistantMessage();
  });

  document.getElementById('plan-change-btn').addEventListener('click', () => {
    document.getElementById('plan-overlay-feedback').classList.remove('hidden');
    const ta = document.getElementById('plan-change-input');
    if (ta) ta.focus();
  });

  document.getElementById('plan-change-submit').addEventListener('click', () => {
    const ta = document.getElementById('plan-change-input');
    const feedback = ta ? ta.value.trim() : '';
    ws.sendJson({ type: 'plan_approval', decision: 'reject', feedback });
    hidePlanOverlay();
    finishAssistantMessage();
    renderUserMessage(feedback || '请修改方案');
    state.pendingPlan = null;
    startAssistantMessage();
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
    renderError(message);
  });

  on('ws:event', handleServerEvent);
}

// ===== Conversation management =====

async function loadConversations() {
  try {
    state.conversations = await api.listConversations();
    state.conversations.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    renderConversationList();
  } catch (err) {
    console.error('Failed to load conversations:', err);
  }
}

async function createNewChat() {
  // Auto-create using first preset (no modal)
  try {
    const preset = _presets.length > 0 ? _presets[0].name : null;
    const { conversation_id } = await api.createChat(null, preset);
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

  // Update sidebar
  renderConversationList();

  // Load history
  try {
    const conv = await api.getConversation(id);
    state.planModeActive = !!conv.enable_plan_mode;
    renderHistory(conv);
  } catch (err) {
    console.error('Failed to load conversation:', err);
  }

  // Connect WebSocket
  ws.connect(id);

  // Close sidebar on mobile
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-backdrop').classList.remove('visible');
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
      document.getElementById('chat-title').textContent = '智能助手';
      setInputEnabled(false);
      setConnectionStatus('disconnected');
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
    // INTERRUPT MODE
    state.isInterrupting = true;
    // Dismiss any pending dialogs
    if (activeApprovalId) {
      resolveApprovalBlock(activeApprovalId, 'interrupted');
      activeApprovalId = null;
    }
    hidePlanOverlay();
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
  ws.send(text);
  input.value = '';
  input.style.height = 'auto';
  state.isStreaming = true;
  setStreamingUI(true);
  startAssistantMessage();
}

function setStreamingUI(streaming) {
  const input = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const cancelBtn = document.getElementById('cancel-btn');

  if (streaming) {
    input.placeholder = '输入内容以打断智能体...';
    sendBtn.classList.add('hidden');
    cancelBtn.classList.remove('hidden');
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
      // Show activity indicator instead of raw tool block
      finalizeTextBlock();
      if (!state.isStreaming) {
        state.isStreaming = true;
        setStreamingUI(true);
      }
      if (state.planModeActive) {
        showActivity('正在分析...');
      } else {
        showActivityForTool(event.tool);
      }
      break;

    case 'tool_result':
      // Silent — activity stays until text_delta or done
      break;

    case 'subagent_start':
      activeSubagentCount++;
      finalizeTextBlock();
      showActivity(activeSubagentCount > 1 ? `正在处理 ${activeSubagentCount} 个任务...` : '正在研究...');
      break;

    case 'subagent_end':
      activeSubagentCount = Math.max(0, activeSubagentCount - 1);
      if (activeSubagentCount > 0) {
        showActivity(activeSubagentCount > 1 ? `正在处理 ${activeSubagentCount} 个任务...` : '正在研究...');
      }
      // If 0, activity cleared by next text_delta or done
      break;

    case 'todo_update':
      state.todos = event.todos || [];
      renderTodoPanel(state.todos);
      break;

    case 'task_update':
      // Persistent task system — render in floating panel
      state.todos = (event.tasks || []).map(t => ({
        content: `#${t.id} ${t.subject}`,
        status: t.status === 'completed' ? 'completed' : t.status === 'in_progress' ? 'in_progress' : 'pending',
        activeForm: t.active_form || '',
      }));
      renderTodoPanel(state.todos);
      break;

    case 'background_result':
    case 'teammate_status':
    case 'compact':
    case 'phase':
    case 'teams_changed':
    case 'approval_changed':
      // Silent — dev/status events suppressed
      break;

    case 'plan_mode_changed':
      state.planModeActive = !!event.enabled;
      break;

    case 'tool_approval_request':
      hideActivity();
      activeApprovalId = showToolApproval();
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
      if (activeApprovalId) {
        resolveApprovalBlock(activeApprovalId, event.decision || 'denied');
        activeApprovalId = null;
      }
      break;

    case 'plan_ready':
      hideActivity();
      state.pendingPlan = event.plan;
      showPlanOverlay(event.plan);
      break;

    case 'plan_approved': {
      // Only render card if not already handled by the local button click
      if (state.pendingPlan != null) {
        const planText = state.pendingPlan;
        hidePlanOverlay();
        finishAssistantMessage();
        renderPlanSummaryCard(planText);
        state.pendingPlan = null;
        state.planModeActive = false;
        startAssistantMessage();
      }
      break;
    }

    case 'plan_rejected':
      if (state.pendingPlan != null) {
        hidePlanOverlay();
        finishAssistantMessage();
        state.pendingPlan = null;
        startAssistantMessage();
      }
      break;

    case 'interrupted':
      state.isInterrupting = false;
      if (event.files && event.files.length > 0) {
        renderFileCards(event.files, state.conversationId);
      }
      break;

    case 'done':
      state.isStreaming = false;
      state.isInterrupting = false;
      activeSubagentCount = 0;
      finishAssistantMessage();
      setStreamingUI(false);
      if (event.files && event.files.length > 0) {
        renderFileCards(event.files, state.conversationId);
      }
      loadConversations();
      break;

    case 'error':
      if (state.isInterrupting && event.message === 'Cancelled') {
        break;
      }
      state.isStreaming = false;
      state.isInterrupting = false;
      finishAssistantMessage();
      setStreamingUI(false);
      renderError(event.message);
      break;

    default:
      console.log('Unhandled event:', event.type);
  }
}

// ===== Boot =====
init();
