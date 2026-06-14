<template>
  <div class="replication-panel">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-text">加载中...</div>

    <!-- 无复制配置 -->
    <div v-else-if="!isMaster && !isSlave" class="empty-card">
      <div class="empty-icon">📡</div>
      <div class="empty-msg">未检测到复制配置</div>
      <div class="empty-hint">当前 MySQL 实例未配置为主库或从库</div>
    </div>

    <template v-else>
      <!-- 主库状态 -->
      <div v-if="isMaster" class="section-card">
        <h3>🏛️ 主库状态</h3>
        <div class="status-grid">
          <div class="status-row">
            <span class="status-label">角色</span>
            <span class="status-value role-badge master">Master</span>
          </div>
          <div class="status-row">
            <span class="status-label">Binlog 文件</span>
            <span class="status-value mono">{{ replData.master?.binlog_file || replData.binlog_file || '-' }}</span>
          </div>
          <div class="status-row">
            <span class="status-label">Binlog Position</span>
            <span class="status-value mono">{{ replData.master?.binlog_position || replData.binlog_position || '-' }}</span>
          </div>
          <div class="status-row" v-if="replData.master?.binlog_do_db || replData.binlog_do_db">
            <span class="status-label">Binlog Do DB</span>
            <span class="status-value">{{ replData.master?.binlog_do_db || replData.binlog_do_db }}</span>
          </div>
          <div class="status-row" v-if="replData.master?.binlog_ignore_db || replData.binlog_ignore_db">
            <span class="status-label">Binlog Ignore DB</span>
            <span class="status-value">{{ replData.master?.binlog_ignore_db || replData.binlog_ignore_db }}</span>
          </div>
        </div>
      </div>

      <!-- 从库状态 -->
      <div v-if="isSlave" class="section-card">
        <h3>🔗 从库状态</h3>
        <div class="status-grid">
          <div class="status-row">
            <span class="status-label">角色</span>
            <span class="status-value role-badge slave">Slave</span>
          </div>
          <div class="status-row">
            <span class="status-label">Master Host:Port</span>
            <span class="status-value mono">{{ replData.slave?.master_host || replData.master_host || '-' }}:{{ replData.slave?.master_port || replData.master_port || '-' }}</span>
          </div>

          <!-- IO Thread -->
          <div class="status-row">
            <span class="status-label">IO Thread</span>
            <span class="status-value">
              <span class="thread-indicator" :class="ioRunning ? 'running' : 'stopped'"></span>
              {{ ioRunning ? 'Running' : 'Stopped' }}
            </span>
          </div>

          <!-- SQL Thread -->
          <div class="status-row">
            <span class="status-label">SQL Thread</span>
            <span class="status-value">
              <span class="thread-indicator" :class="sqlRunning ? 'running' : 'stopped'"></span>
              {{ sqlRunning ? 'Running' : 'Stopped' }}
            </span>
          </div>

          <!-- Seconds Behind Master -->
          <div class="status-row">
            <span class="status-label">Seconds Behind Master</span>
            <span class="status-value" :class="delayClass">{{ secondsBehind }}</span>
          </div>

          <!-- Last IO Error -->
          <div class="status-row" v-if="lastIOError">
            <span class="status-label">Last IO Error</span>
            <span class="status-value error-text">{{ lastIOError }}</span>
          </div>

          <!-- Last SQL Error -->
          <div class="status-row" v-if="lastSQLError">
            <span class="status-label">Last SQL Error</span>
            <span class="status-value error-text">{{ lastSQLError }}</span>
          </div>

          <!-- 其他从库信息 -->
          <div class="status-row" v-if="replData.slave?.relay_log_file || replData.relay_log_file">
            <span class="status-label">Relay Log</span>
            <span class="status-value mono">{{ replData.slave?.relay_log_file || replData.relay_log_file }}</span>
          </div>
          <div class="status-row" v-if="replData.slave?.relay_log_pos || replData.relay_log_pos">
            <span class="status-label">Relay Log Pos</span>
            <span class="status-value mono">{{ replData.slave?.relay_log_pos || replData.relay_log_pos }}</span>
          </div>
          <div class="status-row" v-if="replData.slave?.exec_master_log_pos || replData.exec_master_log_pos">
            <span class="status-label">Exec Master Log Pos</span>
            <span class="status-value mono">{{ replData.slave?.exec_master_log_pos || replData.exec_master_log_pos }}</span>
          </div>
        </div>
      </div>

      <!-- 复制延迟趋势 -->
      <div v-if="isSlave && delayTrend.length > 0" class="section-card">
        <h3>📈 复制延迟趋势</h3>
        <div class="trend-list">
          <div v-for="(item, idx) in delayTrend" :key="idx" class="trend-row">
            <span class="trend-time">{{ item.time }}</span>
            <span class="trend-bar-wrapper">
              <span class="trend-bar" :class="getDelayClass(item.seconds)" :style="{ width: getTrendBarWidth(item.seconds) + '%' }"></span>
            </span>
            <span class="trend-value" :class="getDelayClass(item.seconds)">{{ item.seconds }}s</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 连接测试 -->
    <div class="section-card">
      <h3>🔌 连接测试</h3>
      <div class="test-form">
        <div class="form-row">
          <div class="form-field">
            <label>Host</label>
            <input v-model="testForm.host" type="text" placeholder="127.0.0.1" class="form-input" />
          </div>
          <div class="form-field">
            <label>Port</label>
            <input v-model.number="testForm.port" type="number" placeholder="3306" class="form-input" />
          </div>
          <div class="form-field">
            <label>User</label>
            <input v-model="testForm.user" type="text" placeholder="root" class="form-input" />
          </div>
          <div class="form-field">
            <label>Password</label>
            <input v-model="testForm.password" type="password" placeholder="密码" class="form-input" />
          </div>
        </div>
        <button class="test-btn" @click="handleTestConnection" :disabled="testLoading">
          {{ testLoading ? '测试中...' : '测试连接' }}
        </button>
      </div>
      <div v-if="testResult" class="test-result" :class="testSuccess ? 'success' : 'error'">
        {{ testResult }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'

const loading = ref(true)
const replData = ref({})
const delayTrend = ref([])
const testLoading = ref(false)
const testResult = ref('')
const testSuccess = ref(false)

const testForm = ref({
  host: '',
  port: 3306,
  user: '',
  password: ''
})

const isMaster = computed(() => {
  return replData.value.is_master === true || replData.value.role === 'master'
})

const isSlave = computed(() => {
  return replData.value.is_slave === true || replData.value.role === 'slave'
})

const ioRunning = computed(() => {
  const slave = replData.value.slave || replData.value
  const io = slave.slave_io_running || slave.io_running || slave.io_thread
  if (typeof io === 'string') return io.toLowerCase() === 'yes'
  return io === true
})

const sqlRunning = computed(() => {
  const slave = replData.value.slave || replData.value
  const sql = slave.slave_sql_running || slave.sql_running || slave.sql_thread
  if (typeof sql === 'string') return sql.toLowerCase() === 'yes'
  return sql === true
})

const secondsBehind = computed(() => {
  const slave = replData.value.slave || replData.value
  const val = slave.seconds_behind_master ?? slave.seconds_behind ?? slave.delay ?? null
  if (val == null) return '-'
  return val
})

const delayClass = computed(() => {
  const val = Number(secondsBehind.value)
  if (isNaN(val)) return ''
  if (val < 5) return 'delay-green'
  if (val < 30) return 'delay-yellow'
  return 'delay-red'
})

const lastIOError = computed(() => {
  const slave = replData.value.slave || replData.value
  const err = slave.last_io_error || slave.last_io_errno || ''
  return err || ''
})

const lastSQLError = computed(() => {
  const slave = replData.value.slave || replData.value
  const err = slave.last_sql_error || slave.last_sql_errno || ''
  return err || ''
})

function getDelayClass(seconds) {
  const val = Number(seconds)
  if (isNaN(val)) return ''
  if (val < 5) return 'delay-green'
  if (val < 30) return 'delay-yellow'
  return 'delay-red'
}

function getTrendBarWidth(seconds) {
  const val = Number(seconds)
  if (isNaN(val)) return 0
  const maxSeconds = 120
  return Math.min((val / maxSeconds) * 100, 100)
}

async function loadReplicationStatus() {
  loading.value = true
  try {
    const res = await api.getReplicationStatus({})
    replData.value = res.data || {}

    // 提取延迟趋势
    const data = res.data || {}
    if (Array.isArray(data.delay_trend || data.trend)) {
      delayTrend.value = (data.delay_trend || data.trend).map(item => {
        if (typeof item === 'object') {
          return {
            time: item.time || item.timestamp || item.created_at || '-',
            seconds: item.seconds ?? item.delay ?? item.value ?? 0
          }
        }
        return { time: '-', seconds: item }
      })
    } else {
      delayTrend.value = []
    }
  } catch (e) {
    console.error('loadReplicationStatus error', e)
    replData.value = {}
  } finally {
    loading.value = false
  }
}

async function handleTestConnection() {
  testLoading.value = true
  testResult.value = ''
  try {
    const res = await api.testMySQLConnection({
      host: testForm.value.host,
      port: testForm.value.port,
      user: testForm.value.user,
      password: testForm.value.password
    })
    testSuccess.value = true
    testResult.value = res.data?.message || res.data?.result || '连接成功'
  } catch (e) {
    testSuccess.value = false
    testResult.value = '连接失败：' + (e.response?.data?.detail || e.response?.data?.message || e.message || '未知错误')
  } finally {
    testLoading.value = false
  }
}

onMounted(() => {
  loadReplicationStatus()
})
</script>

<style scoped>
.replication-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
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

/* 无复制配置 */
.empty-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.empty-msg {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
}

/* 状态网格 */
.status-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 13px;
}

