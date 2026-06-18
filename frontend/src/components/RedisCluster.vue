<template>
  <div class="redis-cluster">
    <!-- 加载状态 -->
    <div v-if="loading && !clusterLoaded && !sentinelLoaded" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载 Redis 集群/哨兵数据...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <!-- 集群状态 -->
      <div class="section-card">
        <h3>🌐 集群状态</h3>

        <!-- 非集群模式提示 -->
        <div v-if="!clusterInfo.is_cluster" class="info-message">
          <span class="info-icon">ℹ️</span>
          <span>{{ clusterInfo.message || '当前实例不是集群模式' }}</span>
        </div>

        <!-- 集群模式详情 -->
        <template v-else>
          <!-- 集群概览指标 -->
          <div class="stat-cards">
            <div class="stat-card">
              <div class="stat-icon" style="color: var(--accent-green)">🟢</div>
              <div class="stat-info">
                <div class="stat-value">
                  <span class="status-badge" :class="clusterInfo.cluster_state === 'ok' ? 'badge-green' : 'badge-red'">
                    {{ clusterInfo.cluster_state === 'ok' ? '正常' : '异常' }}
                  </span>
                </div>
                <div class="stat-label">集群状态</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon" style="color: var(--accent-blue)">📦</div>
              <div class="stat-info">
                <div class="stat-value">{{ clusterInfo.cluster_slots_ok ?? '-' }}</div>
                <div class="stat-label">正常槽位</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon" style="color: var(--accent-purple)">🎯</div>
              <div class="stat-info">
                <div class="stat-value">{{ clusterInfo.cluster_slots_assigned ?? '-' }}</div>
                <div class="stat-label">已分配槽位</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon" style="color: var(--accent-yellow)">👑</div>
              <div class="stat-info">
                <div class="stat-value">{{ clusterInfo.master_count ?? '-' }}</div>
                <div class="stat-label">主节点数</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon" style="color: var(--accent-blue)">🔗</div>
              <div class="stat-info">
                <div class="stat-value">{{ clusterInfo.slave_count ?? '-' }}</div>
                <div class="stat-label">从节点数</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon" style="color: var(--accent-green)">✅</div>
              <div class="stat-info">
                <div class="stat-value">{{ clusterInfo.connected_count ?? '-' }}</div>
                <div class="stat-label">已连接节点数</div>
              </div>
            </div>
          </div>

          <!-- 节点列表 -->
          <div class="section-card" style="margin-top: 16px">
            <h3>📋 集群节点列表</h3>
            <div v-if="clusterNodes.length === 0" class="empty-text">暂无节点数据</div>
            <div v-else class="table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>节点 ID</th>
                    <th>地址</th>
                    <th>标志</th>
                    <th>是否主节点</th>
                    <th>是否已连接</th>
                    <th>槽位</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(node, idx) in clusterNodes" :key="idx">
                    <td class="mono-text">{{ node.id || '-' }}</td>
                    <td>{{ node.address || node.ip_port || '-' }}</td>
                    <td>
                      <span class="flag-badge" :class="getFlagClass(node.flags)">{{ node.flags || '-' }}</span>
                    </td>
                    <td>
                      <span class="status-badge" :class="node.is_master ? 'badge-blue' : 'badge-gray'">
                        {{ node.is_master ? '主' : '从' }}
                      </span>
                    </td>
                    <td>
                      <span class="status-badge" :class="node.is_connected ? 'badge-green' : 'badge-red'">
                        {{ node.is_connected ? '已连接' : '未连接' }}
                      </span>
                    </td>
                    <td class="mono-text">{{ node.slots || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </div>

      <!-- 哨兵状态 -->
      <div class="section-card">
        <h3>🛡️ 哨兵状态</h3>

        <!-- 非哨兵模式提示 -->
        <div v-if="!sentinelInfo.is_sentinel" class="info-message">
          <span class="info-icon">ℹ️</span>
          <span>{{ sentinelInfo.message || '当前实例不是 Sentinel 模式' }}</span>
        </div>

        <!-- 哨兵模式详情 -->
        <template v-else>
          <!-- 主节点监控列表 -->
          <div class="section-card" style="margin-bottom: 16px; border: 1px solid var(--border-color)">
            <h3>📡 监控的主节点</h3>
            <div v-if="sentinelMasters.length === 0" class="empty-text">暂无主节点监控数据</div>
            <div v-else class="table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>IP</th>
                    <th>端口</th>
                    <th>从节点数</th>
                    <th>其他哨兵数</th>
                    <th>仲裁数</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(master, idx) in sentinelMasters" :key="idx"
                      :class="{ 'row-selected': selectedMasterName === master.name }"
                      @click="selectMaster(master)">
                    <td class="mono-text">{{ master.name || '-' }}</td>
                    <td>{{ master.ip || '-' }}</td>
                    <td>{{ master.port ?? '-' }}</td>
                    <td>{{ master.num_slaves ?? '-' }}</td>
                    <td>{{ master.num_other_sentinels ?? '-' }}</td>
                    <td>{{ master.quorum ?? '-' }}</td>
                    <td>
                      <span class="status-badge" :class="master.ok || master.status === 'ok' ? 'badge-green' : 'badge-red'">
                        {{ (master.ok || master.status === 'ok') ? '正常' : '异常' }}
                      </span>
                    </td>
                    <td>
                      <button class="action-btn" @click.stop="selectMaster(master)">查看从节点</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 选中主节点的从节点列表 -->
          <div v-if="selectedMasterName" class="section-card" style="border: 1px solid var(--border-color)">
            <h3>📎 从节点列表 — {{ selectedMasterName }}</h3>
            <div v-if="slavesLoading" class="loading-text">加载从节点数据...</div>
            <div v-else-if="sentinelSlaves.length === 0" class="empty-text">暂无从节点数据</div>
            <div v-else class="table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>IP</th>
                    <th>端口</th>
                    <th>状态</th>
                    <th>主节点</th>
                    <th>偏移量</th>
                    <th>延迟</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(slave, idx) in sentinelSlaves" :key="idx">
                    <td>{{ slave.ip || '-' }}</td>
                    <td>{{ slave.port ?? '-' }}</td>
                    <td>
                      <span class="status-badge" :class="slave.ok || slave.status === 'ok' ? 'badge-green' : 'badge-red'">
                        {{ (slave.ok || slave.status === 'ok') ? '正常' : '异常' }}
                      </span>
                    </td>
                    <td class="mono-text">{{ slave.master_host ? `${slave.master_host}:${slave.master_port}` : '-' }}</td>
                    <td class="mono-text">{{ slave.offset ?? slave.master_link_repl_offset ?? '-' }}</td>
                    <td class="mono-text">{{ slave.latency ?? slave.master_last_heartbeat_sec ?? '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
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

// 加载与错误状态
const loading = ref(true)
const clusterLoaded = ref(false)
const sentinelLoaded = ref(false)
const error = ref('')

// 集群数据
const clusterInfo = ref({})
const clusterNodes = ref([])

// 哨兵数据
const sentinelInfo = ref({})
const sentinelMasters = ref([])
const sentinelSlaves = ref([])
const selectedMasterName = ref('')
const slavesLoading = ref(false)

let refreshTimer = null

// 获取标志样式
function getFlagClass(flags) {
  if (!flags) return ''
  const f = String(flags).toLowerCase()
  if (f.includes('master')) return 'flag-master'
  if (f.includes('slave')) return 'flag-slave'
  if (f.includes('fail')) return 'flag-fail'
  return ''
}

// 选择主节点，加载其从节点
async function selectMaster(master) {
  selectedMasterName.value = master.name
  await loadSentinelSlaves(master.name)
}

// 加载集群信息
async function loadClusterInfo() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisClusterInfo(params)
    const data = res.data || {}
    clusterInfo.value = {
      is_cluster: data.is_cluster || data.cluster_state !== undefined,
      mode: data.mode,
      message: data.message,
      cluster_state: data.cluster_state,
      cluster_slots_ok: data.cluster_slots_ok,
      cluster_slots_assigned: data.cluster_slots_assigned,
      master_count: data.master_count,
      slave_count: data.slave_count,
      connected_count: data.connected_count
    }
    clusterLoaded.value = true
  } catch (e) {
    console.error('加载集群信息失败:', e)
  }
}

// 加载集群节点
async function loadClusterNodes() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisClusterNodes(params)
    const data = res.data || {}
    if (Array.isArray(data)) {
      clusterNodes.value = data
    } else if (data.nodes || data.items) {
      clusterNodes.value = data.nodes || data.items
    } else {
      clusterNodes.value = []
    }
  } catch (e) {
    console.error('加载集群节点失败:', e)
    clusterNodes.value = []
  }
}

