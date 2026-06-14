<template>
  <div class="pattern-panel">
    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">日志模式识别</h2>
      <div class="header-actions">
        <button class="recognize-btn" :disabled="recognizing" @click="handleRecognize">
          {{ recognizing ? '识别中...' : '识别模式' }}
        </button>
        <label class="anomaly-toggle">
          <input type="checkbox" v-model="anomalyOnly" @change="handleAnomalyToggle" />
          <span class="toggle-label">仅显示异常</span>
        </label>
        <div class="time-range">
          <button
            v-for="tr in timeRanges"
            :key="tr.value"
            :class="['range-btn', { active: timeRange === tr.value }]"
            @click="changeTimeRange(tr.value)"
          >{{ tr.label }}</button>
        </div>
      </div>
    </div>

    <!-- 统计摘要 -->
    <div class="stats-bar">
      <div class="stats-item">
        <span class="stats-label">模式总数</span>
        <span class="stats-value">{{ patternStats.total_patterns ?? '-' }}</span>
      </div>
      <div class="stats-item anomaly">
        <span class="stats-label">异常数</span>
        <span class="stats-value">{{ patternStats.anomaly_count ?? '-' }}</span>
      </div>
      <div class="stats-item">
        <span class="stats-label">主要类别</span>
        <span class="stats-value highlight">{{ patternStats.top_category ?? '-' }}</span>
      </div>
      <div class="stats-item">
        <span class="stats-label">模式覆盖率</span>
        <span class="stats-value">{{ formatPercent(patternStats.coverage) }}</span>
      </div>
    </div>

    <!-- 模式列表 -->
    <div v-if="loading" class="loading-text">加载中...</div>
    <div v-else-if="displayPatterns.length === 0" class="empty-text">暂无模式数据，点击"识别模式"开始分析</div>
    <div v-else class="pattern-list">
      <div
        v-for="pattern in displayPatterns"
        :key="pattern.id"
        class="pattern-card"
        :class="{ 'anomaly-card': pattern.is_anomaly, 'anomaly-detail-card': anomalyOnly && pattern.is_anomaly }"
      >
        <!-- 模板文本 -->
        <div class="template-row">
          <span class="template-text" v-html="renderTemplate(pattern.template)"></span>
          <span class="anomaly-indicator" :class="pattern.is_anomaly ? 'is-anomaly' : 'is-normal'">
            <span class="anomaly-dot" :class="{ pulse: pattern.is_anomaly }"></span>
            <template v-if="pattern.is_anomaly">
              <span class="anomaly-score">{{ (pattern.anomaly_score ?? 0).toFixed(2) }}</span>
              <span class="trend-arrow" :class="getTrendClass(pattern.trend)">{{ getTrendSymbol(pattern.trend) }}</span>
            </template>
          </span>
        </div>

        <!-- 级别 & 类别 -->
        <div class="meta-row">
          <span class="level-badge" :class="getLevelClass(pattern.level)">{{ pattern.level }}</span>
          <span class="category-badge">{{ pattern.category }}</span>
          <span class="error-codes" v-if="pattern.error_codes && pattern.error_codes.length > 0">
            <span v-for="code in pattern.error_codes" :key="code" class="error-code">{{ code }}</span>
          </span>
        </div>

        <!-- 计数条 -->
        <div class="count-row">
          <span class="count-number">{{ pattern.count ?? 0 }}</span>
          <div class="count-bar-bg">
            <div
              class="count-bar"
              :style="{ width: getCountBarWidth(pattern.count) + '%', background: getLevelColor(pattern.level) }"
            ></div>
          </div>
        </div>

        <!-- 时间 -->
        <div class="time-row">
          <span class="time-label">首次: <span class="time-value">{{ formatTime(pattern.first_seen) }}</span></span>
          <span class="time-label">最近: <span class="time-value">{{ formatTime(pattern.last_seen) }}</span></span>
        </div>

        <!-- 异常详情（仅异常模式且仅显示异常模式时展示） -->
        <div v-if="anomalyOnly && pattern.is_anomaly" class="anomaly-detail">
          <div class="anomaly-detail-row">
            <span class="anomaly-detail-label">异常评分</span>
            <span class="anomaly-detail-score">{{ (pattern.anomaly_score ?? 0).toFixed(2) }}</span>
          </div>
          <div class="anomaly-detail-row">
            <span class="anomaly-detail-label">趋势</span>
            <span class="anomaly-detail-trend" :class="getTrendClass(pattern.trend)">
              {{ getTrendSymbol(pattern.trend) }} {{ getTrendDescription(pattern.trend) }}
            </span>
          </div>
          <div class="anomaly-detail-row" v-if="pattern.suggested_action">
            <span class="anomaly-detail-label">建议操作</span>
            <span class="anomaly-detail-action">{{ pattern.suggested_action }}</span>
          </div>
          <div class="anomaly-detail-row" v-else>
            <span class="anomaly-detail-label">建议操作</span>
            <span class="anomaly-detail-action">{{ getSuggestedAction(pattern) }}</span>
          </div>
        </div>

        <!-- 趋势按钮 -->
        <div class="action-row">
          <button class="trend-btn" @click="toggleTrend(pattern.id)">
            {{ expandedTrends[pattern.id] ? '收起趋势' : '趋势' }}
          </button>
          <button class="sample-btn" @click="toggleSample(pattern.id)">
            {{ expandedSamples[pattern.id] ? '收起样本' : '查看样本' }}
          </button>
        </div>

        <!-- 趋势视图 -->
        <div v-if="expandedTrends[pattern.id]" class="trend-view">
          <div v-if="trendLoading[pattern.id]" class="loading-text small">加载趋势...</div>
          <div v-else-if="!trendData[pattern.id] || trendData[pattern.id].length === 0" class="empty-text small">暂无趋势数据</div>
          <template v-else>
            <div
              v-for="item in trendData[pattern.id]"
              :key="item.hour"
              class="trend-bar-row"
              :class="{ 'trend-anomaly': item.is_anomaly }"
            >
              <span class="trend-hour">{{ item.hour }}</span>
              <span class="trend-bar-track">
                <span
                  class="trend-bar-fill"
                  :style="{ width: getTrendBarWidth(item.count, pattern.id) + '%' }"
                ></span>
              </span>
              <span class="trend-count">{{ item.count }}</span>
            </div>
          </template>
        </div>

        <!-- 样本消息 -->
        <div v-if="expandedSamples[pattern.id]" class="sample-view">
          <div v-if="pattern.sample_messages && pattern.sample_messages.length > 0">
            <div v-for="(msg, idx) in pattern.sample_messages" :key="idx" class="sample-msg">
              {{ msg }}
            </div>
          </div>
          <div v-else-if="pattern.sample" class="sample-msg">{{ pattern.sample }}</div>
          <div v-else class="empty-text small">暂无样本消息</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { api } from '../api.js'

