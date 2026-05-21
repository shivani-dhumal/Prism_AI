/**
 * Gemini AI Chatbot - Frontend Logic
 * Handles chat UI, streaming responses, conversations, and markdown rendering.
 */

// ═══ State ═══
let currentConversationId = null;
let isStreaming = false;

// ═══ DOM Elements ═══
const $ = (sel) => document.querySelector(sel);
const messagesContainer = $("#messages-container");
const messagesList = $("#messages-list");
const welcomeScreen = $("#welcome-screen");
const typingIndicator = $("#typing-indicator");
const messageInput = $("#message-input");
const sendBtn = $("#send-btn");
const newChatBtn = $("#new-chat-btn");
const sidebarToggle = $("#sidebar-toggle");
const sidebar = $("#sidebar");
const conversationList = $("#conversation-list");
const chatTitle = $("#chat-title");
const clearChatBtn = $("#clear-chat-btn");
const searchInput = $("#search-input");

// ═══ Markdown Setup ═══
marked.setOptions({
    highlight: (code, lang) => {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true,
    gfm: true,
});

// Custom renderer for code blocks with copy button
const renderer = new marked.Renderer();
renderer.code = function (code, language) {
    const lang = language || "plaintext";
    const highlighted = lang && hljs.getLanguage(lang)
        ? hljs.highlight(code, { language: lang }).value
        : hljs.highlightAuto(code).value;
    const id = "code-" + Math.random().toString(36).substr(2, 9);
    return `<pre><div class="code-header"><span>${lang}</span><button class="copy-btn" onclick="copyCode('${id}', this)">Copy</button></div><code id="${id}" class="hljs language-${lang}">${highlighted}</code></pre>`;
};
marked.setOptions({ renderer });

// ═══ Copy Code ═══
window.copyCode = function (id, btn) {
    const codeEl = document.getElementById(id);
    if (!codeEl) return;
    navigator.clipboard.writeText(codeEl.textContent).then(() => {
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(() => {
            btn.textContent = "Copy";
            btn.classList.remove("copied");
        }, 2000);
    });
};

// ═══ Auto-resize textarea ═══
messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + "px";
    sendBtn.disabled = !messageInput.value.trim();
});

// ═══ Send on Enter ═══
messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (messageInput.value.trim() && !isStreaming) sendMessage();
    }
});

sendBtn.addEventListener("click", () => {
    if (messageInput.value.trim() && !isStreaming) sendMessage();
});

// ═══ Sidebar Toggle ═══
sidebarToggle.addEventListener("click", () => sidebar.classList.toggle("collapsed"));

// ═══ New Chat ═══
newChatBtn.addEventListener("click", () => startNewChat());

// ═══ Clear Chat ═══
clearChatBtn.addEventListener("click", () => {
    if (currentConversationId) {
        fetch(`/api/conversations/${currentConversationId}`, { method: "DELETE" });
        delete currentConversationId;
    }
    startNewChat();
});

// ═══ Search ═══
searchInput.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll(".conv-item").forEach((item) => {
        const text = item.querySelector(".conv-item-text").textContent.toLowerCase();
        item.style.display = text.includes(q) ? "flex" : "none";
    });
});

// ═══ Suggestion Cards ═══
document.querySelectorAll(".suggestion-card").forEach((card) => {
    card.addEventListener("click", () => {
        messageInput.value = card.dataset.prompt;
        messageInput.dispatchEvent(new Event("input"));
        sendMessage();
    });
});

