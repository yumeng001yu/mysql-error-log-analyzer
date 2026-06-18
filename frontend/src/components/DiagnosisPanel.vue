<template>
  <div class="diagnosis-panel">
    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">一键诊断</h2>
      <div class="header-actions">
        <div class="control-group">
          <label class="control-label">数据库类型</label>
          <select class="control-select" v-model="dbType">
            <option value="mysql">MySQL</option>
            <option value="redis">Redis</option>
            <option value="all">全部</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">实例</label>
          <select class="control-select" v-model="instanceId">
            <option value="">全部实例</option>
            <option v-for="inst in instances" :key="inst.id || inst.name" :value="inst.id || inst.name">
              {{ inst.name || inst.host || ('实例 ' + (inst.id || inst.name)) }}
            </option>
          </select>
        </div>
        <button class="action-btn run-btn" :disabled="running" @click="handleRun">
          {{ running ? '诊断中...' : '开始诊断' }}
        </button>
      </div>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="error = ''">关闭</button>
    </div>

    <!-- 诊断进度 -->
    <div v-if="running" class="progress-card">
      <div class="progress-header">
        <span class="progress-icon">🔍</span>
        <span class="progress-text">正在执行诊断检查，请稍候...</span>
      </div>
      <div class="progress-bar-wrapper">
        <div class="progress-bar"></div>
      </div>
    </div>

    <!-- 诊断结果 -->
    <template v-if="currentResult && !running">
      <!-- 概览卡片 -->
      <div class="overview-cards">
        <div class="ov-card">
          <div class="ov-icon" style="color: var(--accent-green)">✓</div>
          <div class="ov-info">
            <div class="ov-value">{{ summary.passed }}</div>
            <div class="ov-label">通过</div>
          </div>
        </div>
        <div class="ov-card">
          <div class="ov-icon" style="color: var(--accent-yellow)">⚠</div>
          <div class="ov-info">
            <div class="ov-value">{{ summary.warning }}</div>
            <div class="ov-label">告警</div>
          </div>
        </div>
        <div class="ov-card">
          <div class="ov-icon" style="color: var(--accent-yellow)">⚡</div>
          <div class="ov-info">
            <div class="ov-value">{{ summary.critical }}</div>
            <div class="ov-label">严重</div>
          </div>
        </div>
        <div class="ov-card">
          <div class="ov-icon" style="color: var(--accent-red)">✕</div>
          <div class="ov-info">
            <div class="ov-value">{{ summary.error }}</div>
            <div class="ov-label">错误</div>
          </div>
        </div>
        <div class="ov-card" :class="healthCardClass">
          <div class="ov-icon" :style="{ color: healthColor }">💊</div>
          <div class="ov-info">
            <div class="ov-value" :style="{ color: healthColor }">{{ currentResult.health_score != null ? currentResult.health_score : '-' }}</div>
            <div class="ov-label">健康评分</div>
          </div>
        </div>
        <div class="ov-card">
          <div class="ov-icon" :style="{ color: overallColor }">{{ overallIcon }}</div>
          <div class="ov-info">
            <div class="ov-value" :style="{ color: overallColor }">{{ overallLabel }}</div>
            <div class="ov-label">整体状态</div>
          </div>
        </div>
      </div>

      <!-- 检查项列表 -->
      <div class="section-card">
        <h3>检查项列表</h3>
        <div v-if="checkItems.length === 0" class="empty-text">暂无检查项</div>
        <div v-else class="check-list">
          <div
            v-for="(item, idx) in checkItems"
            :key="idx"
            class="check-item"
            :class="'status-' + (item.status || 'skip')"
          >
            <div class="check-header">
              <span class="check-name">{{ item.name || item.check_name || ('检查项 ' + (idx + 1)) }}</span>
              <span class="status-badge" :class="statusBadgeClass(item.status)">{{ statusLabel(item.status) }}</span>
            </div>
            <div class="check-message" v-if="item.message">{{ item.message }}</div>
            <div class="check-detail" v-if="item.detail || item.details">
              <span class="detail-label">详情：</span>
              <span class="detail-text">{{ item.detail || item.details }}</span>
            </div>
            <div class="check-suggestion" v-if="item.suggestion || item.recommendation">
              <span class="suggestion-label">💡 建议：</span>
              <span class="suggestion-text">{{ item.suggestion || item.recommendation }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 空状态 -->
    <div v-if="!currentResult && !running && !error" class="empty-state">
      <div class="empty-icon">🩺</div>
      <p>点击"开始诊断"对数据库进行一键健康检查</p>
    </div>

    <!-- 诊断历史 -->
    <div class="section-card">
      <div class="section-header">
        <h3>诊断历史</h3>
        <button class="refresh-btn" @click="loadHistory">刷新</button>
      </div>
      <div v-if="historyLoading" class="loading-text">加载中...</div>
      <div v-else-if="history.length === 0" class="empty-text">暂无诊断历史</div>
      <div v-else class="history-list">
        <div
          v-for="h in history"
          :key="h.id"
          :class="['history-item', { active: currentResult && currentResult.id === h.id }]"
          @click="viewHistory(h)"
        >
          <div class="history-top">
            <span class="history-db">{{ dbTypeLabel(h.db_type) }}</span>
            <span class="history-score" :class="scoreClass(h.health_score)">
              {{ h.health_score != null ? h.health_score : '-' }}
            </span>
            <span class="status-badge" :class="overallBadgeClass(h)">{{ overallLabelFor(h) }}</span>
          </div>
          <div class="history-time">{{ formatTime(h.created_at || h.started_at) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'
import { formatDateTimeMinute as formatTime } from '../utils/datetime.js'

const dbType = ref('mysql')
const instanceId = ref('')
const instances = ref([])
const running = ref(false)
const error = ref('')
const currentResult = ref(null)
const history = ref([])
const historyLoading = ref(false)

// 概览统计
const summary = computed(() => {
  const items = checkItems.value
  const count = (status) => items.filter(i => (i.status || '').toLowerCase() === status).length
  return {
    passed: count('passed'),
    warning: count('warning'),
    critical: count('critical'),
    error: count('error')
  }
})

const checkItems = computed(() => {
  const r = currentResult.value || {}
  const items = r.checks || r.check_items || r.items || r.results
  return Array.isArray(items) ? items : []
})

const healthCardClass = computed(() => {
  const s = currentResult.value?.health_score
  if (s == null) return ''
  const num = Number(s)
  if (num >= 90) return 'ov-healthy'
  if (num >= 70) return 'ov-warning'
  return 'ov-critical'
})

const healthColor = computed(() => {
  const s = currentResult.value?.health_score
  if (s == null) return 'var(--text-primary)'
  const num = Number(s)
  if (num >= 90) return 'var(--accent-green)'
  if (num >= 70) return 'var(--accent-yellow)'
  return 'var(--accent-red)'
})

const overallLabel = computed(() => overallLabelFor(currentResult.value))
const overallColor = computed(() => {
  const s = currentResult.value?.overall_status || currentResult.value?.status
  return overallColorFor(s, currentResult.value?.health_score)
})
const overallIcon = computed(() => {
  const s = currentResult.value?.overall_status || currentResult.value?.status
  return overallIconFor(s, currentResult.value?.health_score)
})

function overallLabelFor(r) {
  if (!r) return '-'
  const s = (r.overall_status || r.status || '').toLowerCase()
  if (s === 'healthy' || s === 'good') return '健康'
  if (s === 'warning' || s === 'warn') return '告警'
  if (s === 'critical') return '严重'
  if (s === 'error') return '错误'
  // 根据健康评分推断
  if (r.health_score != null) {
    const num = Number(r.health_score)
    if (num >= 90) return '健康'
    if (num >= 70) return '告警'
    return '严重'
  }
  return '-'
}

function overallColorFor(status, score) {
  const s = (status || '').toLowerCase()
  if (s === 'healthy' || s === 'good') return 'var(--accent-green)'
  if (s === 'warning' || s === 'warn') return 'var(--accent-yellow)'
  if (s === 'critical') return '#f97316'
  if (s === 'error') return 'var(--accent-red)'
  if (score != null) {
    const num = Number(score)
    if (num >= 90) return 'var(--accent-green)'
    if (num >= 70) return 'var(--accent-yellow)'
    return 'var(--accent-red)'
  }
  return 'var(--text-primary)'
}

function overallIconFor(status, score) {
  const s = (status || '').toLowerCase()
  if (s === 'healthy' || s === 'good') return '✓'
  if (s === 'warning' || s === 'warn') return '⚠'
  if (s === 'critical') return '⚡'
  if (s === 'error') return '✕'
  if (score != null) {
    const num = Number(score)
    if (num >= 90) return '✓'
    if (num >= 70) return '⚠'
    return '⚡'
  }
  return '○'
}

function overallBadgeClass(r) {
  if (!r) return 'badge-gray'
  const s = (r.overall_status || r.status || '').toLowerCase()
  if (s === 'healthy' || s === 'good') return 'badge-green'
  if (s === 'warning' || s === 'warn') return 'badge-yellow'
  if (s === 'critical') return 'badge-orange'
  if (s === 'error') return 'badge-red'
  if (r.health_score != null) {
    const num = Number(r.health_score)
    if (num >= 90) return 'badge-green'
    if (num >= 70) return 'badge-yellow'
    return 'badge-red'
  }
  return 'badge-gray'
}

function statusBadgeClass(status) {
  const s = (status || 'skip').toLowerCase()
  if (s === 'passed') return 'badge-green'
  if (s === 'warning' || s === 'warn') return 'badge-yellow'
  if (s === 'critical') return 'badge-orange'
  if (s === 'error') return 'badge-red'
  return 'badge-gray'
}

function statusLabel(status) {
  const s = (status || 'skip').toLowerCase()
  if (s === 'passed') return '通过'
  if (s === 'warning' || s === 'warn') return '告警'
  if (s === 'critical') return '严重'
  if (s === 'error') return '错误'
  if (s === 'skip') return '跳过'
  return status || '未知'
}

function scoreClass(score) {
  if (score == null) return ''
  const num = Number(score)
  if (num >= 90) return 'score-green'
  if (num >= 70) return 'score-yellow'
  return 'score-red'
}

function dbTypeLabel(t) {
  const map = { mysql: 'MySQL', redis: 'Redis', all: '全部' }
  return map[t] || t || '-'
}


async function loadInstances() {
  try {
    const res = await api.getInstances()
    const data = res.data
    instances.value = Array.isArray(data) ? data : (data.items || data.instances || [])
  } catch (e) {
    instances.value = []
  }
}

async function handleRun() {
  running.value = true
  error.value = ''
  currentResult.value = null
  try {
    const data = { db_type: dbType.value }
    if (instanceId.value) data.instance_id = instanceId.value
    const res = await api.runDiagnosis(data)
    currentResult.value = res.data || null
    await loadHistory()
  } catch (e) {
    error.value = '诊断失败: ' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    running.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const params = { limit: 20 }
    const res = await api.getDiagnosisHistory(params)
    const data = res.data
    history.value = Array.isArray(data) ? data : (data.items || data.history || [])
  } catch (e) {
    console.error('getDiagnosisHistory error', e)
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

async function viewHistory(h) {
  if (!h || !h.id) {
    currentResult.value = h
    return
  }
  try {
    const res = await api.getDiagnosisDetail(h.id)
    currentResult.value = res.data || h
  } catch (e) {
    currentResult.value = h
  }
}

onMounted(() => {
  loadInstances()
  loadHistory()
})
</script>

<style scoped>
.diagnosis-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.control-label {
  font-size: 12px;
  color: var(--text-muted);
}

.control-select {
  padding: 7px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  outline: none;
  min-width: 140px;
}

.control-select:focus {
  border-color: var(--accent-blue);
}

.action-btn {
  padding: 8px 22px;
  border: none;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.run-btn {
  background: var(--accent-blue);
}

.run-btn:hover:not(:disabled) {
  background: #2563eb;
}

/* 错误状态 */
.error-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid var(--accent-red);
  border-radius: 8px;
}

.error-icon {
  font-size: 20px;
}

.error-msg {
  flex: 1;
  color: var(--accent-red);
  font-size: 13px;
}

.retry-btn {
  padding: 6px 16px;
  background: var(--accent-red);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

/* 进度条 */
.progress-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 14px;
}

.progress-icon {
  font-size: 20px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.progress-bar-wrapper {
  width: 100%;
  height: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan));
  border-radius: 4px;
  animation: progress-slide 1.5s ease-in-out infinite;
}

@keyframes progress-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

.ov-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: border-color 0.2s;
}

.ov-card.ov-healthy {
  border-color: var(--accent-green);
}

.ov-card.ov-warning {
  border-color: var(--accent-yellow);
  background: rgba(245, 158, 11, 0.04);
}

.ov-card.ov-critical {
  border-color: var(--accent-red);
  background: rgba(239, 68, 68, 0.04);
}

.ov-icon {
  font-size: 24px;
  font-weight: 700;
}

.ov-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.ov-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* 通用 section card */
.section-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.section-card h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
}

.refresh-btn {
  padding: 5px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 检查项列表 */
.check-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.check-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 14px;
  border-left: 3px solid var(--text-muted);
}

.check-item.status-passed {
  border-left-color: var(--accent-green);
}

.check-item.status-warning {
  border-left-color: var(--accent-yellow);
}

.check-item.status-critical {
  border-left-color: #f97316;
}

.check-item.status-error {
  border-left-color: var(--accent-red);
}

.check-item.status-skip {
  border-left-color: var(--text-muted);
}

.check-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.check-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.status-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 600;
}

.badge-green {
  background: rgba(16, 185, 129, 0.2);
  color: var(--accent-green);
}

.badge-red {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.badge-yellow {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.badge-orange {
  background: rgba(249, 115, 22, 0.2);
  color: #f97316;
}

.badge-gray {
  background: rgba(107, 114, 128, 0.2);
  color: var(--text-muted);
}

.check-message {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  margin-bottom: 6px;
}

.check-detail {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 4px;
}

.detail-label {
  color: var(--text-muted);
}

.check-suggestion {
  font-size: 12px;
  line-height: 1.5;
  margin-top: 6px;
  padding: 8px 10px;
  background: rgba(59, 130, 246, 0.06);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 4px;
}

.suggestion-label {
  color: var(--accent-blue);
  font-weight: 600;
}

.suggestion-text {
  color: var(--text-secondary);
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-state p {
  font-size: 14px;
}

/* 历史列表 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.history-item:hover {
  background: var(--bg-hover);
}

.history-item.active {
  background: rgba(59, 130, 246, 0.12);
  border-color: var(--accent-blue);
}

.history-top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.history-db {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-cyan);
}

.history-score {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 32px;
  text-align: center;
}

.score-red { color: var(--accent-red); }
.score-yellow { color: var(--accent-yellow); }
.score-green { color: var(--accent-green); }

.history-time {
  font-size: 12px;
  color: var(--text-muted);
}

.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 响应式 */
@media (max-width: 1024px) {
  .overview-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .panel-header {
    flex-direction: column;
    align-items: stretch;
    padding: 12px;
  }

  .header-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .control-group {
    width: 100%;
  }

  .control-select {
    width: 100%;
    min-width: auto;
  }

  .action-btn {
    width: 100%;
    text-align: center;
  }

  .overview-cards {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .ov-card {
    padding: 12px;
    gap: 10px;
  }

  .ov-icon {
    font-size: 20px;
  }

  .ov-value {
    font-size: 18px;
  }

  .check-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .history-top {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