.status-label {
  color: var(--text-muted);
  min-width: 140px;
  flex-shrink: 0;
}

.status-value {
  color: var(--text-primary);
  flex: 1;
  word-break: break-word;
}

.status-value.mono {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

/* 角色标签 */
.role-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 700;
}

.role-badge.master {
  background: rgba(59,130,246,0.2);
  color: var(--accent-blue);
}

.role-badge.slave {
  background: rgba(16,185,129,0.2);
  color: var(--accent-green);
}

/* 线程状态指示器 */
.thread-indicator {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

.thread-indicator.running {
  background: var(--accent-green);
  box-shadow: 0 0 4px var(--accent-green);
}

.thread-indicator.stopped {
  background: var(--accent-red);
  box-shadow: 0 0 4px var(--accent-red);
}

/* 延迟颜色 */
.delay-green { color: var(--accent-green); }
.delay-yellow { color: var(--accent-yellow); }
.delay-red { color: var(--accent-red); }

/* 错误文本 */
.error-text {
  color: var(--accent-red);
  font-size: 12px;
}

/* 延迟趋势 */
.trend-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trend-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.trend-time {
  color: var(--text-muted);
  min-width: 80px;
  font-variant-numeric: tabular-nums;
}

.trend-bar-wrapper {
  flex: 1;
  height: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  overflow: hidden;
}

.trend-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
  min-width: 2px;
}

