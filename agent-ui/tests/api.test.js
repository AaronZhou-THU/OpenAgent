import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the config module before importing api.js
vi.mock('../js/config.js', () => ({
  API_BASE_URL: 'http://test:8000',
  WS_BASE_URL: 'ws://test:8000',
}));

import {
  listConversations,
  getConversation,
  deleteConversation,
  createChat,
  listPresets,
  listTools,
  listSkills,
  fileUrl,
  listWorkspaceFiles,
  readWorkspaceFile,
  getHealth,
} from '../js/api.js';

describe('api.js', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockFetchOk(data) {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
      text: () => Promise.resolve(JSON.stringify(data)),
    });
  }

  function mockFetchError(status, body) {
    fetchMock.mockResolvedValue({
      ok: false,
      status,
      text: () => Promise.resolve(body),
    });
  }

  describe('listConversations', () => {
    it('calls the correct URL', async () => {
      mockFetchOk([]);
      await listConversations();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/conversations',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });

    it('returns the response data', async () => {
      const data = [{ id: 'conv-1', title: 'Test' }];
      mockFetchOk(data);
      const result = await listConversations();
      expect(result).toEqual(data);
    });
  });

  describe('getConversation', () => {
    it('calls the correct URL with id', async () => {
      mockFetchOk({ id: 'conv-123' });
      await getConversation('conv-123');
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/conversations/conv-123',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('deleteConversation', () => {
    it('uses DELETE method', async () => {
      mockFetchOk({});
      await deleteConversation('conv-456');
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/conversations/conv-456',
        expect.objectContaining({
          method: 'DELETE',
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('createChat', () => {
    it('sends POST with correct body when no arguments given', async () => {
      mockFetchOk({ conversation_id: 'new-1' });
      await createChat();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/chat',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });

    it('sends POST with system_prompt when provided', async () => {
      mockFetchOk({ conversation_id: 'new-2' });
      await createChat('You are helpful');
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.system_prompt).toBe('You are helpful');
    });

    it('sends POST with preset when provided', async () => {
      mockFetchOk({ conversation_id: 'new-3' });
      await createChat(null, 'coding');
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.preset).toBe('coding');
    });

    it('includes enableTeams when true', async () => {
      mockFetchOk({ conversation_id: 'new-4' });
      await createChat(null, null, { enableTeams: true });
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.enable_teams).toBe(true);
    });

    it('includes enableTracing when true', async () => {
      mockFetchOk({ conversation_id: 'new-5' });
      await createChat(null, null, { enableTracing: true });
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.enable_tracing).toBe(true);
    });

    it('includes enableApproval when true', async () => {
      mockFetchOk({ conversation_id: 'new-6' });
      await createChat(null, null, { enableApproval: true });
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.enable_approval).toBe(true);
    });

    it('includes all options when all are enabled', async () => {
      mockFetchOk({ conversation_id: 'new-7' });
      await createChat('prompt', 'preset-name', {
        enableTeams: true,
        enableTracing: true,
        enableApproval: true,
      });
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body).toEqual({
        system_prompt: 'prompt',
        preset: 'preset-name',
        enable_teams: true,
        enable_tracing: true,
        enable_approval: true,
      });
    });

    it('omits falsy options from the body', async () => {
      mockFetchOk({ conversation_id: 'new-8' });
      await createChat(null, null, {
        enableTeams: false,
        enableTracing: false,
        enableApproval: false,
      });
      const call = fetchMock.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body).toEqual({});
    });
  });

  describe('listPresets', () => {
    it('calls the correct URL', async () => {
      mockFetchOk([]);
      await listPresets();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/presets',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('listTools', () => {
    it('calls the correct URL', async () => {
      mockFetchOk([]);
      await listTools();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/tools',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('listSkills', () => {
    it('calls the correct URL', async () => {
      mockFetchOk([]);
      await listSkills();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/skills',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('fileUrl', () => {
    it('constructs the correct URL', () => {
      const url = fileUrl('conv-abc', 'output/report.pdf');
      expect(url).toBe('http://test:8000/api/files/conv-abc/output/report.pdf');
    });

    it('handles paths without subdirectories', () => {
      const url = fileUrl('conv-xyz', 'file.txt');
      expect(url).toBe('http://test:8000/api/files/conv-xyz/file.txt');
    });
  });

  describe('listWorkspaceFiles', () => {
    it('calls the correct URL', async () => {
      mockFetchOk([]);
      await listWorkspaceFiles();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/workspace/files',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('readWorkspaceFile', () => {
    it('calls the correct URL with the file path', async () => {
      mockFetchOk({ content: 'file contents' });
      await readWorkspaceFile('src/main.py');
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/api/workspace/file/src/main.py',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('getHealth', () => {
    it('calls the correct URL', async () => {
      mockFetchOk({ status: 'ok' });
      await getHealth();
      expect(fetchMock).toHaveBeenCalledWith(
        'http://test:8000/health',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });
  });

  describe('request error handling', () => {
    it('throws on non-ok response with status and body', async () => {
      mockFetchError(404, 'Not Found');
      await expect(listConversations()).rejects.toThrow('API 404: Not Found');
    });

    it('throws on 500 server error', async () => {
      mockFetchError(500, 'Internal Server Error');
      await expect(listConversations()).rejects.toThrow('API 500: Internal Server Error');
    });

    it('includes the response text in the error message', async () => {
      mockFetchError(403, 'Forbidden: insufficient permissions');
      await expect(listConversations()).rejects.toThrow(
        'API 403: Forbidden: insufficient permissions'
      );
    });
  });
});
