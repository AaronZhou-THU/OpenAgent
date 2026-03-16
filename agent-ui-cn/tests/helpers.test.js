import { describe, it, expect } from 'vitest';

// These helper functions are defined inside renderer.js and app.js as private
// (non-exported) functions. We re-implement them here identically to verify
// the logic in isolation via unit tests.

function escapeHtml(str) {
  if (typeof str !== 'string') str = String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatToolContent(content) {
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

function formatNumber(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return String(n);
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

describe('escapeHtml', () => {
  it('escapes ampersands', () => {
    expect(escapeHtml('foo & bar')).toBe('foo &amp; bar');
  });

  it('escapes less-than signs', () => {
    expect(escapeHtml('<script>')).toBe('&lt;script&gt;');
  });

  it('escapes greater-than signs', () => {
    expect(escapeHtml('a > b')).toBe('a &gt; b');
  });

  it('escapes double quotes', () => {
    expect(escapeHtml('say "hello"')).toBe('say &quot;hello&quot;');
  });

  it('escapes all special characters together', () => {
    expect(escapeHtml('<div class="test"> & </div>')).toBe(
      '&lt;div class=&quot;test&quot;&gt; &amp; &lt;/div&gt;'
    );
  });

  it('handles non-string input by converting to string', () => {
    expect(escapeHtml(42)).toBe('42');
    expect(escapeHtml(true)).toBe('true');
  });

  it('handles null input by returning empty string', () => {
    expect(escapeHtml(null)).toBe('');
  });

  it('handles undefined input by returning empty string', () => {
    expect(escapeHtml(undefined)).toBe('');
  });

  it('returns empty string for empty string input', () => {
    expect(escapeHtml('')).toBe('');
  });
});

describe('formatToolContent', () => {
  it('returns string input as-is', () => {
    expect(formatToolContent('hello world')).toBe('hello world');
  });

  it('returns JSON string for object input', () => {
    const obj = { key: 'value', count: 1 };
    expect(formatToolContent(obj)).toBe(JSON.stringify(obj, null, 2));
  });

  it('returns JSON string for array input', () => {
    const arr = [1, 2, 3];
    expect(formatToolContent(arr)).toBe(JSON.stringify(arr, null, 2));
  });

  it('returns String() for non-serializable input', () => {
    // BigInt throws on JSON.stringify
    const circular = {};
    circular.self = circular;
    expect(formatToolContent(circular)).toBe('[object Object]');
  });

  it('handles null input', () => {
    expect(formatToolContent(null)).toBe('null');
  });

  it('handles numeric input', () => {
    expect(formatToolContent(42)).toBe('42');
  });
});

describe('formatNumber', () => {
  it('returns numbers less than 1000 as a plain string', () => {
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(999)).toBe('999');
    expect(formatNumber(1)).toBe('1');
  });

  it('formats numbers >= 1000 as k', () => {
    expect(formatNumber(1000)).toBe('1.0k');
    expect(formatNumber(1500)).toBe('1.5k');
    expect(formatNumber(999999)).toBe('1000.0k');
  });

  it('formats numbers >= 1000000 as M', () => {
    expect(formatNumber(1000000)).toBe('1.0M');
    expect(formatNumber(2500000)).toBe('2.5M');
    expect(formatNumber(10000000)).toBe('10.0M');
  });

  it('formats boundary values correctly', () => {
    expect(formatNumber(999)).toBe('999');
    expect(formatNumber(1000)).toBe('1.0k');
    expect(formatNumber(999999)).toBe('1000.0k');
    expect(formatNumber(1000000)).toBe('1.0M');
  });
});

describe('formatFileSize', () => {
  it('formats bytes less than 1024 as B', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(1023)).toBe('1023 B');
  });

  it('formats bytes >= 1024 and < 1024*1024 as KB', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(1536)).toBe('1.5 KB');
    expect(formatFileSize(10240)).toBe('10.0 KB');
  });

  it('formats bytes >= 1024*1024 as MB', () => {
    expect(formatFileSize(1048576)).toBe('1.0 MB');
    expect(formatFileSize(2621440)).toBe('2.5 MB');
    expect(formatFileSize(10485760)).toBe('10.0 MB');
  });

  it('formats boundary values correctly', () => {
    expect(formatFileSize(1023)).toBe('1023 B');
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(1048575)).toBe('1024.0 KB');
    expect(formatFileSize(1048576)).toBe('1.0 MB');
  });
});
