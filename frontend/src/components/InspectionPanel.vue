<template>
  <div class="inspection-panel">
    <!-- Tab 切换 -->
    <div class="tabs-bar">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        :class="['tab-btn', { active: activeTab === tab.value }]"
        @click="activeTab = tab.value"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="error = ''">关闭</button>
    </div>

    <!-- Tab 1：巡检执行 -->
    <div v-if="activeTab === 'execute'" class="tab-content">
      <!-- 操作栏 -->
      <div class="panel-header">
        <h2 class="panel-title">定时巡检</h2>
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
            {{ running ? '巡检中...' : '执行巡检' }}
          </button>
        </div>
      </div>

      <!-- 巡检进度 -->
      <div v-if="running" class="progress-card">
        <div class="progress-header">
          <span class="progress-icon">🔍</span>
          <span class="progress-text">正在执行巡检检查，请稍候...</span>
        </div>
        <div class="progress-bar-wrapper">
          <div class="progress-bar"></div>
        </div>
      </div>

      <!-- 巡检结果 -->
      <template v-if="currentResult && !running">
        <!-- 概览 -->
        <div class="overview-cards">
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
          <div class="ov-card">
            <div class="ov-icon" style="color: var(--accent-cyan)">📊</div>
            <div class="ov-info">
              <div class="ov-value">{{ checkItems.length }}</div>
              <div class="ov-label">检查项总数</div>
            </div>
          </div>
          <div class="ov-card">
            <div class="ov-icon" style="color: var(--accent-red)">⚠</div>
            <div class="ov-info">
              <div class="ov-value">{{ issueCount }}</div>
              <div class="ov-label">问题项</div>
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
        <div class="empty-icon">🛡️</div>
        <p>点击"执行巡检"对数据库进行健康检查</p>
      </div>

      <!-- 巡检历史 -->
      <div class="section-card">
        <div class="section-header">
          <h3>巡检历史</h3>
          <button class="refresh-btn" @click="loadHistory">刷新</button>
        </div>
        <div v-if="historyLoading" class="loading-text">加载中...</div>
        <div v-else-if="history.length === 0" class="empty-text">暂无巡检历史</div>
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

    <!-- Tab 2：定时任务 -->
    <div v-if="activeTab === 'schedule'" class="tab-content">
      <!-- 创建定时任务 -->
      <div class="section-card">
        <h3>创建定时任务</h3>
        <div class="schedule-form">
          <div class="control-group">
            <label class="control-label">Cron 表达式</label>
            <input
              type="text"
              class="form-input cron-input"
              v-model="scheduleForm.cron_expression"
              placeholder="如：0 8 * * *（每天 8 点）"
            />
          </div>
          <div class="control-group">
            <label class="control-label">数据库类型</label>
            <select class="control-select" v-model="scheduleForm.db_type">
              <option value="mysql">MySQL</option>
              <option value="redis">Redis</option>
              <option value="all">全部</option>
            </select>
          </div>
          <div class="control-group">
            <label class="control-label">实例</label>
            <select class="control-select" v-model="scheduleForm.instance_id">
              <option value="">全部实例</option>
              <option v-for="inst in instances" :key="inst.id || inst.name" :value="inst.id || inst.name">
                {{ inst.name || inst.host || ('实例 ' + (inst.id || inst.name)) }}
              </option>
            </select>
          </div>
          <button class="action-btn create-btn" :disabled="creating || !scheduleForm.cron_expression" @click="handleCreateSchedule">
            {{ creating ? '创建中...' : '创建任务' }}
          </button>
        </div>
        <div class="cron-hint">
          <span class="hint-label">Cron 说明：</span>
          <span class="hint-text">分 时 日 月 周（如 <code>0 8 * * *</code> 每天 8 点，<code>0 */6 * * *</code> 每 6 小时）</span>
        </div>
      </div>

      <!-- 任务列表 -->
      <div class="section-card">
        <div class="section-header">
          <h3>定时任务列表</h3>
          <button class="refresh-btn" @click="loadSchedules">刷新</button>
        </div>
        <div v-if="schedulesLoading" class="loading-text">加载中...</div>
        <div v-else-if="schedules.length === 0" class="empty-text">暂无定时任务</div>
        <div v-else class="schedule-list">
          <div
            v-for="s in schedules"
            :key="s.id"
            class="schedule-item"
          >
            <div class="schedule-info">
              <div class="schedule-cron">
                <span class="cron-code">{{ s.cron_expression }}</span>
              </div>
              <div class="schedule-meta">
                <span class="schedule-db">{{ dbTypeLabel(s.db_type) }}</span>
                <span class="schedule-instance" v-if="s.instance_id">实例: {{ s.instance_id }}</span>
                <span class="schedule-instance" v-else>全部实例</span>
              </div>
            </div>
            <div class="schedule-actions">
              <span class="status-badge" :class="s.enabled === false ? 'badge-gray' : 'badge-green'">
                {{ s.enabled === false ? '已停用' : '启用中' }}
              </span>
              <button class="btn-delete" @click="deleteSchedule(s.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'
import { formatDateTimeMinute as formatTime } from '../utils/datetime.js'

const tabs = [
  { label: '巡检执行', value: 'execute', icon: '🛡️' },
  { label: '定时任务', value: 'schedule', icon: '⏰' }
]