// 加载哨兵主节点列表
async function loadSentinelMasters() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisSentinelMasters(params)
    const data = res.data || {}
    // 判断是否为哨兵模式
    if (data.is_sentinel !== undefined) {
      sentinelInfo.value = { is_sentinel: data.is_sentinel, mode: data.mode, message: data.message }
      sentinelMasters.value = data.masters || data.items || []
    } else if (Array.isArray(data)) {
      // 如果返回的是数组，说明是哨兵模式
      sentinelInfo.value = { is_sentinel: true }
      sentinelMasters.value = data
    } else {
      sentinelInfo.value = { is_sentinel: data.is_sentinel || false, mode: data.mode, message: data.message }
      sentinelMasters.value = data.masters || data.items || []
    }
    sentinelLoaded.value = true
  } catch (e) {
    // 接口报错可能说明不是哨兵模式
    sentinelInfo.value = { is_sentinel: false }
    sentinelMasters.value = []
    sentinelLoaded.value = true
    console.error('加载哨兵主节点失败:', e)
  }
}

// 加载指定主节点的从节点
async function loadSentinelSlaves(masterName) {
  slavesLoading.value = true
  try {
    const params = { master_name: masterName }
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisSentinelSlaves(params)
    const data = res.data || {}
    if (Array.isArray(data)) {
      sentinelSlaves.value = data
    } else if (data.slaves || data.items) {
      sentinelSlaves.value = data.slaves || data.items
    } else {
      sentinelSlaves.value = []
    }
  } catch (e) {
    console.error('加载从节点失败:', e)
    sentinelSlaves.value = []
  } finally {
    slavesLoading.value = false
  }
}

// 加载全部数据
async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([
      loadClusterInfo(),
      loadClusterNodes(),
      loadSentinelMasters()
    ])
  } catch (e) {
    error.value = '无法获取集群/哨兵数据: ' + (e.response?.data?.detail || e.message || '未知错误')
  }
  loading.value = false
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
.redis-cluster {
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

/* 信息提示 */
.info-message {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid var(--accent-blue);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.info-icon {
  font-size: 18px;
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

/* 标志徽章 */
.flag-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.flag-master {
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent-blue);
}

.flag-slave {
  background: rgba(139, 92, 246, 0.15);
  color: var(--accent-purple);
}

.flag-fail {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-red);
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

.data-table tbody tr {
  cursor: pointer;
  transition: background 0.15s;
}

.data-table tbody tr:hover {
  background: rgba(59, 130, 246, 0.06);
}

.row-selected {
  background: rgba(59, 130, 246, 0.1) !important;
}

.mono-text {
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 11px;
}

/* 操作按钮 */
.action-btn {
  padding: 3px 10px;
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent-blue);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: rgba(59, 130, 246, 0.25);
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
}
</style>
