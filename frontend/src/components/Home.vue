<template>
  <div class="home-page">
    <div class="home-header">
      <h1 class="home-title">数据库运维平台</h1>
      <p class="home-subtitle">选择数据库类型，开始智能运维</p>
    </div>

    <div class="db-cards">
      <!-- MySQL 卡片 -->
      <div
        class="db-card mysql-card"
        :class="{ 'db-disabled': !mysqlEnabled }"
        @click="handleMysqlClick"
        @touchend.passive="handleMysqlTouch"
        role="button"
        tabindex="0"
        aria-label="进入 MySQL 运维"
      >
        <div class="db-card-header">
          <div class="db-card-icon">
            <svg viewBox="0 0 64 64" width="48" height="48">
              <ellipse cx="32" cy="12" rx="22" ry="8" fill="#00758F" :opacity="mysqlEnabled ? 0.9 : 0.4"/>
              <path d="M10 12 v40 c0 4.4 9.8 8 22 8 s22-3.6 22-8 V12" fill="none" stroke="#00758F" stroke-width="2.5" :opacity="mysqlEnabled ? 1 : 0.4"/>
              <path d="M10 28 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#00758F" stroke-width="2" :opacity="mysqlEnabled ? 1 : 0.4"/>
              <path d="M10 44 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#00758F" stroke-width="2" :opacity="mysqlEnabled ? 1 : 0.4"/>
            </svg>
          </div>
          <!-- 开关按钮 -->
          <div
            class="toggle-switch"
            :class="{ 'toggle-on': mysqlEnabled }"
            @click.stop="toggleMysql"
            role="switch"
            :aria-checked="mysqlEnabled"
            aria-label="启用/禁用 MySQL 运维"
          >
            <span class="toggle-knob"></span>
          </div>
        </div>
        <div class="db-card-info">
          <h2 class="db-card-name">MySQL</h2>
          <p class="db-card-desc">错误日志分析 / 慢查询 / 监控告警</p>
        </div>
        <div class="db-card-status">
          <span class="status-dot" :class="mysqlEnabled ? 'active' : 'inactive'"></span>
          <span class="status-text">{{ mysqlEnabled ? '已启用' : '已禁用' }}</span>
        </div>
        <div class="db-card-arrow" v-if="mysqlEnabled">→</div>
        <div class="db-card-badge" v-else>已禁用</div>
      </div>

      <!-- Redis 卡片 -->
      <div
        class="db-card redis-card"
        :class="{ 'db-disabled': !redisEnabled }"
        @click="handleRedisClick"
        @touchend.passive="handleRedisTouch"
        role="button"
        tabindex="0"
        aria-label="进入 Redis 运维"
      >
        <div class="db-card-header">
          <div class="db-card-icon">
            <svg viewBox="0 0 64 64" width="48" height="48">
              <rect x="12" y="14" width="40" height="10" rx="2" fill="#DC382D" :opacity="redisEnabled ? 0.9 : 0.4"/>
              <rect x="12" y="27" width="40" height="10" rx="2" fill="#DC382D" :opacity="redisEnabled ? 0.75 : 0.4"/>
              <rect x="12" y="40" width="40" height="10" rx="2" fill="#DC382D" :opacity="redisEnabled ? 0.6 : 0.4"/>
              <path d="M12 14 L32 4 L52 14" fill="none" stroke="#DC382D" stroke-width="2.5" :opacity="redisEnabled ? 0.9 : 0.4"/>
              <path d="M32 4 L32 50" stroke="#DC382D" stroke-width="1.5" :opacity="redisEnabled ? 0.4 : 0.2"/>
            </svg>
          </div>
          <!-- 开关按钮 -->
          <div
            class="toggle-switch"
            :class="{ 'toggle-on': redisEnabled }"
            @click.stop="toggleRedis"
            role="switch"
            :aria-checked="redisEnabled"
            aria-label="启用/禁用 Redis 运维"
          >
            <span class="toggle-knob"></span>
          </div>
        </div>
        <div class="db-card-info">
          <h2 class="db-card-name">Redis</h2>
          <p class="db-card-desc">实时监控 / 慢查询 / 内存分析</p>
        </div>
        <div class="db-card-status">
          <span class="status-dot" :class="redisEnabled ? 'active' : 'inactive'"></span>
          <span class="status-text">{{ redisEnabled ? '已启用' : '已禁用' }}</span>
        </div>
        <div class="db-card-arrow" v-if="redisEnabled">→</div>
        <div class="db-card-badge" v-else>已禁用</div>
      </div>

      <!-- PostgreSQL 卡片（规划中） -->
      <div class="db-card disabled">
        <div class="db-card-header">
          <div class="db-card-icon">
            <svg viewBox="0 0 64 64" width="48" height="48">
              <ellipse cx="32" cy="12" rx="22" ry="8" fill="#336791" opacity="0.5"/>
              <path d="M10 12 v40 c0 4.4 9.8 8 22 8 s22-3.6 22-8 V12" fill="none" stroke="#336791" stroke-width="2.5" opacity="0.5"/>
              <path d="M10 28 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#336791" stroke-width="2" opacity="0.5"/>
              <path d="M10 44 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#336791" stroke-width="2" opacity="0.5"/>
            </svg>
          </div>
        </div>
        <div class="db-card-info">
          <h2 class="db-card-name">PostgreSQL</h2>
          <p class="db-card-desc">即将支持</p>
        </div>
        <div class="db-card-status">
          <span class="status-dot inactive"></span>
          <span class="status-text">规划中</span>
        </div>
        <div class="db-card-badge">即将推出</div>
      </div>
    </div>

    <!-- 通用运维功能入口（仅当至少一个数据库启用时显示） -->
    <div class="common-section" v-if="mysqlEnabled || redisEnabled">
      <h3 class="common-title">通用运维功能</h3>
      <div class="common-cards">
        <div class="common-card" @click="navigateTo('/diagnosis')">
          <span class="common-icon">🩺</span>
          <span class="common-label">一键诊断</span>
        </div>
        <div class="common-card" @click="navigateTo('/capacity')">
          <span class="common-icon">📦</span>
          <span class="common-label">容量规划</span>
        </div>
        <div class="common-card" @click="navigateTo('/inspection')">
          <span class="common-icon">⏰</span>
          <span class="common-label">定时巡检</span>
        </div>
      </div>
    </div>

    <div class="home-footer">
      <span>DB Ops Analyzer v2.0</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { dbToggle } from '../router.js'

