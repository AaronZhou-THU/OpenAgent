import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock config.js
vi.mock('../js/config.js', () => ({
  API_BASE_URL: 'http://test:8000',
  WS_BASE_URL: 'ws://test:8000',
}));

// Mock state.js — we need a real state object and working emit/on
const mockState = {
  conversationId: null,
  conversations: [],
  messages: [],
  isStreaming: false,
  isConnected: false,
  totalInputTokens: 0,
  totalOutputTokens: 0,
  todos: [],
};

const emittedEvents = [];
const mockEmit = vi.fn((event, data) => {
  emittedEvents.push({ event, data });
});

vi.mock('../js/state.js', () => ({
  state: mockState,
  emit: mockEmit,
  on: vi.fn(),
  resetConversationState: vi.fn(),
}));

// Mock WebSocket class
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.onopen = null;
    this.onclose = null;
    this.onmessage = null;
    this.onerror = null;
    this.sentMessages = [];
    this.closeCode = null;
    this.closeReason = null;
    MockWebSocket.instances.push(this);
  }

  send(data) {
    this.sentMessages.push(data);
  }

  close(code, reason) {
    this.closeCode = code;
    this.closeReason = reason;
    this.readyState = MockWebSocket.CLOSED;
  }
}
MockWebSocket.instances = [];

// Assign WebSocket constants for protocol checks
MockWebSocket.prototype.CONNECTING = 0;
MockWebSocket.prototype.OPEN = 1;
MockWebSocket.prototype.CLOSING = 2;
MockWebSocket.prototype.CLOSED = 3;

