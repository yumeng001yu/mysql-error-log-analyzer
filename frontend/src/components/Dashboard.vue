<template>
  <div class="dashboard">
    <!-- 时间段选择 -->
    <div class="period-selector">
      <button
        v-for="p in periods"
        :key="p.value"
        :class="['period-btn', { active: period === p.value }]"
        @click="changePeriod(p.value)"
      >{{ p.label }}</button>
      <div class="custom-period">
        <input type="number" v-model.number="customValue" min="1" max="365" placeholder="自定义" class="custom-input" />
        <select v-model="customUnit" class="custom-select">
          <option value="h">小时</option>
          <option value="d">天</option>
        </select>
        <button class="period-btn" @click="applyCustomPeriod" :disabled="!customValue || customValue < 1">应用</button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-red)">⚠️</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_errors || 0 }}</div>
          <div class="stat-label">总错误数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-yellow)">📅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.today_errors || 0 }}</div>
          <div class="stat-label">今日错误</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-red)">🚨</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.critical_alerts || 0 }}</div>
          <div class="stat-label">关键告警</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent-green)">🖥️</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.instance_count || 0 }}</div>
          <div class="stat-label">监控实例</div>
        </div>
      </div>
    </div>

    <!-- 分布信息 -->
    <div class="charts-row">
      <div class="chart-card">
        <h3>错误级别分布</h3>
        <div class="text-list" v-if="levelList.length > 0">
          <div v-for="item in levelList" :key="item.level" class="text-list-row">
            <span class="level-dot" :class="item.level.toLowerCase()">●</span>
            <span class="text-list-label">{{ item.level }}</span>
            <span class="text-list-value">{{ item.count }}</span>
          </div>
        </div>
        <div v-else class="empty-text">暂无数据</div>
      </div>
      <div class="chart-card">
        <h3>错误类别分布</h3>
        <div class="text-list" v-if="categoryList.length > 0">
          <div v-for="item in categoryList" :key="item.category" class="text-list-row">
            <span class="text-list-label">{{ item.category }}</span>
            <span class="text-list-value">{{ item.count }}</span>
          </div>
        </div>
        <div v-else class="empty-text">暂无数据</div>
      </div>
    </div>

    <!-- 最近告警 -->
    <div class="chart-card full-width">
      <h3>最近告警</h3>
      <div class="alert-list" v-if="alerts.length > 0">
        <div v-for="alert in alerts.slice(0, 10)" :key="alert.id" class="alert-row">
          <span class="alert-level-dot" :class="alert.alert_type || alert.level">●</span>
          <span class="alert-instance">实例 #{{ alert.instance_id || '' }}</span>
          <span class="alert-message">{{ alert.llm_suggestion || alert.message || alert.alert_type || alert.content }}</span>
          <span class="alert-time">{{ formatTime(alert.created_at || alert.time) }}</span>
        </div>
      </div>
      <div v-else class="empty-text">暂无告警</div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

export default {
  name: 'Dashboard',
  setup() {
    const period = ref('7d')
    const customValue = ref(null)
    const customUnit = ref('h')
    const stats = ref({})
    const alerts = ref([])
    const levelList = ref([])
    const categoryList = ref([])

    const periods = [
      { label: '全部', value: 'all' },
      { label: '7天', value: '7d' },
      { label: '24小时', value: '24h' },
      { label: '1小时', value: '1h' }
    ]

    function formatTime(t) {
      if (!t) return ''
      const d = new Date(t)
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    }

    function getPeriodParam() {
      return period.value === 'all' ? '' : period.value
    }

    async function loadStats() {
      try {
        const res = await api.getLogStats({ period: getPeriodParam() })
        const data = res.data || {}
        stats.value = data

        // 从 stats 中提取级别分布
        const levels = data.levels || []
        if (Array.isArray(levels) && levels.length > 0) {
          levelList.value = levels.map(l => ({
            level: l.level || l.name,
            count: l.count || l.value || 0
          }))
        }
      } catch (e) { console.error('loadStats error', e) }
    }

    async function loadDistribution() {
      try {
        const res = await api.getLogDistribution({ period: getPeriodParam() })
        const data = res.data || {}

        // 级别分布
        const levels = data.by_level || data.levels || []
        if (Array.isArray(levels) && levels.length > 0) {
          levelList.value = levels.map(l => ({
            level: l.level || l.name,
            count: l.count || l.value || 0
          }))
        } else if (typeof levels === 'object') {
          levelList.value = Object.entries(levels).map(([name, value]) => ({
            level: name,
            count: value
          }))
        }

        // 类别分布
        const categories = data.by_category || data.categories || []
        if (Array.isArray(categories) && categories.length > 0) {
          const catData = categories.map(c => ({
            category: c.category || c.name,
            count: c.count || c.value || 0
          }))
          catData.sort((a, b) => b.count - a.count)
          categoryList.value = catData.slice(0, 15)
        } else if (typeof categories === 'object') {
          const catData = Object.entries(categories).map(([name, value]) => ({
            category: name,
            count: value
          }))
          catData.sort((a, b) => b.count - a.count)
          categoryList.value = catData.slice(0, 15)
        }
      } catch (e) { console.error('loadDistribution error', e) }
    }

    async function loadAlerts() {
      try {
        const res = await api.getAlerts({ limit: 10 })
        const data = res.data || {}
        alerts.value = data.items || data.alerts || data || []
      } catch (e) { console.error('loadAlerts error', e) }
    }

    function changePeriod(p) {
      period.value = p
      loadStats()
      loadDistribution()
    }

    function applyCustomPeriod() {
      if (customValue.value && customValue.value > 0) {
        period.value = `${customValue.value}${customUnit.value}`
        loadStats()
        loadDistribution()
      }
    }

    onMounted(() => {
      loadStats()
      loadDistribution()
      loadAlerts()
    })

    return {
      period, customValue, customUnit, stats, alerts,
      periods, levelList, categoryList,
      formatTime, changePeriod, applyCustomPeriod
    }
  }
}
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.period-selector {
  display: flex;
  gap: 8px;
  align-items: center;
}

