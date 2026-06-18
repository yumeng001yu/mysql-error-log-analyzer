<template>
  <div class="redis-memory">
    <!-- 加载状态 -->
    <div v-if="loading && !overview.used_memory_human" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载 Redis 内存分析数据...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <!-- 概览卡片 -->
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-yellow)">💾</div>
          <div class="stat-info">
            <div class="stat-value">{{ overview.used_memory_human || '-' }}</div>
            <div class="stat-label">已用内存</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-purple)">📈</div>
          <div class="stat-info">
            <div class="stat-value">{{ overview.used_memory_peak_human || '-' }}</div>
            <div class="stat-label">内存峰值</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-cyan)">📏</div>
          <div class="stat-info">
            <div class="stat-value">{{ overview.maxmemory_human || '无限制' }}</div>
            <div class="stat-label">最大内存限制</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: var(--accent-green)">📊</div>
          <div class="stat-info">
            <div class="stat-value">
              <span :class="getUsageClass(overview.usage_percent)">{{ formatPercent(overview.usage_percent) }}</span>
            </div>
            <div class="stat-label">内存使用率</div>
          </div>
        </div>
      </div>

      <!-- 碎片率分析 -->
      <div class="section-card">
        <h3>🧩 碎片率分析</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">碎片率</span>
            <span class="detail-value">
              <span :class="getFragClass(fragmentation.ratio)">{{ fragmentation.ratio ?? '-' }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">碎片字节数</span>
            <span class="detail-value">{{ fragmentation.bytes_human || fragmentation.bytes || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">状态</span>
            <span class="detail-value">
              <span class="status-badge" :class="fragStatusBadge">{{ fragStatusLabel }}</span>
            </span>
          </div>
        </div>
        <div v-if="fragmentation.recommendation" class="recommendation-text">
          💡 {{ fragmentation.recommendation }}
        </div>
      </div>

      <!-- 内存组成 -->
      <div class="section-card">
        <h3>📊 内存组成</h3>
        <div class="composition-bars">
          <!-- 数据集 -->
          <div class="comp-row">
            <div class="comp-label">
              <span class="comp-dot" style="background: var(--accent-blue)"></span>
              数据集
            </div>
            <div class="comp-bar-wrapper">
              <div class="comp-bar" :style="{ width: composition.dataset_percent + '%', background: 'var(--accent-blue)' }"></div>
            </div>
            <div class="comp-value">{{ formatPercent(composition.dataset_percent) }}</div>
          </div>
          <!-- 开销 -->
          <div class="comp-row">
            <div class="comp-label">
              <span class="comp-dot" style="background: var(--accent-yellow)"></span>
              开销
            </div>
            <div class="comp-bar-wrapper">
              <div class="comp-bar" :style="{ width: composition.overhead_percent + '%', background: 'var(--accent-yellow)' }"></div>
            </div>
            <div class="comp-value">{{ formatPercent(composition.overhead_percent) }}</div>
          </div>
          <!-- 启动 -->
          <div class="comp-row">
            <div class="comp-label">
              <span class="comp-dot" style="background: var(--accent-purple)"></span>
              启动
            </div>
            <div class="comp-bar-wrapper">
              <div class="comp-bar" :style="{ width: composition.startup_percent + '%', background: 'var(--accent-purple)' }"></div>
            </div>
            <div class="comp-value">{{ formatPercent(composition.startup_percent) }}</div>
          </div>
        </div>
      </div>

      <!-- 淘汰信息 -->
      <div class="section-card">
        <h3>🗑️ 淘汰信息</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">淘汰策略</span>
            <span class="detail-value">{{ eviction.policy || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">策略说明</span>
            <span class="detail-value policy-desc">{{ eviction.policy_desc || getPolicyDesc(eviction.policy) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">已淘汰键数</span>
            <span class="detail-value">
              <span :class="eviction.evicted_keys > 0 ? 'status-warning' : ''">{{ eviction.evicted_keys ?? '-' }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">已过期键数</span>
            <span class="detail-value">{{ eviction.expired_keys ?? '-' }}</span>
          </div>
        </div>
      </div>

      <!-- Lua 内存 -->
      <div class="section-card">
        <h3>🌙 Lua 内存</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">Lua 已用内存</span>
            <span class="detail-value">{{ luaMemory.used_memory_human || luaMemory.used_memory || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Lua 内存字节数</span>
            <span class="detail-value">{{ luaMemory.used_memory_bytes ?? '-' }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'
import { formatPercent, formatBytes } from '../utils/format.js'

const route = useRoute()
const instanceId = ref(route.query.instance_id || '')

// 数据状态
const loading = ref(true)
const error = ref('')
const rawData = ref({})

// 概览信息
const overview = ref({})
// 碎片率信息
const fragmentation = ref({})
// 内存组成
const composition = ref({})
// 淘汰信息
const eviction = ref({})
// Lua 内存
const luaMemory = ref({})

let refreshTimer = null

// 内存使用率样式
function getUsageClass(percent) {
  if (percent == null) return ''
  const num = Number(percent)
  if (num >= 90) return 'status-critical'
  if (num >= 70) return 'status-warning'
  return 'status-healthy'
}

// 碎片率样式
function getFragClass(ratio) {
  if (ratio == null) return ''
  const num = Number(ratio)
  if (num >= 2.0 || num < 1.0) return 'status-warning'
  if (num >= 1.5) return 'status-healthy'
  return 'status-healthy'
}

// 碎片率状态徽章
const fragStatusBadge = computed(() => {
  const ratio = fragmentation.value.ratio
  if (ratio == null) return 'badge-gray'
  const num = Number(ratio)
  if (num >= 3.0 || num < 0.8) return 'badge-red'
  if (num >= 2.0 || num < 1.0) return 'badge-yellow'
  return 'badge-green'
})

const fragStatusLabel = computed(() => {
  const ratio = fragmentation.value.ratio
  if (ratio == null) return '未知'
  const num = Number(ratio)
  if (num >= 3.0 || num < 0.8) return '危险'
  if (num >= 2.0 || num < 1.0) return '警告'
  return '健康'
})

// 淘汰策略说明
function getPolicyDesc(policy) {
  if (!policy) return '-'
  const descMap = {
    'noeviction': '不淘汰，内存满时拒绝写入',
    'allkeys-lru': '从所有键中淘汰最近最少使用的',
    'allkeys-lfu': '从所有键中淘汰最不经常使用的',
    'allkeys-random': '从所有键中随机淘汰',
    'volatile-lru': '从设置了过期时间的键中淘汰最近最少使用的',
    'volatile-lfu': '从设置了过期时间的键中淘汰最不经常使用的',
    'volatile-random': '从设置了过期时间的键中随机淘汰',
    'volatile-ttl': '从设置了过期时间的键中淘汰 TTL 最短的'
  }
  return descMap[policy] || policy
}

// 加载内存数据
async function loadMemory() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisMemory(params)
    const data = res.data || {}
    rawData.value = data

    // API 返回嵌套结构：{ overview, fragmentation, composition, eviction, lua }
    // 同时兼容扁平结构
    const overviewData = data.overview || {}
    const fragData = data.fragmentation || {}
    const compData = data.composition || {}
    const evictData = data.eviction || {}
    const luaData = data.lua || {}

    // 概览
    const maxmemoryHuman = (overviewData.maxmemory_human || data.maxmemory_human)
      || ((overviewData.maxmemory && Number(overviewData.maxmemory) > 0) ? formatBytes(overviewData.maxmemory) : '')
      || ((data.maxmemory && Number(data.maxmemory) > 0) ? formatBytes(data.maxmemory) : '')
      || '无限制'
    overview.value = {
      used_memory_human: overviewData.used_memory_human ?? data.used_memory_human,
      used_memory_peak_human: overviewData.used_memory_peak_human ?? data.used_memory_peak_human,
      maxmemory_human: maxmemoryHuman,
      usage_percent: overviewData.usage_percent ?? data.usage_percent ?? data.memory_usage_percent
    }

    // 碎片率
    fragmentation.value = {
      ratio: fragData.ratio ?? fragData.fragmentation_ratio ?? data.mem_fragmentation_ratio ?? data.fragmentation_ratio,
      bytes: fragData.bytes ?? fragData.fragmentation_bytes ?? data.mem_fragmentation_bytes ?? data.fragmentation_bytes,
      bytes_human: fragData.bytes_human ?? fragData.fragmentation_bytes_human ?? data.mem_fragmentation_bytes_human ?? data.fragmentation_bytes_human,
      status: fragData.status ?? data.fragmentation_status,
      recommendation: fragData.recommendation ?? data.fragmentation_recommendation
    }

    // 内存组成
    composition.value = {
      dataset_percent: compData.dataset_percent ?? data.dataset_percent ?? 0,
      overhead_percent: compData.overhead_percent ?? data.overhead_percent ?? 0,
      startup_percent: compData.startup_percent ?? data.startup_percent ?? 0
    }

    // 淘汰信息
    eviction.value = {
      policy: evictData.policy ?? evictData.maxmemory_policy ?? data.maxmemory_policy ?? data.eviction_policy,
      policy_desc: evictData.policy_desc ?? evictData.maxmemory_policy_desc ?? data.maxmemory_policy_desc ?? data.eviction_policy_desc,
      evicted_keys: evictData.evicted_keys ?? data.evicted_keys,
      expired_keys: evictData.expired_keys ?? data.expired_keys
    }

    // Lua 内存
    luaMemory.value = {
      used_memory: luaData.used_memory ?? luaData.used_memory_lua ?? data.lua_memory ?? data.used_memory_lua,
      used_memory_human: luaData.used_memory_human ?? luaData.used_memory_lua_human ?? data.lua_memory_human ?? data.used_memory_lua_human,
      used_memory_bytes: luaData.used_memory_bytes ?? luaData.used_memory_lua_bytes ?? data.lua_memory_bytes ?? data.used_memory_lua_bytes
    }

    error.value = ''
  } catch (e) {
    error.value = '无法获取 Redis 内存数据: ' + (e.response?.data?.detail || e.message || '未知错误')
  }
}

// 加载全部
async function loadAll() {
  loading.value = true
  await loadMemory()
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
.redis-memory {
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

/* 概览卡片 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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

.badge-gray {
  background: rgba(107, 114, 128, 0.2);
  color: var(--text-muted);
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

.policy-desc {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* 建议文本 */
.recommendation-text {
  margin-top: 12px;
  padding: 10px 14px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* 内存组成条 */
.composition-bars {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.comp-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.comp-label {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 70px;
  font-size: 13px;
  color: var(--text-secondary);
}

.comp-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.comp-bar-wrapper {
  flex: 1;
  height: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  overflow: hidden;
}

.comp-bar {
  height: 100%;
  border-radius: 6px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.comp-value {
  min-width: 50px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
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

  .comp-row {
    gap: 8px;
  }

  .comp-label {
    min-width: 60px;
    font-size: 12px;
  }
}
</style>
