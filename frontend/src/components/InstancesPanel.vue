<template>
  <div class="instances-panel">
    <!-- 提示消息 -->
    <transition name="fade">
      <div v-if="message.text" class="message-bar" :class="message.type">
        {{ message.text }}
      </div>
    </transition>

    <!-- 头部 -->
    <div class="panel-header">
      <div class="header-left">
        <h2 class="panel-title">实例管理</h2>
        <div class="overview-stats">
          <span class="stat-tag total">总计 {{ overview.total }}</span>
          <span class="stat-tag healthy">健康 {{ overview.healthy }}</span>
          <span class="stat-tag unhealthy">异常 {{ overview.unhealthy }}</span>
        </div>
      </div>
      <button class="btn-primary" @click="openAddModal">+ 添加实例</button>
    </div>

    <!-- 分组过滤 -->
    <div class="group-section">
      <div class="group-header" @click="groupExpanded = !groupExpanded">
        <span class="group-title">分组管理</span>
        <span class="collapse-icon">{{ groupExpanded ? '▼' : '▶' }}</span>
      </div>
      <div v-if="groupExpanded" class="group-list">
        <button
          :class="['group-chip', { active: activeGroup === '' }]"
          @click="activeGroup = ''"
        >全部</button>
        <button
          v-for="g in groups"
          :key="g.name"
          :class="['group-chip', { active: activeGroup === g.name }]"
          @click="activeGroup = g.name"
        >
          {{ g.name }} <span class="group-count">{{ g.count }}</span>
        </button>
      </div>
    </div>

    <!-- 实例网格 -->
    <div v-if="loading" class="loading-text">加载中...</div>
    <div v-else-if="filteredInstances.length === 0" class="empty-text">暂无实例，请点击"添加实例"按钮添加</div>
    <div v-else class="instance-grid">
      <div v-for="inst in filteredInstances" :key="inst.id" class="instance-card">
        <div class="card-header">
          <span :class="['status-dot', inst.status || 'unknown']"></span>
          <span class="instance-name">{{ inst.name }}</span>
          <span v-if="inst.group" class="group-badge">{{ inst.group }}</span>
        </div>
        <div class="card-body">
          <div class="card-info-row">
            <span class="info-label">地址</span>
            <span class="info-value">{{ inst.host }}:{{ inst.port }}</span>
          </div>
          <div class="card-stats">
            <span :class="['stat-item', { danger: inst.error_count_24h > 0 }]">
              错误 <strong>{{ inst.error_count_24h ?? 0 }}</strong>
            </span>
            <span :class="['stat-item', { warning: inst.warning_count_24h > 0 }]">
              警告 <strong>{{ inst.warning_count_24h ?? 0 }}</strong>
            </span>
          </div>
          <div class="card-info-row">
            <span class="info-label">最近采集</span>
            <span class="info-value time">{{ formatTime(inst.last_collected_at) }}</span>
          </div>
        </div>
        <div class="card-actions">
          <button class="action-btn" @click="handleTestConnection(inst)" :disabled="inst._testing">
            {{ inst._testing ? '测试中...' : '测试连接' }}
          </button>
          <button class="action-btn" @click="handleViewStatus(inst)">查看状态</button>
          <button class="action-btn" @click="handleCollectLogs(inst)" :disabled="inst._collecting">
            {{ inst._collecting ? '采集中...' : '采集日志' }}
          </button>
          <button class="action-btn" @click="openEditModal(inst)">编辑</button>
          <button class="action-btn danger" @click="handleDelete(inst)">删除</button>
        </div>
      </div>
    </div>

    <!-- 添加/编辑实例弹窗 -->
    <div v-if="showFormModal" class="modal-overlay" @click.self="closeFormModal">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ isEditing ? '编辑实例' : '添加实例' }}</h3>
          <button class="modal-close" @click="closeFormModal">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称 <span class="required">*</span></label>
            <input v-model="form.name" type="text" placeholder="例如：生产主库" />
          </div>
          <div class="form-group">
            <label>主机 <span class="required">*</span></label>
            <input v-model="form.host" type="text" placeholder="例如：192.168.1.100" />
          </div>
          <div class="form-group">
            <label>端口</label>
            <input v-model.number="form.port" type="number" placeholder="3306" />
          </div>
          <div class="form-group">
            <label>日志路径</label>
            <input v-model="form.log_path" type="text" placeholder="/var/log/mysql/error.log" />
          </div>
          <div class="form-group">
            <label>分组</label>
            <input v-model="form.group" type="text" placeholder="可选，例如：生产环境" />
          </div>
          <div class="form-group">
            <label>用户名</label>
            <input v-model="form.username" type="text" placeholder="用于连接测试" />
          </div>
          <div class="form-group">
            <label>密码</label>
            <input v-model="form.password" type="password" placeholder="用于连接测试" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeFormModal">取消</button>
          <button class="btn-primary" @click="handleSaveInstance" :disabled="formSaving">
            {{ formSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 实例状态弹窗 -->
    <div v-if="showStatusModal" class="modal-overlay" @click.self="closeStatusModal">
      <div class="modal modal-lg">
        <div class="modal-header">
          <h3>实例状态 - {{ statusData.instance?.name }}</h3>
          <button class="modal-close" @click="closeStatusModal">&times;</button>
        </div>
        <div class="modal-body" v-if="statusLoading">
          <div class="loading-text">加载中...</div>
        </div>
        <div class="modal-body" v-else>
          <!-- 基本信息 -->
          <div class="status-section">
            <h4>基本信息</h4>
            <div class="status-info-grid">
              <div class="status-info-item">
                <span class="info-label">名称</span>
                <span class="info-value">{{ statusData.instance?.name || '-' }}</span>
              </div>
              <div class="status-info-item">
                <span class="info-label">地址</span>
                <span class="info-value">{{ statusData.instance?.host }}:{{ statusData.instance?.port }}</span>
              </div>
              <div class="status-info-item">
                <span class="info-label">分组</span>
                <span class="info-value">{{ statusData.instance?.group || '-' }}</span>
              </div>
              <div class="status-info-item">
                <span class="info-label">状态</span>
                <span :class="['status-badge', statusData.instance?.status || 'unknown']">
                  {{ statusLabel(statusData.instance?.status) }}
                </span>
              </div>
            </div>
          </div>

          <!-- 连接信息 -->
          <div class="status-section" v-if="statusData.connection">
            <h4>连接信息</h4>
            <div class="status-info-grid">
              <div class="status-info-item">
                <span class="info-label">版本</span>
                <span class="info-value">{{ statusData.connection.version || '-' }}</span>
              </div>
              <div class="status-info-item">
                <span class="info-label">运行时间</span>
                <span class="info-value">{{ formatUptime(statusData.connection.uptime) }}</span>
              </div>
            </div>
          </div>

          <!-- 日志统计 -->
          <div class="status-section" v-if="statusData.log_stats && statusData.log_stats.length > 0">
            <h4>日志统计</h4>
            <table class="stats-table">
              <thead>
                <tr>
                  <th>级别</th>
                  <th>数量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in statusData.log_stats" :key="s.level">
                  <td><span :class="['level-badge', s.level]">{{ s.level }}</span></td>
                  <td>{{ s.count }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 最近错误 -->
          <div class="status-section" v-if="statusData.latest_errors && statusData.latest_errors.length > 0">
            <h4>最近 5 条错误</h4>
            <div class="error-list">
              <div v-for="(err, idx) in statusData.latest_errors" :key="idx" class="error-item">
                <div class="error-meta">
                  <span class="error-time">{{ formatTime(err.timestamp || err.time) }}</span>
                  <span :class="['level-badge', err.level]">{{ err.level }}</span>
                </div>
                <div class="error-msg">{{ err.message || err.content || '-' }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeStatusModal">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { api } from '../api.js'

// 状态
const loading = ref(false)
const instances = ref([])
const groups = ref([])
const overview = reactive({ total: 0, healthy: 0, unhealthy: 0 })
const activeGroup = ref('')
const groupExpanded = ref(false)
const message = reactive({ text: '', type: 'info' })

// 表单弹窗
const showFormModal = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const formSaving = ref(false)
const form = reactive({
  name: '',
  host: '',
  port: 3306,
  log_path: '',
  group: '',
  username: '',
  password: ''
})

// 状态弹窗
const showStatusModal = ref(false)
const statusLoading = ref(false)
const statusData = reactive({
  instance: null,
  log_stats: [],
  latest_errors: [],
  connection: null
})

// 过滤后的实例
const filteredInstances = computed(() => {
  if (!activeGroup.value) return instances.value
  return instances.value.filter(i => i.group === activeGroup.value)
})

// 提示消息
function showMessage(text, type = 'info') {
  message.text = text
  message.type = type
  setTimeout(() => { message.text = '' }, 3000)
}

// 时间格式化
function formatTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

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

function statusLabel(status) {
  if (status === 'healthy') return '健康'
  if (status === 'unhealthy') return '异常'
  return '未知'
}

// 加载数据
async function loadInstances() {
  loading.value = true
  try {
    const res = await api.getInstances()
    const data = res.data
    instances.value = (Array.isArray(data) ? data : data?.items || data?.instances || []).map(i => ({
      ...i,
      _testing: false,
      _collecting: false
    }))
  } catch (e) {
    console.error('loadInstances error', e)
    showMessage('加载实例列表失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadOverview() {
  try {
    const res = await api.getInstancesOverview()
    const data = res.data || {}
    overview.total = data.total ?? 0
    overview.healthy = data.healthy ?? 0
    overview.unhealthy = data.unhealthy ?? 0
  } catch (e) {
    // 从实例列表推算
    overview.total = instances.value.length
    overview.healthy = instances.value.filter(i => i.status === 'healthy').length
    overview.unhealthy = instances.value.filter(i => i.status === 'unhealthy').length
  }
}

async function loadGroups() {
  try {
    const res = await api.getInstanceGroups()
    const data = res.data
    groups.value = Array.isArray(data) ? data : data?.groups || []
  } catch (e) {
    console.error('loadGroups error', e)
  }
}

// 添加/编辑弹窗
function openAddModal() {
  isEditing.value = false
  editingId.value = null
  Object.assign(form, {
    name: '',
    host: '',
    port: 3306,
    log_path: '',
    group: '',
    username: '',
    password: ''
  })
  showFormModal.value = true
}

function openEditModal(inst) {
  isEditing.value = true
  editingId.value = inst.id
  Object.assign(form, {
    name: inst.name || '',
    host: inst.host || '',
    port: inst.port || 3306,
    log_path: inst.log_path || '',
    group: inst.group || '',
    username: inst.username || '',
    password: ''
  })
  showFormModal.value = true
}

function closeFormModal() {
  showFormModal.value = false
}

async function handleSaveInstance() {
  if (!form.name || !form.host) {
    showMessage('名称和主机为必填项', 'error')
    return
  }
  formSaving.value = true
  try {
    const payload = { ...form }
    if (!payload.password) delete payload.password
    if (isEditing.value) {
      await api.updateInstance(editingId.value, payload)
      showMessage('实例更新成功', 'success')
    } else {
      await api.addInstance(payload)
      showMessage('实例添加成功', 'success')
    }
    closeFormModal()
    await loadInstances()
    await loadOverview()
    await loadGroups()
  } catch (e) {
    console.error('saveInstance error', e)
    showMessage(isEditing.value ? '更新实例失败' : '添加实例失败', 'error')
  } finally {
    formSaving.value = false
  }
}

// 删除
async function handleDelete(inst) {
  if (!confirm(`确定要删除实例"${inst.name}"吗？`)) return
  try {
    await api.deleteInstance(inst.id)
    showMessage('实例已删除', 'success')
    await loadInstances()
    await loadOverview()
    await loadGroups()
  } catch (e) {
    console.error('deleteInstance error', e)
    showMessage('删除实例失败', 'error')
  }
}

// 测试连接
async function handleTestConnection(inst) {
  inst._testing = true
  try {
    const res = await api.testInstanceConnection(inst.id)
    const data = res.data || {}
    if (data.success || data.connected) {
      showMessage(`连接成功${data.version ? ' - ' + data.version : ''}`, 'success')
    } else {
      showMessage(`连接失败: ${data.error || data.message || '未知错误'}`, 'error')
    }
  } catch (e) {
    const msg = e.response?.data?.error || e.response?.data?.message || '连接测试失败'
    showMessage(`连接失败: ${msg}`, 'error')
  } finally {
    inst._testing = false
  }
}

// 采集日志
async function handleCollectLogs(inst) {
  inst._collecting = true
  try {
    await api.collectInstanceLogs(inst.id)
    showMessage(`实例"${inst.name}"日志采集已触发`, 'success')
  } catch (e) {
    const msg = e.response?.data?.error || e.response?.data?.message || '采集失败'
    showMessage(`日志采集失败: ${msg}`, 'error')
  } finally {
    inst._collecting = false
  }
}

// 查看状态
async function handleViewStatus(inst) {
  showStatusModal.value = true
  statusLoading.value = true
  statusData.instance = inst
  statusData.log_stats = []
  statusData.latest_errors = []
  statusData.connection = null
  try {
    const res = await api.getInstanceStatus(inst.id)
    const data = res.data || {}
    statusData.instance = data.instance || inst
    statusData.log_stats = data.log_stats || data.stats || []
    statusData.latest_errors = data.latest_errors || data.recent_errors || []
    statusData.connection = data.connection || null
  } catch (e) {
    console.error('getInstanceStatus error', e)
    showMessage('获取实例状态失败', 'error')
  } finally {
    statusLoading.value = false
  }
}

function closeStatusModal() {
  showStatusModal.value = false
}

onMounted(async () => {
  await loadInstances()
  await loadOverview()
  await loadGroups()
})
</script>

<style scoped>
.instances-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 提示消息 */
.message-bar {
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

.message-bar.info { background: rgba(6,182,212,0.15); color: var(--accent-cyan); }
.message-bar.success { background: rgba(16,185,129,0.15); color: var(--accent-green); }
.message-bar.error { background: rgba(239,68,68,0.15); color: var(--accent-red); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* 头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.overview-stats {
  display: flex;
  gap: 8px;
}

.stat-tag {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 600;
}

.stat-tag.total { background: rgba(59,130,246,0.15); color: var(--accent-blue); }
.stat-tag.healthy { background: rgba(16,185,129,0.15); color: var(--accent-green); }
.stat-tag.unhealthy { background: rgba(239,68,68,0.15); color: var(--accent-red); }

/* 按钮 */
.btn-primary {
  padding: 8px 18px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-primary:hover { background: #2563eb; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  padding: 8px 18px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.btn-secondary:hover { background: var(--bg-hover); color: var(--text-primary); }

/* 分组管理 */
.group-section {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.group-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
}

.collapse-icon {
  font-size: 12px;
  color: var(--text-muted);
}

.group-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 12px;
}

.group-chip {
  padding: 4px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 16px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.group-chip:hover { background: var(--bg-hover); color: var(--text-primary); }

.group-chip.active {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

.group-count {
  margin-left: 4px;
  font-weight: 700;
}

/* 实例网格 */
.instance-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.instance-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.2s;
}

.instance-card:hover { border-color: var(--accent-blue); }

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.healthy { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); }
.status-dot.unhealthy { background: var(--accent-red); box-shadow: 0 0 6px var(--accent-red); }
.status-dot.unknown { background: var(--text-muted); }

.instance-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(139,92,246,0.15);
  color: var(--accent-purple);
  font-weight: 600;
  white-space: nowrap;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.info-label {
  color: var(--text-muted);
  flex-shrink: 0;
}

.info-value {
  color: var(--text-secondary);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60%;
}

.info-value.time {
  font-size: 12px;
  color: var(--text-muted);
}

.card-stats {
  display: flex;
  gap: 16px;
}

.stat-item {
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-item strong {
  font-weight: 700;
  margin-left: 2px;
}

.stat-item.danger { color: var(--accent-red); }
.stat-item.warning { color: var(--accent-yellow); }

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.action-btn {
  padding: 4px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.action-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.action-btn.danger:hover { background: var(--accent-red); color: #fff; border-color: var(--accent-red); }

/* 弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 500;
}

.modal {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  width: 480px;
  max-width: 95vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 48px rgba(0,0,0,0.5);
}

.modal-lg {
  width: 640px;
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
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 22px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.modal-close:hover { color: var(--text-primary); }

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border-color);
}

/* 表单 */
.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.required {
  color: var(--accent-red);
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.form-group input:focus { border-color: var(--accent-blue); }
.form-group input::placeholder { color: var(--text-muted); }

/* 状态弹窗 */
.status-section {
  margin-bottom: 20px;
}

.status-section:last-child { margin-bottom: 0; }

.status-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-blue);
  margin: 0 0 10px 0;
}

.status-info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.status-info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-size: 13px;
}

.status-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.status-badge.healthy { background: rgba(16,185,129,0.15); color: var(--accent-green); }
.status-badge.unhealthy { background: rgba(239,68,68,0.15); color: var(--accent-red); }
.status-badge.unknown { background: rgba(100,116,139,0.15); color: var(--text-muted); }

/* 统计表格 */
.stats-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.stats-table th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
}

.stats-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.level-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
}

.level-badge.error { background: rgba(239,68,68,0.2); color: var(--accent-red); }
.level-badge.warning { background: rgba(245,158,11,0.2); color: var(--accent-yellow); }
.level-badge.info { background: rgba(6,182,212,0.2); color: var(--accent-cyan); }
.level-badge.note { background: rgba(100,116,139,0.2); color: var(--text-muted); }

/* 错误列表 */
.error-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px 12px;
}

.error-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.error-time {
  font-size: 12px;
  color: var(--text-muted);
}

.error-msg {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  word-break: break-word;
}

.loading-text, .empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 40px 20px;
}

/* 响应式 */
@media (max-width: 1024px) {
  .instance-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .instance-grid {
    grid-template-columns: 1fr;
  }

  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-left {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .overview-stats {
    flex-wrap: wrap;
  }

  .status-info-grid {
    grid-template-columns: 1fr;
  }

  .modal {
    width: 100%;
    max-width: 100vw;
    max-height: 100vh;
    border-radius: 0;
  }

  .card-actions {
    gap: 4px;
  }

  .action-btn {
    font-size: 11px;
    padding: 3px 8px;
  }
}
</style>
