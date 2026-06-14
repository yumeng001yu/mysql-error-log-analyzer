<template>
  <div class="status-panel">
    <!-- 系统概览 -->
    <div class="overview-card">
      <h3>🖥️ 系统概览</h3>
      <div class="overview-grid">
        <div class="overview-item">
          <span class="overview-label">运行时长</span>
          <span class="overview-value">{{ formatUptime(status.uptime || status.uptime_seconds) }}</span>
        </div>
        <div class="overview-item">
          <span class="overview-label">CPU 占用</span>
          <span class="overview-value">{{ (status.cpu_percent ?? status.cpu ?? '-').toString() }}{{ status.cpu_percent != null || status.cpu != null ? '%' : '' }}</span>
        </div>
        <div class="overview-item">
          <span class="overview-label">内存占用</span>
          <span class="overview-value">{{ formatMemory(status.memory_percent ?? status.memory) }}</span>
        </div>
        <div class="overview-item">
          <span class="overview-label">状态</span>
          <span class="overview-value status-running" v-if="status.running !== false">● 运行中</span>
          <span class="overview-value status-stopped" v-else>● 已停止</span>
        </div>
      </div>
    </div>

    <!-- 实例状态 -->
    <div class="section-title">📂 实例状态</div>
    <div class="instance-grid" v-if="instances.length > 0">
      <div v-for="inst in instances" :key="inst.name || inst.host || inst.id" class="instance-card">
        <div class="instance-header">
          <span class="instance-name">{{ inst.name || inst.host || inst.instance }}</span>
          <span class="instance-status" :class="inst.status || 'running'">
            {{ inst.status === 'error' ? '异常' : '正常' }}
          </span>
        </div>
        <div class="instance-details">
          <div class="instance-row" v-if="inst.log_file || inst.log_path">
            <span class="instance-label">日志文件</span>
            <span class="instance-value">{{ inst.log_file || inst.log_path }}</span>
          </div>
          <div class="instance-row" v-if="inst.log_size || inst.file_size">
            <span class="instance-label">文件大小</span>
            <span class="instance-value">{{ formatSize(inst.log_size || inst.file_size) }}</span>
          </div>
          <div class="instance-row" v-if="inst.last_analysis || inst.last_analyzed">
            <span class="instance-label">最近分析</span>
            <span class="instance-value">{{ formatTime(inst.last_analysis || inst.last_analyzed) }}</span>
          </div>
          <div class="instance-row" v-if="inst.progress != null">
            <span class="instance-label">处理进度</span>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: inst.progress + '%' }"></div>
            </div>
            <span class="instance-value">{{ inst.progress }}%</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="empty-text">暂无实例数据</div>

    <!-- 告警列表 -->
    <div class="section-title">🔔 告警列表</div>
    <div class="alert-table-wrapper" v-if="alerts.length > 0">
      <table class="alert-table">
        <thead>
          <tr>
            <th>级别</th>
            <th>实例</th>
            <th>消息</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="alert in alerts" :key="alert.id" :class="{ unread: !alert.is_read }">
            <td>
              <span class="level-dot" :class="alert.level">●</span>
              {{ alert.level }}
            </td>
            <td>{{ alert.instance || '-' }}</td>
            <td class="alert-msg-cell">{{ alert.message || alert.content }}</td>
            <td class="time-cell">{{ formatTime(alert.created_at || alert.time) }}</td>
            <td>
              <button
                v-if="!alert.is_read"
                class="mark-read-btn"
                @click="markRead(alert)"
              >标记已读</button>
              <span v-else class="read-label">已读</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty-text">暂无告警</div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import { api, wsManager } from '../api.js'

