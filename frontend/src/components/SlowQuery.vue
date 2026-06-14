<template>
  <div class="slow-query">
    <!-- 操作按钮 -->
    <div class="action-bar">
      <button class="action-btn parse-btn" @click="handleParse" :disabled="parseLoading">
        {{ parseLoading ? '解析中...' : '解析慢查询日志' }}
      </button>
      <button class="action-btn analyze-btn" @click="handleAnalyze" :disabled="analyzeLoading">
        {{ analyzeLoading ? '分析中...' : 'AI 分析慢查询' }}
      </button>
    </div>

    <!-- 时间段选择器 -->
    <div class="period-selector">
      <button
        v-for="p in periods"
        :key="p.value"
        :class="['period-btn', { active: period === p.value }]"
        @click="changePeriod(p.value)"
      >{{ p.label }}</button>
      <div class="custom-period">
        <input type="number" v-model.number="customValue" min="1" max="365" placeholder="自定义" class="custom-input" />
        <select v-model="customUnit" class="custom-select">
          <option value="h">小时</option>
          <option value="d">天</option>
        </select>
        <button class="period-btn" @click="applyCustomPeriod" :disabled="!customValue || customValue < 1">应用</button>
      </div>
    </div>

    <!-- 统计概览 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-blue)">🔍</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_count || 0 }}</div>
          <div class="stat-label">总慢查询数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-yellow)">⏱️</div>
        <div class="stat-info">
          <div class="stat-value">{{ formatTime(stats.avg_query_time) }}</div>
          <div class="stat-label">平均查询时间</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-red)">🔴</div>
        <div class="stat-info">
          <div class="stat-value">{{ formatTime(stats.max_query_time) }}</div>
          <div class="stat-label">最大查询时间</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-green)">📊</div>
        <div class="stat-info">
          <div class="stat-value">{{ formatNumber(stats.avg_rows_examined) }}</div>
          <div class="stat-label">平均扫描行数</div>
        </div>
      </div>
    </div>

    <!-- Top 慢查询列表 -->
    <div class="section-card">
      <h3>Top 慢查询 <span class="section-subtitle">(按 sql_hash 分组，Top 20)</span></h3>
      <div v-if="queryLoading" class="loading-text">加载中...</div>
      <div v-else-if="queryList.length === 0" class="empty-text">暂无慢查询数据</div>
      <div v-else class="query-list">
        <div v-for="(item, idx) in queryList" :key="item.sql_hash || idx" class="query-item">
          <div class="query-header">
            <span class="query-rank">#{{ idx + 1 }}</span>
            <span class="query-type-badge" :class="getSqlTypeClass(item.sql_type)">{{ item.sql_type || 'OTHER' }}</span>
            <span class="query-score" v-if="item.score != null">评分: <strong>{{ item.score }}</strong></span>
          </div>
          <div class="query-sql" @click="toggleExpand(idx)">
            <span class="sql-text" :class="{ expanded: expandedItems[idx] }">
              {{ expandedItems[idx] ? item.sql_template : truncateSql(item.sql_template) }}
            </span>
            <span class="expand-hint">{{ expandedItems[idx] ? '收起' : '展开' }}</span>
          </div>
          <div class="query-metrics">
            <div class="metric">
              <span class="metric-label">执行次数</span>
              <span class="metric-value">{{ item.exec_count || 0 }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">平均查询时间</span>
              <span class="metric-value">{{ formatTime(item.avg_query_time) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">最大查询时间</span>
              <span class="metric-value highlight-red">{{ formatTime(item.max_query_time) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">平均锁等待</span>
              <span class="metric-value">{{ formatTime(item.avg_lock_time) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">最大锁等待</span>
              <span class="metric-value highlight-yellow">{{ formatTime(item.max_lock_time) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">平均扫描行数</span>
              <span class="metric-value">{{ formatNumber(item.avg_rows_examined) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">最大扫描行数</span>
              <span class="metric-value highlight-yellow">{{ formatNumber(item.max_rows_examined) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分布统计 -->
    <div class="section-card">
      <h3>SQL 类型分布</h3>
      <div v-if="distribution.length === 0" class="empty-text">暂无分布数据</div>
      <div v-else class="distribution-list">
        <div v-for="item in distribution" :key="item.sql_type" class="distribution-row">
          <span class="dist-type-badge" :class="getSqlTypeClass(item.sql_type)">{{ item.sql_type }}</span>
          <span class="dist-bar-wrapper">
            <span class="dist-bar" :style="{ width: getDistPercent(item.count) + '%' }"></span>
          </span>
          <span class="dist-count">{{ item.count }} 次</span>
          <span class="dist-percent">{{ getDistPercent(item.count) }}%</span>
        </div>
      </div>
    </div>

    <!-- AI 分析结果 -->
    <div v-if="analysisResult" class="section-card analysis-card">
      <h3>🤖 AI 分析建议</h3>
      <div class="analysis-content" v-html="renderMarkdown(analysisResult)"></div>
    </div>

    <!-- 解析结果提示 -->
    <div v-if="parseResult" class="section-card parse-result-card">
      <h3>📋 解析结果</h3>
      <div class="parse-content">{{ parseResult }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const period = ref('7d')
const customValue = ref(null)
const customUnit = ref('h')
const stats = ref({})
const queryList = ref([])
const distribution = ref([])
const expandedItems = ref({})
const queryLoading = ref(false)
const analyzeLoading = ref(false)
const parseLoading = ref(false)
const analysisResult = ref('')
const parseResult = ref('')

const periods = [
  { label: '全部', value: 'all' },
  { label: '7天', value: '7d' },
  { label: '24小时', value: '24h' },
  { label: '1小时', value: '1h' }
]

function getPeriodParam() {
  return period.value === 'all' ? '' : period.value
}

function formatTime(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  if (num >= 3600) return (num / 3600).toFixed(2) + 'h'
  if (num >= 60) return (num / 60).toFixed(2) + 'm'
  if (num >= 1) return num.toFixed(2) + 's'
  return (num * 1000).toFixed(0) + 'ms'
}

function formatNumber(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toFixed(0)
}

function truncateSql(sql) {
  if (!sql) return '-'
  return sql.length > 120 ? sql.substring(0, 120) + '...' : sql
}

function toggleExpand(idx) {
  expandedItems.value[idx] = !expandedItems.value[idx]
}

function getSqlTypeClass(type) {
  const t = (type || '').toUpperCase()
  if (t === 'SELECT') return 'type-select'
  if (t === 'INSERT') return 'type-insert'
  if (t === 'UPDATE') return 'type-update'
  if (t === 'DELETE') return 'type-delete'
  return 'type-other'
}

function getDistPercent(count) {
  const total = distribution.value.reduce((s, d) => s + (d.count || 0), 0)
  if (total === 0) return 0
  return ((count / total) * 100).toFixed(1)
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br/>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
}

async function loadStats() {
  try {
    const res = await api.getSlowQueryStats({ period: getPeriodParam() })
    stats.value = res.data || {}
  } catch (e) {
    console.error('loadSlowQueryStats error', e)
  }
}

async function loadQueryList() {
  queryLoading.value = true
  try {
    const res = await api.getSlowQueryList({
      page: 1,
      page_size: 20,
      sort_by: 'avg_query_time',
      period: getPeriodParam()
    })
    const data = res.data || {}
    queryList.value = data.items || data.list || data || []
  } catch (e) {
    console.error('loadSlowQueryList error', e)
  } finally {
    queryLoading.value = false
  }
}

async function loadDistribution() {
  try {
    const res = await api.getSlowQueryDistribution({ period: getPeriodParam() })
    const data = res.data || {}
    if (Array.isArray(data)) {
      distribution.value = data
    } else if (data.items || data.list) {
      distribution.value = data.items || data.list
    } else if (typeof data === 'object') {
      distribution.value = Object.entries(data).map(([sql_type, count]) => ({ sql_type, count }))
    } else {
      distribution.value = []
    }
  } catch (e) {
    console.error('loadSlowQueryDistribution error', e)
  }
}

async function handleAnalyze() {
  analyzeLoading.value = true
  analysisResult.value = ''
  try {
    const res = await api.analyzeSlowQuery({ period: getPeriodParam() })
    analysisResult.value = res.data?.suggestion || res.data?.analysis || res.data?.result || (typeof res.data === 'string' ? res.data : JSON.stringify(res.data))
  } catch (e) {
    analysisResult.value = '分析失败：' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    analyzeLoading.value = false
  }
}

async function handleParse() {
  parseLoading.value = true
  parseResult.value = ''
  try {
    const res = await api.parseSlowQuery({})
    parseResult.value = res.data?.message || res.data?.result || (typeof res.data === 'string' ? res.data : JSON.stringify(res.data))
    // 解析完成后刷新数据
    await Promise.all([loadStats(), loadQueryList(), loadDistribution()])
  } catch (e) {
    parseResult.value = '解析失败：' + (e.response?.data?.detail || e.message || '未知错误')
  } finally {
    parseLoading.value = false
  }
}

function changePeriod(p) {
  period.value = p
  loadStats()
  loadQueryList()
  loadDistribution()
}

function applyCustomPeriod() {
  if (customValue.value && customValue.value > 0) {
    period.value = `${customValue.value}${customUnit.value}`
    loadStats()
    loadQueryList()
    loadDistribution()
  }
}

onMounted(() => {
  loadStats()
  loadQueryList()
  loadDistribution()
})
</script>

<style scoped>
.slow-query {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.action-bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 8px 20px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.parse-btn {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

.parse-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.analyze-btn {
  background: var(--accent-green);
  color: #fff;
  border-color: var(--accent-green);
}

.analyze-btn:hover:not(:disabled) {
  opacity: 0.85;
}

/* 时间段选择器 */
.period-selector {
  display: flex;
  gap: 8px;
  align-items: center;
}

.custom-period {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  padding-left: 12px;
  border-left: 1px solid var(--border-color);
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

.period-btn {
  padding: 6px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.period-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.period-btn.active {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

/* 统计卡片 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  font-size: 28px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
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
  margin-bottom: 12px;
  color: var(--text-secondary);
}

.section-subtitle {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-muted);
}

/* 慢查询列表 */
.query-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.query-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
}

.query-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.query-rank {
  font-weight: 700;
  color: var(--accent-blue);
  font-size: 14px;
  min-width: 28px;
}

.query-type-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.type-select { background: rgba(59,130,246,0.2); color: var(--accent-blue); }
.type-insert { background: rgba(16,185,129,0.2); color: var(--accent-green); }
.type-update { background: rgba(245,158,11,0.2); color: var(--accent-yellow); }
.type-delete { background: rgba(239,68,68,0.2); color: var(--accent-red); }
.type-other { background: rgba(107,114,128,0.2); color: var(--text-muted); }

.query-score {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}

.query-score strong {
  color: var(--accent-yellow);
}

.query-sql {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 10px 12px;
  margin-bottom: 10px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.sql-text {
  flex: 1;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
  max-height: 3em;
  overflow: hidden;
}

.sql-text.expanded {
  max-height: none;
}

.expand-hint {
  font-size: 11px;
  color: var(--accent-blue);
  white-space: nowrap;
  cursor: pointer;
  flex-shrink: 0;
  padding-top: 2px;
}

.query-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px 16px;
}

.metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  padding: 4px 0;
}

.metric-label {
  color: var(--text-muted);
}

.metric-value {
  color: var(--text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.highlight-red { color: var(--accent-red); }
.highlight-yellow { color: var(--accent-yellow); }

/* 分布统计 */
.distribution-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.distribution-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.dist-type-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  min-width: 60px;
  text-align: center;
}

.dist-bar-wrapper {
  flex: 1;
  height: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  overflow: hidden;
}

.dist-bar {
  height: 100%;
  background: var(--accent-blue);
  border-radius: 4px;
  transition: width 0.3s;
  min-width: 2px;
}

.dist-count {
  color: var(--text-secondary);
  min-width: 60px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.dist-percent {
  color: var(--text-muted);
  min-width: 45px;
  text-align: right;
  font-size: 12px;
}

/* 分析结果 */
.analysis-card {
  border-color: var(--accent-green);
}

.analysis-content {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-primary);
}

.analysis-content :deep(code) {
  background: var(--bg-secondary);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}

.analysis-content :deep(strong) {
  color: var(--accent-blue);
}

/* 解析结果 */
.parse-result-card {
  border-color: var(--accent-blue);
}

.parse-content {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

@media (max-width: 900px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    text-align: center;
  }

  .period-selector {
    flex-wrap: wrap;
    gap: 6px;
  }

  .period-btn {
    padding: 5px 10px;
    font-size: 12px;
  }

  .custom-period {
    margin-left: 0;
    padding-left: 0;
    border-left: none;
    width: 100%;
    margin-top: 4px;
  }

  .custom-input {
    width: 50px;
    font-size: 12px;
    padding: 4px 6px;
  }

  .custom-select {
    font-size: 12px;
    padding: 4px 6px;
  }

  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .stat-card {
    padding: 12px;
    gap: 10px;
  }

  .stat-icon {
    font-size: 22px;
  }

  .stat-value {
    font-size: 20px;
  }

  .stat-label {
    font-size: 11px;
  }

  .query-metrics {
    grid-template-columns: repeat(2, 1fr);
    gap: 4px 10px;
  }

  .distribution-row {
    gap: 8px;
  }

  .dist-bar-wrapper {
    min-width: 60px;
  }
}
</style>
