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

    <div class="semantic-search-bar" v-if="semanticEnabled">
      <input type="text" v-model="semanticQuery" placeholder="语义搜索日志..." class="semantic-input" @keydown.enter="doSemanticSearch" />
      <button class="btn-semantic" @click="doSemanticSearch" :disabled="!semanticQuery">🔍</button>
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

    <!-- 图表区域 -->
    <div class="charts-row">
      <div class="chart-card">
        <h3>错误级别分布</h3>
        <div ref="levelPieRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>错误类别分布</h3>
        <div ref="categoryBarRef" class="chart-container"></div>
      </div>
    </div>

    <div class="chart-card full-width">
      <h3>错误趋势</h3>
      <div class="trend-controls">
        <button
          v-for="g in trendGroups"
          :key="g.value"
          :class="['period-btn', { active: trendGroup === g.value }]"
          @click="trendGroup = g.value; loadTrend()"
        >{{ g.label }}</button>
      </div>
      <div ref="trendLineRef" class="chart-container" style="height: 280px;"></div>
    </div>

    <!-- 最近告警 -->
    <div class="chart-card full-width">
      <h3>最近告警</h3>
      <div class="alert-list" v-if="alerts.length > 0">
        <div v-for="alert in alerts.slice(0, 10)" :key="alert.id" class="alert-row">
          <span class="alert-level-dot" :class="alert.level">●</span>
          <span class="alert-instance">{{ alert.instance || '' }}</span>
          <span class="alert-message">{{ alert.message || alert.content }}</span>
          <span class="alert-time">{{ formatTime(alert.created_at || alert.time) }}</span>
        </div>
      </div>
      <div v-else class="empty-text">暂无告警</div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api.js'

