import assert from 'node:assert/strict';
import test from 'node:test';

import { emit, on, resetConversationState, state } from '../js/state.js';

test('emit notifies subscribers and unsubscribe stops updates', () => {
  let received = null;
  const off = on('message', (data) => {
    received = data;
  });

  emit('message', { ok: true });
  assert.deepEqual(received, { ok: true });

  off();
  received = null;
  emit('message', { ok: false });
  assert.equal(received, null);
});

test('resetConversationState clears transient state', () => {
  state.messages = [{ role: 'user', content: 'hi' }];
  state.isStreaming = true;
  state.isInterrupting = true;
  state.activityText = 'Working...';
  state.planModeActive = true;
  state.pendingPlan = { text: 'plan' };
  state.todos = ['todo'];

  resetConversationState();

  assert.deepEqual(state.messages, []);
  assert.equal(state.isStreaming, false);
  assert.equal(state.isInterrupting, false);
  assert.equal(state.activityText, null);
  assert.equal(state.planModeActive, false);
  assert.equal(state.pendingPlan, null);
  assert.deepEqual(state.todos, []);
});