export default {
  name: 'StatusPanel',
  setup() {
    const status = ref({})
    const instances = ref([])
    const alerts = ref([])

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

    function formatMemory(val) {
      if (val == null) return '-'
      if (typeof val === 'string') return val
      return val.toFixed(1) + '%'
    }

    function formatSize(bytes) {
      if (!bytes) return '-'
      const units = ['B', 'KB', 'MB', 'GB']
      let size = Number(bytes)
      let i = 0
      while (size >= 1024 && i < units.length - 1) {
        size /= 1024
        i++
      }
      return size.toFixed(1) + ' ' + units[i]
    }

    function formatTime(t) {
      if (!t) return '-'
      const d = new Date(t)
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    }

    async function loadStatus() {
      try {
        const res = await api.getStatus()
        status.value = res.data || {}
      } catch { /* ignore */ }
    }

    async function loadInstances() {
      try {
        const res = await api.getInstances()
        const data = res.data || []
        instances.value = Array.isArray(data) ? data : []
      } catch { /* ignore */ }
    }

    async function loadAlerts() {
      try {
        const res = await api.getAlerts({ limit: 50 })
        alerts.value = res.data?.alerts || res.data || []
      } catch { /* ignore */ }
    }

    async function markRead(alert) {
      try {
        await api.markAlertRead(alert.id)
        alert.is_read = true
      } catch { /* ignore */ }
    }

    let refreshTimer = null

    onMounted(() => {
      loadStatus()
      loadInstances()
      loadAlerts()

      // WebSocket 实时状态推送
      wsManager.connect('/ws/status', (data) => {
        status.value = { ...status.value, ...data }
      })

      // 定时刷新
      refreshTimer = setInterval(() => {
        loadStatus()
        loadInstances()
      }, 30000)
    })

    onUnmounted(() => {
      wsManager.disconnect('/ws/status')
      if (refreshTimer) clearInterval(refreshTimer)
    })

    return {
      status, instances, alerts,
      formatUptime, formatMemory, formatSize, formatTime,
      markRead
    }
  }
}
</script>

<style scoped>
.status-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.overview-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.overview-card h3 {
  font-size: 15px;
  margin-bottom: 16px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.overview-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.overview-label {
  font-size: 12px;
  color: var(--text-muted);
}

.overview-value {
  font-size: 18px;
  font-weight: 600;
}

.status-running {
  color: var(--accent-green);
}

.status-stopped {
  color: var(--accent-red);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.instance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.instance-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.instance-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.instance-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.instance-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.instance-status.running, .instance-status.normal {
  background: rgba(16,185,129,0.2);
  color: var(--accent-green);
}

.instance-status.error {
  background: rgba(239,68,68,0.2);
  color: var(--accent-red);
}

.instance-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.instance-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.instance-label {
  color: var(--text-muted);
  min-width: 60px;
}

.instance-value {
  color: var(--text-secondary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-blue);
  border-radius: 3px;
  transition: width 0.3s;
}

/* 告警表格 */
.alert-table-wrapper {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow-x: auto;
}

.alert-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.alert-table th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
}

.alert-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.alert-table tr.unread {
  background: rgba(59,130,246,0.05);
}

.level-dot {
  font-size: 10px;
}

.level-dot.error { color: var(--accent-red); }
.level-dot.warning { color: var(--accent-yellow); }
.level-dot.info { color: var(--accent-cyan); }

.alert-msg-cell {
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time-cell {
  white-space: nowrap;
  color: var(--text-muted);
}

.mark-read-btn {
  padding: 3px 10px;
  background: transparent;
  border: 1px solid var(--accent-blue);
  color: var(--accent-blue);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.mark-read-btn:hover {
  background: var(--accent-blue);
  color: #fff;
}

.read-label {
  color: var(--text-muted);
  font-size: 12px;
}

.empty-text {
  color: var(--text-muted);
  text-align: center;
  padding: 30px;
  font-size: 14px;
}

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .overview-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .overview-value {
    font-size: 15px;
  }

  .instance-grid {
    grid-template-columns: 1fr;
  }

  /* 告警表格改为卡片列表 */
  .alert-table-wrapper {
    overflow-x: visible;
  }

  .alert-table thead {
    display: none;
  }

  .alert-table,
  .alert-table tbody,
  .alert-table tr,
  .alert-table td {
    display: block;
    width: 100%;
  }

  .alert-table tr {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    margin-bottom: 8px;
    padding: 10px 12px;
  }

  .alert-table tr.unread {
    background: rgba(59, 130, 246, 0.08);
  }

  .alert-table td {
    border: none;
    padding: 2px 0;
    font-size: 13px;
  }

  .alert-msg-cell {
    max-width: 100%;
    white-space: normal;
    word-break: break-word;
  }

  .time-cell {
    color: var(--text-muted);
    font-size: 12px;
  }

  .mark-read-btn {
    margin-top: 4px;
  }
}
</style>
