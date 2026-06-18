/**
 * 统一的 Markdown 渲染工具
 *
 * 替代各组件中重复的 renderMarkdown 实现。
 * 使用 marked 解析，失败时降级为简单的换行替换。
 */
import { marked } from 'marked'

/**
 * 渲染 Markdown 文本为 HTML
 * 用于：ChatPanel（MySQL/Redis 通用）, AnalysisReport
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch {
    return text.replace(/\n/g, '<br>')
  }
}
