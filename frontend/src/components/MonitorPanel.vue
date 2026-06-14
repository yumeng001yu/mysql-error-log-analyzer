<template>
  <div class="monitor-panel">
    <!-- 连接状态 -->
    <div class="connection-card" :class="{ connected: connected, disconnected: !connected }">
      <div class="conn-status-dot"></div>
      <div class="conn-info">
        <span class="conn-label">{{ connected ? 'MySQL 已连接' : '无法连接 MySQL，请检查 MySQL 服务状态和连接配置' }}</span>
        <span class="conn-detail" v-if="connected">
          {{ status.version || '-' }} · 运行 {{ formatUptime(status.uptime) }}
        </span>
      </div>
    </div>

    <!-- 自动刷新控制 -->
    <div class="refresh-control">
      <span class="refresh-label">自动刷新：</span>
      <button
        v-for="opt in refreshOptions"
        :key="opt.value"
        :class="['refresh-btn', { active: refreshInterval === opt.value }]"
        @click="setRefresh(opt.value)"
      >{{ opt.label }}</button>
    </div>

    <!-- 核心指标 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-blue)">⚡</div>
        <div class="stat-info">
          <div class="stat-value">{{ status.qps ?? '-' }}</div>
          <div class="stat-label">QPS (每秒查询数)</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-green)">🔄</div>
        <div class="stat-info">
          <div class="stat-value">{{ status.tps ?? '-' }}</div>
          <div class="stat-label">TPS (每秒事务数)</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-yellow)">🔗</div>
        <div class="stat-info">
          <div class="stat-value">{{ status.active_connections ?? '-' }}<span class="stat-unit"> / {{ status.max_connections ?? '-' }}</span></div>
          <div class="stat-label">活跃连接 / 最大连接</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-green)">💾</div>
        <div class="stat-info">
          <div class="stat-value">{{ formatPercent(status.buffer_pool_hit_rate) }}</div>
          <div class="stat-label">Buffer Pool 命中率</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-red)">🐢</div>
        <div class="stat-info">
          <div class="stat-value">{{ status.slow_queries ?? '-' }}</div>
          <div class="stat-label">慢查询数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-yellow)">🔒</div>
        <div class="stat-info">
          <div class="stat-value">{{ status.row_lock_waits ?? '-' }}</div>
          <div class="stat-label">行锁等待次数</div>
        </div>
      </div>
    </div>

    <!-- 进程列表 -->
    <div class="section-card">
      <div class="section-header">
        <h3>进程列表</h3>
        <div class="filter-bar">
          <button
            v-for="f in commandFilters"
            :key="f.value"
            :class="['filter-btn', { active: commandFilter === f.value }]"
            @click="commandFilter = f.value"
          >{{ f.label }}</button>
        </div>
      </div>
      <div v-if="processLoading" class="loading-text">加载中...</div>
      <div v-else-if="filteredProcesslist.length === 0" class="empty-text">暂无进程数据</div>
      <template v-else>
        <!-- 桌面端表格 -->
        <div class="process-table-wrapper desktop-only">
          <table class="process-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>Host</th>
                <th>DB</th>
                <th>Command</th>
                <th>Time</th>
                <th>State</th>
                <th>Info</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="proc in filteredProcesslist" :key="proc.Id || proc.id">
                <td>{{ proc.Id || proc.id }}</td>
                <td>{{ proc.User || proc.user }}</td>
                <td>{{ proc.Host || proc.host }}</td>
                <td>{{ proc.db || proc.DB || '-' }}</td>
                <td><span class="command-badge" :class="getCommandClass(proc.Command || proc.command)">{{ proc.Command || proc.command }}</span></td>
                <td>{{ proc.Time || proc.time || 0 }}</td>
                <td class="state-cell">{{ proc.State || proc.state || '-' }}</td>
                <td class="info-cell">{{ truncateInfo(proc.Info || proc.info) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 移动端卡片 -->
        <div class="process-cards mobile-only">
          <div v-for="proc in filteredProcesslist" :key="proc.Id || proc.id" class="process-card">
            <div class="pcard-header">
              <span class="pcard-id">#{{ proc.Id || proc.id }}</span>
              <span class="command-badge" :class="getCommandClass(proc.Command || proc.command)">{{ proc.Command || proc.command }}</span>
              <span class="pcard-time">{{ proc.Time || proc.time || 0 }}s</span>
            </div>
            <div class="pcard-body">
              <div class="pcard-row"><span class="pcard-label">User</span><span>{{ proc.User || proc.user }}</span></div>
              <div class="pcard-row"><span class="pcard-label">Host</span><span>{{ proc.Host || proc.host }}</span></div>
              <div class="pcard-row"><span class="pcard-label">DB</span><span>{{ proc.db || proc.DB || '-' }}</span></div>
              <div class="pcard-row"><span class="pcard-label">State</span><span>{{ proc.State || proc.state || '-' }}</span></div>
              <div class="pcard-row" v-if="proc.Info || proc.info"><span class="pcard-label">Info</span><span class="pcard-info">{{ truncateInfo(proc.Info || proc.info) }}</span></div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- InnoDB 状态 -->
    <div class="section-card">
      <div class="section-header collapsible" @click="innodbExpanded = !innodbExpanded">
        <h3>InnoDB 状态</h3>
        <span class="collapse-icon">{{ innodbExpanded ? '▼' : '▶' }}</span>
      </div>
      <div v-if="innodbExpanded" class="innodb-content">
        <div v-if="innodbLoading" class="loading-text">加载中...</div>
        <div v-else-if="!innodbStatus" class="empty-text">暂无 InnoDB 状态数据</div>
        <template v-else>
          <div v-for="(section, key) in innodbSections" :key="key" class="innodb-section">
            <div class="innodb-section-title">{{ section.title }}</div>
            <pre class="innodb-pre">{{ section.content }}</pre>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'

const connected = ref(false)
const status = ref({})
const processlist = ref([])
const innodbStatus = ref('')
const processLoading = ref(false)
const innodbLoading = ref(false)
const innodbExpanded = ref(false)
const commandFilter = ref('all')
const refreshInterval = ref(0)
let refreshTimer = null

const refreshOptions = [
  { label: '关闭', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 }
]

const commandFilters = [
  { label: '全部', value: 'all' },
  { label: 'Query', value: 'Query' },
  { label: 'Sleep', value: 'Sleep' },
  { label: 'Connect', value: 'Connect' }
]

const filteredProcesslist = computed(() => {
  if (commandFilter.value === 'all') return processlist.value
  return processlist.value.filter(p => (p.Command || p.command) === commandFilter.value)
})

const innodbSections = computed(() => {
  if (!innodbStatus.value) return []
  const text = typeof innodbStatus.value === 'string' ? innodbStatus.value : JSON.stringify(innodbStatus.value, null, 2)
  const sections = []
  const parts = text.split(/={10,}/)
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i].trim()
    if (!part) continue
    const lines = part.split('\n')
    const title = lines[0].replace(/^-+|-+$/g, '').trim() || `Section ${i + 1}`
    const content = lines.slice(1).join('\n').trim()
    if (content) {
      sections.push({ title, content })
    }
  }
  if (sections.length === 0) {
    sections.push({ title: 'InnoDB Engine Status', content: text })
  }
  return sections
})