export default {
  name: 'Dashboard',
  setup() {
    const period = ref('7d')
    const customValue = ref(null)
    const customUnit = ref('h')
    const trendGroup = ref('hour')
    const stats = ref({})
    const alerts = ref([])

    const levelPieRef = ref(null)
    const categoryBarRef = ref(null)
    const trendLineRef = ref(null)
    let levelPieChart = null
    let categoryBarChart = null
    let trendLineChart = null

    const periods = [
      { label: '全部', value: 'all' },
      { label: '7天', value: '7d' },
      { label: '24小时', value: '24h' },
      { label: '1小时', value: '1h' }
    ]

    const trendGroups = [
      { label: '按小时', value: 'hour' },
      { label: '按天', value: 'day' }
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
        stats.value = res.data || {}
      } catch (e) { /* ignore */ }
    }

    async function loadDistribution() {
      try {
        const res = await api.getLogDistribution({ period: getPeriodParam() })
        const data = res.data || {}

        // 级别饼图
        const levels = data.levels || data.by_level || []
        if (levelPieChart) {
          levelPieChart.setOption({
            tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
            color: ['#ef4444', '#f59e0b', '#06b6d4', '#64748b'],
            series: [{
              type: 'pie',
              radius: ['40%', '70%'],
              center: ['50%', '55%'],
              label: { color: '#94a3b8', fontSize: 12 },
              data: Array.isArray(levels)
                ? levels.map(l => ({ name: l.level || l.name, value: l.count || l.value }))
                : Object.entries(levels).map(([name, value]) => ({ name, value }))
            }]
          })
        }

        // 类别柱状图
        const categories = data.categories || data.by_category || []
        if (categoryBarChart) {
          const catData = Array.isArray(categories) ? categories : Object.entries(categories).map(([name, value]) => ({ name, value }))
          catData.sort((a, b) => (b.count || b.value) - (a.count || a.value))
          const top10 = catData.slice(0, 10)
          categoryBarChart.setOption({
            tooltip: { trigger: 'axis' },
            grid: { left: 100, right: 20, top: 10, bottom: 30 },
            xAxis: { type: 'value', axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: '#1e293b' } } },
            yAxis: {
              type: 'category',
              data: top10.map(c => c.name || c.category).reverse(),
              axisLabel: { color: '#94a3b8', fontSize: 12 }
            },
            series: [{
              type: 'bar',
              data: top10.map(c => c.count || c.value).reverse(),
              itemStyle: { color: '#3b82f6', borderRadius: [0, 4, 4, 0] }
            }]
          })
        }
      } catch (e) { /* ignore */ }
    }

    async function loadTrend() {
      try {
        const res = await api.getLogTrend({ period: getPeriodParam(), group_by: trendGroup.value })
        const data = res.data || []
        const items = Array.isArray(data) ? data : (data.trend || [])

        if (trendLineChart) {
          trendLineChart.setOption({
            tooltip: { trigger: 'axis' },
            grid: { left: 50, right: 20, top: 20, bottom: 30 },
            xAxis: {
              type: 'category',
              data: items.map(i => i.time || i.date || i.hour),
              axisLabel: { color: '#64748b', fontSize: 11 },
              boundaryGap: false
            },
            yAxis: {
              type: 'value',
              axisLabel: { color: '#64748b' },
              splitLine: { lineStyle: { color: '#1e293b' } }
            },
            series: [{
              type: 'line',
              data: items.map(i => i.count || i.value),
              smooth: true,
              areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(59,130,246,0.3)' },
                { offset: 1, color: 'rgba(59,130,246,0.02)' }
              ])},
              lineStyle: { color: '#3b82f6', width: 2 },
              itemStyle: { color: '#3b82f6' }
            }]
          })
        }
      } catch (e) { /* ignore */ }
    }

    async function loadAlerts() {
      try {
        const res = await api.getAlerts({ limit: 10 })
        alerts.value = res.data?.alerts || res.data || []
      } catch (e) { /* ignore */ }
    }

    const semanticEnabled = ref(true)
    const semanticQuery = ref('')

    async function doSemanticSearch() {
      if (!semanticQuery.value) return
      try {
        const res = await api.semanticSearch({ query: semanticQuery.value, k: 10 })
        const data = res.data || {}
        if (data.message && !data.items?.length) {
          semanticEnabled.value = false
        }
      } catch (e) {
        semanticEnabled.value = false
      }
    }

    function changePeriod(p) {
      period.value = p
      loadStats()
      loadDistribution()
      loadTrend()
    }

    function applyCustomPeriod() {
      if (customValue.value && customValue.value > 0) {
        period.value = `${customValue.value}${customUnit.value}`
        loadStats()
        loadDistribution()
        loadTrend()
      }
    }

    function handleResize() {
      levelPieChart?.resize()
      categoryBarChart?.resize()
      trendLineChart?.resize()
    }

    onMounted(async () => {
      await nextTick()
      levelPieChart = echarts.init(levelPieRef.value, 'dark')
      categoryBarChart = echarts.init(categoryBarRef.value, 'dark')
      trendLineChart = echarts.init(trendLineRef.value, 'dark')

      // 设置暗色背景透明
      const darkBg = { backgroundColor: 'transparent' }
      levelPieChart.setOption(darkBg)
      categoryBarChart.setOption(darkBg)
      trendLineChart.setOption(darkBg)

      loadStats()
      loadDistribution()
      loadTrend()
      loadAlerts()

      window.addEventListener('resize', handleResize)
    })

    onUnmounted(() => {
      window.removeEventListener('resize', handleResize)
      levelPieChart?.dispose()
      categoryBarChart?.dispose()
      trendLineChart?.dispose()
    })

    return {
      period, customValue, customUnit, trendGroup, stats, alerts,
      periods, trendGroups,
      levelPieRef, categoryBarRef, trendLineRef,
      semanticEnabled, semanticQuery, doSemanticSearch,
      formatTime, changePeriod, applyCustomPeriod, loadTrend
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

.semantic-search-bar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.semantic-input {
  flex: 1;
  max-width: 300px;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.semantic-input:focus {
  border-color: var(--accent-purple, #8b5cf6);
}

.btn-semantic {
  padding: 6px 12px;
  background: var(--accent-purple, #8b5cf6);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-semantic:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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

.chart-container {
  height: 240px;
  width: 100%;
}

.trend-controls {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
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
</style>
