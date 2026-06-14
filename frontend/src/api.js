import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// JWT token 管理
function getToken() {
  return localStorage.getItem('token')
}

function setToken(token) {
  localStorage.setItem('token', token)
}

function removeToken() {
  localStorage.removeItem('token')
}

// 请求拦截器：附加 token
http.interceptors.request.use(config => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 时清除 token（不自动 reload，避免循环）
http.interceptors.response.use(
  res => res,
  err => {
    if (err.response && err.response.status === 401) {
      removeToken()
      // 不再自动 reload，而是派发自定义事件让 App.vue 处理
      window.dispatchEvent(new CustomEvent('auth-expired'))
    }
    return Promise.reject(err)
  }
)

// ========== REST API ==========

export const api = {
  // 日志
  getLogs(params) {
    return http.get('/logs', { params })
  },
  getLogStats(params) {
    return http.get('/logs/stats', { params })
  },
  getLogDistribution(params) {
    return http.get('/logs/distribution', { params })
  },
  getLogTrend(params) {
    return http.get('/logs/trend', { params })
  },
  // 语义搜索
  semanticSearch(params) {
    return http.get('/logs/semantic', { params })
  },
  // 语义相似度关联（知识图谱用）
  getSemanticSimilar(params) {
    return http.get('/logs/semantic/similar', { params })
  },

  // 分析
  runAnalysis(data) {
    return http.post('/analysis/run', data)
  },
  getAnalysisResults(params) {
    return http.get('/analysis/results', { params })
  },

  // 对话
  sendChat(data) {
    return http.post('/chat', data)
  },

  // 状态
  getStatus() {
    return http.get('/status')
  },

  // 实例
  getInstances(params) {
    return http.get('/instances/', { params })
  },
  addInstance(data) {
    return http.post('/instances/', data)
  },
  updateInstance(id, data) {
    return http.put(`/instances/${id}`, data)
  },
  deleteInstance(id) {
    return http.delete(`/instances/${id}`)
  },
  testInstanceConnection(id) {
    return http.post(`/instances/${id}/test`)
  },
  getInstanceStatus(id) {
    return http.get(`/instances/${id}/status`)
  },
  getInstanceGroups() {
    return http.get('/instances/groups')
  },
  getInstancesOverview() {
    return http.get('/instances/overview')
  },
  collectInstanceLogs(id) {
    return http.post(`/instances/${id}/collect`)
  },

  // 告警
  getAlerts(params) {
    return http.get('/alerts', { params })
  },
  markAlertRead(id) {
    return http.put(`/alerts/${id}/read`)
  },

  // 登录
  login(data) {
    return http.post('/auth/login', data)
  },

  // 设置
  getSettings() {
    return http.get('/settings')
  },
  saveSettings(data) {
    return http.put('/settings', data)
  },
  testLLM(data) {
    return http.post('/settings/test-llm', data)
  },
  testEmbedding(data) {
    return http.post('/settings/test-embedding', data)
  },

  // 慢查询
  getSlowQueryStats(params) { return http.get('/slow-query/stats', { params }) },
  getSlowQueryList(params) { return http.get('/slow-query/list', { params }) },
  getSlowQueryDistribution(params) { return http.get('/slow-query/distribution', { params }) },
  analyzeSlowQuery(data) { return http.post('/slow-query/analyze', data) },
  parseSlowQuery(data) { return http.post('/slow-query/parse', data) },

  // 监控
  getMonitorStatus(params) { return http.get('/monitor/status', { params }) },
  getProcesslist(params) { return http.get('/monitor/processlist', { params }) },
  getInnodbStatus(params) { return http.get('/monitor/innodb', { params }) },
  getMonitorHistory(params) { return http.get('/monitor/history', { params }) },
  getReplicationStatus(params) { return http.get('/monitor/replication', { params }) },
  testMySQLConnection(data) { return http.post('/monitor/test-connection', data) },

  // 告警引擎
  getAlertRules() { return http.get('/alerts/rules') },
  createAlertRule(data) { return http.post('/alerts/rules', data) },
  updateAlertRule(id, data) { return http.put(`/alerts/rules/${id}`, data) },
  deleteAlertRule(id) { return http.delete(`/alerts/rules/${id}`) },
  toggleAlertRule(id) { return http.post(`/alerts/rules/${id}/toggle`) },
  getAlertHistory(params) { return http.get('/alerts/history', { params }) },
  acknowledgeAlert(id) { return http.put(`/alerts/history/${id}/acknowledge`) },
  getNotificationChannels() { return http.get('/alerts/channels') },
  createNotificationChannel(data) { return http.post('/alerts/channels', data) },
  updateNotificationChannel(id, data) { return http.put(`/alerts/channels/${id}`, data) },
  deleteNotificationChannel(id) { return http.delete(`/alerts/channels/${id}`) },
  testNotificationChannel(id) { return http.post(`/alerts/channels/${id}/test`) },
  getAlertStats() { return http.get('/alerts/stats') },
  checkAlerts() { return http.post('/alerts/check') },

  // 模式识别
  recognizePatterns(params) { return http.get('/patterns/recognize', { params }) },
  getPatternAnomalies(params) { return http.get('/patterns/anomalies', { params }) },
  getPatternStats(params) { return http.get('/patterns/stats', { params }) },
  getPatternTrend(patternId, params) { return http.get(`/patterns/${patternId}/trend`, { params }) },

  // 全文本搜索
  searchLogs(params) { return http.get('/search/', { params }) },
  searchSuggest(params) { return http.get('/search/suggest', { params }) },
  getLogContext(id, params) { return http.get(`/search/context/${id}`, { params }) },
  getSearchFields() { return http.get('/search/fields') },

  // 性能基线与异常检测
  buildBaselines(params) { return http.post('/baseline/build', null, { params }) },
  getAnomalies(params) { return http.get('/baseline/anomalies', { params }) },
  getBaselines(params) { return http.get('/baseline/list', { params }) },
  getMetricForecast(metricName, params) { return http.get(`/baseline/forecast/${metricName}`, { params }) },
  getBaselineOverview() { return http.get('/baseline/overview') },

  // 死锁分析
  getDeadlockList(params) { return http.get('/deadlock/list', { params }) },
  getDeadlockDetail(id) { return http.get(`/deadlock/${id}`) },
  getDeadlockStats() { return http.get('/deadlock/stats') },
  analyzeDeadlock(params) { return http.post('/deadlock/analyze', null, { params }) },
  getDeadlockLockChain(id) { return http.get(`/deadlock/lock-chain/${id}`) },

  // 运维报表
  generateReport(params) { return http.post('/reports/generate', null, { params }) },
  getReportList(params) { return http.get('/reports/list', { params }) },
  getReport(id) { return http.get(`/reports/${id}`) },
  deleteReport(id) { return http.delete(`/reports/${id}`) },
  getLatestReport(type, params) { return http.get(`/reports/latest/${type}`, { params }) }
}

// ========== WebSocket 管理 ==========

class WsManager {
  constructor() {
    this.connections = {}
    this.listeners = {}
    this.reconnectTimers = {}
  }

  connect(path, onMessage) {
    if (this.connections[path]) {
      this.connections[path].close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const token = getToken()
    let url = `${protocol}//${window.location.host}${path}`
    if (token) {
      url += `?token=${encodeURIComponent(token)}`
    }

    const ws = new WebSocket(url)

    ws.onopen = () => {
      console.log(`[WS] 已连接: ${path}`)
      if (this.reconnectTimers[path]) {
        clearTimeout(this.reconnectTimers[path])
        this.reconnectTimers[path] = null
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
        if (this.listeners[path]) {
          this.listeners[path].forEach(fn => fn(data))
        }
      } catch (e) {
        console.error('[WS] 解析消息失败:', e)
      }
    }

    ws.onclose = () => {
      console.log(`[WS] 已断开: ${path}`)
      this.connections[path] = null
      // 自动重连
      this.reconnectTimers[path] = setTimeout(() => {
        this.connect(path, onMessage)
      }, 5000)
    }

    ws.onerror = (err) => {
      console.error(`[WS] 错误: ${path}`, err)
    }

    this.connections[path] = ws
    return ws
  }

  on(path, fn) {
    if (!this.listeners[path]) {
      this.listeners[path] = []
    }
    this.listeners[path].push(fn)
  }

  off(path, fn) {
    if (this.listeners[path]) {
      this.listeners[path] = this.listeners[path].filter(f => f !== fn)
    }
  }

  disconnect(path) {
    if (this.connections[path]) {
      this.connections[path].close()
      this.connections[path] = null
    }
    if (this.reconnectTimers[path]) {
      clearTimeout(this.reconnectTimers[path])
      this.reconnectTimers[path] = null
    }
  }

  disconnectAll() {
    Object.keys(this.connections).forEach(path => this.disconnect(path))
  }

  send(path, data) {
    if (this.connections[path] && this.connections[path].readyState === WebSocket.OPEN) {
      this.connections[path].send(JSON.stringify(data))
    }
  }
}

export const wsManager = new WsManager()

export { getToken, setToken, removeToken }