const router = useRouter()

const mysqlEnabled = ref(true)
const redisEnabled = ref(true)

// 初始化开关状态
onMounted(() => {
  mysqlEnabled.value = dbToggle.isEnabled('mysql')
  redisEnabled.value = dbToggle.isEnabled('redis')
})

// 开关切换
function toggleMysql() {
  mysqlEnabled.value = !mysqlEnabled.value
  dbToggle.setEnabled('mysql', mysqlEnabled.value)
}

function toggleRedis() {
  redisEnabled.value = !redisEnabled.value
  dbToggle.setEnabled('redis', redisEnabled.value)
}

// 防止重复触发
let navigating = false

function navigateTo(path) {
  if (navigating) return
  navigating = true
  router.push(path).catch(() => {})
  setTimeout(() => { navigating = false }, 1000)
}

function handleMysqlClick(e) {
  e.preventDefault()
  if (!mysqlEnabled.value) return
  navigateTo('/mysql')
}

function handleMysqlTouch(e) {
  e.preventDefault()
  if (!mysqlEnabled.value) return
  navigateTo('/mysql')
}

function handleRedisClick(e) {
  e.preventDefault()
  if (!redisEnabled.value) return
  navigateTo('/redis')
}

function handleRedisTouch(e) {
  e.preventDefault()
  if (!redisEnabled.value) return
  navigateTo('/redis')
}
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 50px);
  padding: 40px 20px;
}

.home-header {
  text-align: center;
  margin-bottom: 40px;
}

.home-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.home-subtitle {
  font-size: 15px;
  color: var(--text-muted);
  margin: 0;
}

.db-cards {
  display: grid;
  grid-template-columns: repeat(3, 280px);
  gap: 20px;
  max-width: 900px;
  width: 100%;
}

.db-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  cursor: pointer;
  transition: all 0.25s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  position: relative;
  overflow: hidden;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
  user-select: none;
  text-decoration: none;
  color: inherit;
}