const activeTab = ref('execute')
const dbType = ref('mysql')
const instanceId = ref('')
const instances = ref([])
const running = ref(false)
const error = ref('')
const currentResult = ref(null)

// 历史
const history = ref([])
const historyLoading = ref(false)

// 定时任务
const schedules = ref([])
const schedulesLoading = ref(false)
const creating = ref(false)
const scheduleForm = ref({
  cron_expression: '',
  db_type: 'mysql',
  instance_id: ''
})

const checkItems = computed(() => {
  const r = currentResult.value || {}
  const items = r.checks || r.check_items || r.items || r.results
  return Array.isArray(items) ? items : []
})

const issueCount = computed(() => {
  return checkItems.value.filter(i => {
    const s = (i.status || '').toLowerCase()
    return s === 'warning' || s === 'critical' || s === 'error'
  }).length
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
const overallColor = computed(() => overallColorFor(currentResult.value?.overall_status || currentResult.value?.status, currentResult.value?.health_score))
const overallIcon = computed(() => overallIconFor(currentResult.value?.overall_status || currentResult.value?.status, currentResult.value?.health_score))

function overallLabelFor(r) {
  if (!r) return '-'
  const s = (r.overall_status || r.status || '').toLowerCase()
  if (s === 'healthy' || s === 'good') return '健康'
  if (s === 'warning' || s === 'warn') return '告警'
  if (s === 'critical') return '严重'
  if (s === 'error') return '错误'
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
    const res = await api.runInspection(data)
    currentResult.value = res.data || null
    await loadHistory()
  } catch (e) {
    error.value = '巡检失败: ' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    running.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const params = { limit: 20 }
    const res = await api.getInspectionHistory(params)
    const data = res.data
    history.value = Array.isArray(data) ? data : (data.items || data.history || [])
  } catch (e) {
    console.error('getInspectionHistory error', e)
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
    const res = await api.getInspectionDetail(h.id)
    currentResult.value = res.data || h
  } catch (e) {
    currentResult.value = h
  }
}

async function loadSchedules() {
  schedulesLoading.value = true
  try {
    const res = await api.getInspectionSchedules()
    const data = res.data
    schedules.value = Array.isArray(data) ? data : (data.items || data.schedules || [])
  } catch (e) {
    console.error('getInspectionSchedules error', e)
    schedules.value = []
  } finally {
    schedulesLoading.value = false
  }
}

async function handleCreateSchedule() {
  if (!scheduleForm.value.cron_expression) return
  creating.value = true
  error.value = ''
  try {
    const data = {
      cron_expression: scheduleForm.value.cron_expression,
      db_type: scheduleForm.value.db_type
    }
    if (scheduleForm.value.instance_id) data.instance_id = scheduleForm.value.instance_id
    await api.createInspectionSchedule(data)
    scheduleForm.value.cron_expression = ''
    await loadSchedules()
  } catch (e) {
    error.value = '创建定时任务失败: ' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    creating.value = false
  }
}

async function deleteSchedule(id) {
  if (!confirm('确认删除此定时任务？')) return
  try {
    await api.deleteInspectionSchedule(id)
    schedules.value = schedules.value.filter(s => s.id !== id)
  } catch (e) {
    alert('删除任务失败: ' + (e.response?.data?.detail || e.message || '未知错误'))
  }
}

onMounted(() => {
  loadInstances()
  loadHistory()
  loadSchedules()
})
</script>

<style scoped>
.inspection-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Tab 切换 */
.tabs-bar {
  display: flex;
  gap: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 6px;
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.tab-btn.active {
  background: var(--accent-blue);
  color: #fff;
}

.tab-icon {
  font-size: 14px;
}

.tab-content {
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

.form-input {
  padding: 7px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent-blue);
}

.cron-input {
  min-width: 200px;
  font-family: 'Courier New', monospace;
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

.create-btn {
  background: var(--accent-green);
}

.create-btn:hover:not(:disabled) {
  background: #059669;
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
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.ov-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
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

/* 定时任务表单 */
.schedule-form {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.cron-hint {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.hint-label {
  color: var(--text-secondary);
  font-weight: 600;
}

.hint-text code {
  font-family: 'Courier New', monospace;
  color: var(--accent-cyan);
  background: var(--bg-primary);
  padding: 1px 6px;
  border-radius: 3px;
}

/* 任务列表 */
.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.schedule-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.schedule-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 200px;
}

.schedule-cron {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cron-code {
  font-family: 'Courier New', monospace;
  font-size: 14px;
  font-weight: 700;
  color: var(--accent-cyan);
  background: var(--bg-primary);
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.schedule-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted);
  flex-wrap: wrap;
}

.schedule-db {
  color: var(--accent-purple);
  font-weight: 600;
}

.schedule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-delete {
  padding: 4px 12px;
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-red);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}

.btn-delete:hover {
  background: rgba(239, 68, 68, 0.22);
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
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .tabs-bar {
    flex-direction: column;
  }

  .tab-btn {
    width: 100%;
  }

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

  .control-select,
  .cron-input {
    width: 100%;
    min-width: auto;
  }

  .action-btn {
    width: 100%;
    text-align: center;
  }

  .overview-cards {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .ov-card {
    padding: 14px;
    gap: 12px;
  }

  .check-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .schedule-form {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .schedule-item {
    flex-direction: column;
    align-items: stretch;
  }

  .schedule-actions {
    justify-content: flex-end;
  }

  .history-top {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