function formatUptime(seconds) {
  if (!seconds && seconds !== 0) return '-'
  const s = Number(seconds)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}天${h}小时`
  if (h > 0) return `${h}小时${m}分`
  return `${m}分钟`
}

function formatPercent(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  return num.toFixed(1) + '%'
}

function truncateInfo(info) {
  if (!info) return '-'
  return info.length > 60 ? info.substring(0, 60) + '...' : info
}

function getCommandClass(cmd) {
  if (cmd === 'Query') return 'cmd-query'
  if (cmd === 'Sleep') return 'cmd-sleep'
  if (cmd === 'Connect') return 'cmd-connect'
  return 'cmd-other'
}

async function loadStatus() {
  try {
    const res = await api.getMonitorStatus({})
    const data = res.data || {}
    status.value = data
    connected.value = data.connected !== false && data.error == null
  } catch (e) {
    connected.value = false
    console.error('loadMonitorStatus error', e)
  }
}

async function loadProcesslist() {
  processLoading.value = true
  try {
    const res = await api.getProcesslist({})
    const data = res.data || {}
    processlist.value = data.items || data.list || data.processlist || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('loadProcesslist error', e)
  } finally {
    processLoading.value = false
  }
}

async function loadInnodbStatus() {
  innodbLoading.value = true
  try {
    const res = await api.getInnodbStatus({})
    const data = res.data || {}
    innodbStatus.value = data.status || data.innodb_status || data.content || (typeof data === 'string' ? data : '')
  } catch (e) {
    console.error('loadInnodbStatus error', e)
  } finally {
    innodbLoading.value = false
  }
}

function setRefresh(ms) {
  refreshInterval.value = ms
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (ms > 0) {
    refreshTimer = setInterval(() => {
      loadStatus()
      loadProcesslist()
    }, ms)
  }
}

function loadAll() {
  loadStatus()
  loadProcesslist()
  if (innodbExpanded.value) {
    loadInnodbStatus()
  }
}

onMounted(() => {
  loadAll()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.monitor-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 连接状态 */
.connection-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
}

.connection-card.connected {
  border-color: var(--accent-green);
  background: rgba(16,185,129,0.08);
}

.connection-card.disconnected {
  border-color: var(--accent-red);
  background: rgba(239,68,68,0.08);
}

.conn-status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.connected .conn-status-dot {
  background: var(--accent-green);
  box-shadow: 0 0 6px var(--accent-green);
}

.disconnected .conn-status-dot {
  background: var(--accent-red);
  box-shadow: 0 0 6px var(--accent-red);
}

.conn-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.conn-detail {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 12px;
}

/* 自动刷新 */
.refresh-control {
  display: flex;
  align-items: center;
  gap: 6px;
}

.refresh-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.refresh-btn {
  padding: 4px 12px;
  background: var(--bg-card);
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

.refresh-btn.active {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

/* 统计卡片 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  font-size: 26px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-unit {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-muted);
}

.stat-label {
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

/* 进程过滤 */
.filter-bar {
  display: flex;
  gap: 6px;
}

.filter-btn {
  padding: 3px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  transition: all 0.2s;
}

.filter-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.filter-btn.active {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

/* 进程表格 */
.process-table-wrapper {
  overflow-x: auto;
}

.process-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.process-table th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.process-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.state-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-cell {
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.command-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
}

.cmd-query { background: rgba(59,130,246,0.2); color: var(--accent-blue); }
.cmd-sleep { background: rgba(107,114,128,0.2); color: var(--text-muted); }
.cmd-connect { background: rgba(16,185,129,0.2); color: var(--accent-green); }
.cmd-other { background: rgba(245,158,11,0.2); color: var(--accent-yellow); }

/* 移动端卡片 */
.mobile-only { display: none; }
.desktop-only { display: block; }

.process-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.process-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px 12px;
}

.pcard-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.pcard-id {
  font-weight: 700;
  color: var(--accent-blue);
  font-size: 12px;
}

.pcard-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}

.pcard-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pcard-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.pcard-label {
  color: var(--text-muted);
  min-width: 40px;
}

.pcard-info {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  word-break: break-all;
}

/* InnoDB 状态 */
.innodb-content {
  margin-top: 8px;
}

.innodb-section {
  margin-bottom: 14px;
}

.innodb-section:last-child {
  margin-bottom: 0;
}

.innodb-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-blue);
  margin-bottom: 6px;
}

.innodb-pre {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 10px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
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
  .mobile-only { display: flex; }
  .desktop-only { display: none; }

  .connection-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .conn-detail {
    margin-left: 0;
    display: block;
  }

  .refresh-control {
    flex-wrap: wrap;
    gap: 4px;
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
    font-size: 20px;
  }

  .stat-value {
    font-size: 18px;
  }

  .stat-label {
    font-size: 11px;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .filter-bar {
    flex-wrap: wrap;
  }
}
</style>