describe('websocket.js', () => {
  let wsModule;

  beforeEach(async () => {
    // Reset mock state
    MockWebSocket.instances = [];
    emittedEvents.length = 0;
    mockEmit.mockClear();
    mockState.conversationId = null;

    // Set up global WebSocket and its constants
    global.WebSocket = MockWebSocket;
    global.WebSocket.OPEN = MockWebSocket.OPEN;
    global.WebSocket.CONNECTING = MockWebSocket.CONNECTING;
    global.WebSocket.CLOSING = MockWebSocket.CLOSING;
    global.WebSocket.CLOSED = MockWebSocket.CLOSED;

    // Use fake timers for reconnect logic
    vi.useFakeTimers();

    // Re-import to get a fresh module each time
    vi.resetModules();

    // Re-establish mocks after resetModules
    vi.doMock('../js/config.js', () => ({
      API_BASE_URL: 'http://test:8000',
      WS_BASE_URL: 'ws://test:8000',
    }));
    vi.doMock('../js/state.js', () => ({
      state: mockState,
      emit: mockEmit,
      on: vi.fn(),
      resetConversationState: vi.fn(),
    }));

    wsModule = await import('../js/websocket.js');
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('connect', () => {
    it('creates WebSocket with the correct URL', () => {
      wsModule.connect('conv-123');
      expect(MockWebSocket.instances.length).toBe(1);
      expect(MockWebSocket.instances[0].url).toBe('ws://test:8000/api/chat/conv-123/ws');
    });

    it('emits ws:connecting event', () => {
      wsModule.connect('conv-123');
      expect(mockEmit).toHaveBeenCalledWith('ws:connecting');
    });

    it('emits ws:connected and dev:status on open', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen();
      expect(mockEmit).toHaveBeenCalledWith('ws:connected');
      expect(mockEmit).toHaveBeenCalledWith('dev:status', {
        state: 'connected',
        url: 'ws://test:8000/api/chat/conv-123/ws',
      });
    });
  });

  describe('disconnect', () => {
    it('closes the WebSocket with code 1000', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      wsModule.disconnect();
      expect(ws.closeCode).toBe(1000);
      expect(ws.closeReason).toBe('switching conversation');
    });

    it('does not throw when no WebSocket is connected', () => {
      expect(() => wsModule.disconnect()).not.toThrow();
    });
  });

  describe('send', () => {
    it('returns false when not connected', () => {
      const result = wsModule.send('hello');
      expect(result).toBe(false);
    });

    it('returns true and sends data when connected', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.OPEN;

      const result = wsModule.send('hello');
      expect(result).toBe(true);
      expect(ws.sentMessages.length).toBe(1);

      const sent = JSON.parse(ws.sentMessages[0]);
      expect(sent).toEqual({ type: 'message', content: 'hello' });
    });

    it('returns false when WebSocket exists but is not in OPEN state', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.CONNECTING;

      const result = wsModule.send('hello');
      expect(result).toBe(false);
    });
  });

  describe('sendJson', () => {
    it('sends JSON payload when connected', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.OPEN;

      const payload = { type: 'tool_approval_response', decision: 'approve' };
      const result = wsModule.sendJson(payload);

      expect(result).toBe(true);
      expect(ws.sentMessages.length).toBe(1);
      expect(JSON.parse(ws.sentMessages[0])).toEqual(payload);
    });

    it('returns false when not connected', () => {
      const result = wsModule.sendJson({ type: 'test' });
      expect(result).toBe(false);
    });
  });

  describe('isConnected', () => {
    it('returns false when no WebSocket exists', () => {
      // isConnected() returns `null` when ws is null (ws && ...), which is falsy
      expect(wsModule.isConnected()).toBeFalsy();
    });

    it('returns false when WebSocket is not in OPEN state', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.CONNECTING;
      expect(wsModule.isConnected()).toBe(false);
    });

    it('returns true when WebSocket is in OPEN state', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.OPEN;
      expect(wsModule.isConnected()).toBe(true);
    });
  });

  describe('auto-reconnect', () => {
    it('reconnects on abnormal close when conversationId matches', () => {
      mockState.conversationId = 'conv-123';
      wsModule.connect('conv-123');

      const ws1 = MockWebSocket.instances[0];
      ws1.readyState = MockWebSocket.OPEN;
      ws1.onopen();

      // Simulate abnormal close (code !== 1000)
      ws1.onclose({ code: 1006, reason: 'abnormal' });

      // Should emit ws:disconnected
      expect(mockEmit).toHaveBeenCalledWith('ws:disconnected');

      // Advance timer for first reconnect (1 second)
      vi.advanceTimersByTime(1000);

      // A new WebSocket should have been created
      expect(MockWebSocket.instances.length).toBe(2);
      expect(MockWebSocket.instances[1].url).toBe('ws://test:8000/api/chat/conv-123/ws');
    });

    it('does not reconnect on normal close (code 1000)', () => {
      mockState.conversationId = 'conv-123';
      wsModule.connect('conv-123');

      const ws1 = MockWebSocket.instances[0];
      ws1.readyState = MockWebSocket.OPEN;
      ws1.onopen();

      // Simulate normal close
      ws1.onclose({ code: 1000, reason: 'normal' });

      vi.advanceTimersByTime(5000);

      // No new WebSocket should have been created
      expect(MockWebSocket.instances.length).toBe(1);
    });

    it('does not reconnect when conversationId has changed', () => {
      mockState.conversationId = 'conv-123';
      wsModule.connect('conv-123');

      const ws1 = MockWebSocket.instances[0];
      ws1.readyState = MockWebSocket.OPEN;
      ws1.onopen();

      // Simulate the user switching to a different conversation
      mockState.conversationId = 'conv-456';

      // Abnormal close on the old connection
      ws1.onclose({ code: 1006, reason: 'abnormal' });

      vi.advanceTimersByTime(5000);

      // Should not reconnect to the old conversation
      expect(MockWebSocket.instances.length).toBe(1);
    });
  });

  describe('max reconnect attempts', () => {
    it('stops reconnecting after MAX_RECONNECT_ATTEMPTS (3)', () => {
      mockState.conversationId = 'conv-123';
      wsModule.connect('conv-123');

      // Attempt 1: initial connection fails
      const ws1 = MockWebSocket.instances[0];
      ws1.onclose({ code: 1006, reason: 'abnormal' });
      vi.advanceTimersByTime(1000); // 1s delay for attempt 1

      // Attempt 2
      const ws2 = MockWebSocket.instances[1];
      ws2.onclose({ code: 1006, reason: 'abnormal' });
      vi.advanceTimersByTime(2000); // 2s delay for attempt 2

      // Attempt 3
      const ws3 = MockWebSocket.instances[2];
      ws3.onclose({ code: 1006, reason: 'abnormal' });
      vi.advanceTimersByTime(3000); // 3s delay for attempt 3

      // Attempt 4: should have reached max (3 reconnect attempts)
      const ws4 = MockWebSocket.instances[3];
      ws4.onclose({ code: 1006, reason: 'abnormal' });

      // Should emit dev:status with failed message
      expect(mockEmit).toHaveBeenCalledWith('dev:status', {
        state: 'failed',
        message: 'Max reconnect attempts reached',
      });

      vi.advanceTimersByTime(10000);

      // No further WebSocket instances should be created (4 total: 1 initial + 3 reconnects)
      expect(MockWebSocket.instances.length).toBe(4);
    });
  });

  describe('onmessage', () => {
    it('emits ws:event with parsed JSON data', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.OPEN;

      const data = { type: 'text_delta', content: 'hello' };
      ws.onmessage({ data: JSON.stringify(data) });

      expect(mockEmit).toHaveBeenCalledWith('dev:received', JSON.stringify(data));
      expect(mockEmit).toHaveBeenCalledWith('ws:event', data);
    });

    it('does not throw on invalid JSON', () => {
      wsModule.connect('conv-123');
      const ws = MockWebSocket.instances[0];
      ws.readyState = MockWebSocket.OPEN;

      expect(() => {
        ws.onmessage({ data: 'not valid json{{{' });
      }).not.toThrow();

      // dev:received should still be emitted
      expect(mockEmit).toHaveBeenCalledWith('dev:received', 'not valid json{{{');
    });
  });
});
