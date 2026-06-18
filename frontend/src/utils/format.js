/**
 * 统一的数值/字符串格式化工具
 *
 * 替代各组件中重复的 formatPercent/formatBytes/truncate 实现。
 */

/**
 * 百分比格式化：保留 1 位小数
 * 用于：CapacityPanel, RedisReports, RedisMemory, RedisPersistence,
 *      RedisMonitor, PatternPanel, MonitorPanel
 */
export function formatPercent(val) {
  if (val == null) return '-'
  const num = Number(val)
  if (isNaN(num)) return '-'
  return num.toFixed(1) + '%'
}

/**
 * 字节数格式化：自动转换为 B/KB/MB/GB/TB
 * 用于：RedisMemory, RedisMonitor, RedisKeys (as formatMemory)
 */
export function formatBytes(bytes) {
  if (bytes == null) return '-'
  const num = Number(bytes)
  if (isNaN(num) || num === 0) return '0B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(num) / Math.log(1024))
  return (num / Math.pow(1024, i)).toFixed(2) + units[i]
}

/**
 * 字符串截断：超长时添加省略号
 * 用于：DeadlockPanel, LogSearch, KnowledgeGraph, RedisKnowledgeGraph
 */
export function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.substring(0, len) + '...' : str
}
