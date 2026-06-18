<template>
  <div class="capacity-panel">
    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">容量规划</h2>
      <div class="header-actions">
        <div class="control-group">
          <label class="control-label">数据库类型</label>
          <select class="control-select" v-model="dbType">
            <option value="mysql">MySQL</option>
            <option value="redis">Redis</option>
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

    <!-- Tab 1：容量概览 -->
    <div v-if="activeTab === 'summary'" class="tab-content">
      <div v-if="summaryLoading" class="loading-state">
        <div class="loading-spinner"></div>
        <span>加载容量概览...</span>
      </div>
      <div v-else-if="capacityCards.length === 0" class="empty-state">
        <div class="empty-icon">📦</div>
        <p>暂无容量数据</p>
      </div>
      <div v-else class="capacity-grid">
        <div
          v-for="(card, idx) in capacityCards"
          :key="idx"
          :class="['cap-card', 'status-' + (card.status || 'normal')]"
        >
          <div class="cap-header">
            <span class="cap-icon">{{ card.icon }}</span>
            <span class="cap-name">{{ card.name }}</span>
            <span class="status-badge" :class="statusBadgeClass(card.status)">{{ statusLabel(card.status) }}</span>
          </div>
          <div class="cap-current">
            <span class="cap-current-value">{{ card.current }}</span>
            <span class="cap-current-label">当前值</span>
          </div>
          <div class="cap-meta">
            <div class="cap-meta-item">
              <span class="cap-meta-label">最大值</span>
              <span class="cap-meta-value">{{ card.max }}</span>
            </div>
            <div class="cap-meta-item">
              <span class="cap-meta-label">使用率</span>
              <span class="cap-meta-value" :class="usageClass(card.usagePercent)">{{ formatPercent(card.usagePercent) }}</span>
            </div>
          </div>
          <div class="cap-bar-wrapper" v-if="card.usagePercent != null">
            <div class="cap-bar" :class="usageBarClass(card.usagePercent)" :style="{ width: Math.min(100, card.usagePercent) + '%' }"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2：容量预测 -->
    <div v-if="activeTab === 'forecast'" class="tab-content">
      <div class="section-card">
        <div class="section-header">
          <h3>容量预测</h3>
        </div>
        <div class="forecast-controls">
          <label class="filter-label">选择指标：</label>
          <select class="filter-select" v-model="forecastMetric">
            <option value="">请选择指标</option>
            <option v-for="name in metricOptions" :key="name" :value="name">{{ name }}</option>
          </select>
          <label class="filter-label">预测天数：</label>
          <input
            type="number"
            class="days-input"
            v-model.number="forecastDays"
            min="1"
            max="90"
          />
          <button class="action-btn forecast-btn" :disabled="!forecastMetric || forecastLoading" @click="loadForecast">
            {{ forecastLoading ? '加载中...' : '加载预测' }}
          </button>
        </div>

        <div v-if="forecastLoading" class="loading-text">加载预测数据...</div>
        <template v-else-if="forecastLoaded">
          <!-- ECharts 折线图 -->
          <div ref="forecastChartEl" class="forecast-chart"></div>
          <!-- 预计达到阈值的日期 -->
          <div class="threshold-info" v-if="thresholdDate">
            <span class="threshold-icon">🎯</span>
            <span class="threshold-text">
              预计 <strong>{{ thresholdDate }}</strong> 达到阈值
            </span>
          </div>
          <div class="threshold-info threshold-safe" v-else>
            <span class="threshold-icon">✓</span>
            <span class="threshold-text">预测期内不会达到阈值</span>
          </div>
        </template>
        <div v-else class="empty-text">请选择指标并点击"加载预测"查看趋势</div>
      </div>
    </div>

    <!-- Tab 3：阈值检查 -->
    <div v-if="activeTab === 'threshold'" class="tab-content">
      <div class="section-card">
        <div class="section-header">
          <h3>阈值检查</h3>
          <button class="refresh-btn" @click="loadThresholdCheck">刷新</button>
        </div>
        <div v-if="thresholdLoading" class="loading-text">加载中...</div>
        <div v-else-if="thresholdItems.length === 0" class="empty-text">暂无阈值检查数据</div>
        <div v-else class="threshold-list">
          <div
            v-for="(item, idx) in thresholdItems"
            :key="idx"
            class="threshold-item"
            :class="'status-' + (item.status || 'normal')"
          >
            <div class="threshold-header">
              <span class="threshold-name">{{ item.metric || item.name || '-' }}</span>
              <span class="status-badge" :class="statusBadgeClass(item.status)">{{ statusLabel(item.status) }}</span>
            </div>
            <div class="threshold-values">
              <div class="tv-item">
                <span class="tv-label">当前值</span>
                <span class="tv-value">{{ item.current ?? item.current_value ?? '-' }}</span>
              </div>
              <div class="tv-item">
                <span class="tv-label">阈值</span>
                <span class="tv-value">{{ item.threshold ?? '-' }}</span>
              </div>
              <div class="tv-item">
                <span class="tv-label">使用率</span>
                <span class="tv-value" :class="usageClass(item.usage_percent)">{{ formatPercent(item.usage_percent) }}</span>
              </div>
            </div>
            <div class="threshold-suggestion" v-if="item.suggestion || item.recommendation">
              <span class="suggestion-label">💡 建议：</span>
              <span class="suggestion-text">{{ item.suggestion || item.recommendation }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api.js'
import { formatPercent } from '../utils/format.js'

const tabs = [
  { label: '容量概览', value: 'summary', icon: '📦' },
  { label: '容量预测', value: 'forecast', icon: '📈' },
  { label: '阈值检查', value: 'threshold', icon: '🎯' }
]

const activeTab = ref('summary')
const dbType = ref('mysql')
const instanceId = ref('')
const instances = ref([])
const error = ref('')

// 概览
const summaryLoading = ref(false)
const summaryData = ref({})

// 预测
const forecastMetric = ref('')
const forecastDays = ref(7)
const forecastLoading = ref(false)
const forecastLoaded = ref(false)
const forecastHistory = ref([])
const forecastPredicted = ref([])
const forecastTimes = ref([])
const thresholdDate = ref('')

// 阈值检查
const thresholdLoading = ref(false)
const thresholdItems = ref([])

// 图表
const forecastChartEl = ref(null)
let chartInstance = null

const metricOptions = computed(() => {
  const names = new Set()
  thresholdItems.value.forEach(i => { if (i.metric || i.name) names.add(i.metric || i.name) })
  capacityCards.value.forEach(c => { if (c.metricKey) names.add(c.metricKey) })
  // 默认指标
  if (names.size === 0) {
    return ['memory', 'connections', 'keys', 'cpu', 'disk']
  }
  return [...names].sort()
})

const capacityCards = computed(() => {
  const d = summaryData.value || {}
  const items = d.items || d.metrics || d.cards
  if (Array.isArray(items) && items.length > 0) {
    return items.map(it => normalizeCard(it))
  }
  // 兼容扁平结构
  const cards = []
  if (d.memory || d.used_memory != null) {
    cards.push(normalizeCard({
      name: '内存',
      icon: '💾',
      metric_key: 'memory',
      current: d.memory?.current ?? d.used_memory,
      max: d.memory?.max ?? d.max_memory,
      usage_percent: d.memory?.usage_percent ?? d.memory_usage_percent,
      status: d.memory?.status
    }))
  }
  if (d.connections || d.connected_clients != null) {
    cards.push(normalizeCard({
      name: '连接数',
      icon: '🔗',
      metric_key: 'connections',
      current: d.connections?.current ?? d.connected_clients,
      max: d.connections?.max ?? d.max_clients,
      usage_percent: d.connections?.usage_percent,
      status: d.connections?.status
    }))
  }
  if (d.keys || d.total_keys != null) {
    cards.push(normalizeCard({
      name: 'Key 数',
      icon: '🔑',
      metric_key: 'keys',
      current: d.keys?.current ?? d.total_keys,
      max: d.keys?.max,
      usage_percent: d.keys?.usage_percent,
      status: d.keys?.status
    }))
  }
  if (d.fragmentation || d.fragmentation_ratio != null) {
    cards.push(normalizeCard({
      name: '碎片率',
      icon: '🧩',
      metric_key: 'fragmentation',
      current: d.fragmentation?.current ?? d.fragmentation_ratio,
      max: d.fragmentation?.max,
      usage_percent: d.fragmentation?.usage_percent,
      status: d.fragmentation?.status
    }))
  }
  return cards
})

function normalizeCard(it) {
  const usagePercent = it.usage_percent ?? it.usagePercent ?? it.usage
  return {
    name: it.name || it.metric || it.title || '-',
    icon: it.icon || '📊',
    metricKey: it.metric_key || it.metric || it.key,
    current: it.current ?? it.current_value ?? it.value ?? '-',
    max: it.max ?? it.max_value ?? it.limit ?? '-',
    usagePercent: usagePercent != null ? Number(usagePercent) : null,
    status: it.status || (usagePercent != null ? statusFromUsage(usagePercent) : 'normal')
  }
}

function statusFromUsage(percent) {
  const num = Number(percent)
  if (num >= 90) return 'critical'
  if (num >= 70) return 'warning'
  return 'normal'
}

function statusBadgeClass(status) {
  const s = (status || 'normal').toLowerCase()
  if (s === 'critical' || s === 'error') return 'badge-red'
  if (s === 'warning' || s === 'warn') return 'badge-yellow'
  if (s === 'normal' || s === 'healthy' || s === 'ok') return 'badge-green'
  return 'badge-gray'
}

function statusLabel(status) {
  const s = (status || 'normal').toLowerCase()
  if (s === 'critical' || s === 'error') return '严重'
  if (s === 'warning' || s === 'warn') return '告警'
  if (s === 'normal' || s === 'healthy' || s === 'ok') return '正常'
  return status || '未知'
}

function usageClass(percent) {
  if (percent == null) return ''
  const num = Number(percent)
  if (num >= 90) return 'usage-critical'
  if (num >= 70) return 'usage-warning'
  return 'usage-healthy'
}

function usageBarClass(percent) {
  if (percent == null) return ''
  const num = Number(percent)
  if (num >= 90) return 'bar-critical'
  if (num >= 70) return 'bar-warning'
  return 'bar-healthy'
}

// API 调用
async function loadInstances() {
  try {
    const res = await api.getInstances()
    const data = res.data
    instances.value = Array.isArray(data) ? data : (data.items || data.instances || [])
  } catch (e) {
    instances.value = []
  }
}

async function loadSummary() {
  summaryLoading.value = true
  error.value = ''
  try {
    const params = { db_type: dbType.value }
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getCapacitySummary(params)
    summaryData.value = res.data || {}
  } catch (e) {
    error.value = '加载容量概览失败: ' + (e.response?.data?.detail || e.message || '未知错误')
    summaryData.value = {}
  } finally {
    summaryLoading.value = false
  }
}

async function loadForecast() {
  if (!forecastMetric.value) return
  forecastLoading.value = true
  error.value = ''
  try {
    const params = {
      metric_name: forecastMetric.value,
      days: forecastDays.value,
      db_type: dbType.value
    }
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getCapacityForecast(params)
    const data = res.data || {}
    const history = data.history || data.historical || []
    const predicted = data.forecast || data.predicted || []
    forecastTimes.value = data.times || []
    forecastHistory.value = history
    forecastPredicted.value = predicted
    thresholdDate.value = data.threshold_date || data.estimated_threshold_date || ''
    forecastLoaded.value = true
    await nextTick()
    renderChart()
  } catch (e) {
    error.value = '加载预测数据失败: ' + (e.response?.data?.detail || e.message || '未知错误')
    forecastLoaded.value = false
  } finally {
    forecastLoading.value = false
  }
}

async function loadThresholdCheck() {
  thresholdLoading.value = true
  error.value = ''
  try {
    const params = { db_type: dbType.value }
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getCapacityThresholdCheck(params)
    const data = res.data || {}
    const items = data.items || data.checks || (Array.isArray(data) ? data : [])
    thresholdItems.value = items
  } catch (e) {
    error.value = '加载阈值检查失败: ' + (e.response?.data?.detail || e.message || '未知错误')
    thresholdItems.value = []
  } finally {
    thresholdLoading.value = false
  }
}

function renderChart() {
  if (!forecastChartEl.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(forecastChartEl.value)
  }

  // 构建时间轴：历史 + 预测
  const histTimes = forecastHistory.value.map(p => p.time || p.timestamp || '')
  const predTimes = forecastPredicted.value.map(p => p.time || p.timestamp || '')
  const allTimes = [...histTimes, ...predTimes]

  // 历史数据填充在前，预测段在历史末尾衔接
  const histValues = forecastHistory.value.map(p => p.value ?? p.actual ?? null)
  const predValues = forecastPredicted.value.map(p => p.value ?? p.predicted ?? null)
  // 历史系列：histValues + 预测长度的 null
  const histSeries = [...histValues, ...predValues.map(() => null)]
  // 预测系列：历史长度的 null（除最后一个衔接点）+ predValues
  const predSeries = [...histValues.slice(0, -1).map(() => null), ...predValues]

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(26, 34, 52, 0.95)',
      borderColor: '#2a3a52',
      textStyle: { color: '#e2e8f0', fontSize: 12 }
    },
    legend: {
      data: ['历史', '预测'],
      textStyle: { color: '#94a3b8', fontSize: 12 },
      top: 0
    },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: allTimes,
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
        name: '历史',
        type: 'line',
        data: histSeries,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#3b82f6', width: 2 },
        itemStyle: { color: '#3b82f6' }
      },
      {
        name: '预测',
        type: 'line',
        data: predSeries,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#f59e0b', width: 2, type: 'dashed' },
        itemStyle: { color: '#f59e0b' }
      }
    ]
  }
  chartInstance.setOption(option, true)
}

