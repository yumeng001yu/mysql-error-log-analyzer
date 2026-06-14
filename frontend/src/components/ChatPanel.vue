<template>
  <div class="chat-panel">
    <!-- 快捷操作 -->
    <div class="quick-actions">
      <button
        v-for="action in quickActions"
        :key="action.text"
        class="quick-btn"
        @click="sendQuick(action.text)"
      >{{ action.label }}</button>
    </div>

    <!-- 消息列表 -->
    <div class="message-list" ref="messageListRef">
      <div v-if="messages.length === 0" class="empty-chat">
        <div class="empty-icon">💬</div>
        <p>向 AI 助手提问关于 MySQL 错误日志的问题</p>
      </div>
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="message"
        :class="msg.role"
      >
        <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="msg-content">
          <div v-if="msg.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
          <div v-else class="msg-text">{{ msg.content }}</div>
        </div>
      </div>
      <div v-if="loading" class="message assistant">
        <div class="msg-avatar">🤖</div>
        <div class="msg-content">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <textarea
        v-model="inputText"
        @keydown.enter.exact.prevent="sendMessage"
        placeholder="输入问题，按 Enter 发送..."
        rows="1"
        ref="inputRef"
      ></textarea>
      <button class="send-btn" @click="sendMessage" :disabled="loading || !inputText.trim()">
        发送
      </button>
    </div>
  </div>
</template>

<script>
import { ref, nextTick, onMounted } from 'vue'
import { api } from '../api.js'
import { marked } from 'marked'

export default {
  name: 'ChatPanel',
  setup() {
    const messages = ref([])
    const inputText = ref('')
    const loading = ref(false)
    const messageListRef = ref(null)
    const inputRef = ref(null)

    const quickActions = [
      { label: '📊 分析最近1小时', text: '分析最近1小时的错误日志' },
      { label: '📊 分析最近3小时', text: '分析最近3小时的错误日志' },
      { label: '📊 分析最近24小时', text: '分析最近24小时的错误日志' },
      { label: '🔒 查看死锁信息', text: '查看最近的死锁信息' },
      { label: '⚠️ 关键告警', text: '当前有哪些关键告警？' },
      { label: '💡 修复建议', text: '给出最近的错误修复建议' }
    ]

    function renderMarkdown(text) {
      if (!text) return ''
      try {
        return marked.parse(text)
      } catch {
        return text.replace(/\n/g, '<br>')
      }
    }

    function scrollToBottom() {
      nextTick(() => {
        if (messageListRef.value) {
          messageListRef.value.scrollTop = messageListRef.value.scrollHeight
        }
      })
    }

    async function sendMessage() {
      const text = inputText.value.trim()
      if (!text || loading.value) return

      messages.value.push({ role: 'user', content: text })
      inputText.value = ''
      loading.value = true
      scrollToBottom()

      try {
        const res = await api.sendChat({ message: text, history: messages.value.slice(-10) })
        const reply = res.data?.response || res.data?.content || res.data?.message || (typeof res.data === 'string' ? res.data : '未获取到回复')
        messages.value.push({ role: 'assistant', content: reply })
      } catch (e) {
        messages.value.push({ role: 'assistant', content: '❌ 请求失败，请稍后重试。' })
      } finally {
        loading.value = false
        scrollToBottom()
      }
    }

    function sendQuick(text) {
      inputText.value = text
      sendMessage()
    }

    onMounted(() => {
      inputRef.value?.focus()
    })

    return {
      messages, inputText, loading,
      messageListRef, inputRef,
      quickActions, renderMarkdown,
      sendMessage, sendQuick
    }
  }
}
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 130px);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.quick-actions {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.quick-btn {
  padding: 5px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 16px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
  white-space: nowrap;
}

.quick-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent-blue);
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-chat {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.message {
  display: flex;
  gap: 10px;
  max-width: 85%;
}

.message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.msg-avatar {
  font-size: 22px;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.msg-content {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.message.user .msg-content {
  background: var(--accent-blue);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .msg-content {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
}

.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  margin: 10px 0 6px;
  font-size: 15px;
}

.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 20px;
}

.markdown-body :deep(code) {
  background: var(--bg-primary);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
}

.markdown-body :deep(pre) {
  background: var(--bg-primary);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing 1.2s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-4px); }
}

/* 输入区 */
.input-area {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.input-area textarea {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  resize: none;
  outline: none;
  font-family: inherit;
  min-height: 38px;
  max-height: 120px;
}

.input-area textarea:focus {
  border-color: var(--accent-blue);
}

.send-btn {
  padding: 8px 20px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── 移动端适配 ────────────────────────────────────────── */
@media (max-width: 768px) {
  .chat-panel {
    height: calc(100vh - 100px);
  }

  .quick-actions {
    padding: 8px 10px;
    gap: 6px;
  }

  .quick-btn {
    padding: 4px 8px;
    font-size: 11px;
  }

  .message-list {
    padding: 10px;
    gap: 10px;
  }

  .message {
    max-width: 90%;
  }

  .msg-avatar {
    font-size: 18px;
    width: 28px;
    height: 28px;
  }

  .msg-content {
    padding: 8px 10px;
    font-size: 13px;
  }

  .input-area {
    padding: 8px 10px;
    gap: 8px;
  }

  .input-area textarea {
    font-size: 16px; /* 防止 iOS 自动缩放 */
    min-height: 36px;
  }

  .send-btn {
    padding: 8px 14px;
    font-size: 13px;
  }
}
</style>
