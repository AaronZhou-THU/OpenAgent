import { describe, it, expect, beforeEach } from 'vitest';
import { state, emit, on, resetConversationState } from '../js/state.js';

describe('state.js', () => {
  describe('initial state values', () => {
    it('has conversationId set to null', () => {
      expect(state.conversationId).toBe(null);
    });

    it('has conversations as an empty array', () => {
      expect(state.conversations).toEqual([]);
    });

    it('has messages as an empty array', () => {
      expect(state.messages).toEqual([]);
    });

    it('has isStreaming set to false', () => {
      expect(state.isStreaming).toBe(false);
    });

    it('has isConnected set to false', () => {
      expect(state.isConnected).toBe(false);
    });

    it('has totalInputTokens set to 0', () => {
      expect(state.totalInputTokens).toBe(0);
    });

    it('has totalOutputTokens set to 0', () => {
      expect(state.totalOutputTokens).toBe(0);
    });

    it('has todos as an empty array', () => {
      expect(state.todos).toEqual([]);
    });

    it('has teamsActive set to false', () => {
      expect(state.teamsActive).toBe(false);
    });

    it('has approvalActive set to false', () => {
      expect(state.approvalActive).toBe(false);
    });
  });

  describe('emit and on', () => {
    it('emit triggers registered handlers', () => {
      const results = [];
      const unsub = on('test:event', (data) => results.push(data));

      emit('test:event', 'hello');
      expect(results).toEqual(['hello']);

      unsub();
    });

    it('on returns an unsubscribe function', () => {
      const unsub = on('test:unsub', () => {});
      expect(typeof unsub).toBe('function');
      unsub();
    });

    it('unsubscribe removes the handler so it no longer fires', () => {
      const results = [];
      const unsub = on('test:remove', (data) => results.push(data));

      emit('test:remove', 'first');
      expect(results).toEqual(['first']);

      unsub();

      emit('test:remove', 'second');
      expect(results).toEqual(['first']); // should not have added 'second'
    });

    it('multiple handlers for same event all fire', () => {
      const results = [];
      const unsub1 = on('test:multi', (data) => results.push(`a:${data}`));
      const unsub2 = on('test:multi', (data) => results.push(`b:${data}`));

      emit('test:multi', 'value');
      expect(results).toEqual(['a:value', 'b:value']);

      unsub1();
      unsub2();
    });

    it('emit with no listeners does not throw', () => {
      expect(() => emit('nonexistent:event', 'data')).not.toThrow();
    });

    it('handler receives the correct data payload', () => {
      let received = null;
      const unsub = on('test:data', (data) => { received = data; });

      const payload = { key: 'value', count: 42 };
      emit('test:data', payload);
      expect(received).toEqual(payload);

      unsub();
    });
  });

  describe('resetConversationState', () => {
    it('resets only conversation-specific fields', () => {
      // Set up state with values
      state.conversationId = 'conv-123';
      state.conversations = [{ id: 'conv-123' }];
      state.messages = [{ role: 'user', content: 'hello' }];
      state.isStreaming = true;
      state.isConnected = true;
      state.totalInputTokens = 500;
      state.totalOutputTokens = 300;
      state.todos = [{ content: 'task 1', status: 'pending' }];
      state.teamsActive = true;
      state.approvalActive = true;

      resetConversationState();

      // These should be reset
      expect(state.messages).toEqual([]);
      expect(state.isStreaming).toBe(false);
      expect(state.totalInputTokens).toBe(0);
      expect(state.totalOutputTokens).toBe(0);
      expect(state.todos).toEqual([]);
      expect(state.teamsActive).toBe(false);
      expect(state.approvalActive).toBe(false);

      // These should NOT be reset
      expect(state.conversationId).toBe('conv-123');
      expect(state.conversations).toEqual([{ id: 'conv-123' }]);
      expect(state.isConnected).toBe(true);

      // Clean up
      state.conversationId = null;
      state.conversations = [];
      state.isConnected = false;
    });
  });
});
