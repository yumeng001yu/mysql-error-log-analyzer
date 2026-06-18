import { createRouter, createWebHistory } from 'vue-router'
import Home from './components/Home.vue'

// 数据库开关管理：控制是否启用对应数据库的运维模块
// 禁用的数据库组件不会被加载（懒加载），避免占用内存
export const dbToggle = {
  _listeners: [],

  // 获取开关状态（默认都启用）
  isEnabled(db) {
    try {
      const val = localStorage.getItem(`db_enabled_${db}`)
      return val === null ? true : val === 'true'
    } catch (_) {
      return true
    }
  },

  // 设置开关状态
  setEnabled(db, enabled) {
    try {
      localStorage.setItem(`db_enabled_${db}`, String(enabled))
    } catch (_) { /* ignore */ }
    this._listeners.forEach(fn => {
      try { fn(db, enabled) } catch (_) { /* ignore */ }
    })
  },

  // 监听开关变化
  onChange(fn) {
    this._listeners.push(fn)
  },

  offChange(fn) {
    this._listeners = this._listeners.filter(l => l !== fn)
  }
}

const routes = [
  { path: '/', name: 'home', component: Home, meta: { title: '数据库选择' } },
  // MySQL 子路由（懒加载，禁用时不加载）
  { path: '/mysql', name: 'mysql-dashboard', component: () => import('./components/Dashboard.vue'), meta: { title: 'MySQL 仪表盘', db: 'mysql' } },
  { path: '/mysql/logs', name: 'mysql-logs', component: () => import('./components/LogQuery.vue'), meta: { title: 'MySQL 日志查询', db: 'mysql' } },
  { path: '/mysql/analysis', name: 'mysql-analysis', component: () => import('./components/AnalysisReport.vue'), meta: { title: 'MySQL 分析报告', db: 'mysql' } },
  { path: '/mysql/graph', name: 'mysql-graph', component: () => import('./components/KnowledgeGraph.vue'), meta: { title: 'MySQL 知识图谱', db: 'mysql' } },
  { path: '/mysql/chat', name: 'mysql-chat', component: () => import('./components/ChatPanel.vue'), props: route => ({ dbType: 'mysql' }), meta: { title: 'MySQL 对话', db: 'mysql' } },
  { path: '/mysql/status', name: 'mysql-status', component: () => import('./components/StatusPanel.vue'), meta: { title: '系统状态', db: 'mysql' } },
  { path: '/mysql/settings', name: 'mysql-settings', component: () => import('./components/SettingsPanel.vue'), meta: { title: '设置', db: 'mysql' } },
  { path: '/mysql/slow-query', name: 'mysql-slow-query', component: () => import('./components/SlowQuery.vue'), meta: { title: '慢查询分析', db: 'mysql' } },
  { path: '/mysql/monitor', name: 'mysql-monitor', component: () => import('./components/MonitorPanel.vue'), meta: { title: '实时监控', db: 'mysql' } },
  { path: '/mysql/replication', name: 'mysql-replication', component: () => import('./components/ReplicationPanel.vue'), meta: { title: '复制状态', db: 'mysql' } },
  { path: '/mysql/alerts', name: 'mysql-alerts', component: () => import('./components/AlertPanel.vue'), meta: { title: '智能告警', db: 'mysql' } },
  { path: '/mysql/search', name: 'mysql-search', component: () => import('./components/LogSearch.vue'), meta: { title: '日志搜索', db: 'mysql' } },
  { path: '/mysql/patterns', name: 'mysql-patterns', component: () => import('./components/PatternPanel.vue'), meta: { title: '模式识别', db: 'mysql' } },
  { path: '/mysql/deadlock', name: 'mysql-deadlock', component: () => import('./components/DeadlockPanel.vue'), meta: { title: '死锁分析', db: 'mysql' } },
  { path: '/mysql/baseline', name: 'mysql-baseline', component: () => import('./components/BaselinePanel.vue'), meta: { title: '性能基线', db: 'mysql' } },
  { path: '/mysql/instances', name: 'mysql-instances', component: () => import('./components/InstancesPanel.vue'), meta: { title: '实例管理', db: 'mysql' } },
  { path: '/mysql/reports', name: 'mysql-reports', component: () => import('./components/ReportPanel.vue'), meta: { title: '运维报表', db: 'mysql' } },
  // Redis 子路由（懒加载）
  { path: '/redis', name: 'redis-monitor', component: () => import('./components/RedisMonitor.vue'), meta: { title: 'Redis 实时监控', db: 'redis' } },
  { path: '/redis/slowlog', name: 'redis-slowlog', component: () => import('./components/RedisSlowlog.vue'), meta: { title: 'Redis 慢查询', db: 'redis' } },
  { path: '/redis/memory', name: 'redis-memory', component: () => import('./components/RedisMemory.vue'), meta: { title: 'Redis 内存分析', db: 'redis' } },
  { path: '/redis/keys', name: 'redis-keys', component: () => import('./components/RedisKeys.vue'), meta: { title: 'Redis Key 分析', db: 'redis' } },
  { path: '/redis/persistence', name: 'redis-persistence', component: () => import('./components/RedisPersistence.vue'), meta: { title: 'Redis 持久化', db: 'redis' } },
  { path: '/redis/cluster', name: 'redis-cluster', component: () => import('./components/RedisCluster.vue'), meta: { title: 'Redis 集群/哨兵', db: 'redis' } },
  { path: '/redis/graph', name: 'redis-graph', component: () => import('./components/RedisKnowledgeGraph.vue'), meta: { title: 'Redis 知识图谱', db: 'redis' } },
  { path: '/redis/chat', name: 'redis-chat', component: () => import('./components/ChatPanel.vue'), props: route => ({ dbType: 'redis' }), meta: { title: 'Redis 对话', db: 'redis' } },
  { path: '/redis/replication', name: 'redis-replication', component: () => import('./components/ReplicationPanel.vue'), meta: { title: 'Redis 复制状态', db: 'redis' } },
  { path: '/redis/alerts', name: 'redis-alerts', component: () => import('./components/AlertPanel.vue'), meta: { title: 'Redis 智能告警', db: 'redis' } },
  { path: '/redis/instances', name: 'redis-instances', component: () => import('./components/InstancesPanel.vue'), meta: { title: 'Redis 实例管理', db: 'redis' } },
  { path: '/redis/settings', name: 'redis-settings', component: () => import('./components/SettingsPanel.vue'), meta: { title: 'Redis 设置', db: 'redis' } },
  { path: '/redis/reports', name: 'redis-reports', component: () => import('./components/RedisReports.vue'), meta: { title: 'Redis 运维报表', db: 'redis' } },
  { path: '/redis/baseline', name: 'redis-baseline', component: () => import('./components/RedisBaseline.vue'), meta: { title: 'Redis 性能基线', db: 'redis' } },
  // 通用运维功能路由（懒加载）
  { path: '/diagnosis', name: 'diagnosis', component: () => import('./components/DiagnosisPanel.vue'), meta: { title: '一键诊断', db: 'all' } },
  { path: '/capacity', name: 'capacity', component: () => import('./components/CapacityPanel.vue'), meta: { title: '容量规划', db: 'all' } },
  { path: '/inspection', name: 'inspection', component: () => import('./components/InspectionPanel.vue'), meta: { title: '定时巡检', db: 'all' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：禁用的数据库路由不可访问
router.beforeEach((to, from, next) => {
  const db = to.meta?.db
  if (db && db !== 'all' && !dbToggle.isEnabled(db)) {
    // 数据库已禁用，重定向到首页
    next({ path: '/' })
  } else {
    next()
  }
})

export default router
