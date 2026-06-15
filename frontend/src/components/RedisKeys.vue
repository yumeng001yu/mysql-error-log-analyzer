<template>
  <div class="redis-keys">
    <!-- 加载状态 -->
    <div v-if="loading && !keyspace.total_keys" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载 Redis Key 分析数据...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <!-- Keyspace 概览 -->
      <div class="section-card">
        <h3>🗂️ Keyspace 概览</h3>
        <div class="keyspace-overview">
          <div class="total-keys-card">
            <div class="total-label">总键数</div>
            <div class="total-value">{{ keyspace.total_keys ?? '-' }}</div>
          </div>
          <div class="db-breakdown" v-if="keyspace.databases && keyspace.databases.length > 0">
            <div class="db-item" v-for="db in keyspace.databases" :key="db.name">
              <div class="db-header">
                <span class="db-name">{{ db.name }}</span>
                <span class="db-keys-count">{{ db.keys ?? 0 }} 键</span>
              </div>
              <div class="db-details">
                <span class="db-detail">
                  <span class="db-detail-label">过期键</span>
                  <span class="db-detail-value">{{ db.expires ?? '-' }}</span>
                </span>
                <span class="db-detail">
                  <span class="db-detail-label">平均 TTL</span>
                  <span class="db-detail-value">{{ formatTTL(db.avg_ttl) }}</span>
                </span>
              </div>
            </div>
          </div>
          <div v-else class="empty-text">暂无 Keyspace 数据</div>
        </div>
      </div>

      <!-- Top Keys 表格 -->
      <div class="section-card">
        <h3>🔑 Top Keys（按内存排序）</h3>
        <div v-if="topKeysLoading" class="loading-text">加载中...</div>
        <div v-else-if="topKeys.length === 0" class="empty-text">暂无 Top Key 数据</div>
        <div v-else class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>键名</th>
                <th>类型</th>
                <th>TTL</th>
                <th>内存</th>
                <th>长度</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(key, idx) in topKeys" :key="idx">
                <td class="cell-key" :title="key.name || key.key">{{ truncateKey(key.name || key.key) }}</td>
                <td>
                  <span class="type-badge">{{ key.type || '-' }}</span>
                </td>
                <td class="cell-ttl">{{ formatTTL(key.ttl ?? key.ttl_seconds) }}</td>
                <td class="cell-memory">{{ formatMemory(key.memory_bytes ?? key.memory) }}</td>
                <td class="cell-length">{{ key.length ?? key.len ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 扫描操作 -->
      <div class="section-card">
        <h3>🔍 Key 扫描</h3>
        <div class="scan-area">
          <div class="scan-warning">
            ⚠️ 注意：扫描操作会遍历 Redis 中的键，可能对生产环境造成性能影响，请谨慎使用。
          </div>
          <div class="scan-controls">
            <input
              v-model="scanPattern"
              class="scan-input"
              placeholder="扫描模式（如 user:*），留空扫描全部"
            />
            <button
              class="scan-btn"
              :disabled="scanning"
              @click="startScan"
            >
              {{ scanning ? '扫描中...' : '开始扫描' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 扫描结果 -->
      <div class="section-card" v-if="scanResult">
        <h3>📋 扫描结果</h3>
        <div class="scan-summary">
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">扫描模式</span>
              <span class="detail-value">{{ scanResult.pattern || '*' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">扫描总数</span>
              <span class="detail-value">{{ scanResult.total_scanned ?? '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">已分析数</span>
              <span class="detail-value">{{ scanResult.analyzed ?? '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">耗时（秒）</span>
              <span class="detail-value">{{ scanResult.elapsed_seconds ?? '-' }}</span>
            </div>
          </div>
        </div>

        <!-- 扫描 Top Keys -->
        <div v-if="scanResult.top_keys_by_memory && scanResult.top_keys_by_memory.length > 0" class="scan-top-keys">
          <h4>按内存排序 Top Keys</h4>
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>键名</th>
                  <th>类型</th>
                  <th>内存</th>
                  <th>TTL</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(key, idx) in scanResult.top_keys_by_memory" :key="idx">
                  <td class="cell-key" :title="key.name || key.key">{{ truncateKey(key.name || key.key) }}</td>
                  <td><span class="type-badge">{{ key.type || '-' }}</span></td>
                  <td class="cell-memory">{{ formatMemory(key.memory_bytes ?? key.memory) }}</td>
                  <td class="cell-ttl">{{ formatTTL(key.ttl ?? key.ttl_seconds) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const route = useRoute()
const instanceId = ref(route.query.instance_id || '')

// 数据状态
const loading = ref(true)
const error = ref('')
const topKeysLoading = ref(false)

// Keyspace 数据
const keyspace = ref({})
// Top Keys
const topKeys = ref([])
// 扫描相关
const scanPattern = ref('')
const scanning = ref(false)
const scanResult = ref(null)

// 格式化 TTL
function formatTTL(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  if (num === -1) return '永不过期'
  if (num === -2) return '已过期'
  if (num < 0) return String(val)
  if (num < 60) return `${num}秒`
  if (num < 3600) return `${Math.floor(num / 60)}分${num % 60}秒`
  if (num < 86400) return `${Math.floor(num / 3600)}小时${Math.floor((num % 3600) / 60)}分`
  return `${Math.floor(num / 86400)}天${Math.floor((num % 86400) / 3600)}小时`
}

// 格式化内存
function formatMemory(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num) || num === 0) return '0B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(num) / Math.log(1024))
  return (num / Math.pow(1024, i)).toFixed(2) + units[i]
}

// 截断键名
function truncateKey(name) {
  if (!name) return '-'
  return name.length > 60 ? name.substring(0, 60) + '...' : name
}

// 加载 Keyspace
async function loadKeyspace() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisKeyspace(params)
    const data = res.data || {}

    keyspace.value = {
      total_keys: data.total_keys ?? data.keys ?? data.total,
      databases: data.databases ?? data.db ?? []
    }

    // 如果 databases 是对象格式（如 { db0: { keys: 100, expires: 50, avg_ttl: 1234 } }），转换为数组
    if (!Array.isArray(keyspace.value.databases) && typeof keyspace.value.databases === 'object') {
      keyspace.value.databases = Object.entries(keyspace.value.databases).map(([name, info]) => ({
        name,
        keys: info.keys,
        expires: info.expires,
        avg_ttl: info.avg_ttl
      }))
    }

    error.value = ''
  } catch (e) {
    error.value = '无法获取 Keyspace 数据: ' + (e.response?.data?.detail || e.message || '未知错误')
  }
}

// 加载 Top Keys
async function loadTopKeys() {
  topKeysLoading.value = true
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisTopKeys(params)
    const data = res.data || {}
    if (Array.isArray(data)) {
      topKeys.value = data
    } else if (data.items || data.keys || data.top_keys) {
      topKeys.value = data.items || data.keys || data.top_keys
    } else {
      topKeys.value = []
    }
  } catch (e) {
    console.error('loadTopKeys error', e)
    topKeys.value = []
  } finally {
    topKeysLoading.value = false
  }
}

// 开始扫描
async function startScan() {
  scanning.value = true
  scanResult.value = null
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    if (scanPattern.value) params.pattern = scanPattern.value
    const res = await api.scanRedisKeys(params)
    scanResult.value = res.data || {}
  } catch (e) {
    scanResult.value = {
      error: '扫描失败: ' + (e.response?.data?.detail || e.message || '未知错误')
    }
  } finally {
    scanning.value = false
  }
}

// 加载全部
async function loadAll() {
  loading.value = true
  error.value = ''
  await Promise.all([
    loadKeyspace(),
    loadTopKeys()
  ])
  loading.value = false
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
.redis-keys {
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

.section-card h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 16px 0 10px;
  color: var(--text-secondary);
}

/* Keyspace 概览 */
.keyspace-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.total-keys-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.total-label {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--accent-blue);
  font-variant-numeric: tabular-nums;
}

.db-breakdown {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.db-item {
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.db-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.db-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-cyan);
}

.db-keys-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.db-details {
  display: flex;
  gap: 16px;
}

.db-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.db-detail-label {
  font-size: 11px;
  color: var(--text-muted);
}

.db-detail-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
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

.cell-key {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.cell-ttl {
  white-space: nowrap;
  font-size: 11px;
  color: var(--text-secondary);
}

.cell-memory {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.cell-length {
  font-variant-numeric: tabular-nums;
}

.type-badge {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 8px;
  font-weight: 600;
  background: rgba(139, 92, 246, 0.15);
  color: var(--accent-purple);
}

/* 扫描区域 */
.scan-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scan-warning {
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 6px;
  font-size: 12px;
  color: var(--accent-yellow);
  line-height: 1.5;
}

.scan-controls {
  display: flex;
  gap: 10px;
}

.scan-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.scan-input::placeholder {
  color: var(--text-muted);
}

.scan-input:focus {
  border-color: var(--accent-blue);
}

.scan-btn {
  padding: 8px 20px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.scan-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.scan-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 详情网格 */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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

.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 响应式 */
@media (max-width: 900px) {
  .db-breakdown {
    grid-template-columns: repeat(2, 1fr);
  }

  .detail-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .db-breakdown {
    grid-template-columns: 1fr;
  }

  .detail-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .scan-controls {
    flex-direction: column;
  }

  .total-value {
    font-size: 22px;
  }
}
</style>
