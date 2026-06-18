<template>
  <div class="redis-persistence">
    <!-- 加载状态 -->
    <div v-if="loading && !rdb.last_save_time" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载 Redis 持久化监控数据...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span class="error-msg">{{ error }}</span>
      <button class="retry-btn" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <!-- 加载状态指示器 -->
      <div v-if="rdb.bgsave_in_progress || aof.rewrite_in_progress" class="loading-indicator">
        <div class="loading-spinner-sm"></div>
        <span>{{ rdb.bgsave_in_progress ? 'RDB 后台保存进行中...' : 'AOF 重写进行中...' }}</span>
      </div>

      <!-- RDB 持久化 -->
      <div class="section-card">
        <h3>💿 RDB 持久化</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">最近保存时间</span>
            <span class="detail-value">{{ formatTime(rdb.last_save_time) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">距上次保存（秒）</span>
            <span class="detail-value">
              <span :class="getSaveAgeClass(rdb.seconds_since_last_save)">{{ rdb.seconds_since_last_save ?? '-' }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">上次保存后变更数</span>
            <span class="detail-value">
              <span :class="rdb.changes_since_last_save > 100000 ? 'status-warning' : ''">{{ rdb.changes_since_last_save ?? '-' }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">后台保存进行中</span>
            <span class="detail-value">
              <span class="status-badge" :class="rdb.bgsave_in_progress ? 'badge-yellow' : 'badge-green'">
                {{ rdb.bgsave_in_progress ? '是' : '否' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">上次保存状态</span>
            <span class="detail-value">
              <span class="status-badge" :class="rdb.last_bgsave_status === 'ok' ? 'badge-green' : 'badge-red'">
                {{ rdb.last_bgsave_status || '-' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">上次保存耗时（秒）</span>
            <span class="detail-value">
              <span :class="getBgsaveTimeClass(rdb.last_bgsave_time_sec)">{{ rdb.last_bgsave_time_sec ?? '-' }}</span>
            </span>
          </div>
        </div>
        <!-- RDB 健康徽章 -->
        <div class="health-row">
          <span class="health-label">RDB 健康状态</span>
          <span class="status-badge" :class="rdbHealthBadge">{{ rdbHealthLabel }}</span>
        </div>
        <!-- RDB 警告文本 -->
        <div v-if="rdbWarning" class="warning-text">
          ⚠️ {{ rdbWarning }}
        </div>
      </div>

      <!-- AOF 持久化 -->
      <div class="section-card">
        <h3>📝 AOF 持久化</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">AOF 启用</span>
            <span class="detail-value">
              <span class="status-badge" :class="aof.enabled ? 'badge-green' : 'badge-gray'">
                {{ aof.enabled ? '是' : '否' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">重写进行中</span>
            <span class="detail-value">
              <span class="status-badge" :class="aof.rewrite_in_progress ? 'badge-yellow' : 'badge-green'">
                {{ aof.rewrite_in_progress ? '是' : '否' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">上次写入状态</span>
            <span class="detail-value">
              <span class="status-badge" :class="aof.last_write_status === 'ok' ? 'badge-green' : 'badge-red'">
                {{ aof.last_write_status || '-' }}
              </span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">当前 AOF 大小</span>
            <span class="detail-value">{{ aof.current_size || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">AOF 基准大小</span>
            <span class="detail-value">{{ aof.base_size || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">重写进度</span>
            <span class="detail-value">{{ formatPercent(aof.rewrite_percent) }}</span>
          </div>
        </div>
        <!-- AOF 重写进度条 -->
        <div v-if="aof.enabled && aof.rewrite_percent != null" class="progress-row">
          <span class="progress-label">重写进度</span>
          <div class="progress-bar-wrapper">
            <div class="progress-bar" :style="{ width: Math.min(Number(aof.rewrite_percent) || 0, 100) + '%' }"></div>
          </div>
          <span class="progress-value">{{ formatPercent(aof.rewrite_percent) }}</span>
        </div>
        <!-- AOF 健康徽章 -->
        <div class="health-row">
          <span class="health-label">AOF 健康状态</span>
          <span class="status-badge" :class="aofHealthBadge">{{ aofHealthLabel }}</span>
        </div>
        <!-- AOF 警告文本 -->
        <div v-if="aofWarning" class="warning-text">
          ⚠️ {{ aofWarning }}
        </div>
      </div>

      <!-- 综合建议 -->
      <div class="section-card">
        <h3>💡 综合建议</h3>
        <div class="recommendation-text">
          {{ overallRecommendation }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'
import { formatTimestamp as formatTime } from '../utils/datetime.js'
import { formatPercent } from '../utils/format.js'

const route = useRoute()
const instanceId = ref(route.query.instance_id || '')

// 数据状态
const loading = ref(true)
const error = ref('')

// RDB 数据
const rdb = ref({})
// AOF 数据
const aof = ref({})

let refreshTimer = null

// 距上次保存时间样式
function getSaveAgeClass(seconds) {
  if (seconds == null) return ''
  const num = Number(seconds)
  if (num >= 3600) return 'status-warning'
  return ''
}

// 后台保存耗时样式
function getBgsaveTimeClass(seconds) {
  if (seconds == null) return ''
  const num = Number(seconds)
  if (num >= 10) return 'status-critical'
  if (num >= 5) return 'status-warning'
  return ''
}

// RDB 健康状态
const rdbHealthBadge = computed(() => {
  if (rdb.value.last_bgsave_status && rdb.value.last_bgsave_status !== 'ok') return 'badge-red'
  if (rdb.value.bgsave_in_progress) return 'badge-yellow'
  if (rdb.value.last_bgsave_time_sec != null && Number(rdb.value.last_bgsave_time_sec) >= 10) return 'badge-yellow'
  return 'badge-green'
})

const rdbHealthLabel = computed(() => {
  if (rdb.value.last_bgsave_status && rdb.value.last_bgsave_status !== 'ok') return '异常'
  if (rdb.value.bgsave_in_progress) return '保存中'
  if (rdb.value.last_bgsave_time_sec != null && Number(rdb.value.last_bgsave_time_sec) >= 10) return '较慢'
  return '健康'
})

// RDB 警告文本
const rdbWarning = computed(() => {
  const warnings = []
  if (rdb.value.last_bgsave_status && rdb.value.last_bgsave_status !== 'ok') {
    warnings.push(`RDB 上次保存状态异常: ${rdb.value.last_bgsave_status}`)
  }
  if (rdb.value.last_bgsave_time_sec != null && Number(rdb.value.last_bgsave_time_sec) >= 10) {
    warnings.push(`RDB 上次保存耗时 ${rdb.value.last_bgsave_time_sec} 秒，可能导致阻塞，建议优化数据量或调整 save 配置`)
  }
  if (rdb.value.seconds_since_last_save != null && Number(rdb.value.seconds_since_last_save) >= 3600) {
    warnings.push(`距上次 RDB 保存已超过 ${Math.floor(Number(rdb.value.seconds_since_last_save) / 60)} 分钟，存在数据丢失风险`)
  }
  return warnings.join('；')
})

// AOF 健康状态
const aofHealthBadge = computed(() => {
  if (!aof.value.enabled) return 'badge-gray'
  if (aof.value.last_write_status && aof.value.last_write_status !== 'ok') return 'badge-red'
  if (aof.value.rewrite_in_progress) return 'badge-yellow'
  return 'badge-green'
})

const aofHealthLabel = computed(() => {
  if (!aof.value.enabled) return '未启用'
  if (aof.value.last_write_status && aof.value.last_write_status !== 'ok') return '异常'
  if (aof.value.rewrite_in_progress) return '重写中'
  return '健康'
})

// AOF 警告文本
const aofWarning = computed(() => {
  if (!aof.value.enabled) return ''
  const warnings = []
  if (aof.value.last_write_status && aof.value.last_write_status !== 'ok') {
    warnings.push(`AOF 上次写入状态异常: ${aof.value.last_write_status}`)
  }
  if (aof.value.rewrite_percent != null && Number(aof.value.rewrite_percent) > 200) {
    warnings.push(`AOF 重写进度 ${formatPercent(aof.value.rewrite_percent)}，当前文件远大于基准，建议检查重写配置`)
  }
  return warnings.join('；')
})

// 综合建议
const overallRecommendation = computed(() => {
  const tips = []

  if (!aof.value.enabled && rdb.value.seconds_since_last_save != null && Number(rdb.value.seconds_since_last_save) >= 300) {
    tips.push('当前仅使用 RDB 持久化，且保存间隔较长，建议启用 AOF 以减少数据丢失风险。')
  }

  if (aof.value.enabled && rdb.value.last_bgsave_status === 'ok' && aof.value.last_write_status === 'ok') {
    tips.push('RDB 和 AOF 持久化均正常运行，数据安全性较高。')
  }

  if (rdb.value.last_bgsave_time_sec != null && Number(rdb.value.last_bgsave_time_sec) >= 10) {
    tips.push('RDB 保存耗时较长，建议减少 save 配置的频率或优化数据量，避免阻塞主线程。')
  }

  if (aof.value.enabled && aof.value.rewrite_in_progress) {
    tips.push('AOF 正在重写中，请关注重写进度和系统资源使用情况。')
  }

  if (rdb.value.bgsave_in_progress) {
    tips.push('RDB 后台保存正在进行中，请关注保存完成状态。')
  }

  if (tips.length === 0) {
    tips.push('持久化配置正常，暂无特别建议。')
  }

  return tips.join(' ')
})

// 加载持久化详情
async function loadPersistence() {
  try {
    const params = {}
    if (instanceId.value) params.instance_id = instanceId.value
    const res = await api.getRedisPersistenceDetail(params)
    const data = res.data || {}

    // API 返回嵌套结构：{ rdb: {...}, aof: {...}, loading: false, recommendation: "..." }
    // 同时兼容扁平结构
    const rdbData = data.rdb || {}
    const aofData = data.aof || {}

    // RDB 数据
    rdb.value = {
      last_save_time: rdbData.last_save_time ?? rdbData.rdb_last_save_time ?? data.rdb_last_save_time ?? data.last_save_time,
      seconds_since_last_save: rdbData.seconds_since_last_save ?? rdbData.rdb_seconds_since_last_save ?? data.rdb_seconds_since_last_save ?? data.seconds_since_last_save,
      changes_since_last_save: rdbData.changes_since_last_save ?? rdbData.rdb_changes_since_last_save ?? data.rdb_changes_since_last_save ?? data.changes_since_last_save,
      bgsave_in_progress: rdbData.bgsave_in_progress ?? rdbData.rdb_bgsave_in_progress ?? data.rdb_bgsave_in_progress ?? data.bgsave_in_progress ?? false,
      last_bgsave_status: rdbData.last_bgsave_status ?? rdbData.rdb_last_bgsave_status ?? data.rdb_last_bgsave_status ?? data.last_bgsave_status ?? 'ok',
      last_bgsave_time_sec: rdbData.last_bgsave_time_sec ?? rdbData.rdb_last_bgsave_time_sec ?? data.rdb_last_bgsave_time_sec ?? data.last_bgsave_time_sec
    }

    // AOF 数据
    aof.value = {
      enabled: aofData.enabled ?? aofData.aof_enabled ?? data.aof_enabled ?? false,
      rewrite_in_progress: aofData.rewrite_in_progress ?? aofData.aof_rewrite_in_progress ?? data.aof_rewrite_in_progress ?? data.rewrite_in_progress ?? false,
      last_write_status: aofData.last_write_status ?? aofData.aof_last_write_status ?? data.aof_last_write_status ?? data.last_write_status ?? 'ok',
      current_size: aofData.current_size ?? aofData.aof_current_size ?? aofData.aof_current_size_human ?? data.aof_current_size ?? data.aof_current_size_human ?? data.current_size,
      base_size: aofData.base_size ?? aofData.aof_base_size ?? aofData.aof_base_size_human ?? data.aof_base_size ?? data.aof_base_size_human ?? data.base_size,
      rewrite_percent: aofData.rewrite_percent ?? aofData.aof_rewrite_percent ?? data.aof_rewrite_percent ?? data.rewrite_percent
    }

    error.value = ''
  } catch (e) {
    error.value = '无法获取 Redis 持久化数据: ' + (e.response?.data?.detail || e.message || '未知错误')
  }
}

// 加载全部
async function loadAll() {
  loading.value = true
  await loadPersistence()
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
.redis-persistence {
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

/* 加载状态指示器 */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  font-size: 13px;
  color: var(--accent-blue);
}

.loading-spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(59, 130, 246, 0.3);
  border-top-color: var(--accent-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
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

/* 健康状态行 */
.health-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.health-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

/* 警告文本 */
.warning-text {
  margin-top: 10px;
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 6px;
  font-size: 12px;
  color: var(--accent-yellow);
  line-height: 1.5;
}

/* 建议文本 */
.recommendation-text {
  padding: 12px 16px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* 进度条 */
.progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.progress-label {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 60px;
}

.progress-bar-wrapper {
  flex: 1;
  height: 10px;
  background: var(--bg-secondary);
  border-radius: 5px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--accent-blue);
  border-radius: 5px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.progress-value {
  min-width: 50px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* 响应式 */
@media (max-width: 900px) {
  .detail-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .progress-row {
    gap: 8px;
  }

  .progress-label {
    min-width: 50px;
  }
}
</style>
