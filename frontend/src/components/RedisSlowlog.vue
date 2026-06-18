<template>
  <div class="redis-slowlog">
    <!-- 选项卡 -->
    <div class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'list' }]"
        @click="activeTab = 'list'"
      >慢查询列表</button>
      <button
        :class="['tab-btn', { active: activeTab === 'stats' }]"
        @click="activeTab = 'stats'"
      >统计</button>
    </div>

    <!-- 慢查询配置 -->
    <div class="config-card" v-if="slowlogConfig.slower_than != null || slowlogConfig.max_len != null">
      <div class="config-title">⚙️ 慢查询配置</div>
      <div class="config-items">
        <div class="config-item" v-if="slowlogConfig.slower_than != null">
          <span class="config-label">slowlog-log-slower-than</span>
          <span class="config-value">{{ slowlogConfig.slower_than === -1 ? '禁用' : slowlogConfig.slower_than + ' μs' }}</span>
        </div>
        <div class="config-item" v-if="slowlogConfig.max_len != null">
          <span class="config-label">slowlog-max-len</span>
          <span class="config-value">{{ slowlogConfig.max_len }}</span>
        </div>
      </div>
    </div>

    <!-- Tab 1: 慢查询列表 -->
    <div v-if="activeTab === 'list'" class="tab-content">
      <div class="section-card">
        <div v-if="loading" class="loading-text">加载中...</div>
        <div v-else-if="slowlogList.length === 0" class="empty-text">暂无慢查询记录</div>
        <div v-else class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>命令</th>
                <th>耗时(ms)</th>
                <th>时间戳</th>
                <th>客户端</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in slowlogList" :key="item.id || item.log_id">
                <td class="cell-id">{{ item.id || item.log_id || '-' }}</td>
                <td class="cell-cmd" :title="getFullCommand(item)">{{ truncateCommand(item) }}</td>
                <td>
                  <span class="duration-badge" :class="getDurationClass(item.duration || item.used_usec)">
                    {{ formatDuration(item.duration || item.used_usec) }}
                  </span>
                </td>
                <td class="cell-time">{{ formatTimestamp(item.timestamp || item.time || item.start_time) }}</td>
                <td class="cell-client">{{ getClient(item) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab 2: 统计 -->
    <div v-if="activeTab === 'stats'" class="tab-content">
      <!-- 统计概览 -->
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-blue)">📊</div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_count ?? '-' }}</div>
            <div class="stat-label">总慢查询数</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-yellow)">⏱️</div>
          <div class="stat-info">
            <div class="stat-value">{{ formatDuration(stats.avg_duration) }}</div>
            <div class="stat-label">平均耗时</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-red)">🔴</div>
          <div class="stat-info">
            <div class="stat-value">{{ formatDuration(stats.max_duration) }}</div>
            <div class="stat-label">最大耗时</div>
          </div>
        </div>
      </div>

      <!-- 命令分布 -->
      <div class="section-card">
        <h3>📈 命令分布</h3>
        <div v-if="commandDistribution.length === 0" class="empty-text">暂无分布数据</div>
        <div v-else class="distribution-list">
          <div v-for="item in commandDistribution" :key="item.command" class="distribution-row">
            <span class="dist-cmd-badge">{{ item.command }}</span>
            <span class="dist-bar-wrapper">
              <span class="dist-bar" :style="{ width: getDistPercent(item.count) + '%' }"></span>
            </span>
            <span class="dist-count">{{ item.count }} 次</span>
            <span class="dist-percent">{{ getDistPercent(item.count) }}%</span>
          </div>
        </div>
      </div>

      <!-- Top 10 最慢查询 -->
      <div class="section-card">
        <h3>🐢 Top 10 最慢查询</h3>
        <div v-if="topSlowest.length === 0" class="empty-text">暂无数据</div>
        <div v-else class="top-list">
          <div v-for="(item, idx) in topSlowest" :key="idx" class="top-item">
            <div class="top-header">
              <span class="top-rank">#{{ idx + 1 }}</span>
              <span class="duration-badge" :class="getDurationClass(item.duration || item.used_usec)">
                {{ formatDuration(item.duration || item.used_usec) }}
              </span>
            </div>
            <div class="top-cmd" :title="getFullCommand(item)">{{ truncateCommand(item, 200) }}</div>
            <div class="top-meta">
              <span v-if="item.timestamp || item.time">时间: {{ formatTimestamp(item.timestamp || item.time) }}</span>
              <span v-if="getClient(item)">客户端: {{ getClient(item) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'
import { formatTimestamp } from '../utils/datetime.js'

const route = useRoute()
const instanceId = ref(route.query.instance_id || '')

// 状态
const activeTab = ref('list')
const loading = ref(false)
const slowlogList = ref([])
const stats = ref({})
const slowlogConfig = ref({})
let refreshTimer = null

// 命令分布（优先使用 API 返回的统计，否则从列表中计算）
const commandDistribution = computed(() => {
  const apiDist = stats.value.command_distribution
  if (apiDist && typeof apiDist === 'object' && Object.keys(apiDist).length > 0) {
    return Object.entries(apiDist)
      .map(([command, count]) => ({ command, count }))
      .sort((a, b) => b.count - a.count)
  }
  const map = {}
  for (const item of slowlogList.value) {
    const cmd = getCommandName(item)
    if (cmd) {
      map[cmd] = (map[cmd] || 0) + 1
    }
  }
  return Object.entries(map)
    .map(([command, count]) => ({ command, count }))
    .sort((a, b) => b.count - a.count)
})

// Top 10 最慢查询（优先使用 API 返回的 top_slow，否则从列表中排序）
const topSlowest = computed(() => {
  const apiTop = stats.value.top_slow
  if (apiTop && Array.isArray(apiTop) && apiTop.length > 0) {
    return apiTop.slice(0, 10)
  }
  return [...slowlogList.value]
    .sort((a, b) => {
      const da = getDurationUs(a)
      const db = getDurationUs(b)
      return db - da
    })
    .slice(0, 10)
})

// 获取命令名
function getCommandName(item) {
  const cmd = item.command || item.cmd || item.name
  if (cmd) {
    // 如果是数组，取第一个元素
    if (Array.isArray(cmd)) return cmd[0] || '-'
    // 如果是字符串，取第一个单词
    return String(cmd).split(' ')[0].toUpperCase()
  }
  // 从 args 中提取
  if (item.args && Array.isArray(item.args) && item.args.length > 0) {
    return String(item.args[0]).toUpperCase()
  }
  return '-'
}

// 获取完整命令
function getFullCommand(item) {
  const cmd = item.command || item.cmd
  if (cmd) {
    if (Array.isArray(cmd)) return cmd.join(' ')
    return String(cmd)
  }
  if (item.args && Array.isArray(item.args)) {
    return item.args.join(' ')
  }
  return '-'
}

// 截断命令
function truncateCommand(item, maxLen = 80) {
  const full = getFullCommand(item)
  if (!full || full === '-') return '-'
  return full.length > maxLen ? full.substring(0, maxLen) + '...' : full
}

// 获取耗时（微秒）
function getDurationUs(item) {
  const val = item.duration || item.used_usec || item.duration_us
  if (val == null) return 0
  return Number(val)
}

// 格式化耗时
function formatDuration(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  // 如果值大于 10000，认为是微秒
  const ms = num > 10000 ? num / 1000 : num
  if (ms >= 1000) return (ms / 1000).toFixed(2) + 's'
  if (ms >= 1) return ms.toFixed(2) + 'ms'
  return (ms * 1000).toFixed(0) + 'μs'
}

// 耗时颜色等级
function getDurationClass(val) {
  if (val == null) return 'dur-green'
  const num = Number(val)
  // 判断是微秒还是毫秒
  const ms = num > 10000 ? num / 1000 : num
  if (ms > 100) return 'dur-red'
  if (ms >= 10) return 'dur-yellow'
  return 'dur-green'
}

// 获取客户端信息
function getClient(item) {
  if (item.client) return item.client
  if (item.client_ip) {
    const port = item.client_port
    const name = item.client_name
    let result = port ? `${item.client_ip}:${port}` : item.client_ip
    if (name && name !== item.client_ip) result += ` (${name})`
    return result
  }
  if (item.client_address || item.ip) {
    const addr = item.client_address || item.ip
    const port = item.client_port || item.port
    return port ? `${addr}:${port}` : addr
  }
  return '-'
}

// 分布百分比
function getDistPercent(count) {
  const total = commandDistribution.value.reduce((s, d) => s + (d.count || 0), 0)
  if (total === 0) return 0
  return ((count / total) * 100).toFixed(1)
}

// 加载慢查询列表
async function loadSlowlog() {
  loading.value = true
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisSlowlog(params)
    const data = res.data || {}
    if (Array.isArray(data)) {
      slowlogList.value = data
    } else if (data.items || data.list || data.slowlog) {
      slowlogList.value = data.items || data.list || data.slowlog
    } else {
      slowlogList.value = []
    }
  } catch (e) {
    console.error('loadRedisSlowlog error', e)
    slowlogList.value = []
  } finally {
    loading.value = false
  }
}

// 加载统计
async function loadStats() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisSlowlogStats(params)
    const data = res.data || {}
    stats.value = {
      total_count: data.total_entries ?? data.total_count,
      avg_duration: data.avg_duration_ms ?? data.avg_duration,
      max_duration: data.max_duration_ms ?? data.max_duration,
      command_distribution: data.command_distribution || {},
      top_slow: data.top_slow || []
    }
  } catch (e) {
    console.error('loadRedisSlowlogStats error', e)
    stats.value = {}
  }
}

