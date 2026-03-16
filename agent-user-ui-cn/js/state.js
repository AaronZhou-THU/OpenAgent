// Simple app state + event bus

const listeners = new Map();

export const state = {
  conversationId: null,
  conversations: [],
  messages: [],
  isStreaming: false,
  isInterrupting: false,
  isConnected: false,
  activityText: null,     // current activity indicator text
  planModeActive: false,
  pendingPlan: null,
  todos: [],
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
  state.activityText = null;
  state.planModeActive = false;
  state.pendingPlan = null;
  state.todos = [];
}
