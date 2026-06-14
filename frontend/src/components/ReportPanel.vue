<template>
  <div class="report-panel">
    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">运维报表</h2>
      <div class="header-actions">
        <div class="report-tabs">
          <button
            v-for="tab in reportTabs"
            :key="tab.value"
            :class="['tab-btn', { active: activeTab === tab.value }]"
            @click="activeTab = tab.value; loadReportList()"
          >{{ tab.label }}</button>
        </div>
        <div class="header-right">
          <input
            type="date"
            class="date-picker"
            v-model="filterDate"
            @change="loadReportList"
          />
          <button class="btn-generate" @click="showGenerateModal = true">生成报表</button>
        </div>
      </div>
    </div>

    <!-- 报表列表 -->
    <div class="report-list" v-if="!viewingReport">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>加载中...</span>
      </div>
      <div v-else-if="reports.length === 0" class="empty-state">
        <div class="empty-icon">📊</div>
        <p>暂无报表数据</p>
      </div>
      <div v-else class="report-items">
        <div
          v-for="report in reports"
          :key="report.id"
          class="report-item"
        >
          <span class="report-badge" :class="report.type">{{ typeLabel(report.type) }}</span>
          <span class="report-period">{{ report.period }}</span>
          <span class="report-score" :class="scoreClass(report.health_score)">
            {{ report.health_score != null ? report.health_score : '-' }}
          </span>
          <span class="report-time">{{ formatTime(report.generated_at || report.created_at) }}</span>
          <div class="report-actions">
            <button class="btn-view" @click="viewReport(report)">查看</button>
            <button class="btn-delete" @click="deleteReport(report.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 报表详情 -->
    <div class="report-detail" v-if="viewingReport">
      <button class="btn-back" @click="viewingReport = null">&larr; 返回列表</button>

      <!-- 报表头部 -->
      <div class="detail-header">
        <div class="detail-meta">
          <span class="report-badge large" :class="viewingReport.type">{{ typeLabel(viewingReport.type) }}</span>
          <div class="detail-title-area">
            <h3 class="detail-title">{{ typeLabel(viewingReport.type) }} - {{ viewingReport.period }}</h3>
            <span class="detail-time">生成时间：{{ formatTime(viewingReport.generated_at || viewingReport.created_at) }}</span>
          </div>
        </div>
        <div class="health-circle" :class="scoreClass(viewingReport.health_score)">
          <span class="health-value">{{ viewingReport.health_score != null ? viewingReport.health_score : '-' }}</span>
          <span class="health-label">健康分</span>
        </div>
      </div>

      <!-- 报表内容区 -->
      <div class="detail-sections" v-if="viewingReport.sections && viewingReport.sections.length > 0">
        <div v-for="(section, idx) in viewingReport.sections" :key="idx" class="detail-section">
          <h4 class="section-title" v-if="section.title">{{ section.title }}</h4>

          <!-- 指标卡片 -->
          <div v-if="section.content_type === 'metric_cards'" class="metric-cards">
            <div v-for="(card, ci) in section.content" :key="ci" class="metric-card">
              <span class="metric-title">{{ card.title || card.name }}</span>
              <span class="metric-value">{{ card.value }}</span>
            </div>
          </div>

          <!-- 表格 -->
          <div v-else-if="section.content_type === 'table'" class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th v-for="(header, hi) in section.content.headers" :key="hi">{{ header }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in section.content.rows" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 列表 -->
          <div v-else-if="section.content_type === 'list'" class="content-list">
            <ul>
              <li v-for="(item, li) in section.content" :key="li">{{ item }}</li>
            </ul>
          </div>

          <!-- 文本 -->
          <div v-else-if="section.content_type === 'text'" class="content-text">
            <p>{{ section.content }}</p>
          </div>
        </div>
      </div>

      <!-- 摘要 -->
      <div class="detail-summary" v-if="viewingReport.summary">
        <h4 class="section-title">总结</h4>
        <p>{{ viewingReport.summary }}</p>
      </div>
    </div>

    <!-- 生成报表弹窗 -->
    <div class="modal-overlay" v-if="showGenerateModal" @click.self="showGenerateModal = false">
      <div class="modal-card">
        <h3>生成报表</h3>

        <div class="form-group">
          <label>报表类型</label>
          <div class="radio-group">
            <label
              v-for="tab in reportTabs"
              :key="tab.value"
              :class="['radio-label', { active: generateType === tab.value }]"
            >
              <input type="radio" :value="tab.value" v-model="generateType" />
              {{ tab.label }}
            </label>
          </div>
        </div>

        <div class="form-group">
          <label>选择日期</label>
          <input
            v-if="generateType === 'daily'"
            type="date"
            class="form-input"
            v-model="generateDate"
          />
          <input
            v-else-if="generateType === 'weekly'"
            type="week"
            class="form-input"
            v-model="generateDate"
          />
          <input
            v-else-if="generateType === 'monthly'"
            type="month"
            class="form-input"
            v-model="generateDate"
          />
        </div>

        <div class="form-group">
          <label>实例</label>
          <select class="form-input" v-model="generateInstance">
            <option value="">全部实例</option>
            <option v-for="inst in instances" :key="inst.id || inst.name" :value="inst.id || inst.name">
              {{ inst.name || inst.host || ('实例 ' + (inst.id || inst.name)) }}
            </option>
          </select>
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="showGenerateModal = false">取消</button>
          <button class="btn-primary" @click="handleGenerate" :disabled="generating">
            {{ generating ? '生成中...' : '生成' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const reportTabs = [
  { label: '日报', value: 'daily' },
  { label: '周报', value: 'weekly' },
  { label: '月报', value: 'monthly' }
]

const activeTab = ref('daily')
const filterDate = ref('')
const reports = ref([])
const loading = ref(false)
const viewingReport = ref(null)

const showGenerateModal = ref(false)
const generateType = ref('daily')
const generateDate = ref('')
const generateInstance = ref('')
const generating = ref(false)
const instances = ref([])

function typeLabel(type) {
  const map = { daily: '日报', weekly: '周报', monthly: '月报' }
  return map[type] || type
}

function scoreClass(score) {
  if (score == null) return ''
  if (score < 60) return 'score-red'
  if (score < 80) return 'score-yellow'
  return 'score-green'
}

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

async function loadReportList() {
  loading.value = true
  try {
    const params = { type: activeTab.value }
    if (filterDate.value) params.date = filterDate.value
    const res = await api.getReportList(params)
    const data = res.data
    reports.value = Array.isArray(data) ? data : (data.items || data.reports || [])
  } catch (e) {
    console.error('加载报表列表失败', e)
    reports.value = []
  } finally {
    loading.value = false
  }
}

async function viewReport(report) {
  try {
    const res = await api.getReport(report.id)
    viewingReport.value = res.data || report
  } catch (e) {
    console.error('加载报表详情失败', e)
    viewingReport.value = report
  }
}

async function deleteReport(id) {
  if (!confirm('确认删除此报表？')) return
  try {
    await api.deleteReport(id)
    reports.value = reports.value.filter(r => r.id !== id)
  } catch (e) {
    console.error('删除报表失败', e)
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    const params = {
      report_type: generateType.value,
      date: generateDate.value
    }
    if (generateInstance.value) params.instance_id = generateInstance.value
    await api.generateReport(params)
    showGenerateModal.value = false
    loadReportList()
  } catch (e) {
    console.error('生成报表失败', e)
    alert('生成报表失败：' + (e?.response?.data?.error || e?.message || '未知错误'))
  } finally {
    generating.value = false
  }
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

onMounted(() => {
  loadReportList()
  loadInstances()
})
</script>

<style scoped>
.report-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 头部 ─────────────────────────────────────────────── */
.panel-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.panel-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.date-picker {
  padding: 6px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.date-picker:focus {
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

.btn-generate:hover {
  opacity: 0.9;
}

/* ── 报表列表 ─────────────────────────────────────────── */
.report-list {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px;
  color: var(--text-muted);
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
}

.report-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
  transition: background 0.15s;
}

.report-item:last-child {
  border-bottom: none;
}

.report-item:hover {
  background: var(--bg-hover);
}

.report-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
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

.report-period {
  color: var(--text-primary);
  font-weight: 500;
  min-width: 100px;
}

.report-score {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: center;
}

.report-score.score-red { color: var(--accent-red); }
.report-score.score-yellow { color: var(--accent-yellow); }
.report-score.score-green { color: var(--accent-green); }

.report-time {
  color: var(--text-muted);
  font-size: 12px;
  flex: 1;
  white-space: nowrap;
}

.report-actions {
  display: flex;
  gap: 6px;
}

.btn-view {
  padding: 4px 12px;
  background: rgba(59, 130, 246, 0.12);
  color: var(--accent-blue);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}

.btn-view:hover {
  background: rgba(59, 130, 246, 0.25);
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

/* ── 报表详情 ─────────────────────────────────────────── */
.report-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.btn-back {
  align-self: flex-start;
  padding: 6px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.btn-back:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
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

/* ── 内容区段 ─────────────────────────────────────────── */
.detail-sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-section {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 14px 0;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color);
}

/* 指标卡片 */
.metric-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.metric-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-title {
  font-size: 12px;
  color: var(--text-muted);
}

.metric-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

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
  padding: 10px 12px;
  border-bottom: 2px solid var(--border-color);
  white-space: nowrap;
}

.data-table td {
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

/* 列表 */
.content-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.content-list li {
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  position: relative;
  padding-left: 24px;
}

.content-list li::before {
  content: '•';
  position: absolute;
  left: 10px;
  color: var(--accent-blue);
  font-weight: 700;
}

/* 文本 */
.content-text p {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
  margin: 0;
}

/* 摘要 */
.detail-summary {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.detail-summary p {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
  margin: 0;
}

/* ── 弹窗 ─────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
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
  width: 440px;
  max-width: 90vw;
}

.modal-card h3 {
  font-size: 18px;
  margin: 0 0 20px 0;
  color: var(--text-primary);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent-blue);
}

.radio-group {
  display: flex;
  gap: 8px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.radio-label input {
  display: none;
}

.radio-label.active {
  background: rgba(59, 130, 246, 0.12);
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
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

/* ── 移动端适配 ────────────────────────────────────────── */
@media (max-width: 768px) {
  .panel-header {
    padding: 12px;
  }

  .header-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
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

  .header-right {
    width: 100%;
    flex-direction: column;
    gap: 8px;
  }

  .date-picker {
    width: 100%;
  }

  .btn-generate {
    width: 100%;
    text-align: center;
  }

  .report-item {
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px;
  }

  .report-period {
    min-width: auto;
  }

  .report-time {
    flex: 1 1 100%;
    order: 10;
  }

  .report-actions {
    margin-left: auto;
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

  .detail-section {
    padding: 14px;
  }

  .metric-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .metric-value {
    font-size: 18px;
  }

  .data-table {
    font-size: 12px;
  }

  .data-table th,
  .data-table td {
    padding: 7px 8px;
  }

  .modal-card {
    width: 95vw;
    padding: 20px;
  }

  .radio-group {
    flex-wrap: wrap;
  }

  .radio-label {
    flex: 1;
    justify-content: center;
    min-width: 80px;
  }
}

@media (max-width: 480px) {
  .metric-cards {
    grid-template-columns: 1fr;
  }
}
</style>
