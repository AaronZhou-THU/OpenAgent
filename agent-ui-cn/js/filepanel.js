// File Panel — workspace file browser
// Self-initializing module: creates DOM, binds events on import

import { state, on } from './state.js';
import { listWorkspaceFiles, readWorkspaceFile, fileUrl, uploadWorkspaceFiles } from './api.js';

const STORAGE_KEY = 'filepanel:open';

let files = [];
let currentView = 'list'; // 'list' | 'preview'
let currentFile = null;   // preview data from API

// ===== DOM Setup =====

const panel = document.createElement('aside');
panel.id = 'file-panel';
panel.className = 'file-panel collapsed';
panel.innerHTML = `
  <div class="fp-header">
    <div class="fp-header-left">
      <button class="fp-back-btn" style="display:none" title="返回文件列表">&#8592;</button>
      <span class="fp-title">文件</span>
    </div>
    <div class="fp-header-right">
      <button class="fp-upload-btn" title="上传文件">&#8593;</button>
      <button class="fp-refresh-btn" title="刷新文件列表">&#8635;</button>
      <button class="fp-close-btn" title="关闭面板">&times;</button>
    </div>
  </div>
  <div class="fp-body">
    <div class="fp-list"></div>
    <div class="fp-preview" style="display:none">
      <div class="fp-preview-meta"></div>
      <div class="fp-preview-content"></div>
    </div>
    <div class="fp-empty">暂无文件</div>
  </div>
`;

// Insert as last child of #app (after chat-area)
const app = document.getElementById('app');
if (app) {
  app.appendChild(panel);
}

// Hidden file input for uploads
const fileInput = document.createElement('input');
fileInput.type = 'file';
fileInput.multiple = true;
fileInput.style.display = 'none';
panel.appendChild(fileInput);

// Refs
const backBtn = panel.querySelector('.fp-back-btn');
const titleEl = panel.querySelector('.fp-title');
const uploadBtn = panel.querySelector('.fp-upload-btn');
const refreshBtn = panel.querySelector('.fp-refresh-btn');
const closeBtn = panel.querySelector('.fp-close-btn');
const bodyEl = panel.querySelector('.fp-body');
const listEl = panel.querySelector('.fp-list');
const previewEl = panel.querySelector('.fp-preview');
const previewMeta = panel.querySelector('.fp-preview-meta');
const previewContent = panel.querySelector('.fp-preview-content');
const emptyEl = panel.querySelector('.fp-empty');

// ===== Toggle Button (injected into chat header) =====

const toggleBtn = document.createElement('button');
toggleBtn.id = 'files-toggle';
toggleBtn.className = 'dev-toggle-btn files-toggle-btn';
toggleBtn.textContent = '文件';
toggleBtn.title = '切换文件面板';

const headerRight = document.querySelector('.header-right');
if (headerRight) {
  headerRight.insertBefore(toggleBtn, headerRight.firstChild);
}

// ===== State Persistence =====

function isOpen() {
  return localStorage.getItem(STORAGE_KEY) === '1';
}

function setOpen(open) {
  localStorage.setItem(STORAGE_KEY, open ? '1' : '0');
  panel.classList.toggle('collapsed', !open);
  toggleBtn.classList.toggle('active', open);
}

// Restore state
setOpen(isOpen());
if (isOpen()) refreshFiles();

// ===== Event Handlers =====

toggleBtn.addEventListener('click', () => {
  const opening = !isOpen();
  setOpen(opening);
  if (opening) {
    refreshFiles();
  }
});

closeBtn.addEventListener('click', () => setOpen(false));

refreshBtn.addEventListener('click', () => refreshFiles());

backBtn.addEventListener('click', () => showListView());

// Upload: button + hidden input
uploadBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) {
    handleUpload(fileInput.files);
    fileInput.value = '';
  }
});

// Drag-and-drop on the file panel body
bodyEl.addEventListener('dragover', (e) => {
  e.preventDefault();
  bodyEl.classList.add('fp-dragover');
});
bodyEl.addEventListener('dragleave', (e) => {
  e.preventDefault();
  bodyEl.classList.remove('fp-dragover');
});
bodyEl.addEventListener('drop', (e) => {
  e.preventDefault();
  bodyEl.classList.remove('fp-dragover');
  if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files);
});

// ===== File List =====

async function refreshFiles() {
  try {
    files = await listWorkspaceFiles();
  } catch (err) {
    console.error('Failed to list workspace files:', err);
    files = [];
  }
  renderFileList();
}

async function handleUpload(fileList) {
  try {
    await uploadWorkspaceFiles(fileList);
    refreshFiles();
  } catch (err) {
    console.error('Upload failed:', err);
    alert('上传失败：' + err.message);
  }
}

