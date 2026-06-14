import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'

// ── 全局错误日志系统 ──────────────────────────────────────
const errorLog = {
  _logs: [],
  _maxSize: 200,
  _listeners: [],

  add(level, source, message, detail) {
    const entry = {
      id: Date.now() + Math.random().toString(36).slice(2, 6),
      time: new Date().toISOString(),
      level,       // 'error' | 'warn' | 'info'
      source,      // 来源组件/模块
      message,     // 简短描述
      detail       // 详细信息（如 error 对象）
    }
    this._logs.unshift(entry)
    if (this._logs.length > this._maxSize) {
      this._logs = this._logs.slice(0, this._maxSize)
    }
    // 持久化到 localStorage
    try {
      const serializable = this._logs.map(e => ({
        ...e,
        detail: e.detail instanceof Error ? e.detail.message + ' | ' + e.detail.stack : String(e.detail || '')
      }))
      localStorage.setItem('app_error_log', JSON.stringify(serializable.slice(0, 50)))
    } catch (_) { /* ignore */ }

    // 通知监听器
    this._listeners.forEach(fn => {
      try { fn(entry) } catch (_) { /* ignore */ }
    })

    // 同时输出到控制台
    const consoleFn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.info
    consoleFn(`[${level.toUpperCase()}] [${source}] ${message}`, detail || '')
  },

  error(source, message, detail) { this.add('error', source, message, detail) },
  warn(source, message, detail) { this.add('warn', source, message, detail) },
  info(source, message, detail) { this.add('info', source, message, detail) },

  getAll() { return [...this._logs] },
  clear() {
    this._logs = []
    localStorage.removeItem('app_error_log')
  },
  onLoad(fn) { this._listeners.push(fn) },
  offLoad(fn) { this._listeners = this._listeners.filter(l => l !== fn) }
}

// 从 localStorage 恢复之前的日志
try {
  const saved = localStorage.getItem('app_error_log')
  if (saved) {
    errorLog._logs = JSON.parse(saved)
  }
} catch (_) { /* ignore */ }

// 全局 Vue 错误处理
const app = createApp(App)
app.config.errorHandler = (err, instance, info) => {
  const componentName = instance?.$options?.name || (instance && instance.$ && instance.$.type && instance.$.type.name) || 'Unknown'
  errorLog.error(componentName, `Vue error: ${err.message}`, err.stack)
}
app.config.warnHandler = (msg, instance, trace) => {
  const componentName = instance?.$options?.name || 'Unknown'
  errorLog.warn(componentName, msg, trace)
}

// 全局 JS 错误捕获
window.onerror = (msg, url, line, col, err) => {
  errorLog.error('Global', `${msg} (${url}:${line}:${col})`, err?.stack)
}
window.addEventListener('unhandledrejection', (event) => {
  errorLog.error('Promise', `Unhandled rejection: ${event.reason}`, event.reason?.stack)
})

// 路由错误日志
router.onError((error) => {
  errorLog.error('Router', `Navigation error: ${error.message}`, error.stack)
})

// 路由变化日志
router.afterEach((to, from) => {
  errorLog.info('Router', `${from.path} → ${to.path}`)
})

app.use(router)
app.mount('#app')

// 暴露到全局方便调试
window.__errorLog = errorLog

export { errorLog }
