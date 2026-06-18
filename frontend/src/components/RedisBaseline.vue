<template>
  <div class="redis-baseline">
    <!-- 头部操作栏 -->
    <div class="panel-header">
      <h2 class="panel-title">Redis 性能基线</h2>
      <div class="header-actions">
        <button class="action-btn collect-btn" :disabled="collecting" @click="handleCollect">
          {{ collecting ? '采集中...' : '采集指标' }}
        </button>
        <div class="build-control">
          <input
            type="number"
            class="days-input"
            v-model.number="buildDays"
            min="1"
            max="90"
            placeholder="天数"
          />
          <button class="action-btn build-btn" :disabled="building" @click="handleBuild">
            {{ building ? '构建中...' : '构建基线' }}
          </button>
        </div>
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

    <!-- 错误状态 -->
    <div v-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="error = ''">关闭</button>
    </div>

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

    <!-- Tab 1：基线列表 -->
    <div v-if="activeTab === 'baselines'" class="tab-content">
      <div class="section-card">
        <div class="section-header">
          <h3>基线列表</h3>
          <div class="filter-control">
            <label class="filter-label">筛选指标：</label>
            <select class="filter-select" v-model="baselineFilter">
              <option value="">全部</option>
              <option v-for="name in baselineMetricNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </div>
        </div>
        <div v-if="baselinesLoading" class="loading-text">加载中...</div>
        <div v-else-if="filteredBaselines.length === 0" class="empty-text">暂无基线数据，请先采集指标并构建基线</div>
        <div v-else class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>指标名</th>
                <th>周期</th>
                <th>均值</th>
                <th>标准差</th>
                <th>P95</th>
                <th>P99</th>
                <th>样本数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(b, idx) in filteredBaselines" :key="idx">
                <td class="metric-name">{{ b.metric_name }}</td>
                <td>{{ b.period || b.period_type || '-' }}</td>
                <td>{{ formatValue(b.mean) }}</td>
                <td>{{ formatValue(b.std) }}</td>
                <td>{{ formatValue(b.p95) }}</td>
                <td>{{ formatValue(b.p99) }}</td>
                <td>{{ b.sample_count ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab 2：异常检测 -->
    <div v-if="activeTab === 'anomalies'" class="tab-content">
      <div class="section-card">
        <div class="section-header">
          <h3>异常事件</h3>
          <span class="anomaly-count-badge" v-if="anomalies.length > 0">{{ anomalies.length }} 项异常</span>
        </div>
        <div v-if="anomaliesLoading" class="loading-text">加载中...</div>
        <div v-else-if="anomalies.length === 0" class="empty-text">暂无异常事件</div>
        <div v-else class="anomaly-list">
          <div
            v-for="(a, idx) in anomalies"
            :key="idx"
            class="anomaly-card"
            :class="'severity-' + (a.severity || 'warning')"
          >
            <div class="anomaly-header">
              <span class="anomaly-metric">{{ a.metric_name }}</span>
              <span class="severity-badge" :class="'sev-' + (a.severity || 'warning')">{{ getSeverityLabel(a.severity) }}</span>
            </div>
            <div class="anomaly-values">
              <span class="anomaly-current">{{ formatValue(a.current) }}</span>
              <span class="anomaly-vs">vs 基线</span>
              <span class="anomaly-baseline">{{ formatValue(a.baseline_mean) }}</span>
              <span class="anomaly-direction" :class="a.direction === 'above' ? 'dir-up' : 'dir-down'">
                {{ a.direction === 'above' ? '↑' : '↓' }}
              </span>
            </div>
            <div class="anomaly-deviation">
              偏离度：
              <span class="deviation" :class="getDeviationClass(Math.abs(a.deviation || 0))">
                {{ a.deviation != null ? (a.deviation > 0 ? '+' : '') + a.deviation.toFixed(2) + 'σ' : '-' }}
              </span>
            </div>
            <div class="anomaly-desc" v-if="a.description">{{ a.description }}</div>
            <div class="anomaly-time" v-if="a.timestamp">{{ formatTime(a.timestamp) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 3：预测 -->
    <div v-if="activeTab === 'forecast'" class="tab-content">
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
          <label class="filter-label">预测时长(小时)：</label>
          <input
            type="number"
            class="hours-input"
            v-model.number="forecastHours"
            min="1"
            max="168"
          />
          <button class="action-btn forecast-btn" :disabled="!forecastMetric || forecastLoading" @click="loadForecast">
            {{ forecastLoading ? '加载中...' : '加载预测' }}
          </button>
        </div>

        <div v-if="forecastLoading" class="loading-text">加载预测数据...</div>
        <template v-else-if="forecastData.length > 0">
          <!-- ECharts 折线图 -->
          <div ref="forecastChartEl" class="forecast-chart"></div>
          <!-- 预测数据表格 -->
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>预测值</th>
                  <th>下限</th>
                  <th>上限</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(f, idx) in forecastData" :key="idx">
                  <td>{{ f.time }}</td>
                  <td class="metric-name">{{ formatValue(f.predicted) }}</td>
                  <td>{{ formatValue(f.lower) }}</td>
                  <td>{{ formatValue(f.upper) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <div v-else-if="forecastMetric && !forecastLoading" class="empty-text">请点击"加载预测"查看预测数据</div>
        <div v-else class="empty-text">请选择指标查看预测</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api.js'
import { formatTimeShortWithSeconds as formatTime } from '../utils/datetime.js'

const tabs = [
  { label: '基线列表', value: 'baselines', icon: '📊' },
  { label: '异常检测', value: 'anomalies', icon: '⚠️' },
  { label: '预测', value: 'forecast', icon: '📈' }
]

const activeTab = ref('baselines')

// 操作状态
const collecting = ref(false)
const building = ref(false)
const baselinesLoading = ref(false)
const anomaliesLoading = ref(false)
const forecastLoading = ref(false)
const error = ref('')

// 参数
const buildDays = ref(7)
const sensitivity = ref(2.0)
const baselineFilter = ref('')
const forecastMetric = ref('')
const forecastHours = ref(24)

// 数据
const baselines = ref([])
const anomalies = ref([])
const forecastData = ref([])

// 图表
const forecastChartEl = ref(null)
let chartInstance = null

const baselineMetricNames = computed(() => {
  const names = new Set(baselines.value.map(b => b.metric_name))
  anomalies.value.forEach(a => { if (a.metric_name) names.add(a.metric_name) })
  return [...names].sort()
})

const filteredBaselines = computed(() => {
  if (!baselineFilter.value) return baselines.value
  return baselines.value.filter(b => b.metric_name === baselineFilter.value)
})

function formatValue(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  if (Number.isInteger(num) && Math.abs(num) < 1e6) return num.toString()
  if (Math.abs(num) >= 1e6) return num.toExponential(2)
  if (Math.abs(num) < 0.01 && num !== 0) return num.toExponential(2)
  return num.toFixed(2)
}

function getDeviationClass(deviation) {
  if (deviation == null) return ''
  const abs = Math.abs(deviation)
  if (abs > 2) return 'dev-critical'
  if (abs > 1.5) return 'dev-warning'
  return 'dev-normal'
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
async function handleCollect() {
  collecting.value = true
  error.value = ''
  try {
    await api.collectRedisMetrics({})
    await loadBaselines()
  } catch (e) {
    error.value = '采集指标失败: ' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    collecting.value = false
  }
}

async function handleBuild() {
  building.value = true
  error.value = ''
  try {
    await api.buildRedisBaseline({ days: buildDays.value })
    await Promise.all([loadBaselines(), loadAnomalies()])
  } catch (e) {
    error.value = '构建基线失败: ' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    building.value = false
  }
}

async function loadBaselines() {
  baselinesLoading.value = true
  try {
    const res = await api.getRedisBaselines({})
    const data = res.data || {}
    baselines.value = data.baselines || data.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('getRedisBaselines error', e)
    baselines.value = []
  } finally {
    baselinesLoading.value = false
  }
}

async function loadAnomalies() {
  anomaliesLoading.value = true
  try {
    const res = await api.getRedisAnomalies({ sensitivity: sensitivity.value })
    const data = res.data || {}
    anomalies.value = data.anomalies || data.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('getRedisAnomalies error', e)
    anomalies.value = []
  } finally {
    anomaliesLoading.value = false
  }
}

async function loadForecast() {
  if (!forecastMetric.value) return
  forecastLoading.value = true
  try {
    const res = await api.getRedisForecast({
      metric_name: forecastMetric.value,
      hours: forecastHours.value
    })
    const data = res.data || {}
    const items = data.forecasts || data.items || (Array.isArray(data) ? data : [])
    forecastData.value = items.map(f => ({
      time: f.time || f.hour || f.timestamp || '-',
      predicted: f.predicted ?? f.value ?? null,
      lower: f.lower ?? f.min ?? null,
      upper: f.upper ?? f.max ?? null
    }))
    await nextTick()
    renderChart()
  } catch (e) {
    console.error('getRedisForecast error', e)
    forecastData.value = []
  } finally {
    forecastLoading.value = false
  }
}

function renderChart() {
  if (!forecastChartEl.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(forecastChartEl.value)
  }
  const times = forecastData.value.map(f => f.time)
  const predicted = forecastData.value.map(f => f.predicted)
  const lower = forecastData.value.map(f => f.lower)
  const upper = forecastData.value.map(f => f.upper)

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(26, 34, 52, 0.95)',
      borderColor: '#2a3a52',
      textStyle: { color: '#e2e8f0', fontSize: 12 }
    },
    legend: {
      data: ['预测值', '下限', '上限'],
      textStyle: { color: '#94a3b8', fontSize: 12 },
      top: 0
    },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: times,
      axisLine: { lineStyle: { color: '#2a3a52' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: '#2a3a52' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(42, 58, 82, 0.4)' } }
    },
    series: [
      {
        name: '预测值',
        type: 'line',
        data: predicted,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#3b82f6', width: 2 },
        itemStyle: { color: '#3b82f6' }
      },
      {
        name: '下限',
        type: 'line',
        data: lower,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#10b981', width: 1, type: 'dashed' },
        itemStyle: { color: '#10b981' }
      },
      {
        name: '上限',
        type: 'line',
        data: upper,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f59e0b', width: 1, type: 'dashed' },
        itemStyle: { color: '#f59e0b' }
      }
    ]
  }
  chartInstance.setOption(option, true)
}

function handleResize() {
  if (chartInstance) chartInstance.resize()
}

// 切换到预测 Tab 且有数据时重新渲染
watch(activeTab, (val) => {
  if (val === 'forecast' && forecastData.value.length > 0) {
    nextTick(() => renderChart())
  }
})

watch(sensitivity, () => {
  if (activeTab.value === 'anomalies') loadAnomalies()
})

onMounted(() => {
  loadBaselines()
  loadAnomalies()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.redis-baseline {
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
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 8px 18px;
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

.collect-btn {
  background: var(--accent-cyan);
  color: #1a1a1a;
}

.collect-btn:hover:not(:disabled) {
  background: #0891b2;
}

.build-btn {
  background: var(--accent-blue);
}

.build-btn:hover:not(:disabled) {
  background: #2563eb;
}

.forecast-btn {
  background: var(--accent-purple);
}

.forecast-btn:hover:not(:disabled) {
  background: #7c3aed;
}

.build-control {
  display: flex;
  align-items: center;
  gap: 6px;
}

.days-input {
  width: 70px;
  padding: 7px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}

.days-input:focus {
  border-color: var(--accent-blue);
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
  flex-wrap: wrap;
  gap: 8px;
}

.section-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.filter-control {
  display: flex;
  align-items: center;
  gap: 8px;
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
  outline: none;
}

.filter-select:focus {
  border-color: var(--accent-blue);
}

/* 表格 */
.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.data-table th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.data-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.metric-name {
  font-weight: 600;
  color: var(--accent-cyan);
  white-space: nowrap;
}

/* 异常列表 */
.anomaly-count-badge {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
  font-weight: 600;
}

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
  color: var(--text-secondary);
}

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

.anomaly-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.anomaly-time {
  font-size: 11px;
  color: var(--text-muted);
}

/* 预测区 */
.forecast-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.hours-input {
  width: 70px;
  padding: 5px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 12px;
  outline: none;
}

.hours-input:focus {
  border-color: var(--accent-blue);
}

.forecast-chart {
  width: 100%;
  height: 320px;
  margin-bottom: 16px;
}

/* 通用 */
.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 响应式 */
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

  .build-control {
    width: 100%;
  }

  .days-input {
    flex: 1;
  }

  .sensitivity-control {
    width: 100%;
    justify-content: space-between;
  }

  .sensitivity-slider {
    flex: 1;
  }

  .action-btn {
    width: 100%;
    text-align: center;
  }

  .tabs-bar {
    flex-direction: column;
  }

  .tab-btn {
    width: 100%;
  }

  .filter-control {
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
    align-items: stretch;
    gap: 6px;
  }

  .forecast-chart {
    height: 240px;
  }

  .data-table {
    font-size: 11px;
  }

  .data-table th,
  .data-table td {
    padding: 6px 8px;
  }
}
</style>
