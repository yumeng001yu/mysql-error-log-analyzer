<template>
  <div class="app-layout" v-if="loggedIn">
    <!-- 左侧导航 -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <span class="logo-icon">🔍</span>
        <span class="logo-text">日志分析器</span>
      </div>
      <nav class="sidebar-nav">
        <router-link
          v-for="item in navItems"
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
    <div class="main-area">
      <!-- 顶部告警通知栏 -->
      <header class="top-bar">
        <div class="top-bar-title">{{ currentTitle }}</div>
        <div class="alert-indicator" v-if="unreadAlerts > 0" @click="showAlertPanel = !showAlertPanel">
          <span class="alert-badge blink">{{ unreadAlerts }}</span>
          <span class="alert-text">条未读告警</span>
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
  </div>

  <!-- 登录页 -->
  <LoginPage v-else @login-success="onLoginSuccess" />
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import LoginPage from './components/LoginPage.vue'
import { api, wsManager, getToken, removeToken } from './api.js'

export default {
  name: 'App',
  components: { LoginPage },
  setup() {
    const route = useRoute()
    const loggedIn = ref(!!getToken())
    const recentAlerts = ref([])
    const showAlertPanel = ref(false)

    const navItems = [
      { path: '/', icon: '📊', label: '仪表盘' },
      { path: '/logs', icon: '📋', label: '日志查询' },
      { path: '/analysis', icon: '🔬', label: '分析报告' },
      { path: '/graph', icon: '🕸️', label: '知识图谱' },
      { path: '/chat', icon: '💬', label: '对话' },
      { path: '/status', icon: '⚙️', label: '系统状态' }
    ]

    const currentTitle = computed(() => {
      const item = navItems.find(n => n.path === route.path)
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

    async function loadAlerts() {
      try {
        const res = await api.getAlerts({ limit: 20 })
        recentAlerts.value = res.data?.alerts || res.data || []
      } catch (e) {
        // 静默处理
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

    onMounted(() => {
      if (loggedIn.value) {
        initWebSockets()
        loadAlerts()
      }
    })

    onUnmounted(() => {
      wsManager.disconnectAll()
    })

    return {
      loggedIn,
      navItems,
      currentTitle,
      recentAlerts,
      showAlertPanel,
      unreadAlerts,
      formatTime,
      markRead,
      markAllRead,
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
</style>
