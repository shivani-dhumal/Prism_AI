<template>
  <div>
    <!-- Hero / Header -->
    <section class="hero" style="margin-bottom: 32px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; text-align: left;">
      <div>
        <h1>Code Assistant</h1>
        <p>Ask questions about your code, issues, and improvements.</p>
      </div>
      <div class="model-select-wrapper">
        <span class="model-label">
          <i class="fas fa-brain" style="color: var(--accent);"></i> AI Model:
        </span>
        <select id="modelSelect" v-model="currentModel" @change="changeModel">
          <option value="gemma">Local Gemma (Offline)</option>
          <option value="gemini">Google Gemini (Cloud)</option>
        </select>
      </div>
    </section>

    <!-- Chat Container -->
    <div class="chat-container">
      <div class="messages" ref="messagesContainer">
        <!-- Main messages list -->
        <div 
          v-for="(msg, index) in chatMessages" 
          :key="index" 
          :class="['message', msg.role]"
        >
          <div v-if="msg.role === 'assistant'">
            <strong>PrismAI:</strong><br>
            <div v-html="renderMarkdown(msg.text)"></div>
          </div>
          <div v-else>
            {{ msg.text }}
          </div>
        </div>

        <!-- System Notice -->
        <div v-if="systemNotice" class="system-notice">
          <i class="fas fa-info-circle" style="color: var(--accent);"></i> {{ systemNotice }}
        </div>

        <!-- Typing/Thinking Indicator -->
        <div v-if="thinking" class="message assistant typing-indicator">
          <span>PrismAI is thinking</span>
          <div class="dot"></div>
          <div class="dot"></div>
          <div class="dot"></div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="compose-area">
        <textarea 
          v-model="userInput" 
          @keydown.enter.exact.prevent="sendMessage"
          placeholder="Type your message... (Enter to send, Shift+Enter for newline)"
          ref="chatInput"
        ></textarea>
        <button class="btn btn-primary" @click="sendMessage" :disabled="thinking">Send</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { API, MD } from '../api.js'

const route = useRoute()

const currentModel = ref(localStorage.getItem('chat_model') || 'gemma')
const chatMessages = ref([
  {
    role: 'assistant',
    text: "Hi! I'm your AI code assistant. Ask me anything about your code, issues, or improvements. 👋"
  }
])
const userInput = ref('')
const thinking = ref(false)
const systemNotice = ref('')
const messagesContainer = ref(null)
const chatInput = ref(null)

let contextMessage = ''

onMounted(() => {
  // Get context from URL parameter (from issues or dependency graph)
  contextMessage = route.query.context || ''

  if (contextMessage) {
    const isIssueContext = contextMessage.toLowerCase().includes('issue:') || contextMessage.toLowerCase().includes('severity:')
    const contextTitle = isIssueContext ? 'code issue' : 'dependencies'
    const contextPrompt = isIssueContext 
      ? 'I can explain the root cause, why the fix works, and what risk remains.'
      : 'How would you like me to help with this?'

    chatMessages.value = [
      {
        role: 'assistant',
        text: `I see you want help with a ${contextTitle}. Here's what I understand:<br><br><pre style="background: var(--bg-alt); padding: 10px; border-radius: 4px; font-size: 11px; max-height: 200px; overflow-y: auto; color: var(--text);">${escapeHtml(contextMessage)}</pre><br>${contextPrompt}`
      }
    ]

    chatInput.value?.setAttribute('placeholder', `Ask about the ${contextTitle} above...`)
    chatInput.value?.focus()

    // If it's an issue context, auto-send the explanation request
    if (isIssueContext) {
      setTimeout(() => {
        userInput.value = 'Tell me the reason for this issue, why the fixed code works, and what could happen if I do not fix it.'
        sendMessage()
      }, 500)
    }
  }
})

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }
  return text.replace(/[&<>"']/g, m => map[m])
}

function renderMarkdown(text) {
  return MD.render(text)
}

function changeModel() {
  localStorage.setItem('chat_model', currentModel.value)
  const modelName = currentModel.value === 'gemma' ? 'Local Gemma (Offline)' : 'Google Gemini (Cloud)'
  systemNotice.value = `Switched to ${modelName}`
  setTimeout(() => {
    systemNotice.value = ''
  }, 3000)
}

async function scrollChat() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

async function sendMessage() {
  const msg = userInput.value.trim()
  if (!msg || thinking.value) return
  
  userInput.value = ''
  chatMessages.value.push({ role: 'user', text: msg })
  await scrollChat()
  
  thinking.value = true
  
  try {
    let fullMessage = msg
    if (contextMessage) {
      const isIssueContext = contextMessage.toLowerCase().includes('issue:') || contextMessage.toLowerCase().includes('severity:')
      if (isIssueContext) {
        fullMessage = `Issue Context:\n${contextMessage}\n\nQuestion: ${msg}`
      } else {
        fullMessage = `Dependency Context:\n${contextMessage}\n\nQuestion: ${msg}`
      }
    }

    let res
    if (currentModel.value === 'gemma') {
      res = await API.ollamaChat({ message: fullMessage })
    } else {
      res = await API.aiChat({ message: fullMessage })
    }

    const responseText = res.response || res || 'No response received'
    chatMessages.value.push({ role: 'assistant', text: responseText })
  } catch (err) {
    console.error('Chat error:', err)
    chatMessages.value.push({ 
      role: 'assistant', 
      text: `Error: ${err.message || 'Failed to get response'}` 
    })
  } finally {
    thinking.value = false
    await scrollChat()
  }
}
</script>

<style scoped>
.model-select-wrapper {
  background: var(--bg-alt);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: var(--shadow-sm);
}

.model-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
}

#modelSelect {
  background: transparent;
  color: var(--text);
  border: none;
  font-family: var(--f-body);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  outline: none;
}

#modelSelect option {
  background: var(--bg-card);
  color: var(--text);
}

.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 280px);
  gap: 16px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--bg-alt);
  border-radius: var(--radius-lg);
}

.message {
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  max-width: 70%;
  word-wrap: break-word;
}

.message.user {
  align-self: flex-end;
  background: var(--accent);
  color: white;
}

.message.assistant {
  align-self: flex-start;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text);
}

.system-notice {
  align-self: center;
  background: var(--bg-alt);
  font-size: 11px;
  padding: 6px 16px;
  border-radius: 20px;
  color: var(--text-2);
  margin: 12px 0;
  border: 1px dashed var(--border);
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: var(--shadow-sm);
}

.compose-area {
  display: flex;
  gap: 12px;
}

.compose-area textarea {
  flex: 1;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-family: var(--f-body);
  resize: vertical;
  min-height: 50px;
  max-height: 150px;
}

.compose-area .btn {
  align-self: flex-end;
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 20px;
}

.typing-indicator span {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  margin-right: 8px;
}

.dot {
  width: 6px;
  height: 6px;
  background: var(--accent);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}
</style>