function handleResize() {
  if (chartInstance) chartInstance.resize()
}

// 切换 Tab 时按需加载数据
watch(activeTab, (val) => {
  if (val === 'summary' && capacityCards.value.length === 0) loadSummary()
  if (val === 'threshold' && thresholdItems.value.length === 0) loadThresholdCheck()
  if (val === 'forecast' && forecastLoaded.value) {
    nextTick(() => renderChart())
  }
})

watch([dbType, instanceId], () => {
  loadSummary()
  if (activeTab.value === 'threshold') loadThresholdCheck()
  forecastLoaded.value = false
})

onMounted(() => {
  loadInstances()
  loadSummary()
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
.capacity-panel {
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

/* 加载与空状态 */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 0;
  color: var(--text-muted);
  font-size: 13px;
}

.loading-spinner {
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

/* 容量卡片网格 */
.capacity-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.cap-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-left: 3px solid var(--text-muted);
}

.cap-card.status-normal {
  border-left-color: var(--accent-green);
}

.cap-card.status-warning {
  border-left-color: var(--accent-yellow);
}

.cap-card.status-critical {
  border-left-color: var(--accent-red);
}

.cap-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cap-icon {
  font-size: 20px;
}

.cap-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.cap-current {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cap-current-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.cap-current-label {
  font-size: 11px;
  color: var(--text-muted);
}

.cap-meta {
  display: flex;
  gap: 12px;
}

.cap-meta-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cap-meta-label {
  font-size: 11px;
  color: var(--text-muted);
}

.cap-meta-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.usage-healthy { color: var(--accent-green); }
.usage-warning { color: var(--accent-yellow); }
.usage-critical { color: var(--accent-red); }

.cap-bar-wrapper {
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 3px;
  overflow: hidden;
}

.cap-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.bar-healthy { background: var(--accent-green); }
.bar-warning { background: var(--accent-yellow); }
.bar-critical { background: var(--accent-red); }

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

/* 预测控制 */
.forecast-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
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

.days-input {
  width: 70px;
  padding: 5px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 12px;
  outline: none;
}

.days-input:focus {
  border-color: var(--accent-blue);
}

.action-btn {
  padding: 6px 16px;
  border: none;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.forecast-btn {
  background: var(--accent-purple);
}

.forecast-btn:hover:not(:disabled) {
  background: #7c3aed;
}

.forecast-chart {
  width: 100%;
  height: 340px;
  margin-bottom: 16px;
}

.threshold-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 6px;
  font-size: 13px;
}

.threshold-info.threshold-safe {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.3);
}

.threshold-icon {
  font-size: 18px;
}

.threshold-text {
  color: var(--text-secondary);
}

.threshold-text strong {
  color: var(--accent-yellow);
}

.threshold-safe .threshold-text strong {
  color: var(--accent-green);
}

/* 阈值检查列表 */
.threshold-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.threshold-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 14px;
  border-left: 3px solid var(--text-muted);
}

.threshold-item.status-normal {
  border-left-color: var(--accent-green);
}

.threshold-item.status-warning {
  border-left-color: var(--accent-yellow);
}

.threshold-item.status-critical {
  border-left-color: var(--accent-red);
}

.threshold-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.threshold-name {
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

.badge-gray {
  background: rgba(107, 114, 128, 0.2);
  color: var(--text-muted);
}

.threshold-values {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.tv-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tv-label {
  font-size: 11px;
  color: var(--text-muted);
}

.tv-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.threshold-suggestion {
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

.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 响应式 */
@media (max-width: 1024px) {
  .capacity-grid {
    grid-template-columns: repeat(2, 1fr);
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

  .tabs-bar {
    flex-direction: column;
  }

  .tab-btn {
    width: 100%;
  }

  .capacity-grid {
    grid-template-columns: 1fr;
  }

  .forecast-controls {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }

  .filter-select {
    max-width: 100%;
    width: 100%;
  }

  .forecast-chart {
    height: 260px;
  }

  .threshold-values {
    gap: 12px;
  }
}
</style>
