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

async function importFresh(modulePath) {
  const url = new URL(`../${modulePath}`, import.meta.url);
  url.searchParams.set('t', `${Date.now()}-${Math.random()}`);
  return import(url.href);
}

test('fileUrl uses the configured API base URL', async () => {
  globalThis.localStorage = createStorage({ API_BASE_URL: 'https://example.test' });
  const api = await importFresh('js/api.js');
  assert.equal(api.fileUrl('conv-1', 'notes.txt'), 'https://example.test/api/files/conv-1/notes.txt');
});

test('createChat sends the expected request body', async () => {
  globalThis.localStorage = createStorage({ API_BASE_URL: 'https://example.test' });

  let called = null;
  globalThis.fetch = async (url, options) => {
    called = { url, options };
    return {
      ok: true,
      async json() {
        return { conversation_id: 'abc123' };
      },
    };
  };

  const api = await importFresh('js/api.js');
  const result = await api.createChat(null, 'coding');

  assert.deepEqual(result, { conversation_id: 'abc123' });
  assert.equal(called.url, 'https://example.test/api/chat');
  assert.equal(called.options.method, 'POST');
  assert.equal(called.options.body, JSON.stringify({ preset: 'coding' }));
});
