<template>
  <div class="app-layout" v-if="loggedIn">
    <!-- 左侧导航（桌面端）- 仅在数据库子页面显示 -->
    <aside class="sidebar desktop-only" v-if="!isHomePage">
      <div class="sidebar-logo" @click="$router.push('/')" style="cursor:pointer">
        <span class="logo-icon">🔍</span>
        <span class="logo-text">日志分析器</span>
      </div>
      <nav class="sidebar-nav">
        <router-link to="/" class="nav-item back-item">
          <span class="nav-icon">←</span>
          <span class="nav-label">返回首页</span>
        </router-link>
        <router-link
          v-for="item in currentNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: $route.path === item.path }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="logout-btn" @click="handleLogout">退出登录</button>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <div class="main-area" :class="{ 'home-mode': isHomePage }">
      <!-- 顶部栏 -->
      <header class="top-bar" :class="{ 'home-top-bar': isHomePage }">
        <button class="mobile-menu-btn mobile-only" v-if="!isHomePage" @click="mobileMenuOpen = !mobileMenuOpen">
          <span class="menu-icon">{{ mobileMenuOpen ? '✕' : '☰' }}</span>
        </button>
        <div class="top-bar-title">{{ isHomePage ? '数据库日志分析平台' : currentTitle }}</div>
        <div class="top-bar-right">
          <div class="alert-indicator" v-if="!isHomePage && unreadAlerts > 0" @click="showAlertPanel = !showAlertPanel">
            <span class="alert-badge blink">{{ unreadAlerts }}</span>
            <span class="alert-text desktop-only">条未读告警</span>
          </div>
          <button class="error-log-btn" @click="showErrorLog = !showErrorLog" title="错误日志">
            <span :style="{ color: hasErrors ? 'var(--accent-red)' : 'var(--text-muted)' }">📋</span>
          </button>
          <button class="logout-btn-small" v-if="isHomePage" @click="handleLogout">退出</button>
        </div>
        <!-- 告警下拉面板 -->
        <div class="alert-panel" v-if="showAlertPanel && recentAlerts.length > 0">
          <div class="alert-panel-header">
            <span>最近告警</span>
            <button @click="markAllRead">全部已读</button>
          </div>
          <div
            v-for="alert in recentAlerts.slice(0, 10)"
            :key="alert.id"
            class="alert-item"
            :class="{ unread: !alert.is_read }"
            @click="markRead(alert.id)"
          >
            <span class="alert-level" :class="alert.level">●</span>
            <span class="alert-msg">{{ alert.message || alert.content }}</span>
            <span class="alert-time">{{ formatTime(alert.created_at || alert.time) }}</span>
          </div>
        </div>
      </header>

      <main class="content">
        <router-view />
      </main>
    </div>

    <!-- 移动端侧边栏遮罩 -->
    <div class="mobile-overlay" v-if="mobileMenuOpen" @click="mobileMenuOpen = false"></div>
    <!-- 移动端侧边栏（滑出） -->
    <aside class="mobile-sidebar" :class="{ open: mobileMenuOpen }">
      <div class="sidebar-logo">
        <span class="logo-icon">🔍</span>
        <span class="logo-text">日志分析器</span>
      </div>
      <nav class="sidebar-nav">
        <router-link to="/" class="nav-item back-item" @click="mobileMenuOpen = false">
          <span class="nav-icon">←</span>
          <span class="nav-label">返回首页</span>
        </router-link>
        <router-link
          v-for="item in currentNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: $route.path === item.path }"
          @click="mobileMenuOpen = false"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="logout-btn" @click="handleLogout">退出登录</button>
      </div>
    </aside>

    <!-- 移动端底部导航栏 - 仅在数据库子页面显示 -->
    <nav class="bottom-nav mobile-only" v-if="!isHomePage">
      <router-link
        v-for="item in currentBottomNavItems"
        :key="item.path"
        :to="item.path"
        class="bottom-nav-item"
        :class="{ active: $route.path === item.path }"
      >
        <span class="bottom-nav-icon">{{ item.icon }}</span>
        <span class="bottom-nav-label">{{ item.label }}</span>
      </router-link>
    </nav>

    <!-- 错误日志面板 -->
    <div class="error-log-panel" v-if="showErrorLog">
      <div class="error-log-header">
        <span>错误日志</span>
        <div class="error-log-actions">
          <button @click="clearErrorLog">清空</button>
          <button @click="showErrorLog = false">关闭</button>
        </div>
      </div>
      <div class="error-log-list">
        <div v-if="errorLogs.length === 0" class="error-log-empty">暂无错误日志</div>
        <div
          v-for="log in errorLogs"
          :key="log.id"
          class="error-log-item"
          :class="'level-' + log.level"
        >
          <span class="log-level-badge">{{ log.level }}</span>
          <span class="log-source">[{{ log.source }}]</span>
          <span class="log-message">{{ log.message }}</span>
          <span class="log-time">{{ formatLogTime(log.time) }}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 登录页 -->
  <LoginPage v-else @login-success="onLoginSuccess" />
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import LoginPage from './components/LoginPage.vue'
import { api, wsManager, getToken, setToken, removeToken } from './api.js'

