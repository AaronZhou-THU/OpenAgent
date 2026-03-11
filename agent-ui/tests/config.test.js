import { describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('config.js', () => {
  let storage;

  beforeEach(() => {
    storage = new Map();
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: {
        getItem(key) {
          return storage.has(key) ? storage.get(key) : null;
        },
        setItem(key, value) {
          storage.set(key, String(value));
        },
        removeItem(key) {
          storage.delete(key);
        },
        clear() {
          storage.clear();
        },
      },
    });
  });

  afterEach(() => {
    localStorage.removeItem('API_BASE_URL');
    vi.resetModules();
  });

  it('API_BASE_URL defaults to http://localhost:8000 when localStorage is empty', async () => {
    localStorage.removeItem('API_BASE_URL');
    const config = await import('../js/config.js');
    expect(config.API_BASE_URL).toBe('http://localhost:8000');
  });

  it('WS_BASE_URL converts http to ws for default URL', async () => {
    localStorage.removeItem('API_BASE_URL');
    const config = await import('../js/config.js');
    expect(config.WS_BASE_URL).toBe('ws://localhost:8000');
  });

  it('WS_BASE_URL converts https to wss', async () => {
    localStorage.setItem('API_BASE_URL', 'https://example.com:9000');
    const config = await import('../js/config.js');
    expect(config.WS_BASE_URL).toBe('wss://example.com:9000');
  });

  it('API_BASE_URL uses localStorage value when set', async () => {
    localStorage.setItem('API_BASE_URL', 'http://custom-host:4000');
    const config = await import('../js/config.js');
    expect(config.API_BASE_URL).toBe('http://custom-host:4000');
  });

  it('WS_BASE_URL converts http to ws for custom URL', async () => {
    localStorage.setItem('API_BASE_URL', 'http://custom-host:4000');
    const config = await import('../js/config.js');
    expect(config.WS_BASE_URL).toBe('ws://custom-host:4000');
  });
});
