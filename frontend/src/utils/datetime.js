/**
 * 统一的时间格式化工具
 *
 * 替代各组件中重复的 formatTime/formatTimestamp 实现。
 * 保留原有组件中的所有格式变体，确保替换后显示行为完全一致。
 */

/**
 * 完整日期时间：YYYY-MM-DD HH:mm:ss
 * 用于：LogSearch
 */
export function formatDateTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '-'
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/**
 * 日期时间到分钟：YYYY-MM-DD HH:mm
 * 用于：InspectionPanel, DiagnosisPanel, RedisReports, ReportPanel, InstancesPanel
 */
export function formatDateTimeMinute(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '-'
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 短日期时间：M/D H:mm（月/日/时 不补零，分补零）
 * 用于：PatternPanel, Dashboard, StatusPanel
 */
export function formatTimeShort(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '-'
  const month = d.getMonth() + 1
  const day = d.getDate()
  const hour = d.getHours()
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${hour}:${min}`
}

/**
 * 短日期时间含秒：M/D HH:mm:ss（月/日不补零，时分秒补零）
 * 用于：BaselinePanel, RedisBaseline
 */
export function formatTimeShortWithSeconds(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '-'
  const month = d.getMonth() + 1
  const day = d.getDate()
  const pad = n => String(n).padStart(2, '0')
  return `${month}/${day} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/**
 * 时间戳格式化（支持 Unix 秒级/毫秒级时间戳）
 * 用于：RedisSlowlog, RedisPersistence
 */
export function formatTimestamp(val) {
  if (!val) return '-'
  const num = Number(val)
  // Unix 秒级时间戳
  if (!isNaN(num) && num > 1e9 && num < 1e12) {
    const d = new Date(num * 1000)
    return d.toLocaleString('zh-CN', { hour12: false })
  }
  // Unix 毫秒级时间戳
  if (!isNaN(num) && num > 1e12) {
    const d = new Date(num)
    return d.toLocaleString('zh-CN', { hour12: false })
  }
  return String(val)
}

/**
 * 时长格式化（秒 → h/m/s/ms）
 * 用于：SlowQuery 的 formatTime（实际是时长而非日期）
 */
export function formatDuration(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  if (num >= 3600) return (num / 3600).toFixed(2) + 'h'
  if (num >= 60) return (num / 60).toFixed(2) + 'm'
  if (num >= 1) return num.toFixed(2) + 's'
  return (num * 1000).toFixed(0) + 'ms'
}

/**
 * 仅时间：HH:mm:ss
 * 用于：App.vue 的 formatLogTime（错误日志时间显示）
 */
export function formatLogTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
