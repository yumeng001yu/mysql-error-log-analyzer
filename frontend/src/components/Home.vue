<template>
  <div class="home-page">
    <div class="home-header">
      <h1 class="home-title">数据库日志分析平台</h1>
      <p class="home-subtitle">选择数据库类型，开始智能分析</p>
    </div>

    <div class="db-cards">
      <!-- MySQL 卡片：使用多重事件绑定确保移动端可点击 -->
      <div
        class="db-card mysql-card"
        @click="handleMysqlClick"
        @touchend.passive="handleMysqlTouch"
        role="button"
        tabindex="0"
        aria-label="进入 MySQL 分析"
      >
        <div class="db-card-icon">
          <svg viewBox="0 0 64 64" width="56" height="56">
            <ellipse cx="32" cy="12" rx="22" ry="8" fill="#00758F" opacity="0.9"/>
            <path d="M10 12 v40 c0 4.4 9.8 8 22 8 s22-3.6 22-8 V12" fill="none" stroke="#00758F" stroke-width="2.5"/>
            <path d="M10 28 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#00758F" stroke-width="2"/>
            <path d="M10 44 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#00758F" stroke-width="2"/>
          </svg>
        </div>
        <div class="db-card-info">
          <h2 class="db-card-name">MySQL</h2>
          <p class="db-card-desc">错误日志自动发现与分析</p>
        </div>
        <div class="db-card-status">
          <span class="status-dot active"></span>
          <span class="status-text">已就绪</span>
        </div>
        <div class="db-card-arrow">→</div>
      </div>

      <div class="db-card disabled">
        <div class="db-card-icon">
          <svg viewBox="0 0 64 64" width="56" height="56">
            <ellipse cx="32" cy="12" rx="22" ry="8" fill="#336791" opacity="0.5"/>
            <path d="M10 12 v40 c0 4.4 9.8 8 22 8 s22-3.6 22-8 V12" fill="none" stroke="#336791" stroke-width="2.5" opacity="0.5"/>
            <path d="M10 28 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#336791" stroke-width="2" opacity="0.5"/>
            <path d="M10 44 c0 4.4 9.8 8 22 8 s22-3.6 22-8" fill="none" stroke="#336791" stroke-width="2" opacity="0.5"/>
          </svg>
        </div>
        <div class="db-card-info">
          <h2 class="db-card-name">PostgreSQL</h2>
          <p class="db-card-desc">即将支持</p>
        </div>
        <div class="db-card-status">
          <span class="status-dot"></span>
          <span class="status-text">规划中</span>
        </div>
        <div class="db-card-badge">即将推出</div>
      </div>

      <!-- Redis 卡片：已支持 -->
      <div
        class="db-card redis-card"
        @click="handleRedisClick"
        @touchend.passive="handleRedisTouch"
        role="button"
        tabindex="0"
        aria-label="进入 Redis 分析"
      >
        <div class="db-card-icon">
          <svg viewBox="0 0 64 64" width="56" height="56">
            <rect x="12" y="14" width="40" height="10" rx="2" fill="#DC382D" opacity="0.9"/>
            <rect x="12" y="27" width="40" height="10" rx="2" fill="#DC382D" opacity="0.75"/>
            <rect x="12" y="40" width="40" height="10" rx="2" fill="#DC382D" opacity="0.6"/>
            <path d="M12 14 L32 4 L52 14" fill="none" stroke="#DC382D" stroke-width="2.5" opacity="0.9"/>
            <path d="M32 4 L32 50" stroke="#DC382D" stroke-width="1.5" opacity="0.4"/>
          </svg>
        </div>
        <div class="db-card-info">
          <h2 class="db-card-name">Redis</h2>
          <p class="db-card-desc">实时监控与慢查询分析</p>
        </div>
        <div class="db-card-status">
          <span class="status-dot active"></span>
          <span class="status-text">已就绪</span>
        </div>
        <div class="db-card-arrow">→</div>
      </div>
    </div>

    <div class="home-footer">
      <span>DB Log Analyzer v1.0</span>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

// 防止重复触发
let navigating = false

function navigateToMysql() {
  if (navigating) return
  navigating = true
  console.log('[Home] 导航到 MySQL (SPA)')
  router.push('/mysql').catch(() => {})
  // 1秒后重置锁，允许后续导航
  setTimeout(() => { navigating = false }, 1000)
}

function handleMysqlClick(e) {
  e.preventDefault()
  navigateToMysql()
}

function handleMysqlTouch(e) {
  // touchend 触发后不再触发 click（移动端）
  e.preventDefault()
  navigateToMysql()
}

// Redis 导航
function navigateToRedis() {
  if (navigating) return
  navigating = true
  console.log('[Home] 导航到 Redis (SPA)')
  router.push('/redis').catch(() => {})
  setTimeout(() => { navigating = false }, 1000)
}

function handleRedisClick(e) {
  e.preventDefault()
  navigateToRedis()
}

function handleRedisTouch(e) {
  e.preventDefault()
  navigateToRedis()
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
  margin-bottom: 48px;
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
  grid-template-columns: repeat(2, 320px);
  gap: 20px;
  max-width: 700px;
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

/* MySQL 卡片特殊样式 */
.db-card.mysql-card:hover {
  border-color: var(--accent-blue);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.12);
}

.db-card.mysql-card:active {
  transform: scale(0.98);
  background: var(--bg-hover);
}

/* Redis 卡片特殊样式 */
.db-card.redis-card:hover {
  border-color: #DC382D;
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(220, 56, 45, 0.12);
}

.db-card.redis-card:active {
  transform: scale(0.98);
  background: var(--bg-hover);
}

.db-card.disabled {
  cursor: default;
  opacity: 0.6;
}

.db-card-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
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
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
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

.db-card-arrow {
  font-size: 20px;
  color: var(--accent-blue);
  opacity: 0;
  transition: opacity 0.2s, transform 0.2s;
}

.db-card.mysql-card:hover .db-card-arrow {
  opacity: 1;
  transform: translateX(4px);
}

.db-card.redis-card:hover .db-card-arrow {
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

.home-footer {
  margin-top: 48px;
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

  /* 移动端 MySQL 卡片：增加点击区域和反馈 */
  .db-card.mysql-card {
    min-height: 72px;
    border-width: 1.5px;
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
}
</style>
