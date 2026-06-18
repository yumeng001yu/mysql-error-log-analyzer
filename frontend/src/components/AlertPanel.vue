<template>
  <div class="alert-panel">
    <!-- 提示消息 -->
    <transition name="fade">
      <div v-if="message.text" class="message-bar" :class="message.type">
        {{ message.text }}
      </div>
    </transition>

    <!-- 标签页 -->
    <div class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </div>

    <!-- Tab 1: 告警历史 -->
    <div v-if="activeTab === 'history'" class="tab-content">
      <!-- 统计概览 -->
      <div class="stats-row">
        <div class="stat-item">
          <span class="stat-num">{{ stats.total }}</span>
          <span class="stat-desc">告警总数</span>
        </div>
        <div class="stat-item firing">
          <span class="stat-num">{{ stats.firing }}</span>
          <span class="stat-desc">触发中</span>
        </div>
        <div class="stat-item acknowledged">
          <span class="stat-num">{{ stats.acknowledged }}</span>
          <span class="stat-desc">已确认</span>
        </div>
        <div class="stat-item resolved">
          <span class="stat-num">{{ stats.resolved }}</span>
          <span class="stat-desc">已解决</span>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <select v-model="historyFilter.level" class="filter-select">
          <option value="all">全部级别</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select v-model="historyFilter.status" class="filter-select">
          <option value="all">全部状态</option>
          <option value="firing">触发中</option>
          <option value="acknowledged">已确认</option>
          <option value="resolved">已解决</option>
        </select>
        <select v-model="historyFilter.timeRange" class="filter-select">
          <option value="1h">最近 1 小时</option>
          <option value="6h">最近 6 小时</option>
          <option value="24h">最近 24 小时</option>
          <option value="7d">最近 7 天</option>
          <option value="30d">最近 30 天</option>
        </select>
      </div>

      <!-- 告警列表 -->
      <div v-if="historyLoading" class="loading-text">加载中...</div>
      <div v-else-if="alertHistory.length === 0" class="empty-text">暂无告警记录</div>
      <div v-else class="alert-list">
        <div v-for="alert in alertHistory" :key="alert.id" class="alert-card">
          <div class="alert-card-header">
            <span :class="['level-badge', alert.level]">{{ levelLabel(alert.level) }}</span>
            <span class="alert-rule-name">{{ alert.rule_name || '-' }}</span>
            <span :class="['status-badge', alert.status]">
              <span v-if="alert.status === 'firing'" class="pulse-dot"></span>
              {{ statusLabel(alert.status) }}
            </span>
          </div>
          <div class="alert-message">{{ alert.message || '-' }}</div>
          <div class="alert-card-footer">
            <span class="alert-time">{{ alert.triggered_at || alert.created_at || '-' }}</span>
            <button
              v-if="alert.status === 'firing'"
              class="ack-btn"
              @click="acknowledgeAlert(alert.id)"
            >确认</button>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="historyPagination.total > historyPagination.pageSize" class="pagination">
        <button
          class="page-btn"
          :disabled="historyPagination.page <= 1"
          @click="historyPagination.page--"
        >上一页</button>
        <span class="page-info">{{ historyPagination.page }} / {{ totalPages }}</span>
        <button
          class="page-btn"
          :disabled="historyPagination.page >= totalPages"
          @click="historyPagination.page++"
        >下一页</button>
      </div>
    </div>

    <!-- Tab 2: 告警规则 -->
    <div v-if="activeTab === 'rules'" class="tab-content">
      <div class="section-actions">
        <button class="primary-btn" @click="openRuleModal()">新建规则</button>
      </div>

      <div v-if="rulesLoading" class="loading-text">加载中...</div>
      <div v-else-if="alertRules.length === 0" class="empty-text">暂无告警规则</div>
      <div v-else class="rule-list">
        <div v-for="rule in alertRules" :key="rule.id" class="rule-card">
          <div class="rule-card-header">
            <div class="rule-title-row">
              <span class="rule-name">{{ rule.name }}</span>
              <span :class="['type-badge', rule.rule_type]">{{ ruleTypeLabel(rule.rule_type) }}</span>
              <span :class="['level-badge', rule.level]">{{ levelLabel(rule.level) }}</span>
            </div>
            <div class="rule-desc">{{ rule.description || '-' }}</div>
          </div>
          <div class="rule-detail">
            <span class="rule-detail-item">
              <span class="detail-label">指标</span>
              <span class="detail-value">{{ metricLabel(rule.metric) }}</span>
            </span>
            <span class="rule-detail-item">
              <span class="detail-label">条件</span>
              <span class="detail-value">{{ conditionLabel(rule.condition) }} {{ rule.threshold }}</span>
            </span>
            <span class="rule-detail-item">
              <span class="detail-label">窗口</span>
              <span class="detail-value">{{ rule.window }} 分钟</span>
            </span>
          </div>
          <div class="rule-card-footer">
            <label class="toggle-switch">
              <input type="checkbox" :checked="rule.enabled" @change="toggleRule(rule.id)" />
              <span class="toggle-slider"></span>
              <span class="toggle-text">{{ rule.enabled ? '已启用' : '已禁用' }}</span>
            </label>
            <div class="rule-actions">
              <button class="action-btn edit" @click="openRuleModal(rule)">编辑</button>
              <button class="action-btn delete" @click="deleteRule(rule.id)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 规则编辑弹窗 -->
      <transition name="fade">
        <div v-if="ruleModalVisible" class="modal-overlay" @click.self="ruleModalVisible = false">
          <div class="modal-content">
            <div class="modal-header">
              <h3>{{ editingRule.id ? '编辑规则' : '新建规则' }}</h3>
              <button class="modal-close" @click="ruleModalVisible = false">&times;</button>
            </div>
            <div class="modal-body">
              <div class="form-grid">
                <div class="form-group full-width">
                  <label>规则名称</label>
                  <input type="text" v-model="editingRule.name" placeholder="输入规则名称" />
                </div>
                <div class="form-group full-width">
                  <label>描述</label>
                  <textarea v-model="editingRule.description" placeholder="输入规则描述" rows="2"></textarea>
                </div>
                <div class="form-group">
                  <label>规则类型</label>
                  <select v-model="editingRule.rule_type">
                    <option value="threshold">阈值</option>
                    <option value="trend">趋势</option>
                    <option value="pattern">模式</option>
                    <option value="anomaly">异常</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>指标</label>
                  <select v-model="editingRule.metric">
                    <option value="error_count">错误数</option>
                    <option value="warning_count">警告数</option>
                    <option value="error_rate">错误率</option>
                    <option value="slow_query_count">慢查询数</option>
                    <option value="connection_count">连接数</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>条件</label>
                  <select v-model="editingRule.condition">
                    <option value="gt">大于 (>)</option>
                    <option value="gte">大于等于 (>=)</option>
                    <option value="lt">小于 (<)</option>
                    <option value="lte">小于等于 (<=)</option>
                    <option value="eq">等于 (=)</option>
                    <option value="ne">不等于 (!=)</option>
                    <option value="increase_rate">增长率</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>阈值</label>
                  <input type="number" v-model.number="editingRule.threshold" placeholder="0" />
                </div>
                <div class="form-group">
                  <label>时间窗口</label>
                  <select v-model="editingRule.window">
                    <option :value="5">5 分钟</option>
                    <option :value="15">15 分钟</option>
                    <option :value="30">30 分钟</option>
                    <option :value="60">60 分钟</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>级别</label>
                  <select v-model="editingRule.level">
                    <option value="critical">Critical</option>
                    <option value="warning">Warning</option>
                    <option value="info">Info</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>冷却时间 (秒)</label>
                  <input type="number" v-model.number="editingRule.cooldown" placeholder="300" min="0" />
                </div>
                <div class="form-group full-width">
                  <label>通知渠道</label>
                  <div class="checkbox-group">
                    <label v-for="ch in notificationChannels" :key="ch.id" class="checkbox-label">
                      <input
                        type="checkbox"
                        :value="ch.id"
                        :checked="editingRule.notification_channels && editingRule.notification_channels.includes(ch.id)"
                        @change="toggleChannelSelection(ch.id)"
                      />
                      <span>{{ ch.name }}</span>
                    </label>
                    <span v-if="notificationChannels.length === 0" class="text-muted">暂无通知渠道</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button class="cancel-btn" @click="ruleModalVisible = false">取消</button>
              <button class="primary-btn" :disabled="ruleSaving" @click="saveRule">
                {{ ruleSaving ? '保存中...' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- Tab 3: 通知渠道 -->
    <div v-if="activeTab === 'channels'" class="tab-content">
      <div class="section-actions">
        <button class="primary-btn" @click="openChannelModal()">新建渠道</button>
      </div>

      <div v-if="channelsLoading" class="loading-text">加载中...</div>
      <div v-else-if="notificationChannels.length === 0" class="empty-text">暂无通知渠道</div>
      <div v-else class="channel-list">
        <div v-for="ch in notificationChannels" :key="ch.id" class="channel-card">
          <div class="channel-card-header">
            <span class="channel-name">{{ ch.name }}</span>
            <span :class="['type-badge', 'ch-type', ch.type]">
              <span class="ch-type-icon">{{ channelTypeIcon(ch.type) }}</span>
              {{ channelTypeLabel(ch.type) }}
            </span>
          </div>
          <div class="channel-status">
            <span :class="['enabled-status', ch.enabled ? 'enabled' : 'disabled']">
              {{ ch.enabled ? '已启用' : '已禁用' }}
            </span>
          </div>
          <div class="channel-card-footer">
            <button
              class="action-btn test"
              :disabled="testingChannelId === ch.id"
              @click="testChannel(ch.id)"
            >{{ testingChannelId === ch.id ? '测试中...' : '测试' }}</button>
            <div class="channel-actions">
              <button class="action-btn edit" @click="openChannelModal(ch)">编辑</button>
              <button class="action-btn delete" @click="deleteChannel(ch.id)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 渠道编辑弹窗 -->
      <transition name="fade">
        <div v-if="channelModalVisible" class="modal-overlay" @click.self="channelModalVisible = false">
          <div class="modal-content">
            <div class="modal-header">
              <h3>{{ editingChannel.id ? '编辑渠道' : '新建渠道' }}</h3>
              <button class="modal-close" @click="channelModalVisible = false">&times;</button>
            </div>
            <div class="modal-body">
              <div class="form-grid">
                <div class="form-group full-width">
                  <label>渠道名称</label>
                  <input type="text" v-model="editingChannel.name" placeholder="输入渠道名称" />
                </div>
                <div class="form-group full-width">
                  <label>类型</label>
                  <select v-model="editingChannel.type" @change="resetChannelConfig">
                    <option value="webhook">Webhook</option>
                    <option value="email">Email</option>
                    <option value="dingtalk">钉钉</option>
                    <option value="feishu">飞书</option>
                    <option value="slack">Slack</option>
                  </select>
                </div>
                <!-- webhook -->
                <template v-if="editingChannel.type === 'webhook'">
                  <div class="form-group full-width">
                    <label>Webhook URL</label>
                    <input type="text" v-model="editingChannel.config.url" placeholder="https://example.com/webhook" />
                  </div>
                </template>
                <!-- email -->
                <template v-if="editingChannel.type === 'email'">
                  <div class="form-group full-width">
                    <label>邮箱地址</label>
                    <input type="text" v-model="editingChannel.config.emails" placeholder="多个地址用逗号分隔" />
                  </div>
                </template>
                <!-- dingtalk -->
                <template v-if="editingChannel.type === 'dingtalk'">
                  <div class="form-group full-width">
                    <label>Webhook URL</label>
                    <input type="text" v-model="editingChannel.config.url" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
                  </div>
                  <div class="form-group full-width">
                    <label>Secret</label>
                    <input type="password" v-model="editingChannel.config.secret" placeholder="签名密钥" />
                  </div>
                </template>
                <!-- feishu -->
                <template v-if="editingChannel.type === 'feishu'">
                  <div class="form-group full-width">
                    <label>Webhook URL</label>
                    <input type="text" v-model="editingChannel.config.url" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
                  </div>
                  <div class="form-group full-width">
                    <label>Secret</label>
                    <input type="password" v-model="editingChannel.config.secret" placeholder="签名密钥" />
                  </div>
                </template>
                <!-- slack -->
                <template v-if="editingChannel.type === 'slack'">
                  <div class="form-group full-width">
                    <label>Webhook URL</label>
                    <input type="text" v-model="editingChannel.config.url" placeholder="https://hooks.slack.com/services/..." />
                  </div>
                </template>
              </div>
            </div>
            <div class="modal-footer">
              <button class="cancel-btn" @click="channelModalVisible = false">取消</button>
              <button class="primary-btn" :disabled="channelSaving" @click="saveChannel">
                {{ channelSaving ? '保存中...' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { api } from '../api.js'
import { useMessage } from '../composables/useMessage.js'

// ==================== 通用 ====================

const activeTab = ref('history')
const { message, showMessage } = useMessage()

const tabs = [
  { key: 'history', label: '告警历史' },
  { key: 'rules', label: '告警规则' },
  { key: 'channels', label: '通知渠道' }
]

function levelLabel(level) {
  const map = { critical: 'Critical', warning: 'Warning', info: 'Info' }
  return map[level] || level
}

function statusLabel(status) {
  const map = { firing: '触发中', acknowledged: '已确认', resolved: '已解决' }
  return map[status] || status
}

function ruleTypeLabel(type) {
  const map = { threshold: '阈值', trend: '趋势', pattern: '模式', anomaly: '异常' }
  return map[type] || type
}

function metricLabel(metric) {
  const map = {
    error_count: '错误数',
    warning_count: '警告数',
    error_rate: '错误率',
    slow_query_count: '慢查询数',
    connection_count: '连接数'
  }
  return map[metric] || metric
}

function conditionLabel(cond) {
  const map = {
    gt: '>', gte: '>=', lt: '<', lte: '<=',
    eq: '=', ne: '!=', increase_rate: '增长率'
  }
  return map[cond] || cond
}

function channelTypeLabel(type) {
  const map = { webhook: 'Webhook', email: 'Email', dingtalk: '钉钉', feishu: '飞书', slack: 'Slack' }
  return map[type] || type
}

function channelTypeIcon(type) {
  const map = { webhook: 'W', email: 'E', dingtalk: 'D', feishu: 'F', slack: 'S' }
  return map[type] || '?'
}

// ==================== Tab 1: 告警历史 ====================

const stats = reactive({ total: 0, firing: 0, acknowledged: 0, resolved: 0 })
const historyFilter = reactive({ level: 'all', status: 'all', timeRange: '24h' })
const alertHistory = ref([])
const historyLoading = ref(false)
const historyPagination = reactive({ page: 1, pageSize: 10, total: 0 })

const totalPages = computed(() => Math.max(1, Math.ceil(historyPagination.total / historyPagination.pageSize)))

async function loadAlertStats() {
  try {
    const res = await api.getAlertStats()
    const data = res.data || {}
    stats.total = data.total ?? 0
    stats.firing = data.firing ?? 0
    stats.acknowledged = data.acknowledged ?? 0
    stats.resolved = data.resolved ?? 0
  } catch (e) {
    console.error('loadAlertStats error', e)
  }
}

async function loadAlertHistory() {
  historyLoading.value = true
  try {
    const params = {
      page: historyPagination.page,
      page_size: historyPagination.pageSize
    }
    if (historyFilter.level !== 'all') params.level = historyFilter.level
    if (historyFilter.status !== 'all') params.status = historyFilter.status
    if (historyFilter.timeRange) params.time_range = historyFilter.timeRange

    const res = await api.getAlertHistory(params)
    const data = res.data || {}
    alertHistory.value = data.items || data.list || (Array.isArray(data) ? data : [])
    historyPagination.total = data.total ?? alertHistory.value.length
  } catch (e) {
    console.error('loadAlertHistory error', e)
  } finally {
    historyLoading.value = false
  }
}

async function acknowledgeAlert(id) {
  try {
    await api.acknowledgeAlert(id)
    showMessage('告警已确认')
    loadAlertHistory()
    loadAlertStats()
  } catch (e) {
    showMessage('确认失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  }
}

watch([() => historyFilter.level, () => historyFilter.status, () => historyFilter.timeRange], () => {
  historyPagination.page = 1
  loadAlertHistory()
})

watch(() => historyPagination.page, () => {
  loadAlertHistory()
})

// ==================== Tab 2: 告警规则 ====================

const alertRules = ref([])
const rulesLoading = ref(false)
const ruleModalVisible = ref(false)
const ruleSaving = ref(false)
const editingRule = reactive({
  id: null,
  name: '',
  description: '',
  rule_type: 'threshold',
  metric: 'error_count',
  condition: 'gt',
  threshold: 0,
  window: 5,
  level: 'warning',
  cooldown: 300,
  notification_channels: []
})

const notificationChannels = ref([])

function openRuleModal(rule) {
  if (rule) {
    Object.assign(editingRule, {
      id: rule.id,
      name: rule.name || '',
      description: rule.description || '',
      rule_type: rule.rule_type || 'threshold',
      metric: rule.metric || 'error_count',
      condition: rule.condition || 'gt',
      threshold: rule.threshold ?? 0,
      window: rule.window ?? 5,
      level: rule.level || 'warning',
      cooldown: rule.cooldown ?? 300,
      notification_channels: rule.notification_channels || []
    })
  } else {
    Object.assign(editingRule, {
      id: null,
      name: '',
      description: '',
      rule_type: 'threshold',
      metric: 'error_count',
      condition: 'gt',
      threshold: 0,
      window: 5,
      level: 'warning',
      cooldown: 300,
      notification_channels: []
    })
  }
  ruleModalVisible.value = true
}

function toggleChannelSelection(channelId) {
  const idx = editingRule.notification_channels.indexOf(channelId)
  if (idx >= 0) {
    editingRule.notification_channels.splice(idx, 1)
  } else {
    editingRule.notification_channels.push(channelId)
  }
}

async function loadAlertRules() {
  rulesLoading.value = true
  try {
    const res = await api.getAlertRules()
    const data = res.data || {}
    alertRules.value = data.items || data.list || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('loadAlertRules error', e)
  } finally {
    rulesLoading.value = false
  }
}

async function saveRule() {
  ruleSaving.value = true
  try {
    const payload = { ...editingRule }
    if (payload.id) {
      await api.updateAlertRule(payload.id, payload)
      showMessage('规则已更新')
    } else {
      await api.createAlertRule(payload)
      showMessage('规则已创建')
    }
    ruleModalVisible.value = false
    loadAlertRules()
  } catch (e) {
    showMessage('保存失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  } finally {
    ruleSaving.value = false
  }
}

async function deleteRule(id) {
  if (!confirm('确定要删除此规则吗？')) return
  try {
    await api.deleteAlertRule(id)
    showMessage('规则已删除')
    loadAlertRules()
  } catch (e) {
    showMessage('删除失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  }
}

async function toggleRule(id) {
  try {
    await api.toggleAlertRule(id)
    loadAlertRules()
  } catch (e) {
    showMessage('操作失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  }
}

// ==================== Tab 3: 通知渠道 ====================

const channelsLoading = ref(false)
const channelModalVisible = ref(false)
const channelSaving = ref(false)
const testingChannelId = ref(null)
const editingChannel = reactive({
  id: null,
  name: '',
  type: 'webhook',
  config: {}
})

function openChannelModal(channel) {
  if (channel) {
    Object.assign(editingChannel, {
      id: channel.id,
      name: channel.name || '',
      type: channel.type || 'webhook',
      config: { ...(channel.config || {}) }
    })
  } else {
    Object.assign(editingChannel, {
      id: null,
      name: '',
      type: 'webhook',
      config: {}
    })
  }
  channelModalVisible.value = true
}

function resetChannelConfig() {
  editingChannel.config = {}
}

async function loadNotificationChannels() {
  channelsLoading.value = true
  try {
    const res = await api.getNotificationChannels()
    const data = res.data || {}
    notificationChannels.value = data.items || data.list || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('loadNotificationChannels error', e)
  } finally {
    channelsLoading.value = false
  }
}

async function saveChannel() {
  channelSaving.value = true
  try {
    const payload = { ...editingChannel }
    if (payload.id) {
      await api.updateNotificationChannel(payload.id, payload)
      showMessage('渠道已更新')
    } else {
      await api.createNotificationChannel(payload)
      showMessage('渠道已创建')
    }
    channelModalVisible.value = false
    loadNotificationChannels()
  } catch (e) {
    showMessage('保存失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  } finally {
    channelSaving.value = false
  }
}

async function deleteChannel(id) {
  if (!confirm('确定要删除此渠道吗？')) return
  try {
    await api.deleteNotificationChannel(id)
    showMessage('渠道已删除')
    loadNotificationChannels()
  } catch (e) {
    showMessage('删除失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  }
}

async function testChannel(id) {
  testingChannelId.value = id
  try {
    const res = await api.testNotificationChannel(id)
    const ok = res.data?.success ?? res.data?.ok
    if (ok) {
      showMessage('测试通知发送成功')
    } else {
      showMessage('测试失败：' + (res.data?.error || res.data?.message || '未知错误'), 'error')
    }
  } catch (e) {
    showMessage('测试失败：' + (e.response?.data?.detail || e.message || '未知错误'), 'error')
  } finally {
    testingChannelId.value = null
  }
}

// ==================== 初始化 ====================

watch(activeTab, (tab) => {
  if (tab === 'history') {
    loadAlertHistory()
    loadAlertStats()
  } else if (tab === 'rules') {
    loadAlertRules()
    loadNotificationChannels()
  } else if (tab === 'channels') {
    loadNotificationChannels()
  }
})

onMounted(() => {
  loadAlertHistory()
  loadAlertStats()
})
</script>

<style scoped>
.alert-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 提示消息 */
.message-bar {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  z-index: 1000;
  white-space: nowrap;
}

.message-bar.success {
  background: rgba(16, 185, 129, 0.15);
  color: var(--accent-green);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.message-bar.error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-red);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 标签页 */
.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 0;
}

.tab-btn {
  padding: 10px 20px;
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
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计概览 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-item {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.stat-item.firing .stat-num {
  color: var(--accent-red);
}

.stat-item.acknowledged .stat-num {
  color: var(--accent-blue);
}

.stat-item.resolved .stat-num {
  color: var(--accent-green);
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-select {
  padding: 6px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  cursor: pointer;
  font-family: inherit;
}

.filter-select:focus {
  border-color: var(--accent-blue);
}

/* 告警列表 */
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.alert-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.alert-rule-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  flex: 1;
}

.alert-message {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.alert-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.alert-time {
  font-size: 12px;
  color: var(--text-muted);
}

/* 级别徽章 */
.level-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.level-badge.critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.level-badge.warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.level-badge.info {
  background: rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}

/* 状态徽章 */
.status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.status-badge.firing {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

.status-badge.acknowledged {
  background: rgba(59, 130, 246, 0.2);
  color: var(--accent-blue);
}

.status-badge.resolved {
  background: rgba(16, 185, 129, 0.2);
  color: var(--accent-green);
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-red);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.3); }
}

/* 确认按钮 */
.ack-btn {
  padding: 4px 14px;
  background: transparent;
  border: 1px solid var(--accent-blue);
  color: var(--accent-blue);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.ack-btn:hover {
  background: var(--accent-blue);
  color: #fff;
}

/* 分页 */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.page-btn {
  padding: 6px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 13px;
  color: var(--text-muted);
}

/* 区域操作按钮 */
.section-actions {
  display: flex;
  justify-content: flex-end;
}

.primary-btn {
  padding: 8px 20px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.primary-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 规则列表 */
.rule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rule-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rule-card-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rule-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rule-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.rule-desc {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 类型徽章 */
.type-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.type-badge.threshold {
  background: rgba(139, 92, 246, 0.2);
  color: var(--accent-purple);
}

.type-badge.trend {
  background: rgba(59, 130, 246, 0.2);
  color: var(--accent-blue);
}

.type-badge.pattern {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.type-badge.anomaly {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-red);
}

/* 规则详情 */
.rule-detail {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.rule-detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.detail-label {
  color: var(--text-muted);
}

.detail-value {
  color: var(--text-primary);
  font-weight: 500;
}

/* 规则卡片底部 */
.rule-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 开关 */
.toggle-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.toggle-switch input[type="checkbox"] {
  display: none;
}

.toggle-slider {
  width: 36px;
  height: 20px;
  background: var(--border-color);
  border-radius: 10px;
  position: relative;
  transition: background 0.2s;
}

.toggle-slider::after {
  content: '';
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
}

.toggle-switch input:checked + .toggle-slider {
  background: var(--accent-blue);
}

.toggle-switch input:checked + .toggle-slider::after {
  transform: translateX(16px);
}

.toggle-text {
  font-size: 12px;
  color: var(--text-muted);
}

/* 操作按钮 */
.rule-actions,
.channel-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.action-btn.edit:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.action-btn.delete:hover {
  border-color: var(--accent-red);
  color: var(--accent-red);
}

.action-btn.test {
  border-color: var(--accent-green);
  color: var(--accent-green);
}

.action-btn.test:hover {
  background: var(--accent-green);
  color: #fff;
}

.action-btn.test:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 渠道列表 */
.channel-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.channel-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.channel-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.channel-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.ch-type {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.ch-type-icon {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.1);
}

.type-badge.ch-type.webhook {
  background: rgba(139, 92, 246, 0.2);
  color: var(--accent-purple);
}

.type-badge.ch-type.email {
  background: rgba(59, 130, 246, 0.2);
  color: var(--accent-blue);
}

.type-badge.ch-type.dingtalk {
  background: rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}

.type-badge.ch-type.feishu {
  background: rgba(245, 158, 11, 0.2);
  color: var(--accent-yellow);
}

.type-badge.ch-type.slack {
  background: rgba(16, 185, 129, 0.2);
  color: var(--accent-green);
}

.channel-status {
  display: flex;
  align-items: center;
}

.enabled-status {
  font-size: 12px;
  font-weight: 500;
}

.enabled-status.enabled {
  color: var(--accent-green);
}

.enabled-status.disabled {
  color: var(--text-muted);
}

.channel-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.modal-content {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  width: 560px;
  max-width: 90vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}

.modal-close:hover {
  color: var(--text-primary);
}

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

.cancel-btn {
  padding: 8px 20px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.cancel-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 表单 */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.form-group input,
.form-group select,
.form-group textarea {
  padding: 8px 12px;
  background: var(--bg-primary, var(--bg-card));
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  font-family: inherit;
  transition: border-color 0.2s;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  border-color: var(--accent-blue);
}

.form-group input::placeholder,
.form-group textarea::placeholder {
  color: var(--text-muted);
}

.form-group select {
  cursor: pointer;
  appearance: auto;
}

.form-group textarea {
  resize: vertical;
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 15px;
  height: 15px;
  accent-color: var(--accent-blue);
  cursor: pointer;
}

.text-muted {
  font-size: 12px;
  color: var(--text-muted);
}

/* 加载/空状态 */
.loading-text,
.empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 30px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .stat-item {
    padding: 12px;
  }

  .stat-num {
    font-size: 22px;
  }

  .filter-bar {
    flex-direction: column;
  }

  .filter-select {
    width: 100%;
  }

  .tabs {
    overflow-x: auto;
  }

  .tab-btn {
    padding: 8px 14px;
    font-size: 13px;
    white-space: nowrap;
  }

  .alert-card-header {
    flex-wrap: wrap;
  }

  .rule-detail {
    flex-direction: column;
    gap: 6px;
  }

  .rule-card-footer {
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }

  .channel-card-footer {
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }

  .modal-content {
    max-width: 95vw;
    max-height: 90vh;
  }

  .form-grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .form-group.full-width {
    grid-column: 1;
  }

  .message-bar {
    font-size: 13px;
    padding: 8px 16px;
    max-width: 90vw;
    white-space: normal;
    text-align: center;
  }

  .section-actions {
    justify-content: stretch;
  }

  .primary-btn {
    width: 100%;
  }
}
</style>