export default {
  name: 'App',
  components: { LoginPage },
  setup() {
    const route = useRoute()
    const loggedIn = ref(!!getToken())
    const recentAlerts = ref([])
    const showAlertPanel = ref(false)
    const mobileMenuOpen = ref(false)
    const showErrorLog = ref(false)
    const errorLogs = ref([])
    const hasErrors = ref(false)

    // 自动登录：如果没有 token，尝试无密码登录获取 token
    async function autoLogin() {
      if (getToken()) {
        loggedIn.value = true
        return
      }
      try {
        const res = await api.login({ username: 'admin', password: '' })
        const token = res.data?.token
        if (token) {
          setToken(token)
          loggedIn.value = true
        }
      } catch (e) {
        // 登录失败，显示登录页
        console.warn('自动登录失败，需要手动登录', e)
      }
    }

    // 判断是否在首页
    const isHomePage = computed(() => route.path === '/')

    // MySQL 导航项
    const mysqlNavItems = [
      { path: '/mysql', icon: '📊', label: '仪表盘' },
      { path: '/mysql/monitor', icon: '💓', label: '实时监控' },
      { path: '/mysql/slow-query', icon: '🐢', label: '慢查询分析' },
      { path: '/mysql/alerts', icon: '🔔', label: '智能告警' },
      { path: '/mysql/search', icon: '🔍', label: '日志搜索' },
      { path: '/mysql/patterns', icon: '🧩', label: '模式识别' },
      { path: '/mysql/deadlock', icon: '🔒', label: '死锁分析' },
      { path: '/mysql/baseline', icon: '📈', label: '性能基线' },
      { path: '/mysql/instances', icon: '🖥️', label: '实例管理' },
      { path: '/mysql/reports', icon: '📄', label: '运维报表' },
      { path: '/mysql/replication', icon: '🔗', label: '复制状态' },
      { path: '/mysql/logs', icon: '📋', label: '日志查询' },
      { path: '/mysql/analysis', icon: '🔬', label: '分析报告' },
      { path: '/mysql/graph', icon: '🕸️', label: '知识图谱' },
      { path: '/mysql/chat', icon: '💬', label: '对话' },
      { path: '/mysql/settings', icon: '🔧', label: '设置' },
      { path: '/mysql/status', icon: '⚙️', label: '系统状态' }
    ]

    const mysqlBottomNavItems = [
      { path: '/mysql', icon: '📊', label: '仪表盘' },
      { path: '/mysql/monitor', icon: '💓', label: '监控' },
      { path: '/mysql/alerts', icon: '🔔', label: '告警' },
      { path: '/mysql/search', icon: '🔍', label: '搜索' },
      { path: '/mysql/settings', icon: '🔧', label: '设置' }
    ]

    // Redis 导航项
    const redisNavItems = [
      { path: '/redis', icon: '💓', label: '实时监控' },
      { path: '/redis/slowlog', icon: '🐢', label: '慢查询' },
      { path: '/redis/memory', icon: '💾', label: '内存分析' },
      { path: '/redis/keys', icon: '🔑', label: 'Key 分析' },
      { path: '/redis/persistence', icon: '💿', label: '持久化' },
      { path: '/redis/cluster', icon: '🌐', label: '集群/哨兵' },
      { path: '/redis/replication', icon: '🔗', label: '复制状态' },
      { path: '/redis/alerts', icon: '🔔', label: '智能告警' },
      { path: '/redis/instances', icon: '🖥️', label: '实例管理' },
      { path: '/redis/settings', icon: '🔧', label: '设置' }
    ]

    const redisBottomNavItems = [
      { path: '/redis', icon: '💓', label: '监控' },
      { path: '/redis/slowlog', icon: '🐢', label: '慢查询' },
      { path: '/redis/keys', icon: '🔑', label: 'Key' },
      { path: '/redis/alerts', icon: '🔔', label: '告警' },
      { path: '/redis/settings', icon: '🔧', label: '设置' }
    ]

    // 根据当前路由动态选择导航项
    const currentNavItems = computed(() => {
      const db = route.meta?.db
      if (db === 'mysql') return mysqlNavItems
      if (db === 'redis') return redisNavItems
      return mysqlNavItems // 默认
    })

    const currentBottomNavItems = computed(() => {
      const db = route.meta?.db
      if (db === 'mysql') return mysqlBottomNavItems
      if (db === 'redis') return redisBottomNavItems
      return mysqlBottomNavItems
    })

    const currentTitle = computed(() => {
      if (isHomePage.value) return '数据库日志分析平台'
      const items = currentNavItems.value
      const item = items.find(n => n.path === route.path)
      return item ? item.label : 'MySQL 错误日志分析器'
    })

    const unreadAlerts = computed(() => {
      return recentAlerts.value.filter(a => !a.is_read).length
    })

    function formatTime(t) {
      if (!t) return ''
      const d = new Date(t)
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    }

    function formatLogTime(t) {
      if (!t) return ''
      const d = new Date(t)
      return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
    }

    // 错误日志管理
    function refreshErrorLog() {
      try {
        const saved = localStorage.getItem('app_error_log')
        if (saved) {
          errorLogs.value = JSON.parse(saved)
          hasErrors.value = errorLogs.value.some(l => l.level === 'error')
        }
      } catch (_) { /* ignore */ }
    }

    function clearErrorLog() {
      try {
        if (window.__errorLog) window.__errorLog.clear()
      } catch (_) { /* ignore */ }
      errorLogs.value = []
      hasErrors.value = false
    }

    async function loadAlerts() {
      try {
        const res = await api.getAlerts({ limit: 20 })
        const data = res.data
        if (Array.isArray(data)) {
          recentAlerts.value = data
        } else if (Array.isArray(data?.alerts)) {
          recentAlerts.value = data.alerts
        } else if (Array.isArray(data?.items)) {
          recentAlerts.value = data.items
        } else {
          recentAlerts.value = []
        }
      } catch (e) {
        recentAlerts.value = []
      }
    }

    async function markRead(id) {
      try {
        await api.markAlertRead(id)
        const alert = recentAlerts.value.find(a => a.id === id)
        if (alert) alert.is_read = true
      } catch (e) { /* ignore */ }
    }

    async function markAllRead() {
      for (const alert of recentAlerts.value.filter(a => !a.is_read)) {
        await markRead(alert.id)
      }
    }

    function onLoginSuccess() {
      loggedIn.value = true
      initWebSockets()
      loadAlerts()
    }

    function handleLogout() {
      removeToken()
      wsManager.disconnectAll()
      loggedIn.value = false
    }

    function initWebSockets() {
      wsManager.connect('/ws/alerts', (data) => {
        recentAlerts.value.unshift(data)
        if (recentAlerts.value.length > 50) {
          recentAlerts.value = recentAlerts.value.slice(0, 50)
        }
      })
    }

    // 监听认证过期事件
    function onAuthExpired() {
      console.warn('[App] 认证过期，重新登录')
      loggedIn.value = false
      autoLogin()
    }

    // 定期刷新错误日志
    let errorLogTimer = null

    onMounted(async () => {
      await autoLogin()
      if (loggedIn.value) {
        initWebSockets()
        loadAlerts()
      }
      refreshErrorLog()
      errorLogTimer = setInterval(refreshErrorLog, 3000)
      window.addEventListener('auth-expired', onAuthExpired)
    })

    onUnmounted(() => {
      wsManager.disconnectAll()
      if (errorLogTimer) clearInterval(errorLogTimer)
      window.removeEventListener('auth-expired', onAuthExpired)
    })

    return {
      loggedIn,
      isHomePage,
      currentNavItems,
      currentBottomNavItems,
      mobileMenuOpen,
      currentTitle,
      recentAlerts,
      showAlertPanel,
      unreadAlerts,
      showErrorLog,
      errorLogs,
      hasErrors,
      formatTime,
      formatLogTime,
      markRead,
      markAllRead,
      clearErrorLog,
      onLoginSuccess,
      handleLogout
    }
  }
}
</script>

