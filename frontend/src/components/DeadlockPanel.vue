<template>
  <div class="deadlock-panel">
    <!-- 提示消息 -->
    <transition name="fade">
      <div v-if="message.text" class="message-bar" :class="message.type">
        {{ message.text }}
      </div>
    </transition>

    <!-- 头部 -->
    <div class="panel-header">
      <h2 class="panel-title">InnoDB 死锁分析</h2>
      <div class="header-actions">
        <button class="primary-btn" :disabled="analyzing" @click="handleAnalyze">
          {{ analyzing ? '分析中...' : '分析死锁' }}
        </button>
        <div class="time-range-group">
          <button
            v-for="tr in timeRanges"
            :key="tr.value"
            :class="['range-btn', { active: timeRange === tr.value }]"
            @click="timeRange = tr.value"
          >{{ tr.label }}</button>
        </div>
        <select v-model="severityFilter" class="filter-select">
          <option value="all">全部级别</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>
    </div>

    <!-- 统计概览 -->
    <div class="stats-row">
      <div class="stat-item">
        <span class="stat-num">{{ stats.total }}</span>
        <span class="stat-desc">死锁总数</span>
      </div>
      <div class="stat-item critical">
        <span class="stat-num">{{ stats.critical }}</span>
        <span class="stat-desc">Critical</span>
      </div>
      <div class="stat-item affected">
        <span class="stat-num">{{ stats.affectedTables }}</span>
        <span class="stat-desc">涉及表</span>
      </div>
      <div class="stat-item frequency">
        <span class="stat-num">{{ stats.avgFrequency }}</span>
        <span class="stat-desc">平均频率</span>
      </div>
    </div>

    <!-- 死锁列表 -->
    <div v-if="listLoading" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>
    <div v-else-if="deadlockList.length === 0" class="empty-state">
      <p>暂无死锁记录</p>
      <p class="hint">点击"分析死锁"开始检测</p>
    </div>
    <div v-else class="deadlock-list">
      <div
        v-for="item in deadlockList"
        :key="item.id"
        class="deadlock-card"
        @click="openDetail(item)"
      >
        <div class="card-header">
          <span :class="['severity-badge', item.severity]">{{ severityLabel(item.severity) }}</span>
          <span class="card-time">{{ item.timestamp || item.detected_at || '-' }}</span>
        </div>
        <div class="card-body">
          <div class="card-tables">
            <span class="card-label">涉及表：</span>
            <span class="card-value">{{ formatTables(item.affected_tables) }}</span>
          </div>
          <div class="card-cause">
            <span class="card-label">根因：</span>
            <span class="card-value">{{ item.root_cause_summary || item.root_cause || '-' }}</span>
          </div>
          <div class="card-txn-count">
            <span class="card-label">事务数：</span>
            <span class="card-value">{{ item.transaction_count || item.transactions?.length || '-' }}</span>
          </div>
        </div>
        <div class="card-footer">
          <button class="detail-btn" @click.stop="openDetail(item)">查看详情</button>
        </div>
      </div>
    </div>

    <!-- 死锁详情弹窗 -->
    <transition name="fade">
      <div v-if="detailVisible" class="modal-overlay" @click.self="detailVisible = false">
        <div class="modal-content">
          <div class="modal-header">
            <h3>死锁详情</h3>
            <button class="modal-close" @click="detailVisible = false">&times;</button>
          </div>
          <div class="modal-body" v-if="detailLoading">
            <div class="loading-state">
              <div class="spinner"></div>
              <p>加载中...</p>
            </div>
          </div>
          <div class="modal-body" v-else>
            <!-- 1. 锁等待链图 -->
            <div class="detail-section">
              <h4 class="section-title">锁等待链图</h4>
              <div class="lock-chain-container" ref="lockChainRef">
                <svg :width="chainSvgWidth" :height="chainSvgHeight" class="lock-chain-svg">
                  <defs>
                    <marker id="dl-arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                      <polygon points="0 0, 10 3.5, 0 7" fill="var(--accent-blue)" />
                    </marker>
                    <marker id="dl-arrow-red" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                      <polygon points="0 0, 10 3.5, 0 7" fill="var(--accent-red)" />
                    </marker>
                  </defs>
                  <g v-for="(edge, ei) in chainEdges" :key="'edge-' + ei">
                    <line
                      :x1="edge.x1"
                      :y1="edge.y1"
                      :x2="edge.x2"
                      :y2="edge.y2"
                      :stroke="edge.isVictim ? 'var(--accent-red)' : 'var(--accent-blue)'"
                      :stroke-width="2"
                      :stroke-dasharray="edge.isVictim ? '6,3' : 'none'"
                      :marker-end="edge.isVictim ? 'url(#dl-arrow-red)' : 'url(#dl-arrow)'"
                    />
                    <text
                      :x="(edge.x1 + edge.x2) / 2"
                      :y="(edge.y1 + edge.y2) / 2 - 6"
                      text-anchor="middle"
                      fill="var(--text-muted)"
                      font-size="10"
                    >waiting for</text>
                  </g>
                  <g v-for="(node, ni) in chainNodes" :key="'node-' + ni" :transform="`translate(${node.x},${node.y})`">
                    <rect
                      :x="-node.w / 2"
                      :y="-node.h / 2"
                      :width="node.w"
                      :height="node.h"
                      :rx="8"
                      :ry="8"
                      :fill="node.isVictim ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.1)'"
                      :stroke="node.isVictim ? 'var(--accent-red)' : 'var(--accent-blue)'"
                      :stroke-width="node.isVictim ? 2.5 : 1.5"
                    />
                    <text
                      :y="-6"
                      text-anchor="middle"
                      fill="var(--text-primary)"
                      font-size="11"
                      font-weight="600"
                    >{{ node.threadLabel }}</text>
                    <text
                      :y="10"
                      text-anchor="middle"
                      fill="var(--text-secondary)"
                      font-size="9"
                    >{{ truncateText(node.queryLabel, 28) }}</text>
                    <text
                      v-if="node.isVictim"
                      :y="node.h / 2 + 14"
                      text-anchor="middle"
                      fill="var(--accent-red)"
                      font-size="10"
                      font-weight="700"
                    >VICTIM</text>
                  </g>
                </svg>
                <div v-if="chainNodes.length === 0" class="chain-empty">暂无锁等待链数据</div>
              </div>
            </div>

            <!-- 2. 事务详情 -->
            <div class="detail-section">
              <h4 class="section-title">事务详情</h4>
              <div v-if="detailData.transactions && detailData.transactions.length > 0" class="txn-list">
                <div v-for="(txn, ti) in detailData.transactions" :key="ti" class="txn-card">
                  <div class="txn-header">
                    <span class="txn-id">事务 {{ txn.transaction_id || txn.id || (ti + 1) }}</span>
                    <span class="txn-thread">Thread: {{ txn.thread_id || '-' }}</span>
                    <span v-if="txn.is_victim" class="victim-badge">Victim</span>
                  </div>
                  <div class="txn-query">
                    <code>{{ txn.query || txn.sql || '-' }}</code>
                  </div>
                  <!-- 持有锁 -->
                  <div v-if="txn.locks_held && txn.locks_held.length > 0" class="lock-table-wrapper">
                    <span class="lock-table-label">持有锁</span>
                    <table class="lock-table">
                      <thead>
                        <tr>
                          <th>类型</th>
                          <th>模式</th>
                          <th>数据库</th>
                          <th>表</th>
                          <th>索引</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(lock, li) in txn.locks_held" :key="'held-' + li">
                          <td>{{ lock.lock_type || lock.type || '-' }}</td>
                          <td>{{ lock.lock_mode || lock.mode || '-' }}</td>
                          <td>{{ lock.database || lock.db || '-' }}</td>
                          <td>{{ lock.table || '-' }}</td>
                          <td>{{ lock.index || '-' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <!-- 请求锁 -->
                  <div v-if="txn.locks_requested && txn.locks_requested.length > 0" class="lock-table-wrapper">
                    <span class="lock-table-label">请求锁</span>
                    <table class="lock-table">
                      <thead>
                        <tr>
                          <th>类型</th>
                          <th>模式</th>
                          <th>数据库</th>
                          <th>表</th>
                          <th>索引</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(lock, li) in txn.locks_requested" :key="'req-' + li">
                          <td>{{ lock.lock_type || lock.type || '-' }}</td>
                          <td>{{ lock.lock_mode || lock.mode || '-' }}</td>
                          <td>{{ lock.database || lock.db || '-' }}</td>
                          <td>{{ lock.table || '-' }}</td>
                          <td>{{ lock.index || '-' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              <div v-else class="no-data-text">暂无事务详情</div>
            </div>

            <!-- 3. 根因分析 -->
            <div class="detail-section">
              <h4 class="section-title">根因分析</h4>
              <p class="root-cause-text">{{ detailData.root_cause || detailData.root_cause_summary || '-' }}</p>
            </div>

            <!-- 4. 优化建议 -->
            <div class="detail-section">
              <h4 class="section-title">优化建议</h4>
              <ul v-if="detailData.suggestions && detailData.suggestions.length > 0" class="suggestion-list">
                <li v-for="(sug, si) in detailData.suggestions" :key="si" class="suggestion-item">
                  <span class="suggestion-icon">&#128161;</span>
                  <span>{{ typeof sug === 'string' ? sug : sug.suggestion || sug.text || sug.message || '-' }}</span>
                </li>
              </ul>
              <p v-else class="no-data-text">暂无优化建议</p>
            </div>

            <!-- 5. 索引建议 -->
            <div class="detail-section">
              <h4 class="section-title">索引建议</h4>
              <table v-if="detailData.index_suggestions && detailData.index_suggestions.length > 0" class="index-table">
                <thead>
                  <tr>
                    <th>表</th>
                    <th>建议索引</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(idx, ii) in detailData.index_suggestions" :key="ii">
                    <td>{{ idx.table || '-' }}</td>
                    <td><code>{{ idx.suggested_index || idx.index || '-' }}</code></td>
                    <td>{{ idx.reason || '-' }}</td>
                  </tr>
                </tbody>
              </table>
              <p v-else class="no-data-text">暂无索引建议</p>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api.js'
import { useMessage } from '../composables/useMessage.js'
import { truncate as truncateText } from '../utils/format.js'

// ==================== 通用 ====================

const { message, showMessage } = useMessage()

function severityLabel(severity) {
  const map = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' }
  return map[severity] || severity || '-'
}

function formatTables(tables) {
  if (!tables) return '-'
  if (Array.isArray(tables)) return tables.join(', ')
  if (typeof tables === 'string') return tables
  return '-'
}

// ==================== 筛选 ====================

const timeRange = ref('7d')
const severityFilter = ref('all')

const timeRanges = [
  { label: '1d', value: '1d' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' }
]

// ==================== 统计 ====================

const stats = ref({
  total: 0,
  critical: 0,
  affectedTables: 0,
  avgFrequency: '-'
})

async function loadStats() {
  try {
    const res = await api.getDeadlockStats()
    const data = res.data || {}
    stats.value = {
      total: data.total ?? data.deadlock_count ?? 0,
      critical: data.critical ?? data.critical_count ?? 0,
      affectedTables: data.affected_tables ?? data.affected_tables_count ?? 0,
      avgFrequency: data.avg_frequency ?? data.frequency ?? '-'
    }
    if (typeof stats.value.avgFrequency === 'number') {
      stats.value.avgFrequency = stats.value.avgFrequency.toFixed(1) + '次/天'
    } else if (!String(stats.value.avgFrequency).includes('次')) {
      stats.value.avgFrequency = String(stats.value.avgFrequency) + '次/天'
    }
  } catch (e) {
    console.error('loadDeadlockStats error', e)
  }
}

// ==================== 列表 ====================

const deadlockList = ref([])
const listLoading = ref(false)
const analyzing = ref(false)

async function loadList() {
  listLoading.value = true
  try {
    const params = { time_range: timeRange.value }
    if (severityFilter.value !== 'all') params.severity = severityFilter.value
    const res = await api.getDeadlockList(params)
    const data = res.data || {}
    deadlockList.value = data.items || data.list || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('loadDeadlockList error', e)
  } finally {
    listLoading.value = false
  }
}

async function handleAnalyze() {
  analyzing.value = true
  try {
    const params = { time_range: timeRange.value }
    await api.analyzeDeadlock(params)
    showMessage('死锁分析完成')
    loadList()
    loadStats()
  } catch (e) {
    showMessage('分析失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  } finally {
    analyzing.value = false
  }
}

watch([timeRange, severityFilter], () => {
  loadList()
})

// ==================== 详情 ====================

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref({})
const lockChainRef = ref(null)

const chainSvgWidth = ref(600)
const chainSvgHeight = ref(300)

const chainNodes = computed(() => {
  const chain = detailData.value.lock_chain || detailData.value.chain || []
  if (!Array.isArray(chain) || chain.length === 0) return []

  const nodeW = 180
  const nodeH = 56
  const gapX = 80
  const startX = nodeW / 2 + 30
  const startY = chainSvgHeight.value / 2

  return chain.map((item, i) => ({
    x: startX + i * (nodeW + gapX),
    y: startY,
    w: nodeW,
    h: nodeH,
    threadLabel: `Thread ${item.thread_id || item.thread || '-'}`,
    queryLabel: item.query || item.sql || '',
    isVictim: !!item.is_victim
  }))
})

const chainEdges = computed(() => {
  const nodes = chainNodes.value
  const edges = []
  for (let i = 0; i < nodes.length - 1; i++) {
    const src = nodes[i]
    const tgt = nodes[i + 1]
    edges.push({
      x1: src.x + src.w / 2,
      y1: src.y,
      x2: tgt.x - tgt.w / 2,
      y2: tgt.y,
      isVictim: tgt.isVictim
    })
  }
  return edges
})

async function openDetail(item) {
  detailVisible.value = true
  detailLoading.value = true
  detailData.value = {}
  try {
    const [detailRes, chainRes] = await Promise.all([
      api.getDeadlockDetail(item.id),
      api.getDeadlockLockChain(item.id).catch(() => ({ data: {} }))
    ])
    const data = detailRes.data || {}
    detailData.value = {
      ...data,
      lock_chain: chainRes.data?.nodes || chainRes.data?.chain || chainRes.data?.items || (Array.isArray(chainRes.data) ? chainRes.data : [])
    }
  } catch (e) {
    console.error('loadDeadlockDetail error', e)
  } finally {
    detailLoading.value = false
  }
}

// ==================== 初始化 ====================

onMounted(() => {
  loadStats()
  loadList()
})
</script>

<style scoped>
.deadlock-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 提示消息 */
.message-bar {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  z-index: 1000;
  white-space: nowrap;
}

.message-bar.success {
  background: rgba(16, 185, 129, 0.15);
  color: var(--accent-green);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.message-bar.error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-red);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 头部 */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
  gap: 10px;
  flex-wrap: wrap;
}

.primary-btn {
  padding: 8px 20px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.primary-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 时间范围按钮组 */
.time-range-group {
  display: flex;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}

.range-btn {
  padding: 6px 14px;
  background: var(--bg-card);
  border: none;
  border-right: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.range-btn:last-child {
  border-right: none;
}

.range-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.range-btn.active {
  background: var(--accent-blue);
  color: #fff;
}

/* 筛选下拉 */
.filter-select {
  padding: 6px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  cursor: pointer;
  font-family: inherit;
}

.filter-select:focus {
  border-color: var(--accent-blue);
}

/* 统计概览 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-item {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.stat-item.critical .stat-num {
  color: var(--accent-red);
}

.stat-item.affected .stat-num {
  color: var(--accent-blue);
}

.stat-item.frequency .stat-num {
  color: var(--accent-yellow);
  font-size: 22px;
}

/* 死锁列表 */
.deadlock-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.deadlock-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.deadlock-card:hover {
  border-color: var(--accent-blue);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-time {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.card-label {
  color: var(--text-muted);
  min-width: 60px;
  flex-shrink: 0;
}

.card-value {
  color: var(--text-primary);
  word-break: break-all;
}

.card-body > div {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
}

.detail-btn {
  padding: 4px 14px;
  background: transparent;
  border: 1px solid var(--accent-blue);
  color: var(--accent-blue);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.detail-btn:hover {
  background: var(--accent-blue);
  color: #fff;
}

/* 严重程度徽章 */
.severity-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.severity-badge.critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.severity-badge.high {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.severity-badge.medium {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.severity-badge.low {
  background: rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}

/* 加载/空状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 20px;
  color: var(--text-muted);
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border-color, #333);
  border-top-color: var(--accent-blue, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-muted);
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 6px;
}

/* ==================== 详情弹窗 ==================== */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.modal-content {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  width: 800px;
  max-width: 92vw;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 详情区域 */
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-color);
}

/* 锁等待链图 */
.lock-chain-container {
  background: var(--bg-secondary, var(--bg-primary, #111));
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow-x: auto;
  padding: 16px;
  min-height: 160px;
  position: relative;
}

.lock-chain-svg {
  display: block;
  min-width: 100%;
}

.chain-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px;
}

/* 事务详情 */
.txn-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.txn-card {
  background: var(--bg-secondary, var(--bg-primary, #111));
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.txn-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.txn-id {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.txn-thread {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'Courier New', monospace;
}

.victim-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 700;
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.txn-query {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
  padding: 10px 12px;
  overflow-x: auto;
}

.txn-query code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--accent-green);
  white-space: pre-wrap;
  word-break: break-all;
}

/* 锁表格 */
.lock-table-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lock-table-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.lock-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.lock-table th,
.lock-table td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.lock-table th {
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

.lock-table td {
  color: var(--text-primary);
  word-break: break-all;
}

.lock-table tr:last-child td {
  border-bottom: none;
}

/* 根因分析 */
.root-cause-text {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
  margin: 0;
  padding: 12px 16px;
  background: var(--bg-secondary, var(--bg-primary, #111));
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

/* 优化建议 */
.suggestion-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  padding: 8px 12px;
  background: var(--bg-secondary, var(--bg-primary, #111));
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.suggestion-icon {
  flex-shrink: 0;
  font-size: 14px;
}

/* 索引建议表格 */
.index-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.index-table th,
.index-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.index-table th {
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

.index-table td {
  color: var(--text-primary);
  word-break: break-all;
}

.index-table td code {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.1);
  padding: 2px 6px;
  border-radius: 3px;
}

.index-table tr:last-child td {
  border-bottom: none;
}

.no-data-text {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* ==================== 移动端适配 ==================== */
@media (max-width: 768px) {
  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .primary-btn {
    width: 100%;
    text-align: center;
  }

  .time-range-group {
    flex: 1;
  }

  .range-btn {
    flex: 1;
    text-align: center;
  }

  .filter-select {
    flex: 1;
  }

  .stats-row {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .stat-item {
    padding: 12px;
  }

  .stat-num {
    font-size: 22px;
  }

  .stat-item.frequency .stat-num {
    font-size: 18px;
  }

  .card-header {
    flex-wrap: wrap;
  }

  .card-time {
    margin-left: 0;
    width: 100%;
  }

  .card-body > div {
    flex-direction: column;
    gap: 2px;
  }

  .modal-content {
    max-width: 98vw;
    max-height: 95vh;
    border-radius: 8px;
  }

  .lock-chain-container {
    padding: 10px;
  }

  .lock-table,
  .index-table {
    font-size: 11px;
  }

  .lock-table th,
  .lock-table td,
  .index-table th,
  .index-table td {
    padding: 4px 6px;
  }

  .txn-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}
</style>