// ═══ Core: Send Message ═══
async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || isStreaming) return;

    isStreaming = true;
    messageInput.value = "";
    messageInput.style.height = "auto";
    sendBtn.disabled = true;

    // Hide welcome screen
    welcomeScreen.classList.add("hidden");

    // Add user message to UI
    appendMessage("user", text);

    // Show typing
    typingIndicator.classList.remove("hidden");
    scrollToBottom();

    try {
        const res = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                conversation_id: currentConversationId,
            }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Request failed");
        }

        // Hide typing, create assistant message
        typingIndicator.classList.add("hidden");
        const assistantEl = appendMessage("assistant", "");
        const contentEl = assistantEl.querySelector(".message-content");

        // Read SSE stream
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === "meta") {
                        currentConversationId = data.conversation_id;
                        chatTitle.textContent = data.title;
                        loadConversations();
                    } else if (data.type === "chunk") {
                        fullText += data.content;
                        contentEl.innerHTML = marked.parse(fullText);
                        scrollToBottom();
                    } else if (data.type === "error") {
                        contentEl.innerHTML = `<span style="color:#ef4444;">Error: ${data.content}</span>`;
                    }
                } catch (_) { /* skip malformed */ }
            }
        }

        // Final render
        contentEl.innerHTML = marked.parse(fullText);
        hljs.highlightAll();

    } catch (err) {
        typingIndicator.classList.add("hidden");
        appendMessage("assistant", `**Error:** ${err.message}`);
    }

    isStreaming = false;
    sendBtn.disabled = false;
    messageInput.focus();
    scrollToBottom();
}

// ═══ Append Message to DOM ═══
function appendMessage(role, content) {
    const div = document.createElement("div");
    div.className = `message ${role}`;

    const avatarHTML =
        role === "user"
            ? `<div class="message-avatar">U</div>`
            : `<div class="message-avatar"><svg viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" fill="url(#g1)" opacity="0.9"/><path d="M2 17l10 5 10-5" stroke="url(#g1)" stroke-width="1.5" fill="none"/><path d="M2 12l10 5 10-5" stroke="url(#g1)" stroke-width="1.5" fill="none"/><defs><linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#fff"/><stop offset="100%" style="stop-color:#e0d4ff"/></linearGradient></defs></svg></div>`;

    const rendered = content ? marked.parse(content) : "";
    div.innerHTML = `${avatarHTML}<div class="message-content">${rendered}</div>`;
    messagesList.appendChild(div);
    scrollToBottom();
    return div;
}

// ═══ Scroll ═══
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ═══ Load Conversations ═══
async function loadConversations() {
    try {
        const res = await fetch("/api/conversations");
        const convs = await res.json();
        conversationList.innerHTML = "";

        convs.forEach((c) => {
            const item = document.createElement("div");
            item.className = `conv-item ${c.id === currentConversationId ? "active" : ""}`;
            item.innerHTML = `
                <svg class="conv-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <span class="conv-item-text">${c.title}</span>
                <button class="conv-item-delete" title="Delete">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                    </svg>
                </button>
            `;

            item.addEventListener("click", (e) => {
                if (e.target.closest(".conv-item-delete")) return;
                loadConversation(c.id);
            });

            item.querySelector(".conv-item-delete").addEventListener("click", (e) => {
                e.stopPropagation();
                deleteConversation(c.id);
            });

            conversationList.appendChild(item);
        });
    } catch (err) {
        console.error("Failed to load conversations:", err);
    }
}

// ═══ Load Single Conversation ═══
async function loadConversation(id) {
    try {
        const res = await fetch(`/api/conversations/${id}`);
        const conv = await res.json();

        currentConversationId = id;
        chatTitle.textContent = conv.title;

        // Clear and rebuild messages
        messagesList.innerHTML = "";
        welcomeScreen.classList.add("hidden");

        conv.messages.forEach((msg) => appendMessage(msg.role, msg.content));

        // Update active state in sidebar
        document.querySelectorAll(".conv-item").forEach((el) => el.classList.remove("active"));
        document.querySelectorAll(".conv-item").forEach((el) => {
            if (el.querySelector(".conv-item-text").textContent === conv.title) {
                el.classList.add("active");
            }
        });

        scrollToBottom();
    } catch (err) {
        console.error("Failed to load conversation:", err);
    }
}

// ═══ Delete Conversation ═══
async function deleteConversation(id) {
    await fetch(`/api/conversations/${id}`, { method: "DELETE" });
    if (currentConversationId === id) startNewChat();
    loadConversations();
}

// ═══ Start New Chat ═══
function startNewChat() {
    currentConversationId = null;
    messagesList.innerHTML = "";
    welcomeScreen.classList.remove("hidden");
    chatTitle.textContent = "New Chat";
    document.querySelectorAll(".conv-item").forEach((el) => el.classList.remove("active"));
    messageInput.focus();
}

// ═══ Init ═══
loadConversations();
messageInput.focus();