// 状态
const loading = ref(false)
const recognizing = ref(false)
const anomalyOnly = ref(false)
const timeRange = ref('24h')
const patterns = ref([])
const patternStats = ref({})
const expandedTrends = reactive({})
const expandedSamples = reactive({})
const trendData = reactive({})
const trendLoading = reactive({})

const timeRanges = [
  { label: '1h', value: '1h' },
  { label: '6h', value: '6h' },
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' }
]

// 计算属性
const displayPatterns = computed(() => {
  if (anomalyOnly.value) {
    return patterns.value.filter(p => p.is_anomaly)
  }
  return patterns.value
})

// 方法
function formatTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '-'
  const month = d.getMonth() + 1
  const day = d.getDate()
  const hour = d.getHours()
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${hour}:${min}`
}

function formatPercent(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  return num.toFixed(1) + '%'
}

function renderTemplate(template) {
  if (!template) return ''
  // 将 * 占位符高亮显示
  return template
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*/g, '<span class="wildcard">*</span>')
}

function getLevelClass(level) {
  if (!level) return 'level-info'
  const l = level.toLowerCase()
  if (l === 'error' || l === 'critical') return 'level-error'
  if (l === 'warning' || l === 'warn') return 'level-warning'
  if (l === 'note' || l === 'notice') return 'level-note'
  return 'level-info'
}

function getLevelColor(level) {
  if (!level) return 'var(--accent-cyan)'
  const l = level.toLowerCase()
  if (l === 'error' || l === 'critical') return 'var(--accent-red)'
  if (l === 'warning' || l === 'warn') return 'var(--accent-yellow)'
  if (l === 'note' || l === 'notice') return 'var(--accent-purple)'
  return 'var(--accent-cyan)'
}

function getCountBarWidth(count) {
  if (!count || count <= 0) return 0
  const maxCount = Math.max(...patterns.value.map(p => p.count || 0), 1)
  return Math.round((count / maxCount) * 100)
}

function getTrendClass(trend) {
  if (trend === 'increasing') return 'trend-up'
  if (trend === 'decreasing') return 'trend-down'
  if (trend === 'spike') return 'trend-spike'
  return 'trend-stable'
}

function getTrendSymbol(trend) {
  if (trend === 'increasing') return '↑'
  if (trend === 'decreasing') return '↓'
  if (trend === 'spike') return '⚡'
  return '→'
}

function getTrendDescription(trend) {
  if (trend === 'increasing') return '持续增长'
  if (trend === 'decreasing') return '逐步减少'
  if (trend === 'spike') return '突然激增'
  return '保持稳定'
}

function getSuggestedAction(pattern) {
  const level = (pattern.level || '').toLowerCase()
  const category = (pattern.category || '').toLowerCase()
  if (level === 'error' || level === 'critical') {
    if (category.includes('connection') || category.includes('连接')) return '检查数据库连接配置和网络状态'
    if (category.includes('replication') || category.includes('复制')) return '检查主从复制状态和网络延迟'
    if (category.includes('innodb') || category.includes('存储')) return '检查 InnoDB 状态和磁盘空间'
    if (category.includes('lock') || category.includes('锁')) return '检查锁等待和长事务'
    return '建议立即排查错误原因，关注相关日志详情'
  }
  if (level === 'warning' || level === 'warn') {
    if (category.includes('connection') || category.includes('连接')) return '关注连接数变化，检查是否接近上限'
    if (category.includes('memory') || category.includes('内存')) return '监控内存使用，考虑优化配置'
    return '持续关注，防止升级为错误级别'
  }
  return '常规关注，无需紧急处理'
}

function getTrendBarWidth(count, patternId) {
  if (!count || count <= 0) return 0
  const data = trendData[patternId]
  if (!data || data.length === 0) return 0
  const maxCount = Math.max(...data.map(d => d.count || 0), 1)
  return Math.round((count / maxCount) * 100)
}

// 交互
async function handleRecognize() {
  recognizing.value = true
  try {
    const res = await api.recognizePatterns({ period: timeRange.value })
    const data = res.data || {}
    patterns.value = data.patterns || data.items || (Array.isArray(data) ? data : [])
    await loadStats()
  } catch (e) {
    console.error('recognizePatterns error', e)
  } finally {
    recognizing.value = false
  }
}

function handleAnomalyToggle() {
  // 切换异常模式时，如果需要可以加载异常数据
  if (anomalyOnly.value && patterns.value.length === 0) {
    loadAnomalies()
  }
}

async function loadAnomalies() {
  loading.value = true
  try {
    const res = await api.getPatternAnomalies({ period: timeRange.value })
    const data = res.data || {}
    patterns.value = data.patterns || data.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('getPatternAnomalies error', e)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await api.getPatternStats({ period: timeRange.value })
    patternStats.value = res.data || {}
  } catch (e) {
    console.error('getPatternStats error', e)
  }
}

async function loadPatternTrend(patternId) {
  trendLoading[patternId] = true
  try {
    const res = await api.getPatternTrend(patternId, { period: timeRange.value })
    const data = res.data || {}
    trendData[patternId] = data.items || data.trend || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('getPatternTrend error', e)
    trendData[patternId] = []
  } finally {
    trendLoading[patternId] = false
  }
}

function toggleTrend(patternId) {
  if (expandedTrends[patternId]) {
    expandedTrends[patternId] = false
  } else {
    expandedTrends[patternId] = true
    if (!trendData[patternId]) {
      loadPatternTrend(patternId)
    }
  }
}

function toggleSample(patternId) {
  expandedSamples[patternId] = !expandedSamples[patternId]
}

function changeTimeRange(range) {
  timeRange.value = range
  loadStats()
}

// 初始化
onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.pattern-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.recognize-btn {
  padding: 8px 20px;
  background: var(--accent-blue);
  border: none;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s;
}

.recognize-btn:hover:not(:disabled) {
  background: #2563eb;
}

.recognize-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.anomaly-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  user-select: none;
}

.anomaly-toggle input[type="checkbox"] {
  accent-color: var(--accent-red);
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.toggle-label {
  font-size: 13px;
}

.time-range {
  display: flex;
  gap: 4px;
}

.range-btn {
  padding: 5px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.range-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.range-btn.active {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

/* 统计摘要 */
.stats-bar {
  display: flex;
  gap: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 20px;
}

.stats-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  text-align: center;
}

.stats-label {
  font-size: 12px;
  color: var(--text-muted);
}

.stats-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stats-item.anomaly .stats-value {
  color: var(--accent-red);
}

.stats-value.highlight {
  color: var(--accent-cyan);
}

/* 模式列表 */
.pattern-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pattern-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: border-color 0.2s;
}

.pattern-card:hover {
  border-color: var(--accent-blue);
}

.pattern-card.anomaly-card {
  border-left: 3px solid var(--accent-red);
}

.pattern-card.anomaly-detail-card {
  padding: 20px;
  background: rgba(239, 68, 68, 0.04);
}

/* 模板行 */
.template-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.template-text {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  word-break: break-all;
  flex: 1;
}

.template-text :deep(.wildcard) {
  color: var(--accent-cyan);
  font-weight: 700;
}

/* 异常指示器 */
.anomaly-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.anomaly-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.anomaly-indicator.is-normal .anomaly-dot {
  background: var(--accent-green);
  box-shadow: 0 0 4px var(--accent-green);
}

.anomaly-indicator.is-anomaly .anomaly-dot {
  background: var(--accent-red);
  box-shadow: 0 0 6px var(--accent-red);
}

.anomaly-dot.pulse {
  animation: pulse-red 1.5s ease-in-out infinite;
}

@keyframes pulse-red {
  0%, 100% {
    box-shadow: 0 0 4px var(--accent-red);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 0 12px var(--accent-red), 0 0 20px rgba(239, 68, 68, 0.3);
    transform: scale(1.2);
  }
}

.anomaly-score {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-red);
  font-variant-numeric: tabular-nums;
}

.trend-arrow {
  font-size: 14px;
  font-weight: 700;
}

.trend-up {
  color: var(--accent-red);
}

.trend-down {
  color: var(--accent-green);
}

.trend-spike {
  color: var(--accent-yellow);
}

.trend-stable {
  color: var(--text-muted);
}

/* 元数据行 */
.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.level-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.level-badge.level-error {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.level-badge.level-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.level-badge.level-note {
  background: rgba(139, 92, 246, 0.2);
  color: var(--accent-purple);
}

.level-badge.level-info {
  background: rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}

.category-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent-blue);
}

.error-codes {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.error-code {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(139, 92, 246, 0.15);
  color: var(--accent-purple);
  font-family: 'Courier New', monospace;
}

/* 计数行 */
.count-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.count-number {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  min-width: 40px;
  font-variant-numeric: tabular-nums;
}

.count-bar-bg {
  flex: 1;
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 3px;
  overflow: hidden;
}

.count-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
  min-width: 2px;
}

/* 时间行 */
.time-row {
  display: flex;
  gap: 16px;
  font-size: 12px;
}

.time-label {
  color: var(--text-muted);
}

.time-value {
  color: var(--text-secondary);
}

/* 异常详情 */
.anomaly-detail {
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.anomaly-detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 13px;
}

.anomaly-detail-label {
  color: var(--text-muted);
  min-width: 70px;
  flex-shrink: 0;
}

.anomaly-detail-score {
  color: var(--accent-red);
  font-weight: 700;
  font-size: 18px;
}

.anomaly-detail-trend {
  font-weight: 600;
}

.anomaly-detail-action {
  color: var(--accent-cyan);
  line-height: 1.4;
}

/* 操作行 */
.action-row {
  display: flex;
  gap: 8px;
}

.trend-btn,
.sample-btn {
  padding: 4px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.trend-btn:hover,
.sample-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent-blue);
}

/* 趋势视图 */
.trend-view {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trend-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 3px 0;
}

.trend-bar-row.trend-anomaly {
  background: rgba(239, 68, 68, 0.1);
  border-radius: 3px;
  padding: 3px 6px;
}

.trend-hour {
  color: var(--text-muted);
  min-width: 40px;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.trend-bar-track {
  flex: 1;
  height: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  overflow: hidden;
}

.trend-bar-fill {
  display: block;
  height: 100%;
  background: var(--accent-blue);
  border-radius: 4px;
  transition: width 0.3s ease;
  min-width: 2px;
}

.trend-anomaly .trend-bar-fill {
  background: var(--accent-red);
}

.trend-count {
  color: var(--text-secondary);
  min-width: 24px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 样本视图 */
.sample-view {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sample-msg {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding: 6px 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  word-break: break-all;
}

/* 通用 */
.loading-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

.loading-text.small {
  padding: 10px;
  font-size: 12px;
}

.empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

.empty-text.small {
  padding: 10px;
  font-size: 12px;
}

/* 响应式 */
@media (max-width: 768px) {
  .panel-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .header-actions {
    width: 100%;
    flex-wrap: wrap;
    gap: 8px;
  }

  .recognize-btn {
    padding: 7px 16px;
    font-size: 12px;
  }

  .time-range {
    flex-wrap: wrap;
  }

  .range-btn {
    padding: 4px 8px;
    font-size: 11px;
  }

  .stats-bar {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px;
  }

  .stats-item {
    min-width: calc(50% - 5px);
  }

  .stats-value {
    font-size: 16px;
  }

  .stats-label {
    font-size: 11px;
  }

  .pattern-card {
    padding: 12px;
    gap: 8px;
  }

  .template-text {
    font-size: 12px;
  }

  .template-row {
    flex-direction: column;
    gap: 6px;
  }

  .anomaly-indicator {
    align-self: flex-start;
  }

  .meta-row {
    gap: 6px;
  }

  .time-row {
    flex-direction: column;
    gap: 4px;
  }

  .count-row {
    gap: 8px;
  }

  .count-number {
    font-size: 13px;
  }

  .anomaly-detail {
    padding: 10px;
  }

  .anomaly-detail-row {
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
  }

  .anomaly-detail-label {
    min-width: unset;
  }

  .trend-view {
    padding: 8px;
  }

  .sample-view {
    padding: 8px;
  }
}
</style>
