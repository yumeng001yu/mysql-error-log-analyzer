<template>
  <div class="analysis-report">
    <!-- 触发分析 -->
    <div class="action-bar">
      <div class="time-range">
        <label>分析时间段：</label>
        <select v-model="analysisPeriod" @change="onPeriodSelect">
          <option value="1h">最近1小时</option>
          <option value="3h">最近3小时</option>
          <option value="5h">最近5小时</option>
          <option value="12h">最近12小时</option>
          <option value="24h">最近24小时</option>
          <option value="3d">最近3天</option>
          <option value="7d">最近7天</option>
          <option value="30d">最近30天</option>
          <option value="all">全量分析</option>
          <option value="custom">自定义...</option>
        </select>
        <div v-if="analysisPeriod === 'custom'" class="custom-range">
          <input type="number" v-model.number="customValue" min="1" max="365" placeholder="数值" class="custom-input" />
          <select v-model="customUnit" class="custom-select">
            <option value="h">小时</option>
            <option value="d">天</option>
          </select>
        </div>
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

    <!-- 错误提示 -->
    <div class="error-bar" v-if="errorMessage">
      <span class="error-icon">⚠️</span>
      <span>{{ errorMessage }}</span>
      <button class="error-dismiss" @click="errorMessage = ''">✕</button>
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
              <span class="priority-badge" :class="s.priority || 'medium'">{{ priorityLabel(s.priority) }}</span>
              <span class="suggestion-title">{{ s.category || s.title || `建议 #${idx + 1}` }}</span>
            </div>
            <div class="suggestion-body" v-html="renderMarkdown(s.content || s.suggestion || s.description || '')"></div>
          </div>
        </div>
      </div>

      <!-- 关联分析 -->
      <div class="report-card" v-if="result.correlations && result.correlations.length > 0">
        <h3>🔗 关联分析</h3>
        <div class="correlation-list">
          <div v-for="(c, idx) in result.correlations" :key="idx" class="correlation-item">
            <span class="corr-type-badge" :class="c.type">{{ corrTypeLabel(c.type) }}</span>
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
            <span class="priority-badge" :class="p.level || 'medium'">{{ priorityLabel(p.level) }}</span>
            <span class="priority-issue">{{ p.issue || p.title }}</span>
            <span class="priority-desc">{{ p.description }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 无结果提示 -->
    <div v-if="!result && !analyzing && !errorMessage" class="empty-state">
      <div class="empty-icon">🔬</div>
      <p>暂无分析结果，请点击"触发分析"开始</p>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
import { renderMarkdown } from '../utils/markdown.js'

export default {
  name: 'AnalysisReport',
  setup() {
    const analysisPeriod = ref('24h')
    const customValue = ref(3)
    const customUnit = ref('h')
    const analyzing = ref(false)
    const showConfirm = ref(false)
    const result = ref(null)
    const errorMessage = ref('')

    function priorityLabel(p) {
      const map = { high: '高', medium: '中', low: '低', critical: '紧急' }
      return map[p] || p || '中'
    }

    function corrTypeLabel(t) {
      const map = { time_pattern: '时间模式', cross_category: '跨类别', anomaly: '异常' }
      return map[t] || t || '关联'
    }

    function onPeriodSelect() {
      if (analysisPeriod.value !== 'custom') {
        customValue.value = null
      }
    }

    function getEffectivePeriod() {
      if (analysisPeriod.value === 'custom' && customValue.value && customValue.value > 0) {
        return `${customValue.value}${customUnit.value}`
      }
      return analysisPeriod.value
    }

    function confirmRunAnalysis() {
      errorMessage.value = ''
      if (getEffectivePeriod() === 'all') {
        showConfirm.value = true
      } else {
        runAnalysis()
      }
    }

    async function runAnalysis() {
      showConfirm.value = false
      analyzing.value = true
      errorMessage.value = ''
      const effectivePeriod = getEffectivePeriod()
      try {
        const res = await api.runAnalysis({ period: effectivePeriod })
        const data = res.data || {}
        if (data.summary || data.suggestions?.length || data.correlations?.length || data.priorities?.length) {
          result.value = data
        } else {
          result.value = null
        }
      } catch (e) {
        console.error('分析失败', e)
        result.value = null
        const msg = e?.response?.data?.error || e?.response?.data?.message || e?.message || '未知错误'
        errorMessage.value = `分析失败: ${msg}`
      } finally {
        analyzing.value = false
      }
    }

    async function loadResults() {
      try {
        const res = await api.getAnalysisResults()
        const data = res.data || {}
        if (data.summary || data.suggestions?.length || data.priorities?.length) {
          result.value = data
        }
      } catch { /* ignore */ }
    }

    onMounted(() => {
      loadResults()
    })

    return {
      analysisPeriod, customValue, customUnit, analyzing, showConfirm, result, errorMessage,
      renderMarkdown, confirmRunAnalysis, runAnalysis, onPeriodSelect,
      priorityLabel, corrTypeLabel
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

.custom-range {
  display: flex;
  align-items: center;
  gap: 6px;
}

.custom-input {
  width: 60px;
  padding: 6px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  text-align: center;
}

.custom-input:focus {
  border-color: var(--accent-blue);
}

.custom-select {
  padding: 6px 8px;
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

/* 错误提示 */
.error-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--accent-red);
  font-size: 14px;
  line-height: 1.5;
}

.error-icon {
  flex-shrink: 0;
}

.error-bar span:nth-child(2) {
  flex: 1;
}

.error-dismiss {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--accent-red);
  cursor: pointer;
  font-size: 16px;
  padding: 0 4px;
  opacity: 0.7;
}

.error-dismiss:hover {
  opacity: 1;
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
  align-items: flex-start;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 13px;
}

.corr-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  background: rgba(59,130,246,0.15);
  color: var(--accent-blue);
}

.corr-type-badge.time_pattern { background: rgba(139,92,246,0.15); color: #8b5cf6; }
.corr-type-badge.cross_category { background: rgba(245,158,11,0.15); color: #f59e0b; }
.corr-type-badge.anomaly { background: rgba(239,68,68,0.15); color: #ef4444; }

.corr-index {
  color: var(--accent-blue);
  font-weight: 700;
  min-width: 24px;
}

.corr-body {
  color: var(--text-secondary);
  line-height: 1.6;
  flex: 1;
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

.priority-issue {
  font-weight: 600;
  color: var(--text-primary);
  min-width: 60px;
}

.priority-desc {
  color: var(--text-secondary);
  flex: 1;
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

/* ── 移动端适配 ────────────────────────────────────────── */
@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding: 12px;
  }

  .time-range {
    flex-wrap: wrap;
    gap: 6px;
  }

  .time-range label {
    width: 100%;
    font-size: 12px;
  }

  .time-range select {
    flex: 1;
    min-width: 0;
    font-size: 14px;
  }

  .custom-range {
    width: 100%;
  }

  .btn-primary {
    width: 100%;
    text-align: center;
  }

  .modal-card {
    width: 95vw;
    padding: 20px;
  }

  .report-card {
    padding: 14px;
  }

  .report-card h3 {
    font-size: 14px;
  }

  .suggestion-item {
    padding: 10px;
  }

  .priority-item {
    flex-wrap: wrap;
    padding: 6px 10px;
    font-size: 12px;
  }

  .priority-desc {
    width: 100%;
    margin-top: 4px;
  }

  .error-bar {
    font-size: 13px;
    padding: 10px 12px;
  }
}
</style>