<style>
:root {
  --bg-primary: #0a0e17;
  --bg-secondary: #111827;
  --bg-card: #1a2234;
  --bg-hover: #243049;
  --border-color: #2a3a52;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent-blue: #3b82f6;
  --accent-green: #10b981;
  --accent-red: #ef4444;
  --accent-yellow: #f59e0b;
  --accent-purple: #8b5cf6;
  --accent-cyan: #06b6d4;
  --sidebar-width: 200px;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  overflow: hidden;
  height: 100vh;
}

#app {
  height: 100vh;
}

.app-layout {
  display: flex;
  height: 100vh;
}

/* ── 首页模式 ──────────────────────────────────────────── */
.main-area.home-mode {
  /* 首页时没有侧边栏，占满全宽 */
  margin-left: 0;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.error-log-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.2s;
}

.error-log-btn:hover {
  background: var(--bg-hover);
}

.logout-btn-small {
  background: none;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.logout-btn-small:hover {
  background: var(--accent-red);
  color: #fff;
  border-color: var(--accent-red);
}

.back-item {
  color: var(--text-muted) !important;
  font-size: 12px !important;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 10px !important;
}

.back-item:hover {
  color: var(--accent-blue) !important;
}

/* 侧边栏 */
.sidebar {
  width: var(--sidebar-width);
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-logo {
  padding: 20px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--border-color);
}

.logo-icon {
  font-size: 22px;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-blue);
  color: #fff;
}

.nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border-color);
}

.logout-btn {
  width: 100%;
  padding: 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.logout-btn:hover {
  background: var(--accent-red);
  color: #fff;
  border-color: var(--accent-red);
}

/* 主内容区 */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.top-bar {
  height: 50px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: relative;
  flex-shrink: 0;
}

.top-bar-title {
  font-size: 16px;
  font-weight: 600;
}

.alert-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 4px;
  transition: background 0.2s;
}

.alert-indicator:hover {
  background: var(--bg-hover);
}

.alert-badge {
  background: var(--accent-red);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 10px;
}

.alert-badge.blink {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.alert-text {
  color: var(--accent-red);
  font-size: 13px;
}

.alert-panel {
  position: absolute;
  top: 50px;
  right: 16px;
  width: 380px;
  max-height: 400px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow-y: auto;
  z-index: 100;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

.alert-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 14px;
  font-weight: 600;
}

.alert-panel-header button {
  background: none;
  border: none;
  color: var(--accent-blue);
  cursor: pointer;
  font-size: 12px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  font-size: 13px;
}

.alert-item:hover {
  background: var(--bg-hover);
}

.alert-item.unread {
  background: rgba(59, 130, 246, 0.08);
}

.alert-level {
  font-size: 10px;
}

.alert-level.error { color: var(--accent-red); }
.alert-level.warning { color: var(--accent-yellow); }
.alert-level.info { color: var(--accent-cyan); }

.alert-msg {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alert-time {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* ── 错误日志面板 ──────────────────────────────────────── */
.error-log-panel {
  position: fixed;
  bottom: 60px;
  right: 16px;
  width: 420px;
  max-height: 50vh;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  z-index: 300;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  display: flex;
  flex-direction: column;
}

.error-log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
  font-weight: 600;
}

.error-log-actions {
  display: flex;
  gap: 8px;
}

.error-log-actions button {
  background: none;
  border: none;
  color: var(--accent-blue);
  cursor: pointer;
  font-size: 12px;
}

.error-log-list {
  overflow-y: auto;
  max-height: calc(50vh - 40px);
  padding: 4px 0;
}

.error-log-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 20px;
}

.error-log-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 14px;
  font-size: 11px;
  font-family: monospace;
  border-bottom: 1px solid rgba(42, 58, 82, 0.3);
}

