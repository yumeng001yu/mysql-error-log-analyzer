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

// 响应拦截器：401 时清除 token
http.interceptors.response.use(
  res => res,
  err => {
    if (err.response && err.response.status === 401) {
      removeToken()
      window.location.reload()
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
  getInstances() {
    return http.get('/instances')
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
  }
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
