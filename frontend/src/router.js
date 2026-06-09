import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './components/Dashboard.vue'
import LogQuery from './components/LogQuery.vue'
import AnalysisReport from './components/AnalysisReport.vue'
import KnowledgeGraph from './components/KnowledgeGraph.vue'
import ChatPanel from './components/ChatPanel.vue'
import StatusPanel from './components/StatusPanel.vue'

const routes = [
  { path: '/', name: 'dashboard', component: Dashboard, meta: { title: '仪表盘' } },
  { path: '/logs', name: 'logs', component: LogQuery, meta: { title: '日志查询' } },
  { path: '/analysis', name: 'analysis', component: AnalysisReport, meta: { title: '分析报告' } },
  { path: '/graph', name: 'graph', component: KnowledgeGraph, meta: { title: '知识图谱' } },
  { path: '/chat', name: 'chat', component: ChatPanel, meta: { title: '对话' } },
  { path: '/status', name: 'status', component: StatusPanel, meta: { title: '系统状态' } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