.db-card-header {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  position: relative;
}

.db-card-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 开关按钮 */
.toggle-switch {
  position: absolute;
  top: -4px;
  right: 0;
  width: 44px;
  height: 24px;
  background: var(--border-color);
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.25s ease;
  display: flex;
  align-items: center;
  padding: 2px;
}

.toggle-switch.toggle-on {
  background: #22c55e;
}

.toggle-knob {
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.25s ease;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}

.toggle-switch.toggle-on .toggle-knob {
  transform: translateX(20px);
}

/* MySQL 卡片样式 */
.db-card.mysql-card:hover:not(.db-disabled) {
  border-color: var(--accent-blue);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.12);
}

.db-card.mysql-card:active:not(.db-disabled) {
  transform: scale(0.98);
  background: var(--bg-hover);
}

/* Redis 卡片样式 */
.db-card.redis-card:hover:not(.db-disabled) {
  border-color: #DC382D;
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(220, 56, 45, 0.12);
}

.db-card.redis-card:active:not(.db-disabled) {
  transform: scale(0.98);
  background: var(--bg-hover);
}

/* 禁用状态 */
.db-card.db-disabled {
  cursor: default;
  opacity: 0.55;
}

.db-card.disabled {
  cursor: default;
  opacity: 0.6;
}

.db-card-info {
  text-align: center;
}

.db-card-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.db-card-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.4;
}

.db-card-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}

.status-dot.active {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.5);
}

.status-dot.inactive {
  background: #6b7280;
}

.db-card-arrow {
  font-size: 20px;
  color: var(--accent-blue);
  opacity: 0;
  transition: opacity 0.2s, transform 0.2s;
}

.db-card.mysql-card:hover:not(.db-disabled) .db-card-arrow {
  opacity: 1;
  transform: translateX(4px);
}

.db-card.redis-card:hover:not(.db-disabled) .db-card-arrow {
  opacity: 1;
  transform: translateX(4px);
  color: #DC382D;
}

.db-card-badge {
  position: absolute;
  top: 12px;
  right: -28px;
  background: var(--accent-blue);
  color: #fff;
  font-size: 10px;
  padding: 2px 32px;
  transform: rotate(45deg);
  opacity: 0.7;
}

.db-card.db-disabled .db-card-badge {
  background: #6b7280;
}

/* 通用运维功能区域 */
.common-section {
  margin-top: 40px;
  width: 100%;
  max-width: 900px;
}

.common-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-muted);
  margin: 0 0 16px;
  text-align: center;
}

.common-cards {
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
}

.common-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-width: 120px;
}

.common-card:hover {
  border-color: var(--accent-blue);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
}

.common-icon {
  font-size: 28px;
}

.common-label {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.home-footer {
  margin-top: 40px;
  color: var(--text-muted);
  font-size: 12px;
  opacity: 0.5;
}

/* ── 移动端适配 ────────────────────────────────────────── */
@media (max-width: 768px) {
  .home-page {
    padding: 24px 16px;
    min-height: calc(100vh - 100px);
  }

  .home-title {
    font-size: 22px;
  }

  .home-subtitle {
    font-size: 13px;
  }

  .db-cards {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .db-card {
    flex-direction: row;
    padding: 16px;
    gap: 14px;
    align-items: center;
    min-height: 64px;
  }

  .db-card-header {
    width: auto;
  }

  .db-card-icon {
    width: 40px;
    height: 40px;
    flex-shrink: 0;
  }

  .db-card-icon svg {
    width: 40px;
    height: 40px;
  }

  .db-card-info {
    text-align: left;
    flex: 1;
  }

  .db-card-name {
    font-size: 15px;
  }

  .db-card-desc {
    font-size: 12px;
  }

  .db-card-status {
    flex-shrink: 0;
  }

  .db-card-arrow {
    display: none;
  }

  .db-card-badge {
    top: 8px;
    right: -24px;
    font-size: 9px;
    padding: 2px 28px;
  }

  .home-header {
    margin-bottom: 28px;
  }

  .home-footer {
    margin-top: 28px;
  }

  .common-cards {
    flex-direction: column;
    align-items: stretch;
  }

  .common-card {
    flex-direction: row;
    justify-content: center;
    gap: 12px;
  }
}
</style>
