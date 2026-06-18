<template>
  <div class="redis-reports">
    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">Redis 运维报表</h2>
      <div class="header-actions">
        <div class="report-tabs">
          <button
            v-for="tab in reportTabs"
            :key="tab.value"
            :class="['tab-btn', { active: activeType === tab.value }]"
            @click="activeType = tab.value; loadReportList()"
          >{{ tab.label }}</button>
        </div>
        <button class="btn-generate" :disabled="generating" @click="handleGenerate">
          {{ generating ? '生成中...' : '生成报表' }}
        </button>
      </div>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="loadReportList">重试</button>
    </div>

    <!-- 主体：左列表 + 右详情 -->
    <div class="reports-body">
      <!-- 左侧：报表列表 -->
      <div class="report-list-panel">
        <div class="list-header">
          <h3>报表列表</h3>
          <span class="list-count" v-if="reports.length > 0">{{ reports.length }} 份</span>
        </div>
        <div v-if="listLoading" class="loading-state">
          <div class="loading-spinner"></div>
          <span>加载中...</span>
        </div>
        <div v-else-if="reports.length === 0" class="empty-state">
          <div class="empty-icon">📊</div>
          <p>暂无{{ activeTypeLabel }}报表</p>
        </div>
        <div v-else class="report-items">
          <div
            v-for="report in reports"
            :key="report.id"
            :class="['report-item', { active: selectedId === report.id }]"
            @click="selectReport(report)"
          >
            <div class="item-top">
              <span class="report-badge" :class="report.report_type || report.type">{{ typeLabel(report.report_type || report.type) }}</span>
              <span class="report-score" :class="scoreClass(report.health_score)">
                {{ report.health_score != null ? report.health_score : '-' }}
              </span>
            </div>
            <div class="item-period">{{ report.period || report.title || '-' }}</div>
            <div class="item-time">{{ formatTime(report.generated_at || report.created_at) }}</div>
            <div class="item-actions">
              <button class="btn-delete" @click.stop="deleteReport(report.id)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：报表详情 -->
      <div class="report-detail-panel">
        <div v-if="detailLoading" class="loading-state">
          <div class="loading-spinner"></div>
          <span>加载报表详情...</span>
        </div>
        <div v-else-if="!currentDetail" class="empty-state">
          <div class="empty-icon">📄</div>
          <p>请从左侧选择一份报表查看详情</p>
        </div>
        <template v-else>
          <!-- 详情头部 -->
          <div class="detail-header">
            <div class="detail-meta">
              <span class="report-badge large" :class="currentDetail.report_type || currentDetail.type">
                {{ typeLabel(currentDetail.report_type || currentDetail.type) }}
              </span>
              <div class="detail-title-area">
                <h3 class="detail-title">{{ typeLabel(currentDetail.report_type || currentDetail.type) }} - {{ currentDetail.period || '' }}</h3>
                <span class="detail-time">生成时间：{{ formatTime(currentDetail.generated_at || currentDetail.created_at) }}</span>
              </div>
            </div>
            <div class="health-circle" :class="scoreClass(currentDetail.health_score)">
              <span class="health-value">{{ currentDetail.health_score != null ? currentDetail.health_score : '-' }}</span>
              <span class="health-label">健康分</span>
            </div>
          </div>

          <!-- 概览卡片 -->
          <div class="section-card">
            <h3>📋 概览</h3>
            <div class="overview-cards">
              <div class="ov-card" v-for="(card, idx) in overviewCards" :key="idx">
                <div class="ov-icon" :style="{ color: card.color }">{{ card.icon }}</div>
                <div class="ov-info">
                  <div class="ov-value">{{ card.value }}</div>
                  <div class="ov-label">{{ card.label }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 内存分析 -->
          <div class="section-card" v-if="memoryAnalysis">
            <h3>💾 内存分析</h3>
            <div class="detail-grid">
              <div class="detail-item">
                <span class="detail-label">已用内存</span>
                <span class="detail-value">{{ memoryAnalysis.used_memory_human || '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">内存峰值</span>
                <span class="detail-value">{{ memoryAnalysis.peak_memory_human || '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">内存使用率</span>
                <span class="detail-value" :class="usageClass(memoryAnalysis.usage_percent)">
                  {{ formatPercent(memoryAnalysis.usage_percent) }}
                </span>
              </div>
              <div class="detail-item">
                <span class="detail-label">碎片率</span>
                <span class="detail-value">{{ memoryAnalysis.fragmentation_ratio ?? '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">淘汰键数</span>
                <span class="detail-value">{{ memoryAnalysis.evicted_keys ?? '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">过期键数</span>
                <span class="detail-value">{{ memoryAnalysis.expired_keys ?? '-' }}</span>
              </div>
            </div>
          </div>

          <!-- 慢查询 Top 10 -->
          <div class="section-card">
            <h3>🐢 慢查询 Top 10</h3>
            <div v-if="slowQueries.length === 0" class="empty-text">暂无慢查询数据</div>
            <div v-else class="table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>命令</th>
                    <th>耗时(μs)</th>
                    <th>客户端</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(sq, idx) in slowQueries" :key="idx">
                    <td>{{ idx + 1 }}</td>
                    <td class="cmd-cell">{{ sq.command || sq.cmd || '-' }}</td>
                    <td>{{ sq.duration ?? sq.duration_us ?? '-' }}</td>
                    <td>{{ sq.client || sq.client_addr || '-' }}</td>
                    <td>{{ formatTime(sq.timestamp || sq.time) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 健康评分明细 -->
          <div class="section-card" v-if="healthItems.length > 0">
            <h3>💊 健康评分明细</h3>
            <div class="health-list">
              <div v-for="(item, idx) in healthItems" :key="idx" class="health-item">
                <div class="health-item-header">
                  <span class="health-item-name">{{ item.name || item.metric || '-' }}</span>
                  <span class="status-badge" :class="scoreBadgeClass(item.score)">{{ item.score != null ? item.score : '-' }}</span>
                </div>
                <div class="health-item-msg" v-if="item.message">{{ item.message }}</div>
              </div>
            </div>
          </div>

          <!-- 优化建议 -->
          <div class="section-card" v-if="suggestions.length > 0">
            <h3>💡 优化建议</h3>
            <div class="suggestion-list">
              <div v-for="(s, idx) in suggestions" :key="idx" class="suggestion-item">
                <span class="suggestion-bullet">{{ idx + 1 }}</span>
                <span class="suggestion-text">{{ typeof s === 'string' ? s : (s.suggestion || s.message || s.content || '-') }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'
import { formatDateTimeMinute as formatTime } from '../utils/datetime.js'
import { formatPercent } from '../utils/format.js'

const reportTabs = [
  { label: '日报', value: 'daily' },
  { label: '周报', value: 'weekly' },
  { label: '月报', value: 'monthly' }
]

const activeType = ref('daily')
const reports = ref([])
const listLoading = ref(false)
const detailLoading = ref(false)
const generating = ref(false)
const error = ref('')
const selectedId = ref(null)
const currentDetail = ref(null)

const activeTypeLabel = computed(() => typeLabel(activeType.value))

function typeLabel(type) {
  const map = { daily: '日报', weekly: '周报', monthly: '月报' }
  return map[type] || type || '-'
}

function scoreClass(score) {
  if (score == null) return ''
  const num = Number(score)
  if (num >= 90) return 'score-green'
  if (num >= 70) return 'score-yellow'
  return 'score-red'
}

function scoreBadgeClass(score) {
  if (score == null) return 'badge-gray'
  const num = Number(score)
  if (num >= 90) return 'badge-green'
  if (num >= 70) return 'badge-yellow'
  return 'badge-red'
}

function usageClass(percent) {
  if (percent == null) return ''
  const num = Number(percent)
  if (num >= 90) return 'status-critical'
  if (num >= 70) return 'status-warning'
  return 'status-healthy'
}

// 概览卡片
const overviewCards = computed(() => {
  const d = currentDetail.value || {}
  const ov = d.overview || {}
  return [
    { icon: '⚡', label: 'QPS', value: ov.qps ?? d.qps ?? '-', color: 'var(--accent-blue)' },
    { icon: '🔗', label: '连接数', value: ov.connected_clients ?? d.connected_clients ?? '-', color: 'var(--accent-green)' },
    { icon: '🎯', label: '命中率', value: formatPercent(ov.hit_rate ?? d.hit_rate), color: 'var(--accent-cyan)' },
    { icon: '🔑', label: '总键数', value: ov.total_keys ?? d.total_keys ?? '-', color: 'var(--accent-purple)' }
  ]
})

// 内存分析
const memoryAnalysis = computed(() => {
  const d = currentDetail.value || {}
  return d.memory || d.memory_analysis || null
})

// 慢查询 Top 10
const slowQueries = computed(() => {
  const d = currentDetail.value || {}
  const sq = d.slow_queries || d.slowlog || d.top_slow_queries
  if (Array.isArray(sq)) return sq.slice(0, 10)
  return []
})

// 健康评分明细
const healthItems = computed(() => {
  const d = currentDetail.value || {}
  const h = d.health_details || d.health_items || d.scores
  if (Array.isArray(h)) return h
  return []
})

// 优化建议
const suggestions = computed(() => {
  const d = currentDetail.value || {}
  const s = d.suggestions || d.recommendations || d.optimization_suggestions
  if (Array.isArray(s)) return s
  if (typeof s === 'string' && s) return [s]
  return []
})

async function loadReportList() {
  listLoading.value = true
  error.value = ''
  try {
    const params = { report_type: activeType.value }
    const res = await api.getRedisReports(params)
    const data = res.data
    reports.value = Array.isArray(data) ? data : (data.items || data.reports || [])
    // 自动选中第一份
    if (reports.value.length > 0 && !reports.value.some(r => r.id === selectedId.value)) {
      selectReport(reports.value[0])
    } else if (reports.value.length === 0) {
      selectedId.value = null
      currentDetail.value = null
    }
  } catch (e) {
    error.value = '加载报表列表失败: ' + (e.response?.data?.detail || e.message || '未知错误')
    reports.value = []
  } finally {
    listLoading.value = false
  }
}

async function selectReport(report) {
  if (!report || !report.id) return
  selectedId.value = report.id
  detailLoading.value = true
  try {
    const res = await api.getRedisReportDetail(report.id)
    currentDetail.value = res.data || report
  } catch (e) {
    // 详情加载失败时回退到列表项数据
    currentDetail.value = report
    console.error('加载报表详情失败', e)
  } finally {
    detailLoading.value = false
  }
}

async function deleteReport(id) {
  if (!confirm('确认删除此报表？')) return
  try {
    await api.deleteRedisReport(id)
    reports.value = reports.value.filter(r => r.id !== id)
    if (selectedId.value === id) {
      selectedId.value = null
      currentDetail.value = null
      if (reports.value.length > 0) selectReport(reports.value[0])
    }
  } catch (e) {
    alert('删除报表失败: ' + (e.response?.data?.detail || e.message || '未知错误'))
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    await api.generateRedisReport({ report_type: activeType.value })
    await loadReportList()
  } catch (e) {
    alert('生成报表失败: ' + (e.response?.data?.detail || e.message || '未知错误'))
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  loadReportList()
})
</script>

<style scoped>
.redis-reports {
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

.report-tabs {
  display: flex;
  gap: 6px;
}

.tab-btn {
  padding: 6px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
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
  border-color: var(--accent-blue);
}

.btn-generate {
  padding: 7px 18px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: opacity 0.2s;
}

.btn-generate:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-generate:hover:not(:disabled) {
  opacity: 0.9;
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

.retry-btn:hover {
  opacity: 0.85;
}

/* 主体布局 */
.reports-body {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  align-items: start;
}

/* 左侧列表 */
.report-list-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.list-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.list-count {
  font-size: 12px;
  color: var(--text-muted);
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px;
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
  padding: 50px 20px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-state p {
  font-size: 14px;
}

.report-items {
  display: flex;
  flex-direction: column;
  max-height: 600px;
  overflow-y: auto;
}

.report-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.report-item:last-child {
  border-bottom: none;
}

.report-item:hover {
  background: var(--bg-hover);
}

.report-item.active {
  background: rgba(59, 130, 246, 0.12);
  border-left: 3px solid var(--accent-blue);
  padding-left: 13px;
}

.item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.report-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.report-badge.daily {
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent-blue);
}

.report-badge.weekly {
  background: rgba(16, 185, 129, 0.15);
  color: var(--accent-green);
}

.report-badge.monthly {
  background: rgba(139, 92, 246, 0.15);
  color: var(--accent-purple);
}

.report-badge.large {
  padding: 4px 14px;
  font-size: 14px;
}

.report-score {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: center;
}

.score-red { color: var(--accent-red); }
.score-yellow { color: var(--accent-yellow); }
.score-green { color: var(--accent-green); }

.item-period {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.item-time {
  font-size: 12px;
  color: var(--text-muted);
}

.item-actions {
  display: flex;
  justify-content: flex-end;
}

.btn-delete {
  padding: 3px 10px;
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-red);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  transition: background 0.15s;
}

.btn-delete:hover {
  background: rgba(239, 68, 68, 0.22);
}

/* 右侧详情 */
.report-detail-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  gap: 20px;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}

.detail-title-area {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.detail-time {
  font-size: 13px;
  color: var(--text-muted);
}

.health-circle {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 3px solid;
}

.health-circle.score-red {
  border-color: var(--accent-red);
  background: rgba(239, 68, 68, 0.08);
}

.health-circle.score-yellow {
  border-color: var(--accent-yellow);
  background: rgba(245, 158, 11, 0.08);
}

.health-circle.score-green {
  border-color: var(--accent-green);
  background: rgba(16, 185, 129, 0.08);
}

.health-value {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.health-circle.score-red .health-value { color: var(--accent-red); }
.health-circle.score-yellow .health-value { color: var(--accent-yellow); }
.health-circle.score-green .health-value { color: var(--accent-green); }

.health-label {
  font-size: 11px;
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

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.ov-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.ov-icon {
  font-size: 24px;
}

.ov-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.ov-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* 详情网格 */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.detail-label {
  font-size: 12px;
  color: var(--text-muted);
}

.detail-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.status-healthy { color: var(--accent-green); font-weight: 600; }
.status-warning { color: var(--accent-yellow); font-weight: 600; }
.status-critical { color: var(--accent-red); font-weight: 600; }

/* 表格 */
.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  text-align: left;
  padding: 9px 12px;
  border-bottom: 2px solid var(--border-color);
  white-space: nowrap;
}

.data-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.cmd-cell {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--accent-cyan);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 健康评分明细 */
.health-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.health-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px 12px;
}

.health-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.health-item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.health-item-msg {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
  line-height: 1.4;
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

/* 优化建议 */
.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.suggestion-bullet {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  background: var(--accent-blue);
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.suggestion-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 响应式 */
@media (max-width: 1024px) {
  .reports-body {
    grid-template-columns: 1fr;
  }

  .report-items {
    max-height: 400px;
  }

  .overview-cards {
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

  .report-tabs {
    width: 100%;
  }

  .tab-btn {
    flex: 1;
    text-align: center;
    padding: 6px 8px;
    font-size: 12px;
  }

  .btn-generate {
    width: 100%;
  }

  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px;
    gap: 16px;
  }

  .health-circle {
    align-self: center;
  }

  .overview-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .data-table {
    font-size: 12px;
  }

  .data-table th,
  .data-table td {
    padding: 7px 8px;
  }
}
</style>