.trend-bar.delay-green { background: var(--accent-green); }
.trend-bar.delay-yellow { background: var(--accent-yellow); }
.trend-bar.delay-red { background: var(--accent-red); }

.trend-value {
  min-width: 40px;
  text-align: right;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 连接测试表单 */
.test-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 140px;
}

.form-field label {
  font-size: 12px;
  color: var(--text-muted);
}

.form-input {
  padding: 8px 10px;
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

.form-input::placeholder {
  color: var(--text-muted);
}

.test-btn {
  align-self: flex-start;
  padding: 8px 24px;
  background: var(--accent-blue);
  color: #fff;
  border: 1px solid var(--accent-blue);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.test-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.test-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.test-result {
  margin-top: 10px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.test-result.success {
  background: rgba(16,185,129,0.1);
  border: 1px solid var(--accent-green);
  color: var(--accent-green);
}

.test-result.error {
  background: rgba(239,68,68,0.1);
  border: 1px solid var(--accent-red);
  color: var(--accent-red);
}

.loading-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 40px;
}

@media (max-width: 768px) {
  .status-row {
    flex-direction: column;
    gap: 2px;
  }

  .status-label {
    min-width: auto;
  }

  .form-row {
    flex-direction: column;
    gap: 10px;
  }

  .form-field {
    min-width: auto;
  }

  .test-btn {
    width: 100%;
    text-align: center;
  }

  .trend-time {
    min-width: 60px;
    font-size: 11px;
  }

  .trend-row {
    gap: 6px;
  }
}
</style>
