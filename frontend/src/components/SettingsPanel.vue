<template>
  <div class="settings-panel">
    <!-- 提示消息 -->
    <transition name="fade">
      <div v-if="message.text" class="message-bar" :class="message.type">
        {{ message.text }}
      </div>
    </transition>

    <!-- LLM 大模型配置 -->
    <div class="config-card">
      <div class="card-header">
        <h3>🤖 LLM 大模型配置</h3>
        <button
          class="test-btn"
          :disabled="testingLLM"
          @click="testLLMConnection"
        >
          {{ testingLLM ? '测试中...' : '测试连接' }}
        </button>
      </div>
      <div class="form-grid">
        <div class="form-group">
          <label>Provider</label>
          <select v-model="llm.provider">
            <option value="openai">OpenAI</option>
            <option value="ollama">Ollama</option>
            <option value="custom">Custom</option>
          </select>
        </div>
        <div class="form-group">
          <label>Model</label>
          <input type="text" v-model="llm.model" placeholder="gpt-4" />
        </div>
        <div class="form-group full-width">
          <label>API Base URL</label>
          <input type="text" v-model="llm.api_base_url" placeholder="https://api.openai.com/v1" />
        </div>
        <div class="form-group full-width">
          <label>API Key</label>
          <input type="password" v-model="llm.api_key" placeholder="sk-..." />
        </div>
        <div class="form-group">
          <label>Temperature</label>
          <input type="number" v-model.number="llm.temperature" min="0" max="1" step="0.1" />
        </div>
        <div class="form-group">
          <label>Timeout (秒)</label>
          <input type="number" v-model.number="llm.timeout" min="1" />
        </div>
      </div>
    </div>

    <!-- Embedding 模型配置 -->
    <div class="config-card">
      <div class="card-header">
        <h3>📐 Embedding 模型配置</h3>
        <div class="header-actions">
          <label class="toggle-label">
            <input type="checkbox" v-model="embedding.enabled" />
            <span>启用</span>
          </label>
          <button
            class="test-btn"
            :disabled="testingEmbedding || !embedding.enabled"
            @click="testEmbeddingConnection"
          >
            {{ testingEmbedding ? '测试中...' : '测试连接' }}
          </button>
        </div>
      </div>
      <div class="form-grid" :class="{ disabled: !embedding.enabled }">
        <div class="form-group">
          <label>Provider</label>
          <select v-model="embedding.provider">
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI</option>
            <option value="custom">Custom</option>
          </select>
        </div>
        <div class="form-group">
          <label>Model</label>
          <input type="text" v-model="embedding.model" placeholder="nomic-embed-text" />
        </div>
        <div class="form-group full-width">
          <label>API Base URL</label>
          <input type="text" v-model="embedding.api_base_url" placeholder="http://localhost:11434" />
        </div>
        <div class="form-group full-width">
          <label>API Key</label>
          <input type="password" v-model="embedding.api_key" placeholder="留空则不需要" />
        </div>
        <div class="form-group">
          <label>Dimension</label>
          <input type="number" v-model.number="embedding.dimension" min="1" />
        </div>
        <div class="form-group">
          <label>Batch Size</label>
          <input type="number" v-model.number="embedding.batch_size" min="1" />
        </div>
      </div>
    </div>

    <!-- 保存按钮 -->
    <div class="actions">
      <button class="save-btn" :disabled="saving" @click="saveSettings">
        {{ saving ? '保存中...' : '保存配置' }}
      </button>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../api.js'

