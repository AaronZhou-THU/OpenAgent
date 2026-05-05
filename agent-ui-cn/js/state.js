// Simple app state + event bus

const listeners = new Map();

export const state = {
  conversationId: null,
  conversations: [],
  messages: [],         // rendered message groups
  isStreaming: false,
  isInterrupting: false,
  isConnected: false,
  totalInputTokens: 0,
  totalOutputTokens: 0,
  todos: [],
  planModeActive: false,
  pendingPlan: null,
  teamsActive: false,
  approvalActive: false,
  thinkingActive: false,
  thinkingEffort: 'high',
};

export function emit(event, data) {
  const handlers = listeners.get(event);
  if (handlers) {
    for (const fn of handlers) fn(data);
  }
}

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}

export function resetConversationState() {
  state.messages = [];
  state.isStreaming = false;
  state.isInterrupting = false;
  state.totalInputTokens = 0;
  state.totalOutputTokens = 0;
  state.todos = [];
  state.planModeActive = false;
  state.pendingPlan = null;
  state.teamsActive = false;
  state.approvalActive = false;
  state.thinkingActive = false;
  state.thinkingEffort = 'high';
}
