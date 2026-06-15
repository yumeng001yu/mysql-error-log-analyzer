import { createRouter, createWebHistory } from 'vue-router'
import Home from './components/Home.vue'
import Dashboard from './components/Dashboard.vue'
import LogQuery from './components/LogQuery.vue'
import AnalysisReport from './components/AnalysisReport.vue'
import KnowledgeGraph from './components/KnowledgeGraph.vue'
import ChatPanel from './components/ChatPanel.vue'
import StatusPanel from './components/StatusPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import SlowQuery from './components/SlowQuery.vue'
import MonitorPanel from './components/MonitorPanel.vue'
import ReplicationPanel from './components/ReplicationPanel.vue'
import AlertPanel from './components/AlertPanel.vue'
import LogSearch from './components/LogSearch.vue'
import PatternPanel from './components/PatternPanel.vue'
import DeadlockPanel from './components/DeadlockPanel.vue'
import BaselinePanel from './components/BaselinePanel.vue'
import InstancesPanel from './components/InstancesPanel.vue'
import ReportPanel from './components/ReportPanel.vue'
import RedisMonitor from './components/RedisMonitor.vue'
import RedisSlowlog from './components/RedisSlowlog.vue'
import RedisMemory from './components/RedisMemory.vue'
import RedisKeys from './components/RedisKeys.vue'
import RedisPersistence from './components/RedisPersistence.vue'
import RedisCluster from './components/RedisCluster.vue'

const routes = [
  { path: '/', name: 'home', component: Home, meta: { title: '数据库选择' } },
  // MySQL 子路由
  { path: '/mysql', name: 'mysql-dashboard', component: Dashboard, meta: { title: 'MySQL 仪表盘', db: 'mysql' } },
  { path: '/mysql/logs', name: 'mysql-logs', component: LogQuery, meta: { title: 'MySQL 日志查询', db: 'mysql' } },
  { path: '/mysql/analysis', name: 'mysql-analysis', component: AnalysisReport, meta: { title: 'MySQL 分析报告', db: 'mysql' } },
  { path: '/mysql/graph', name: 'mysql-graph', component: KnowledgeGraph, meta: { title: 'MySQL 知识图谱', db: 'mysql' } },
  { path: '/mysql/chat', name: 'mysql-chat', component: ChatPanel, meta: { title: 'MySQL 对话', db: 'mysql' } },
  { path: '/mysql/status', name: 'mysql-status', component: StatusPanel, meta: { title: '系统状态', db: 'mysql' } },
  { path: '/mysql/settings', name: 'mysql-settings', component: SettingsPanel, meta: { title: '设置', db: 'mysql' } },
  { path: '/mysql/slow-query', name: 'mysql-slow-query', component: SlowQuery, meta: { title: '慢查询分析', db: 'mysql' } },
  { path: '/mysql/monitor', name: 'mysql-monitor', component: MonitorPanel, meta: { title: '实时监控', db: 'mysql' } },
  { path: '/mysql/replication', name: 'mysql-replication', component: ReplicationPanel, meta: { title: '复制状态', db: 'mysql' } },
  { path: '/mysql/alerts', name: 'mysql-alerts', component: AlertPanel, meta: { title: '智能告警', db: 'mysql' } },
  { path: '/mysql/search', name: 'mysql-search', component: LogSearch, meta: { title: '日志搜索', db: 'mysql' } },
  { path: '/mysql/patterns', name: 'mysql-patterns', component: PatternPanel, meta: { title: '模式识别', db: 'mysql' } },
  { path: '/mysql/deadlock', name: 'mysql-deadlock', component: DeadlockPanel, meta: { title: '死锁分析', db: 'mysql' } },
  { path: '/mysql/baseline', name: 'mysql-baseline', component: BaselinePanel, meta: { title: '性能基线', db: 'mysql' } },
  { path: '/mysql/instances', name: 'mysql-instances', component: InstancesPanel, meta: { title: '实例管理', db: 'mysql' } },
  { path: '/mysql/reports', name: 'mysql-reports', component: ReportPanel, meta: { title: '运维报表', db: 'mysql' } },
  // Redis 子路由
  { path: '/redis', name: 'redis-monitor', component: RedisMonitor, meta: { title: 'Redis 实时监控', db: 'redis' } },
  { path: '/redis/slowlog', name: 'redis-slowlog', component: RedisSlowlog, meta: { title: 'Redis 慢查询', db: 'redis' } },
  { path: '/redis/memory', name: 'redis-memory', component: RedisMemory, meta: { title: 'Redis 内存分析', db: 'redis' } },
  { path: '/redis/keys', name: 'redis-keys', component: RedisKeys, meta: { title: 'Redis Key 分析', db: 'redis' } },
  { path: '/redis/persistence', name: 'redis-persistence', component: RedisPersistence, meta: { title: 'Redis 持久化', db: 'redis' } },
  { path: '/redis/cluster', name: 'redis-cluster', component: RedisCluster, meta: { title: 'Redis 集群/哨兵', db: 'redis' } },
  { path: '/redis/replication', name: 'redis-replication', component: ReplicationPanel, meta: { title: 'Redis 复制状态', db: 'redis' } },
  { path: '/redis/alerts', name: 'redis-alerts', component: AlertPanel, meta: { title: 'Redis 智能告警', db: 'redis' } },
  { path: '/redis/instances', name: 'redis-instances', component: InstancesPanel, meta: { title: 'Redis 实例管理', db: 'redis' } },
  { path: '/redis/settings', name: 'redis-settings', component: SettingsPanel, meta: { title: 'Redis 设置', db: 'redis' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
