import assert from 'node:assert/strict';
import test from 'node:test';

function createStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
    clear() {
      store.clear();
    },
  };
}

async function importFreshConfig() {
  const url = new URL('../js/config.js', import.meta.url);
  url.searchParams.set('t', `${Date.now()}-${Math.random()}`);
  return import(url.href);
}

test('API_BASE_URL defaults to localhost', async () => {
  globalThis.localStorage = createStorage();
  const config = await importFreshConfig();
  assert.equal(config.API_BASE_URL, 'http://localhost:8000');
  assert.equal(config.WS_BASE_URL, 'ws://localhost:8000');
});

test('API_BASE_URL respects localStorage override', async () => {
  globalThis.localStorage = createStorage({ API_BASE_URL: 'https://agent.example.com' });
  const config = await importFreshConfig();
  assert.equal(config.API_BASE_URL, 'https://agent.example.com');
  assert.equal(config.WS_BASE_URL, 'wss://agent.example.com');
});
