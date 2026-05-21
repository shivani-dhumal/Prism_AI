/* PrismAI API helper */
const API = (() => {
  async function req(url, options = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
      body: options.body && typeof options.body !== "string"
        ? JSON.stringify(options.body)
        : options.body,
    });
    const text = await res.text();
    let data;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) {
      const err = new Error((data && data.error) || `HTTP ${res.status}`);
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;
  }

  return {
    // Scans
    validatePath:   (path) => req("/api/validate-path", { method: "POST", body: { path } }),
    startScan:      (folder_path, scan_name) => req("/api/scan", { method: "POST", body: { folder_path, scan_name } }),
    scanStatus:     (id) => req(`/api/scan/${id}/status`),
    listScans:      () => req("/api/scans"),
    deleteScan:     (id) => req(`/api/scan/${id}`, { method: "DELETE" }),

    // Dashboard / files / code
    dashboard:      () => req("/api/dashboard-data"),
    currentProject: () => req("/api/current-project"),
    fileTree:       () => req("/api/file-tree"),
    architecture:   () => req("/api/architecture"),
    fileContent:    (path) => req(`/api/file/content?path=${encodeURIComponent(path)}`),
    fileAnnotations:(path) => req(`/api/file/annotations?path=${encodeURIComponent(path)}`),

    // Bugs
    allBugs:        () => req("/api/all-bugs"),
    bugSummary:     () => req("/api/bugs/summary"),
    bugsByFile:     (path) => req(`/api/bugs/file?path=${encodeURIComponent(path)}`),
    updateBugStatus:(id, status, fixed_code) => req(`/api/bugs/${id}/status`, { method: "PATCH", body: { status, fixed_code } }),
    aiFix:          (id, body) => req(`/api/bugs/${id}/ai-fix`, { method: "POST", body }),
    applyFix:       (id, body) => req(`/api/bugs/${id}/apply-fix`, { method: "POST", body }),

    // AI Chat
    aiChat:         (body) => req("/api/ai/chat", { method: "POST", body }),
    ollamaChat:     (body) => req("/api/ollama/chat", { method: "POST", body }),

    // Helpers
    severityClass: (s) => `sev-${(s || "").toLowerCase()}`,
    statusClass:   (s) => `status-${(s || "open").toLowerCase()}`,
    formatPath:    (p) => (p || "").split(/[\\\/]/).pop() || p,
    shortPath:     (p, max = 60) => {
      if (!p) return "";
      if (p.length <= max) return p;
      return "..." + p.slice(-max + 1);
    },
    timeAgo: (iso) => {
      if (!iso) return "-";
      const d = new Date(iso);
      const diff = (Date.now() - d.getTime()) / 1000;
      if (diff < 60) return "just now";
      if (diff < 3600) return Math.floor(diff / 60) + "m ago";
      if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
      if (diff < 86400 * 7) return Math.floor(diff / 86400) + "d ago";
      return d.toLocaleDateString();
    },
  };
})();

// Tiny markdown renderer for chat
const MD = {
  render(text) {
    if (!text) return "";
    let s = text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    s = s.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="md-pre"><code class="md-code lang-${lang || "txt"}">${code.trim()}</code></pre>`);
    s = s.replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|\s)\*([^*\n]+)\*/g, "$1<em>$2</em>");
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    s = s.replace(/\n/g, "<br>");
    return s;
  }
};
