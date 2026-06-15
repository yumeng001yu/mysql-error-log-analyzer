<template>
  <div class="redis-monitor">
    <!-- 加载状态 -->
    <div v-if="loading && !serverInfo.version" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载 Redis 监控数据...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <!-- 服务器信息卡片 -->
      <div class="server-info-card">
        <div class="server-icon">🔴</div>
        <div class="server-details">
          <div class="server-title">
            Redis {{ serverInfo.version || '-' }}
            <span class="status-badge" :class="connectionClass">{{ connectionLabel }}</span>
          </div>
          <div class="server-meta">
            <span v-if="serverInfo.mode">模式: {{ serverInfo.mode }}</span>
            <span v-if="serverInfo.uptime">运行时间: {{ formatUptime(serverInfo.uptime) }}</span>
            <span v-if="serverInfo.os">OS: {{ serverInfo.os }}</span>
          </div>
        </div>
      </div>

      <!-- 核心指标卡片 -->
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-blue)">⚡</div>
          <div class="stat-info">
            <div class="stat-value">{{ metrics.qps ?? '-' }}</div>
            <div class="stat-label">QPS (每秒命令数)</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-green)">🔗</div>
          <div class="stat-info">
            <div class="stat-value">{{ metrics.connected_clients ?? '-' }}</div>
            <div class="stat-label">已连接客户端</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-yellow)">💾</div>
          <div class="stat-info">
            <div class="stat-value">{{ memory.used_memory_human || '-' }}</div>
            <div class="stat-label">已用内存</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-green)">🎯</div>
          <div class="stat-info">
            <div class="stat-value">{{ formatPercent(metrics.hit_rate) }}</div>
            <div class="stat-label">缓存命中率</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-red)">🗑️</div>
          <div class="stat-info">
            <div class="stat-value">{{ metrics.evicted_keys ?? '-' }}</div>
            <div class="stat-label">淘汰键数</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-purple)">⏰</div>
          <div class="stat-info">
            <div class="stat-value">{{ metrics.expired_keys ?? '-' }}</div>
            <div class="stat-label">过期键数</div>
          </div>
        </div>
      </div>

      <!-- 内存详情 -->
      <div class="section-card">
        <h3>💾 内存信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">已用内存</span>
            <span class="detail-value">{{ memory.used_memory_human || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">内存峰值</span>
            <span class="detail-value">{{ memory.used_memory_peak_human || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">最大内存限制</span>
            <span class="detail-value">{{ memory.maxmemory_human || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">内存使用率</span>
            <span class="detail-value">
              <span :class="getUsageClass(memory.usage_percent)">{{ formatPercent(memory.usage_percent) }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">碎片率</span>
            <span class="detail-value">
              <span :class="getFragmentationClass(memory.fragmentation_ratio)">{{ memory.fragmentation_ratio ?? '-' }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">淘汰策略</span>
            <span class="detail-value">{{ memory.maxmemory_policy || '-' }}</span>
          </div>
        </div>
      </div>

      <!-- 客户端信息 -->
      <div class="section-card">
        <h3>🔗 客户端信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">已连接客户端</span>
            <span class="detail-value">{{ clients.connected ?? '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">阻塞客户端</span>
            <span class="detail-value">
              <span :class="clients.blocked > 0 ? 'status-critical' : ''">{{ clients.blocked ?? '-' }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">最大客户端数</span>
            <span class="detail-value">{{ clients.maxclients ?? '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">客户端使用率</span>
            <span class="detail-value">
              <span :class="getUsageClass(clients.usage_percent)">{{ formatPercent(clients.usage_percent) }}</span>
            </span>
          </div>
        </div>
      </div>

      <!-- 持久化信息 -->
      <div class="section-card">
        <h3>💿 持久化信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">RDB 最近保存</span>
            <span class="detail-value">{{ persistence.rdb_last_save_time || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">RDB 变更次数</span>
            <span class="detail-value">{{ persistence.rdb_changes_since_last_save ?? '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">AOF 启用</span>
            <span class="detail-value">
              <span class="status-badge" :class="persistence.aof_enabled ? 'badge-green' : 'badge-gray'">
                {{ persistence.aof_enabled ? '是' : '否' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">AOF 重写中</span>
            <span class="detail-value">
              <span class="status-badge" :class="persistence.aof_rewrite_in_progress ? 'badge-yellow' : 'badge-green'">
                {{ persistence.aof_rewrite_in_progress ? '是' : '否' }}
              </span>
            </span>
          </div>
        </div>
      </div>

      <!-- 复制信息 -->
      <div class="section-card">
        <h3>🔄 复制信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">角色</span>
            <span class="detail-value">
              <span class="status-badge" :class="replication.role === 'master' ? 'badge-blue' : 'badge-purple'">
                {{ replication.role === 'master' ? '主节点' : replication.role === 'slave' ? '从节点' : (replication.role || '-') }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">已连接从节点</span>
            <span class="detail-value">{{ replication.connected_slaves ?? '-' }}</span>
          </div>
        </div>
      </div>

      <!-- 延迟事件 -->
      <div class="section-card">
        <h3>⏱️ 延迟事件</h3>
        <div v-if="latencyLoading" class="loading-text">加载中...</div>
        <div v-else-if="latencyEvents.length === 0" class="empty-text">暂无延迟事件</div>
        <div v-else class="latency-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>事件名称</th>
                <th>最大延迟(μs)</th>
                <th>最近延迟(μs)</th>
                <th>发生次数</th>
                <th>时间戳</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(evt, idx) in latencyEvents" :key="idx">
                <td>{{ evt.event_name || evt.name || '-' }}</td>
                <td :class="getLatencyClass(evt.max_latency || evt.max)">{{ evt.max_latency || evt.max || '-' }}</td>
                <td>{{ evt.last_latency || evt.recent || '-' }}</td>
                <td>{{ evt.count || '-' }}</td>
                <td>{{ evt.timestamp || evt.time || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const route = useRoute()
const instanceId = ref(route.query.instance_id || '')

// 数据状态
const loading = ref(true)
const error = ref('')
const serverInfo = ref({})
const metrics = ref({})
const memory = ref({})
const clients = ref({})
const persistence = ref({})
const replication = ref({})
const latencyEvents = ref([])
const latencyLoading = ref(false)

let refreshTimer = null

// 格式化运行时间
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

// 格式化百分比
function formatPercent(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  return num.toFixed(1) + '%'
}

// 连接状态样式
const connectionClass = ref('badge-green')
const connectionLabel = ref('已连接')

// 内存使用率样式
function getUsageClass(percent) {
  if (percent == null) return ''
  const num = Number(percent)
  if (num >= 90) return 'status-critical'
  if (num >= 70) return 'status-warning'
  return 'status-healthy'
}

// 碎片率样式
function getFragmentationClass(ratio) {
  if (ratio == null) return ''
  const num = Number(ratio)
  if (num >= 2.0 || num < 1.0) return 'status-warning'
  return 'status-healthy'
}

// 延迟等级样式
function getLatencyClass(val) {
  if (val == null) return ''
  const num = Number(val)
  if (num >= 10000) return 'status-critical'
  if (num >= 1000) return 'status-warning'
  return 'status-healthy'
}

// 加载 Redis 状态
async function loadStatus() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisStatus(params)
    const data = res.data || {}

    // 服务器信息
    serverInfo.value = {
      version: data.redis_version || data.version,
      mode: data.redis_mode || data.mode,
      uptime: data.uptime_in_seconds || data.uptime,
      os: data.os
    }

    // 核心指标
    metrics.value = {
      qps: data.instantaneous_ops_per_sec || data.qps,
      connected_clients: data.connected_clients,
      hit_rate: data.hit_rate ?? data.keyspace_hit_rate,
      evicted_keys: data.evicted_keys,
      expired_keys: data.expired_keys
    }

    // 内存信息
    memory.value = {
      used_memory_human: data.used_memory_human,
      used_memory_peak_human: data.used_memory_peak_human,
      maxmemory_human: data.maxmemory_human || (data.maxmemory && Number(data.maxmemory) > 0 ? formatBytes(data.maxmemory) : '无限制'),
      usage_percent: data.memory_usage_percent ?? data.usage_percent,
      fragmentation_ratio: data.mem_fragmentation_ratio ?? data.fragmentation_ratio,
      maxmemory_policy: data.maxmemory_policy
    }

    // 客户端信息
    const maxclients = data.maxclients || data.max_clients
    const connected = Number(data.connected_clients) || 0
    clients.value = {
      connected: data.connected_clients,
      blocked: data.blocked_clients,
      maxclients: maxclients,
      usage_percent: maxclients && Number(maxclients) > 0 ? (connected / Number(maxclients) * 100) : null
    }

    // 连接状态
    connectionClass.value = data.error ? 'badge-red' : 'badge-green'
    connectionLabel.value = data.error ? '连接失败' : '已连接'

    error.value = ''
  } catch (e) {
    error.value = '无法获取 Redis 状态: ' + (e.response?.data?.detail || e.message || '未知错误')
    connectionClass.value = 'badge-red'
    connectionLabel.value = '连接失败'
  }
}

// 加载持久化信息
async function loadPersistence() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisPersistence(params)
    const data = res.data || {}
    persistence.value = {
      rdb_last_save_time: data.rdb_last_save_time || data.last_save_time || '-',
      rdb_changes_since_last_save: data.rdb_changes_since_last_save ?? data.changes_since_last_save,
      aof_enabled: data.aof_enabled,
      aof_rewrite_in_progress: data.aof_rewrite_in_progress
    }
  } catch (e) {
    console.error('loadRedisPersistence error', e)
  }
}

// 加载复制信息
async function loadReplication() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisReplication(params)
    const data = res.data || {}
    replication.value = {
      role: data.role,
      connected_slaves: data.connected_slaves
    }
  } catch (e) {
    console.error('loadRedisReplication error', e)
  }
}

// 加载延迟事件
async function loadLatency() {
  latencyLoading.value = true
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisLatency(params)
    const data = res.data || {}
    if (Array.isArray(data)) {
      latencyEvents.value = data
    } else if (data.items || data.events) {
      latencyEvents.value = data.items || data.events
    } else {
      latencyEvents.value = []
    }
  } catch (e) {
    console.error('loadRedisLatency error', e)
    latencyEvents.value = []
  } finally {
    latencyLoading.value = false
  }
}

// 格式化字节数
function formatBytes(bytes) {
  const num = Number(bytes)
  if (isNaN(num) || num === 0) return '0B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(num) / Math.log(1024))
  return (num / Math.pow(1024, i)).toFixed(2) + units[i]
}

// 加载全部数据
async function loadAll() {
  loading.value = true
  error.value = ''
  await Promise.all([
    loadStatus(),
    loadPersistence(),
    loadReplication(),
    loadLatency()
  ])
  loading.value = false
}

// 自动刷新：每10秒
function startAutoRefresh() {
  refreshTimer = setInterval(() => {
    loadAll()
  }, 10000)
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
.redis-monitor {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 60px 0;
  color: var(--text-muted);
  font-size: 14px;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 错误状态 */
.error-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
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
  transition: opacity 0.2s;
}

.retry-btn:hover {
  opacity: 0.85;
}

/* 服务器信息卡片 */
.server-info-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.server-icon {
  font-size: 32px;
}

.server-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.server-meta {
  display: flex;
  gap: 16px;
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

/* 状态徽章 */
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

.badge-blue {
  background: rgba(59, 130, 246, 0.2);
  color: var(--accent-blue);
}

.badge-purple {
  background: rgba(139, 92, 246, 0.2);
  color: var(--accent-purple);
}

.badge-gray {
  background: rgba(107, 114, 128, 0.2);
  color: var(--text-muted);
}

/* 状态颜色 */
.status-healthy {
  color: var(--accent-green);
  font-weight: 600;
}

.status-warning {
  color: var(--accent-yellow);
  font-weight: 600;
}

.status-critical {
  color: var(--accent-red);
  font-weight: 600;
}

/* 核心指标卡片 */
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

/* 数据表格 */
.latency-table-wrapper {
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

  .detail-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .server-info-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .server-title {
    font-size: 15px;
    flex-wrap: wrap;
  }

  .server-meta {
    flex-direction: column;
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

  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