// 加载配置
async function loadConfig() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisSlowlogConfig(params)
    const data = res.data || {}
    slowlogConfig.value = {
      slower_than: data.slowlog_log_slower_than ?? data.slower_than ?? data['slowlog-log-slower-than'],
      max_len: data.slowlog_max_len ?? data.max_len ?? data['slowlog-max-len']
    }
  } catch (e) {
    console.error('loadRedisSlowlogConfig error', e)
  }
}

// 加载全部
async function loadAll() {
  await Promise.all([
    loadSlowlog(),
    loadStats(),
    loadConfig()
  ])
}

// 自动刷新：每30秒
function startAutoRefresh() {
  refreshTimer = setInterval(() => {
    loadAll()
  }, 30000)
}

onMounted(() => {
  loadAll()
  startAutoRefresh()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.redis-slowlog {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 选项卡 */
.tab-bar {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 0;
}

.tab-btn {
  padding: 8px 20px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.tab-btn.active {
  color: var(--accent-blue);
  border-bottom-color: var(--accent-blue);
}

.tab-content {
  margin-top: 4px;
}

/* 配置卡片 */
.config-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 18px;
}

.config-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.config-items {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.config-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.config-label {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'Courier New', monospace;
}

.config-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-cyan);
  font-variant-numeric: tabular-nums;
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

.section-card h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-secondary);
}

/* 数据表格 */
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

.cell-id {
  color: var(--text-muted);
  font-size: 11px;
}

.cell-cmd {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.cell-time {
  white-space: nowrap;
  font-size: 11px;
  color: var(--text-secondary);
}

.cell-client {
  font-size: 11px;
  color: var(--text-secondary);
}

/* 耗时徽章 */
.duration-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.dur-green {
  background: rgba(16, 185, 129, 0.2);
  color: var(--accent-green);
}

.dur-yellow {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.dur-red {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

/* 命令分布 */
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

.dist-cmd-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  min-width: 60px;
  text-align: center;
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent-blue);
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

/* Top 列表 */
.top-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.top-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
}

.top-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.top-rank {
  font-weight: 700;
  color: var(--accent-blue);
  font-size: 14px;
  min-width: 28px;
}

.top-cmd {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-primary);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 6px;
  word-break: break-all;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-meta {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: var(--text-muted);
}

.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 响应式 */
@media (max-width: 900px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .tab-btn {
    padding: 6px 14px;
    font-size: 13px;
  }

  .stat-cards {
    grid-template-columns: 1fr;
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

  .config-items {
    flex-direction: column;
    gap: 8px;
  }

  .distribution-row {
    gap: 8px;
  }

  .dist-bar-wrapper {
    min-width: 60px;
  }

  .top-meta {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
