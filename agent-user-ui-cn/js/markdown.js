// Configure marked.js + highlight.js

const renderer = new marked.Renderer();

// Open links in new tab
renderer.link = function ({ href, title, text }) {
  const titleAttr = title ? ` title="${title}"` : '';
  return `<a href="${href}"${titleAttr} target="_blank" rel="noopener">${text}</a>`;
};

marked.setOptions({
  renderer,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

export function renderMarkdown(text) {
  const raw = marked.parse(text);
  if (typeof DOMPurify !== 'undefined') {
    return DOMPurify.sanitize(raw);
  }
  return raw;
}
