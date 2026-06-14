<template>
  <div class="baseline-panel">
    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">性能基线与异常检测</h2>
      <div class="header-actions">
        <button class="action-btn build-btn" :disabled="building" @click="handleBuild">
          {{ building ? '构建中...' : '构建基线' }}
        </button>
        <button class="action-btn detect-btn" :disabled="detecting" @click="handleDetect">
          {{ detecting ? '检测中...' : '检测异常' }}
        </button>
        <div class="sensitivity-control">
          <span class="sensitivity-label">灵敏度</span>
          <input
            type="range"
            class="sensitivity-slider"
            v-model.number="sensitivity"
            min="1.0"
            max="4.0"
            step="0.5"
          />
          <span class="sensitivity-value">{{ sensitivity.toFixed(1) }}σ</span>
        </div>
      </div>
    </div>

    <!-- 概览仪表盘 -->
    <div class="overview-cards">
      <div class="overview-card">
        <div class="ov-icon" style="color: var(--accent-blue)">📊</div>
        <div class="ov-info">
          <div class="ov-value">{{ overview.baseline_count ?? '-' }}</div>
          <div class="ov-label">已建基线数</div>
        </div>
      </div>
      <div class="overview-card" :class="{ 'ov-warning': anomalyCount > 0 && anomalyCount <= 2, 'ov-critical': anomalyCount >= 3 }">
        <div class="ov-icon" :style="{ color: anomalyCount === 0 ? 'var(--accent-green)' : anomalyCount <= 2 ? 'var(--accent-yellow)' : 'var(--accent-red)' }">⚠️</div>
        <div class="ov-info">
          <div class="ov-value">{{ anomalyCount }}</div>
          <div class="ov-label">当前异常数</div>
        </div>
      </div>
      <div class="overview-card">
        <div class="ov-icon" style="color: var(--accent-cyan)">📈</div>
        <div class="ov-info">
          <div class="ov-value">{{ overview.metric_count ?? '-' }}</div>
          <div class="ov-label">监控指标数</div>
        </div>
      </div>
      <div class="overview-card" :class="healthClass">
        <div class="ov-icon" :style="{ color: healthColor }">💊</div>
        <div class="ov-info">
          <div class="ov-value" :style="{ color: healthColor }">{{ healthLabel }}</div>
          <div class="ov-label">健康状态</div>
        </div>
      </div>
    </div>

    <!-- 指标状态表 -->
    <div class="section-card">
      <div class="section-header">
        <h3>指标状态</h3>
      </div>
      <div v-if="anomaliesLoading" class="loading-text">加载中...</div>
      <div v-else-if="metricStatusList.length === 0" class="empty-text">暂无指标数据，请先构建基线并检测异常</div>
      <template v-else>
        <div class="metric-table-wrapper desktop-only">
          <table class="metric-table">
            <thead>
              <tr>
                <th>指标</th>
                <th>当前值</th>
                <th>基线均值</th>
                <th>偏离度</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in metricStatusList" :key="m.metric_name">
                <td class="metric-name">{{ m.metric_name }}</td>
                <td>{{ formatValue(m.current) }}</td>
                <td>{{ formatValue(m.baseline_mean) }}</td>
                <td>
                  <span class="deviation" :class="getDeviationClass(m.deviation)">
                    {{ m.deviation != null ? m.deviation.toFixed(2) + 'σ' : '-' }}
                  </span>
                </td>
                <td>
                  <span class="status-badge" :class="getStatusClass(m.status)">{{ getStatusLabel(m.status) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="metric-cards mobile-only">
          <div v-for="m in metricStatusList" :key="m.metric_name" class="metric-card">
            <div class="mc-header">
              <span class="mc-name">{{ m.metric_name }}</span>
              <span class="status-badge" :class="getStatusClass(m.status)">{{ getStatusLabel(m.status) }}</span>
            </div>
            <div class="mc-body">
              <div class="mc-row">
                <span class="mc-label">当前值</span>
                <span class="mc-val">{{ formatValue(m.current) }}</span>
              </div>
              <div class="mc-row">
                <span class="mc-label">基线均值</span>
                <span class="mc-val">{{ formatValue(m.baseline_mean) }}</span>
              </div>
              <div class="mc-row">
                <span class="mc-label">偏离度</span>
                <span class="deviation" :class="getDeviationClass(m.deviation)">
                  {{ m.deviation != null ? m.deviation.toFixed(2) + 'σ' : '-' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 异常列表 -->
    <div class="section-card" v-if="anomalies.length > 0">
      <div class="section-header">
        <h3>异常列表</h3>
        <span class="anomaly-count-badge">{{ anomalies.length }} 项异常</span>
      </div>
      <div class="anomaly-list">
        <div v-for="(a, idx) in anomalies" :key="idx" class="anomaly-card" :class="'severity-' + (a.severity || 'warning')">
          <div class="anomaly-header">
            <span class="anomaly-metric">{{ a.metric_name }}</span>
            <span class="severity-badge" :class="'sev-' + (a.severity || 'warning')">{{ getSeverityLabel(a.severity) }}</span>
          </div>
          <div class="anomaly-values">
            <span class="anomaly-current">{{ formatValue(a.current) }}</span>
            <span class="anomaly-vs">vs</span>
            <span class="anomaly-baseline">{{ formatValue(a.baseline_mean) }}</span>
            <span class="anomaly-direction" :class="a.direction === 'above' ? 'dir-up' : 'dir-down'">
              {{ a.direction === 'above' ? '↑' : '↓' }}
            </span>
          </div>
          <div class="anomaly-deviation">
            <span class="deviation" :class="getDeviationClass(Math.abs(a.deviation || 0))">
              {{ a.deviation != null ? (a.deviation > 0 ? '+' : '') + a.deviation.toFixed(1) + 'σ' : '-' }}
            </span>
          </div>
          <div class="anomaly-desc" v-if="a.description">{{ a.description }}</div>
          <div class="anomaly-time" v-if="a.timestamp">{{ formatTime(a.timestamp) }}</div>
        </div>
      </div>
    </div>

    <!-- 基线详情（可折叠） -->
    <div class="section-card">
      <div class="section-header collapsible" @click="baselineExpanded = !baselineExpanded">
        <h3>基线详情</h3>
        <span class="collapse-icon">{{ baselineExpanded ? '▼' : '▶' }}</span>
      </div>
      <div v-if="baselineExpanded" class="baseline-content">
        <div class="baseline-filter">
          <label class="filter-label">筛选指标：</label>
          <select class="filter-select" v-model="baselineFilter">
            <option value="">全部</option>
            <option v-for="name in baselineMetricNames" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
        <div v-if="baselinesLoading" class="loading-text">加载中...</div>
        <div v-else-if="filteredBaselines.length === 0" class="empty-text">暂无基线数据</div>
        <template v-else>
          <div class="baseline-table-wrapper">
            <table class="baseline-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>周期</th>
                  <th>周期键</th>
                  <th>均值</th>
                  <th>标准差</th>
                  <th>P50</th>
                  <th>P95</th>
                  <th>P99</th>
                  <th>样本数</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(b, idx) in filteredBaselines" :key="idx">
                  <td class="metric-name">{{ b.metric_name }}</td>
                  <td>{{ b.period }}</td>
                  <td>{{ b.period_key }}</td>
                  <td>{{ formatValue(b.mean) }}</td>
                  <td>{{ formatValue(b.std) }}</td>
                  <td>{{ formatValue(b.p50) }}</td>
                  <td>{{ formatValue(b.p95) }}</td>
                  <td>{{ formatValue(b.p99) }}</td>
                  <td>{{ b.sample_count ?? '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>

    <!-- 预测区 -->
    <div class="section-card">
      <div class="section-header">
        <h3>指标预测</h3>
      </div>
      <div class="forecast-controls">
        <label class="filter-label">选择指标：</label>
        <select class="filter-select" v-model="forecastMetric">
          <option value="">请选择指标</option>
          <option v-for="name in baselineMetricNames" :key="name" :value="name">{{ name }}</option>
        </select>
        <button class="action-btn forecast-btn" :disabled="!forecastMetric || forecastLoading" @click="loadForecast">
          {{ forecastLoading ? '加载中...' : '加载预测' }}
        </button>
      </div>
      <div v-if="forecastLoading" class="loading-text">加载中...</div>
      <div v-else-if="forecastData.length > 0" class="forecast-list">
        <div v-for="(f, idx) in forecastData" :key="idx" class="forecast-row">
          <span class="forecast-time">{{ f.time }}</span>
          <span class="forecast-text">
            预测: <strong>{{ formatValue(f.predicted) }}</strong>
            <span class="forecast-range">(范围: {{ formatValue(f.lower) }} - {{ formatValue(f.upper) }})</span>
          </span>
        </div>
      </div>
      <div v-else-if="forecastMetric && !forecastLoading" class="empty-text">请点击"加载预测"查看预测数据</div>
      <div v-else class="empty-text">请选择指标查看预测</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'

// 状态
const building = ref(false)
const detecting = ref(false)
const anomaliesLoading = ref(false)
const baselinesLoading = ref(false)
const forecastLoading = ref(false)
const sensitivity = ref(2.0)
const overview = ref({})
const anomalies = ref([])
const baselines = ref([])
const baselineExpanded = ref(false)
const baselineFilter = ref('')
const forecastMetric = ref('')
const forecastData = ref([])

// 计算属性
const anomalyCount = computed(() => anomalies.value.length)

const healthLabel = computed(() => {
  const c = anomalyCount.value
  if (c === 0) return '健康'
  if (c <= 2) return '注意'
  return '告警'
})

const healthColor = computed(() => {
  const c = anomalyCount.value
  if (c === 0) return 'var(--accent-green)'
  if (c <= 2) return 'var(--accent-yellow)'
  return 'var(--accent-red)'
})

const healthClass = computed(() => {
  const c = anomalyCount.value
  if (c === 0) return 'ov-healthy'
  if (c <= 2) return 'ov-warning'
  return 'ov-critical'
})

const baselineMetricNames = computed(() => {
  const names = new Set(baselines.value.map(b => b.metric_name))
  anomalies.value.forEach(a => { if (a.metric_name) names.add(a.metric_name) })
  return [...names].sort()
})

const metricStatusList = computed(() => {
  if (anomalies.value.length === 0 && baselines.value.length === 0) return []
  const map = new Map()
  baselines.value.forEach(b => {
    if (!map.has(b.metric_name)) {
      map.set(b.metric_name, { metric_name: b.metric_name, baseline_mean: b.mean, current: null, deviation: null, status: 'normal' })
    }
  })
  anomalies.value.forEach(a => {
    const entry = map.get(a.metric_name) || { metric_name: a.metric_name, baseline_mean: a.baseline_mean, current: null, deviation: null, status: 'normal' }
    entry.current = a.current
    entry.deviation = a.deviation
    entry.status = a.severity || 'warning'
    map.set(a.metric_name, entry)
  })
  return [...map.values()]
})

const filteredBaselines = computed(() => {
  if (!baselineFilter.value) return baselines.value
  return baselines.value.filter(b => b.metric_name === baselineFilter.value)
})

// 方法
function formatValue(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  if (Number.isInteger(num) && Math.abs(num) < 1e6) return num.toString()
  if (Math.abs(num) >= 1e6) return num.toExponential(2)
  if (Math.abs(num) < 0.01 && num !== 0) return num.toExponential(2)
  return num.toFixed(2)
}

function formatTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '-'
  const month = d.getMonth() + 1
  const day = d.getDate()
  const hour = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  const sec = String(d.getSeconds()).padStart(2, '0')
  return `${month}/${day} ${hour}:${min}:${sec}`
}

function getDeviationClass(deviation) {
  if (deviation == null) return ''
  const abs = Math.abs(deviation)
  if (abs > 2) return 'dev-critical'
  if (abs > 1.5) return 'dev-warning'
  return 'dev-normal'
}

function getStatusClass(status) {
  if (!status) return 'status-normal'
  const s = status.toLowerCase()
  if (s === 'critical' || s === 'error') return 'status-critical'
  if (s === 'warning' || s === 'warn') return 'status-warning'
  return 'status-normal'
}

function getStatusLabel(status) {
  if (!status) return '正常'
  const s = status.toLowerCase()
  if (s === 'critical' || s === 'error') return '严重'
  if (s === 'warning' || s === 'warn') return '警告'
  return '正常'
}

function getSeverityLabel(severity) {
  if (!severity) return '警告'
  const s = severity.toLowerCase()
  if (s === 'critical') return '严重'
  if (s === 'warning') return '警告'
  if (s === 'info') return '信息'
  return '警告'
}

// API 调用
async function handleBuild() {
  building.value = true
  try {
    await api.buildBaselines({ sensitivity: sensitivity.value })
    await Promise.all([loadOverview(), loadBaselines()])
  } catch (e) {
    console.error('buildBaselines error', e)
  } finally {
    building.value = false
  }
}

async function handleDetect() {
  detecting.value = true
  anomaliesLoading.value = true
  try {
    const res = await api.getAnomalies({ sensitivity: sensitivity.value })
    const data = res.data || {}
    anomalies.value = data.anomalies || data.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('getAnomalies error', e)
  } finally {
    detecting.value = false
    anomaliesLoading.value = false
  }
}

async function loadOverview() {
  try {
    const res = await api.getBaselineOverview()
    overview.value = res.data || {}
  } catch (e) {
    console.error('getBaselineOverview error', e)
  }
}

async function loadBaselines() {
  baselinesLoading.value = true
  try {
    const res = await api.getBaselines({})
    const data = res.data || {}
    baselines.value = data.baselines || data.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('getBaselines error', e)
  } finally {
    baselinesLoading.value = false
  }
}

async function loadForecast() {
  if (!forecastMetric.value) return
  forecastLoading.value = true
  try {
    const res = await api.getMetricForecast(forecastMetric.value, { sensitivity: sensitivity.value })
    const data = res.data || {}
    const items = data.forecasts || data.items || (Array.isArray(data) ? data : [])
    forecastData.value = items.slice(0, 12).map(f => ({
      time: f.time || f.hour || f.timestamp || '-',
      predicted: f.predicted ?? f.value ?? null,
      lower: f.lower ?? f.min ?? null,
      upper: f.upper ?? f.max ?? null
    }))
  } catch (e) {
    console.error('getMetricForecast error', e)
    forecastData.value = []
  } finally {
    forecastLoading.value = false
  }
}

// 初始化
onMounted(() => {
  loadOverview()
  loadBaselines()
})
</script>

<style scoped>
.baseline-panel {
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

.action-btn {
  padding: 8px 20px;
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

.build-btn {
  background: var(--accent-blue);
}

.build-btn:hover:not(:disabled) {
  background: #2563eb;
}

.detect-btn {
  background: var(--accent-yellow);
  color: #1a1a1a;
}

.detect-btn:hover:not(:disabled) {
  background: #d97706;
}

.forecast-btn {
  background: var(--accent-cyan);
  color: #1a1a1a;
  padding: 6px 16px;
  font-size: 12px;
}

.forecast-btn:hover:not(:disabled) {
  background: #0891b2;
}

/* 灵敏度控制 */
.sensitivity-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sensitivity-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.sensitivity-slider {
  width: 100px;
  accent-color: var(--accent-blue);
  cursor: pointer;
}

.sensitivity-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-cyan);
  min-width: 36px;
  font-variant-numeric: tabular-nums;
}

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.overview-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: border-color 0.2s;
}

.overview-card.ov-healthy {
  border-color: var(--accent-green);
}

.overview-card.ov-warning {
  border-color: var(--accent-yellow);
  background: rgba(245, 158, 11, 0.06);
}

.overview-card.ov-critical {
  border-color: var(--accent-red);
  background: rgba(239, 68, 68, 0.06);
}

.ov-icon {
  font-size: 26px;
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

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.section-header.collapsible {
  cursor: pointer;
  user-select: none;
}

.collapse-icon {
  font-size: 12px;
  color: var(--text-muted);
}

/* 异常数量徽章 */
.anomaly-count-badge {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
  font-weight: 600;
}

/* 指标状态表 */
.metric-table-wrapper {
  overflow-x: auto;
}

.metric-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.metric-table th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.metric-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.metric-name {
  font-weight: 600;
  color: var(--accent-cyan);
  white-space: nowrap;
}

/* 偏离度 */
.deviation {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.dev-normal {
  color: var(--accent-green);
}

.dev-warning {
  color: var(--accent-yellow);
}

.dev-critical {
  color: var(--accent-red);
}

/* 状态徽章 */
.status-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.status-normal {
  background: rgba(16, 185, 129, 0.2);
  color: var(--accent-green);
}

.status-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.status-critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

/* 移动端指标卡片 */
.mobile-only { display: none; }
.desktop-only { display: block; }

.metric-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px 12px;
}

.mc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.mc-name {
  font-weight: 600;
  color: var(--accent-cyan);
  font-size: 13px;
}

.mc-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mc-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.mc-label {
  color: var(--text-muted);
}

.mc-val {
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* 异常列表 */
.anomaly-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.anomaly-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-left: 3px solid var(--accent-yellow);
}

.anomaly-card.severity-critical {
  border-left-color: var(--accent-red);
  background: rgba(239, 68, 68, 0.04);
}

.anomaly-card.severity-warning {
  border-left-color: var(--accent-yellow);
}

.anomaly-card.severity-info {
  border-left-color: var(--accent-cyan);
}

.anomaly-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.anomaly-metric {
  font-weight: 700;
  color: var(--text-primary);
  font-size: 14px;
}

.severity-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.sev-critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.sev-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.sev-info {
  background: rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}

.anomaly-values {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.anomaly-current {
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.anomaly-vs {
  color: var(--text-muted);
  font-size: 11px;
}

.anomaly-baseline {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.anomaly-direction {
  font-size: 16px;
  font-weight: 700;
}

.dir-up {
  color: var(--accent-red);
}

.dir-down {
  color: var(--accent-green);
}

.anomaly-deviation {
  font-size: 13px;
}

.anomaly-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.anomaly-time {
  font-size: 11px;
  color: var(--text-muted);
}

/* 基线详情 */
.baseline-content {
  margin-top: 8px;
}

.baseline-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.filter-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.filter-select {
  padding: 5px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  max-width: 200px;
}

.filter-select:focus {
  outline: none;
  border-color: var(--accent-blue);
}

.baseline-table-wrapper {
  overflow-x: auto;
}

.baseline-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.baseline-table th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.baseline-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.baseline-table .metric-name {
  color: var(--accent-cyan);
}

/* 预测区 */
.forecast-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.forecast-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.forecast-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
}

.forecast-time {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--accent-cyan);
  min-width: 50px;
  font-weight: 600;
}

.forecast-text {
  color: var(--text-primary);
}

.forecast-text strong {
  color: var(--accent-blue);
  font-variant-numeric: tabular-nums;
}

.forecast-range {
  color: var(--text-muted);
  font-size: 12px;
  margin-left: 4px;
}

/* 通用 */
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
  .mobile-only { display: flex; }
  .desktop-only { display: none; }

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

  .action-btn {
    padding: 7px 14px;
    font-size: 12px;
  }

  .sensitivity-control {
    width: 100%;
  }

  .sensitivity-slider {
    flex: 1;
  }

  .overview-cards {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .overview-card {
    padding: 12px;
    gap: 10px;
  }

  .ov-icon {
    font-size: 20px;
  }

  .ov-value {
    font-size: 18px;
  }

  .ov-label {
    font-size: 11px;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .baseline-filter {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .filter-select {
    max-width: 100%;
    width: 100%;
  }

  .forecast-controls {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .forecast-controls .filter-select {
    width: 100%;
  }

  .forecast-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    padding: 8px;
  }

  .anomaly-values {
    flex-wrap: wrap;
    gap: 6px;
  }
}
</style>
