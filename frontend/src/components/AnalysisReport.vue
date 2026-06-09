<template>
  <div class="analysis-report">
    <!-- 触发分析 -->
    <div class="action-bar">
      <div class="time-range">
        <label>分析时间段：</label>
        <select v-model="analysisPeriod">
          <option value="1h">最近1小时</option>
          <option value="24h">最近24小时</option>
          <option value="7d">最近7天</option>
          <option value="30d">最近30天</option>
          <option value="all">全量分析</option>
        </select>
      </div>
      <button class="btn-primary" @click="confirmRunAnalysis" :disabled="analyzing">
        {{ analyzing ? '分析中...' : '🔍 触发分析' }}
      </button>
    </div>

    <!-- 全量分析确认弹窗 -->
    <div class="modal-overlay" v-if="showConfirm" @click.self="showConfirm = false">
      <div class="modal-card">
        <h3>⚠️ 确认全量分析</h3>
        <p>全量分析将处理所有日志数据，可能需要较长时间。确认继续？</p>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showConfirm = false">取消</button>
          <button class="btn-primary" @click="runAnalysis">确认分析</button>
        </div>
      </div>
    </div>

    <!-- 分析状态 -->
    <div class="status-bar" v-if="analyzing">
      <div class="spinner"></div>
      <span>正在分析日志，请稍候...</span>
    </div>

    <!-- 分析结果 -->
    <div v-if="result" class="report-content">
      <!-- 整体摘要 -->
      <div class="report-card">
        <h3>📋 整体摘要</h3>
        <div class="markdown-body" v-html="renderMarkdown(result.summary || result.content)"></div>
      </div>

      <!-- 各类错误修复建议 -->
      <div class="report-card" v-if="result.suggestions && result.suggestions.length > 0">
        <h3>💡 修复建议</h3>
        <div class="suggestion-list">
          <div v-for="(s, idx) in result.suggestions" :key="idx" class="suggestion-item">
            <div class="suggestion-header">
              <span class="priority-badge" :class="s.priority || 'medium'">{{ s.priority || '中' }}</span>
              <span class="suggestion-title">{{ s.category || s.title || `建议 #${idx + 1}` }}</span>
            </div>
            <div class="suggestion-body" v-html="renderMarkdown(s.content || s.description || '')"></div>
          </div>
        </div>
      </div>

      <!-- 关联分析 -->
      <div class="report-card" v-if="result.correlations && result.correlations.length > 0">
        <h3>🔗 关联分析</h3>
        <div class="correlation-list">
          <div v-for="(c, idx) in result.correlations" :key="idx" class="correlation-item">
            <span class="corr-index">#{{ idx + 1 }}</span>
            <div class="corr-body" v-html="renderMarkdown(c.description || c.content || (typeof c === 'string' ? c : JSON.stringify(c)))"></div>
          </div>
        </div>
      </div>

      <!-- 优先级排序 -->
      <div class="report-card" v-if="result.priorities && result.priorities.length > 0">
        <h3>🎯 优先级排序</h3>
        <div class="priority-list">
          <div v-for="(p, idx) in result.priorities" :key="idx" class="priority-item">
            <span class="priority-rank">{{ idx + 1 }}</span>
            <span class="priority-badge" :class="p.level || 'medium'">{{ p.level || '中' }}</span>
            <span class="priority-text">{{ p.issue || p.description || p.title }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 无结果提示 -->
    <div v-if="!result && !analyzing" class="empty-state">
      <div class="empty-icon">🔬</div>
      <p>暂无分析结果，请点击"触发分析"开始</p>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
import { marked } from 'marked'

export default {
  name: 'AnalysisReport',
  setup() {
    const analysisPeriod = ref('24h')
    const analyzing = ref(false)
    const showConfirm = ref(false)
    const result = ref(null)

    function renderMarkdown(text) {
      if (!text) return ''
      try {
        return marked.parse(text)
      } catch {
        return text.replace(/\n/g, '<br>')
      }
    }

    function confirmRunAnalysis() {
      if (analysisPeriod.value === 'all') {
        showConfirm.value = true
      } else {
        runAnalysis()
      }
    }

    async function runAnalysis() {
      showConfirm.value = false
      analyzing.value = true
      try {
        await api.runAnalysis({ period: analysisPeriod.value })
        // 轮询获取结果
        let attempts = 0
        const poll = async () => {
          try {
            const res = await api.getAnalysisResults({ period: analysisPeriod.value })
            const data = res.data
            if (data && (data.summary || data.content || data.suggestions)) {
              result.value = data
              analyzing.value = false
            } else if (attempts < 30) {
              attempts++
              setTimeout(poll, 2000)
            } else {
              analyzing.value = false
            }
          } catch {
            if (attempts < 30) {
              attempts++
              setTimeout(poll, 2000)
            } else {
              analyzing.value = false
            }
          }
        }
        setTimeout(poll, 1500)
      } catch (e) {
        analyzing.value = false
      }
    }

    async function loadResults() {
      try {
        const res = await api.getAnalysisResults()
        const data = res.data
        if (data && (data.summary || data.content || data.suggestions)) {
          result.value = data
        }
      } catch { /* ignore */ }
    }

    onMounted(() => {
      loadResults()
    })

    return {
      analysisPeriod, analyzing, showConfirm, result,
      renderMarkdown, confirmRunAnalysis, runAnalysis
    }
  }
}
</script>

<style scoped>
.analysis-report {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.action-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.time-range {
  display: flex;
  align-items: center;
  gap: 8px;
}

.time-range label {
  font-size: 13px;
  color: var(--text-secondary);
}

.time-range select {
  padding: 6px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.btn-primary {
  padding: 8px 20px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 8px 20px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.modal-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 28px;
  width: 420px;
  max-width: 90vw;
}

.modal-card h3 {
  font-size: 18px;
  margin-bottom: 12px;
}

.modal-card p {
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 20px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* 分析状态 */
.status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--accent-cyan);
  font-size: 14px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 报告卡片 */
.report-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.report-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.report-card h3 {
  font-size: 15px;
  margin-bottom: 14px;
  color: var(--text-primary);
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  color: var(--text-primary);
  margin: 12px 0 6px;
}

.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 20px;
}

.markdown-body :deep(code) {
  background: var(--bg-secondary);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
}

.markdown-body :deep(pre) {
  background: var(--bg-secondary);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

/* 建议列表 */
.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.suggestion-item {
  background: var(--bg-secondary);
  border-radius: 6px;
  padding: 14px;
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.suggestion-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.priority-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.priority-badge.high, .priority-badge.critical { background: rgba(239,68,68,0.2); color: var(--accent-red); }
.priority-badge.medium { background: rgba(245,158,11,0.2); color: var(--accent-yellow); }
.priority-badge.low { background: rgba(16,185,129,0.2); color: var(--accent-green); }

.suggestion-body {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* 关联分析 */
.correlation-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.correlation-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 13px;
}

.corr-index {
  color: var(--accent-blue);
  font-weight: 700;
  min-width: 24px;
}

.corr-body {
  color: var(--text-secondary);
  line-height: 1.6;
}

/* 优先级 */
.priority-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.priority-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 13px;
}

.priority-rank {
  font-weight: 700;
  color: var(--accent-blue);
  min-width: 20px;
}

.priority-text {
  color: var(--text-primary);
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  font-size: 14px;
}
</style>