function renderFileList() {
  listEl.innerHTML = '';

  if (files.length === 0) {
    emptyEl.style.display = '';
    listEl.style.display = 'none';
    return;
  }

  emptyEl.style.display = 'none';
  listEl.style.display = '';

  // Sort: directories (by path depth) then by name
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));

  for (const f of sorted) {
    const item = document.createElement('div');
    item.className = 'fp-file-item';
    item.innerHTML = `
      <span class="fp-file-icon">${fileIcon(f.name)}</span>
      <div class="fp-file-info">
        <span class="fp-file-name" title="${escapeAttr(f.path)}">${escapeHtml(f.path)}</span>
        <span class="fp-file-size">${formatSize(f.size)}</span>
      </div>
    `;
    item.addEventListener('click', () => openFile(f));
    listEl.appendChild(item);
  }
}

// ===== File Preview =====

async function openFile(f) {
  // Show loading state
  currentView = 'preview';
  previewEl.style.display = '';
  listEl.style.display = 'none';
  emptyEl.style.display = 'none';
  backBtn.style.display = '';
  refreshBtn.style.display = 'none';
  titleEl.textContent = f.name;
  previewContent.innerHTML = '<div class="fp-loading">加载中...</div>';
  previewMeta.innerHTML = '';

  try {
    currentFile = await readWorkspaceFile(f.path);
  } catch (err) {
    previewContent.innerHTML = `<div class="fp-error">文件加载失败</div>`;
    return;
  }

  // Meta bar: size + download link
  const dlUrl = state.conversationId ? fileUrl(state.conversationId, f.path) : '#';
  previewMeta.innerHTML = `
    <span class="fp-meta-size">${formatSize(currentFile.size)}</span>
    <a class="fp-meta-download" href="${escapeAttr(dlUrl)}" download="${escapeAttr(currentFile.name)}" target="_blank" title="下载">&#8595; 下载</a>
  `;

  if (currentFile.binary) {
    previewContent.innerHTML = `<div class="fp-binary-notice">二进制文件 &mdash; 无法预览</div>`;
    return;
  }

  if (currentFile.content === null || currentFile.content === undefined) {
    previewContent.innerHTML = `<div class="fp-binary-notice">无可用内容</div>`;
    return;
  }

  // Render content with syntax highlighting
  const lang = currentFile.language;
  const ext = f.name.split('.').pop().toLowerCase();

  // Markdown files: render as HTML (sanitized)
  if (lang === 'markdown' || ext === 'md') {
    let html = (typeof marked !== 'undefined' && marked.parse)
      ? marked.parse(currentFile.content)
      : escapeHtml(currentFile.content);
    if (typeof DOMPurify !== 'undefined') {
      html = DOMPurify.sanitize(html);
    }
    previewContent.innerHTML = `<div class="fp-markdown message-content">${html}</div>`;
    return;
  }

  // Code files: syntax highlight
  const pre = document.createElement('pre');
  const code = document.createElement('code');
  if (lang) {
    code.className = `language-${lang}`;
  }
  code.textContent = currentFile.content;
  pre.appendChild(code);
  previewContent.innerHTML = '';
  previewContent.appendChild(pre);

  if (typeof hljs !== 'undefined') {
    hljs.highlightElement(code);
  }
}

function showListView() {
  currentView = 'list';
  currentFile = null;
  previewEl.style.display = 'none';
  backBtn.style.display = 'none';
  refreshBtn.style.display = '';
  titleEl.textContent = '文件';
  renderFileList();
}

// ===== Event Bus Subscriptions =====

// Auto-refresh when agent finishes (done event includes files)
on('ws:event', (event) => {
  if (event.type === 'done' && isOpen()) {
    refreshFiles();
  }
});

// Reset when switching conversations
on('conversation:select', () => {
  files = [];
  showListView();
  if (isOpen()) {
    refreshFiles();
  }
});

// ===== Helpers =====

function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const icons = {
    py: '\u{1F40D}', js: '\u{1F7E8}', ts: '\u{1F535}', jsx: '\u{269B}', tsx: '\u{269B}',
    html: '\u{1F310}', css: '\u{1F3A8}', json: '\u{1F4CB}', md: '\u{1F4DD}',
    pdf: '\u{1F4D5}', docx: '\u{1F4C4}', xlsx: '\u{1F4CA}', pptx: '\u{1F4CA}',
    png: '\u{1F5BC}', jpg: '\u{1F5BC}', jpeg: '\u{1F5BC}', gif: '\u{1F5BC}', svg: '\u{1F5BC}',
    zip: '\u{1F4E6}', tar: '\u{1F4E6}', gz: '\u{1F4E6}',
    sh: '\u{1F4DF}', bash: '\u{1F4DF}',
    sql: '\u{1F5C3}', csv: '\u{1F4C8}',
    txt: '\u{1F4C3}', log: '\u{1F4C3}',
  };
  return icons[ext] || '\u{1F4C4}';
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(str) {
  if (typeof str !== 'string') str = String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  return escapeHtml(str);
}
