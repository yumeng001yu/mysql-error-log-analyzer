<template>
  <div class="knowledge-graph">
    <div class="graph-toolbar">
      <button class="btn-secondary" @click="loadGraph">🔄 刷新</button>
      <button class="btn-secondary" @click="resetZoom">重置视图</button>
      <span class="toolbar-hint">拖拽节点 · 滚轮缩放 · 点击查看详情</span>
    </div>

    <div ref="graphRef" class="graph-container"></div>

    <!-- 节点详情面板 -->
    <div class="detail-panel" v-if="selectedNode">
      <div class="detail-header">
        <span>{{ selectedNode.name }}</span>
        <button class="close-btn" @click="selectedNode = null">✕</button>
      </div>
      <div class="detail-body">
        <div class="detail-row">
          <span class="detail-label">类型</span>
          <span class="detail-value">{{ nodeTypeLabel(selectedNode.type) }}</span>
        </div>
        <div class="detail-row" v-if="selectedNode.count">
          <span class="detail-label">出现次数</span>
          <span class="detail-value">{{ selectedNode.count }}</span>
        </div>
        <div class="detail-row" v-if="selectedNode.description">
          <span class="detail-label">描述</span>
          <span class="detail-value">{{ selectedNode.description }}</span>
        </div>
        <div class="detail-row" v-if="selectedNode.suggestion">
          <span class="detail-label">建议</span>
          <span class="detail-value">{{ selectedNode.suggestion }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api.js'

export default {
  name: 'KnowledgeGraph',
  setup() {
    const graphRef = ref(null)
    const selectedNode = ref(null)
    let chart = null

    const typeColors = {
      error_code: '#ef4444',
      category: '#f59e0b',
      root_cause: '#8b5cf6',
      suggestion: '#10b981'
    }

    const typeLabels = {
      error_code: '错误码',
      category: '错误类别',
      root_cause: '根因',
      suggestion: '修复建议'
    }

    function nodeTypeLabel(type) {
      return typeLabels[type] || type
    }

    function buildGraphData(data) {
      const nodes = []
      const links = []

      // 从分析结果构建图谱数据
      // 支持多种数据格式
      if (data.nodes && data.links) {
        // 直接提供图数据的格式
        data.nodes.forEach(n => {
          nodes.push({
            id: n.id || n.name,
            name: n.name || n.id,
            type: n.type || 'category',
            count: n.count || n.value || 1,
            description: n.description,
            suggestion: n.suggestion,
            symbolSize: Math.max(20, Math.min(60, (n.count || n.value || 1) * 2 + 15)),
            itemStyle: { color: typeColors[n.type] || '#3b82f6' },
            label: { show: true, fontSize: 11, color: '#e2e8f0' }
          })
        })
        data.links.forEach(l => {
          links.push({
            source: l.source,
            target: l.target,
            lineStyle: { color: '#334155', curveness: 0.2 }
          })
        })
      } else if (Array.isArray(data)) {
        // 从分析结果数组构建
        const nodeMap = new Map()

        data.forEach(item => {
          const cat = item.category || item.classification || '未知类别'
          const code = item.error_code || item.code || item.message?.substring(0, 30)
          const cause = item.root_cause || item.cause
          const suggestion = item.suggestion || item.fix

          // 添加类别节点
          if (!nodeMap.has('cat_' + cat)) {
            nodeMap.set('cat_' + cat, {
              id: 'cat_' + cat, name: cat, type: 'category',
              count: 1, symbolSize: 30, itemStyle: { color: typeColors.category },
              label: { show: true, fontSize: 11, color: '#e2e8f0' }
            })
          } else {
            nodeMap.get('cat_' + cat).count++
            nodeMap.get('cat_' + cat).symbolSize = Math.min(60, 30 + nodeMap.get('cat_' + cat).count * 3)
          }

          // 添加错误码节点
          if (code) {
            const codeId = 'code_' + code
            if (!nodeMap.has(codeId)) {
              nodeMap.set(codeId, {
                id: codeId, name: code, type: 'error_code',
                count: 1, symbolSize: 25, itemStyle: { color: typeColors.error_code },
                label: { show: true, fontSize: 10, color: '#e2e8f0' }
              })
              links.push({ source: codeId, target: 'cat_' + cat, lineStyle: { color: '#334155', curveness: 0.2 } })
            } else {
              nodeMap.get(codeId).count++
              nodeMap.get(codeId).symbolSize = Math.min(55, 25 + nodeMap.get(codeId).count * 2)
            }
          }

          // 添加根因节点
          if (cause) {
            const causeId = 'cause_' + cause
            if (!nodeMap.has(causeId)) {
              nodeMap.set(causeId, {
                id: causeId, name: cause.length > 20 ? cause.substring(0, 20) + '...' : cause,
                type: 'root_cause', description: cause, count: 1, symbolSize: 28,
                itemStyle: { color: typeColors.root_cause },
                label: { show: true, fontSize: 10, color: '#e2e8f0' }
              })
              links.push({ source: 'cat_' + cat, target: causeId, lineStyle: { color: '#334155', curveness: 0.2 } })
            }
          }

          // 添加建议节点
          if (suggestion) {
            const sugId = 'sug_' + suggestion
            if (!nodeMap.has(sugId)) {
              nodeMap.set(sugId, {
                id: sugId, name: suggestion.length > 20 ? suggestion.substring(0, 20) + '...' : suggestion,
                type: 'suggestion', suggestion, count: 1, symbolSize: 26,
                itemStyle: { color: typeColors.suggestion },
                label: { show: true, fontSize: 10, color: '#e2e8f0' }
              })
              const causeId = cause ? 'cause_' + cause : 'cat_' + cat
              links.push({ source: causeId, target: sugId, lineStyle: { color: '#334155', curveness: 0.2 } })
            }
          }
        })

        nodeMap.forEach(n => nodes.push(n))
      }

      return { nodes, links }
    }

    async function loadGraph() {
      try {
        const res = await api.getAnalysisResults()
        const data = res.data
        if (!data) return

        const graphData = buildGraphData(data)

        if (chart) {
          chart.setOption({
            backgroundColor: 'transparent',
            tooltip: {
              formatter: (params) => {
                if (params.dataType === 'node') {
                  return `<b>${params.name}</b><br/>类型: ${nodeTypeLabel(params.data.type)}<br/>次数: ${params.data.count || '-'}`
                }
                return `${params.data.source} → ${params.data.target}`
              }
            },
            series: [{
              type: 'graph',
              layout: 'force',
              roam: true,
              draggable: true,
              force: {
                repulsion: 300,
                edgeLength: [80, 200],
                gravity: 0.1
              },
              data: graphData.nodes,
              links: graphData.links,
              emphasis: {
                focus: 'adjacency',
                lineStyle: { width: 3 }
              },
              edgeSymbol: ['none', 'arrow'],
              edgeSymbolSize: 8,
              lineStyle: { opacity: 0.6 }
            }]
          })
        }
      } catch (e) { /* ignore */ }
    }

    function resetZoom() {
      if (chart) {
        chart.dispatchAction({ type: 'restore' })
      }
    }

    function handleResize() {
      chart?.resize()
    }

    onMounted(async () => {
      await nextTick()
      chart = echarts.init(graphRef.value, 'dark')
      chart.setOption({ backgroundColor: 'transparent' })

      chart.on('click', (params) => {
        if (params.dataType === 'node') {
          selectedNode.value = params.data
        }
      })

      loadGraph()
      window.addEventListener('resize', handleResize)
    })

    onUnmounted(() => {
      window.removeEventListener('resize', handleResize)
      chart?.dispose()
    })

    return {
      graphRef, selectedNode,
      nodeTypeLabel, loadGraph, resetZoom
    }
  }
}
</script>

<style scoped>
.knowledge-graph {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
}

.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn-secondary {
  padding: 6px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-secondary:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.toolbar-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}

.graph-container {
  height: calc(100vh - 200px);
  min-height: 500px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.detail-panel {
  position: absolute;
  top: 60px;
  right: 20px;
  width: 300px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 50;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  font-weight: 600;
  font-size: 14px;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
}

.close-btn:hover {
  color: var(--text-primary);
}

.detail-body {
  padding: 12px 16px;
}

.detail-row {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}

.detail-label {
  color: var(--text-muted);
  min-width: 60px;
}

.detail-value {
  color: var(--text-primary);
  flex: 1;
  word-break: break-all;
}
</style>