.error-log-item.level-error {
  background: rgba(239, 68, 68, 0.08);
}

.error-log-item.level-warn {
  background: rgba(245, 158, 11, 0.05);
}

.log-level-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  text-transform: uppercase;
  flex-shrink: 0;
}

.level-error .log-level-badge {
  background: var(--accent-red);
  color: #fff;
}

.level-warn .log-level-badge {
  background: var(--accent-yellow);
  color: #000;
}

.level-info .log-level-badge {
  background: var(--accent-cyan);
  color: #000;
}

.log-source {
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.log-message {
  color: var(--text-secondary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-time {
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 10px;
}

/* 滚动条 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* ── 响应式工具类 ──────────────────────────────────────── */
.mobile-only {
  display: none;
}

.desktop-only {
  display: flex;
}

/* ── 移动端菜单按钮 ────────────────────────────────────── */
.mobile-menu-btn {
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.mobile-menu-btn:hover {
  background: var(--bg-hover);
}

.menu-icon {
  font-size: 18px;
}

/* ── 移动端侧边栏（滑出） ──────────────────────────────── */
.mobile-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 200;
}

.mobile-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 260px;
  height: 100vh;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  z-index: 201;
  transform: translateX(-100%);
  transition: transform 0.3s ease;
}

.mobile-sidebar.open {
  transform: translateX(0);
}

/* ── 底部导航栏 ────────────────────────────────────────── */
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: space-around;
  align-items: center;
  z-index: 100;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

.bottom-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-decoration: none;
  color: var(--text-muted);
  font-size: 10px;
  padding: 4px 0;
  min-width: 48px;
  transition: color 0.2s;
}

.bottom-nav-icon {
  font-size: 18px;
}

.bottom-nav-label {
  font-size: 10px;
}

.bottom-nav-item.active {
  color: var(--accent-blue);
}

/* ── 移动端适配 ────────────────────────────────────────── */
@media (max-width: 768px) {
  .mobile-only {
    display: flex;
  }

  .desktop-only {
    display: none;
  }

  .main-area {
    padding-bottom: 56px;
  }

  .main-area.home-mode {
    padding-bottom: 0;
  }

  .top-bar {
    padding: 0 12px;
    height: 44px;
  }

  .top-bar-title {
    font-size: 15px;
  }

  .content {
    padding: 12px;
  }

  .alert-panel {
    right: 8px;
    left: 8px;
    width: auto;
    max-height: 60vh;
  }

  .alert-indicator {
    padding: 4px 8px;
  }

  .error-log-panel {
    right: 8px;
    left: 8px;
    width: auto;
    bottom: 60px;
    max-height: 40vh;
  }
}

/* ── 小屏手机适配 ──────────────────────────────────────── */
@media (max-width: 400px) {
  .bottom-nav-item {
    min-width: 40px;
  }

  .bottom-nav-label {
    font-size: 9px;
  }
}
</style>