.custom-period {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  padding-left: 12px;
  border-left: 1px solid var(--border-color);
}

.custom-input {
  width: 60px;
  padding: 6px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  text-align: center;
}

.custom-input:focus {
  border-color: var(--accent-blue);
}

.custom-select {
  padding: 6px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.period-btn {
  padding: 6px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.period-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.period-btn.active {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  font-size: 28px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 2px;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.chart-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.chart-card h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-secondary);
}

.chart-card.full-width {
  width: 100%;
}

.text-list {
  display: flex;
  flex-direction: column;
}

.text-list-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
}

.text-list-row:last-child {
  border-bottom: none;
}

.level-dot {
  font-size: 10px;
}

.level-dot.error { color: var(--accent-red); }
.level-dot.warning { color: var(--accent-yellow); }
.level-dot.info { color: var(--accent-cyan); }
.level-dot.critical { color: var(--accent-red); }

.text-list-label {
  flex: 1;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.text-list-value {
  color: var(--accent-blue);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  min-width: 40px;
  text-align: right;
}

.alert-list {
  display: flex;
  flex-direction: column;
}

.alert-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
}

.alert-row:last-child {
  border-bottom: none;
}

.alert-level-dot {
  font-size: 10px;
}

.alert-level-dot.error { color: var(--accent-red); }
.alert-level-dot.warning { color: var(--accent-yellow); }
.alert-level-dot.info { color: var(--accent-cyan); }
.alert-level-dot.critical { color: var(--accent-red); }

.alert-instance {
  color: var(--accent-cyan);
  min-width: 80px;
}

.alert-message {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alert-time {
  color: var(--text-muted);
  white-space: nowrap;
  font-size: 12px;
}

.empty-text {
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

@media (max-width: 900px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .period-selector {
    flex-wrap: wrap;
    gap: 6px;
  }

  .period-btn {
    padding: 5px 10px;
    font-size: 12px;
  }

  .custom-period {
    margin-left: 0;
    padding-left: 0;
    border-left: none;
    width: 100%;
    margin-top: 4px;
  }

  .custom-input {
    width: 50px;
    font-size: 12px;
    padding: 4px 6px;
  }

  .custom-select {
    font-size: 12px;
    padding: 4px 6px;
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
    font-size: 22px;
  }

  .stat-value {
    font-size: 22px;
  }

  .stat-label {
    font-size: 11px;
  }

  .charts-row {
    grid-template-columns: 1fr;
  }

  .chart-card {
    padding: 12px;
  }

  .chart-card h3 {
    font-size: 13px;
    margin-bottom: 8px;
  }

  .text-list-row {
    gap: 6px;
    padding: 6px 0;
    font-size: 12px;
  }

  .alert-row {
    gap: 6px;
    padding: 6px 0;
    font-size: 12px;
  }

  .alert-instance {
    min-width: 60px;
    font-size: 11px;
  }

  .alert-message {
    font-size: 12px;
  }
}
</style>