export default {
  name: 'SettingsPanel',
  setup() {
    const llm = reactive({
      provider: 'openai',
      model: 'gpt-4',
      api_base_url: '',
      api_key: '',
      temperature: 0.3,
      timeout: 60
    })

    const embedding = reactive({
      enabled: false,
      provider: 'ollama',
      model: 'nomic-embed-text',
      api_base_url: '',
      api_key: '',
      dimension: 768,
      batch_size: 32
    })

    const saving = ref(false)
    const testingLLM = ref(false)
    const testingEmbedding = ref(false)
    const message = reactive({ text: '', type: '' })

    function showMessage(text, type = 'success') {
      message.text = text
      message.type = type
      setTimeout(() => {
        message.text = ''
      }, 3000)
    }

    async function loadSettings() {
      try {
        const res = await api.getSettings()
        const data = res.data || {}
        if (data.llm) {
          Object.keys(data.llm).forEach(key => {
            if (key in llm) llm[key] = data.llm[key]
          })
        }
        if (data.embedding) {
          Object.keys(data.embedding).forEach(key => {
            if (key in embedding) embedding[key] = data.embedding[key]
          })
        }
      } catch {
        // 首次加载失败时使用默认值
      }
    }

    async function saveSettings() {
      saving.value = true
      try {
        await api.saveSettings({ llm: { ...llm }, embedding: { ...embedding } })
        showMessage('✅ 配置保存成功', 'success')
      } catch (e) {
        showMessage('❌ 保存失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
      } finally {
        saving.value = false
      }
    }

    async function testLLMConnection() {
      testingLLM.value = true
      try {
        const res = await api.testLLM({ ...llm })
        const ok = res.data?.success ?? res.data?.ok
        if (ok) {
          showMessage('✅ LLM 连接成功', 'success')
        } else {
          showMessage('❌ LLM 连接失败：' + (res.data?.error || res.data?.message || '未知错误'), 'error')
        }
      } catch (e) {
        showMessage('❌ LLM 连接失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
      } finally {
        testingLLM.value = false
      }
    }

    async function testEmbeddingConnection() {
      testingEmbedding.value = true
      try {
        const res = await api.testEmbedding({ ...embedding })
        const ok = res.data?.success ?? res.data?.ok
        if (ok) {
          showMessage('✅ Embedding 连接成功', 'success')
        } else {
          showMessage('❌ Embedding 连接失败：' + (res.data?.error || res.data?.message || '未知错误'), 'error')
        }
      } catch (e) {
        showMessage('❌ Embedding 连接失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
      } finally {
        testingEmbedding.value = false
      }
    }

    onMounted(() => {
      loadSettings()
    })

    return {
      llm, embedding,
      saving, testingLLM, testingEmbedding,
      message,
      saveSettings, testLLMConnection, testEmbeddingConnection
    }
  }
}
</script>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: relative;
}

/* 提示消息 */
.message-bar {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  z-index: 1000;
  white-space: nowrap;
}

.message-bar.success {
  background: rgba(16, 185, 129, 0.15);
  color: var(--accent-green);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.message-bar.error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-red);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 配置卡片 */
.config-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.card-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.toggle-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-blue);
  cursor: pointer;
}

/* 表单网格 */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.form-grid.disabled {
  opacity: 0.45;
  pointer-events: none;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.form-group input,
.form-group select {
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  font-family: inherit;
  transition: border-color 0.2s;
}

.form-group input:focus,
.form-group select:focus {
  border-color: var(--accent-blue);
}

.form-group input::placeholder {
  color: var(--text-muted);
}

.form-group select {
  cursor: pointer;
  appearance: auto;
}

/* 按钮 */
.test-btn {
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--accent-blue);
  color: var(--accent-blue);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
  white-space: nowrap;
}

.test-btn:hover:not(:disabled) {
  background: var(--accent-blue);
  color: #fff;
}

.test-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.save-btn {
  padding: 10px 32px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: opacity 0.2s;
}

.save-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.save-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .config-card {
    padding: 14px;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .form-grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .form-group.full-width {
    grid-column: 1;
  }

  .message-bar {
    font-size: 13px;
    padding: 8px 16px;
    max-width: 90vw;
    white-space: normal;
    text-align: center;
  }

  .actions {
    justify-content: stretch;
  }

  .save-btn {
    width: 100%;
  }
}
</style>
