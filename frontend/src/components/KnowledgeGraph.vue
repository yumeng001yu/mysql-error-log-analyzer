<template>
  <div class="knowledge-graph">
    <div class="graph-toolbar">
      <button class="btn-secondary" @click="loadGraph">刷新</button>
      <button class="btn-secondary" @click="resetZoom">重置视图</button>
      <span class="toolbar-hint">拖拽节点 | 滚轮缩放 | 点击查看详情</span>
      <span class="embedding-status" v-if="embeddingAvailable === false">Embedding 未配置</span>
      <span class="embedding-status success" v-if="embeddingAvailable === true">语义关联已加载</span>
    </div>

    <!-- SVG 力导向图谱 -->
    <div class="graph-container" ref="containerRef">
      <svg
        ref="svgRef"
        :width="svgWidth"
        :height="svgHeight"
        @wheel.prevent="onWheel"
        @mousedown="onSvgMouseDown"
        @mousemove="onSvgMouseMove"
        @mouseup="onSvgMouseUp"
        @mouseleave="onSvgMouseUp"
        @touchstart.prevent="onTouchStart"
        @touchmove.prevent="onTouchMove"
        @touchend="onTouchEnd"
      >
        <defs>
          <!-- 箭头标记 -->
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" :fill="edgeColor" />
          </marker>
          <!-- 发光效果 -->
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        <g :transform="`translate(${panX},${panY}) scale(${zoom})`">
          <!-- 边 -->
          <g class="edges">
            <line
              v-for="edge in edges"
              :key="edge.id"
              :x1="edge.source.x"
              :y1="edge.source.y"
              :x2="edge.target.x"
              :y2="edge.target.y"
              :stroke="edge.highlight ? edge.source.color : edgeColor"
              :stroke-width="edge.highlight ? 2.5 : 1.2"
              :stroke-opacity="edge.highlight ? 0.9 : 0.35"
              :marker-end="edge.highlight ? 'url(#arrowhead)' : ''"
            />
          </g>

          <!-- 节点 -->
          <g
            v-for="node in nodes"
            :key="node.id"
            :transform="`translate(${node.x},${node.y})`"
            class="graph-node"
            :class="{ selected: selectedNode && selectedNode.id === node.id, highlighted: node.highlighted }"
            @mousedown.stop.prevent="onNodeMouseDown(node, $event)"
            @touchstart.stop.prevent="onNodeTouchStart(node, $event)"
            @click.stop="selectNode(node)"
          >
            <!-- 外圈光晕 -->
            <circle
              v-if="node.highlighted || (selectedNode && selectedNode.id === node.id)"
              :r="nodeRadius(node) + 6"
              fill="none"
              :stroke="node.color"
              stroke-width="2"
              stroke-opacity="0.4"
              filter="url(#glow)"
            />
            <!-- 节点圆 -->
            <circle
              :r="nodeRadius(node)"
              :fill="node.color"
              fill-opacity="0.85"
              :stroke="node.color"
              stroke-width="2"
              stroke-opacity="0.3"
            />
            <!-- 节点文字 -->
            <text
              :dy="nodeRadius(node) + 14"
              text-anchor="middle"
              fill="var(--text-primary)"
              font-size="11"
              font-weight="500"
            >{{ truncate(node.name, 12) }}</text>
            <!-- 计数徽标 -->
            <text
              v-if="node.count"
              text-anchor="middle"
              dy="4"
              fill="#fff"
              font-size="10"
              font-weight="700"
            >{{ node.count > 99 ? '99+' : node.count }}</text>
          </g>
        </g>
      </svg>

      <!-- 图例 -->
      <div class="graph-legend">
        <div class="legend-item" v-for="(color, type) in typeColors" :key="type">
          <span class="legend-dot" :style="{ background: color }"></span>
          <span class="legend-label">{{ typeLabels[type] }}</span>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="nodes.length === 0 && !loading" class="empty-state">
      <p>暂无图谱数据</p>
      <p class="hint">请先确保有日志数据，然后点击刷新</p>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>正在构建知识图谱...</p>
    </div>

    <!-- 节点详情面板 -->
    <div class="detail-panel" v-if="selectedNode">
      <div class="detail-header">
        <span class="detail-type-dot" :style="{ background: selectedNode.color }"></span>
        <span class="detail-name">{{ selectedNode.name }}</span>
        <button class="close-btn" @click="selectedNode = null">&times;</button>
      </div>
      <div class="detail-body">
        <div class="detail-row">
          <span class="detail-label">类型</span>
          <span class="detail-value">{{ typeLabels[selectedNode.type] || selectedNode.type }}</span>
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
        <!-- 关联节点 -->
        <div class="detail-row" v-if="relatedNodes.length > 0">
          <span class="detail-label">关联</span>
          <div class="related-list">
            <span
              v-for="rn in relatedNodes"
              :key="rn.id"
              class="related-tag"
              :style="{ borderColor: rn.color, color: rn.color }"
              @click="selectNode(rn)"
            >{{ truncate(rn.name, 10) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { api } from '../api.js'

export default {
  name: 'KnowledgeGraph',
  setup() {
    const svgRef = ref(null)
    const containerRef = ref(null)
    const selectedNode = ref(null)
    const embeddingAvailable = ref(null)
    const loading = ref(false)
    const nodes = ref([])
    const edges = ref([])
    const svgWidth = ref(800)
    const svgHeight = ref(500)
    const zoom = ref(1)
    const panX = ref(0)
    const panY = ref(0)

    const typeColors = {
      center: '#6366f1',
      level: '#3b82f6',
      category: '#f59e0b',
      error_code: '#ef4444',
      root_cause: '#8b5cf6',
      suggestion: '#10b981',
      semantic: '#ec4899'
    }

    const typeLabels = {
      center: '中心',
      level: '错误级别',
      category: '错误类别',
      error_code: '错误码',
      root_cause: '根因',
      suggestion: '修复建议',
      semantic: '语义关联'
    }

    const edgeColor = '#555'

    // 力模拟参数
    let animFrame = null
    let simRunning = false
    const SIM_ALPHA_DECAY = 0.02
    const SIM_VELOCITY_DECAY = 0.4
    let simAlpha = 1

    // 拖拽状态
    let draggingNode = null
    let dragOffsetX = 0
    let dragOffsetY = 0
    let isPanning = false
    let panStartX = 0
    let panStartY = 0
    let panStartPanX = 0
    let panStartPanY = 0

    // 关联节点
    const relatedNodes = computed(() => {
      if (!selectedNode.value) return []
      const ids = new Set()
      edges.value.forEach(e => {
        if (e.source.id === selectedNode.value.id) ids.add(e.target.id)
        if (e.target.id === selectedNode.value.id) ids.add(e.source.id)
      })
      return nodes.value.filter(n => ids.has(n.id))
    })

    function truncate(str, len) {
      if (!str) return ''
      return str.length > len ? str.substring(0, len) + '...' : str
    }

    function nodeRadius(node) {
      if (node.type === 'center') return 28
      if (node.count > 50) return 22
      if (node.count > 20) return 18
      if (node.count > 5) return 15
      if (node.type === 'suggestion') return 13
      return 12
    }

    // ── 力模拟 ──────────────────────────────────────────────
    function startSimulation() {
      simAlpha = 1
      simRunning = true
      tick()
    }

    function tick() {
      if (!simRunning) return
      if (simAlpha < 0.001) {
        simRunning = false
        return
      }

      const cx = svgWidth.value / 2
      const cy = svgHeight.value / 2

      // 斥力（节点间）
      for (let i = 0; i < nodes.value.length; i++) {
        for (let j = i + 1; j < nodes.value.length; j++) {
          const a = nodes.value[i]
          const b = nodes.value[j]
          let dx = b.x - a.x
          let dy = b.y - a.y
          let dist = Math.sqrt(dx * dx + dy * dy) || 1
          const minDist = nodeRadius(a) + nodeRadius(b) + 30
          const repulsion = (minDist * minDist) / dist
          const fx = (dx / dist) * repulsion * simAlpha * 0.05
          const fy = (dy / dist) * repulsion * simAlpha * 0.05
          if (!a.fixed) { a.vx = (a.vx || 0) - fx; a.vy = (a.vy || 0) - fy }
          if (!b.fixed) { b.vx = (b.vx || 0) + fx; b.vy = (b.vy || 0) + fy }
        }
      }

      // 引力（沿边）
      edges.value.forEach(e => {
        const a = e.source
        const b = e.target
        let dx = b.x - a.x
        let dy = b.y - a.y
        let dist = Math.sqrt(dx * dx + dy * dy) || 1
        const idealLen = 120
        const attraction = (dist - idealLen) * simAlpha * 0.003
        const fx = (dx / dist) * attraction
        const fy = (dy / dist) * attraction
        if (!a.fixed) { a.vx = (a.vx || 0) + fx; a.vy = (a.vy || 0) + fy }
        if (!b.fixed) { b.vx = (b.vx || 0) - fx; b.vy = (b.vy || 0) - fy }
      })

      // 中心引力
      nodes.value.forEach(n => {
        if (n.fixed) return
        n.vx = (n.vx || 0) + (cx - n.x) * simAlpha * 0.001
        n.vy = (n.vy || 0) + (cy - n.y) * simAlpha * 0.001
      })

      // 更新位置
      nodes.value.forEach(n => {
        if (n.fixed) return
        n.vx = (n.vx || 0) * SIM_VELOCITY_DECAY
        n.vy = (n.vy || 0) * SIM_VELOCITY_DECAY
        n.x += n.vx
        n.y += n.vy
        // 边界约束
        const r = nodeRadius(n)
        n.x = Math.max(r, Math.min(svgWidth.value - r, n.x))
        n.y = Math.max(r, Math.min(svgHeight.value - r, n.y))
      })

      simAlpha *= (1 - SIM_ALPHA_DECAY)
      animFrame = requestAnimationFrame(tick)
    }

    function stopSimulation() {
      simRunning = false
      if (animFrame) {
        cancelAnimationFrame(animFrame)
        animFrame = null
      }
    }

    // ── 交互 ──────────────────────────────────────────────
    function selectNode(node) {
      selectedNode.value = node
      // 高亮关联节点和边
      nodes.value.forEach(n => { n.highlighted = false })
      edges.value.forEach(e => { e.highlight = false })
      if (node) {
        const relatedIds = new Set()
        edges.value.forEach(e => {
          if (e.source.id === node.id) { e.highlight = true; relatedIds.add(e.target.id) }
          if (e.target.id === node.id) { e.highlight = true; relatedIds.add(e.source.id) }
        })
        nodes.value.forEach(n => { if (relatedIds.has(n.id)) n.highlighted = true })
      }
    }

    function onNodeMouseDown(node, e) {
      draggingNode = node
      node.fixed = true
      dragOffsetX = e.clientX / zoom.value - node.x
      dragOffsetY = e.clientY / zoom.value - node.y
      // 重启模拟
      if (!simRunning) { simAlpha = 0.3; simRunning = true; tick() }
    }

    function onNodeTouchStart(node, e) {
      if (e.touches.length === 1) {
        draggingNode = node
        node.fixed = true
        const touch = e.touches[0]
        dragOffsetX = touch.clientX / zoom.value - node.x
        dragOffsetY = touch.clientY / zoom.value - node.y
        if (!simRunning) { simAlpha = 0.3; simRunning = true; tick() }
      }
    }

    function onSvgMouseDown(e) {
      isPanning = true
      panStartX = e.clientX
      panStartY = e.clientY
      panStartPanX = panX.value
      panStartPanY = panY.value
    }

    function onSvgMouseMove(e) {
      if (draggingNode) {
        draggingNode.x = e.clientX / zoom.value - dragOffsetX
        draggingNode.y = e.clientY / zoom.value - dragOffsetY
      } else if (isPanning) {
        panX.value = panStartPanX + (e.clientX - panStartX)
        panY.value = panStartPanY + (e.clientY - panStartY)
      }
    }

    function onSvgMouseUp() {
      if (draggingNode) {
        draggingNode.fixed = false
        draggingNode = null
      }
      isPanning = false
    }

    function onTouchStart(e) {
      if (e.touches.length === 1 && !draggingNode) {
        isPanning = true
        panStartX = e.touches[0].clientX
        panStartY = e.touches[0].clientY
        panStartPanX = panX.value
        panStartPanY = panY.value
      }
    }

    function onTouchMove(e) {
      if (draggingNode && e.touches.length === 1) {
        const touch = e.touches[0]
        draggingNode.x = touch.clientX / zoom.value - dragOffsetX
        draggingNode.y = touch.clientY / zoom.value - dragOffsetY
      } else if (isPanning && e.touches.length === 1) {
        panX.value = panStartPanX + (e.touches[0].clientX - panStartX)
        panY.value = panStartPanY + (e.touches[0].clientY - panStartY)
      }
    }

    function onTouchEnd() {
      if (draggingNode) {
        draggingNode.fixed = false
        draggingNode = null
      }
      isPanning = false
    }

    function onWheel(e) {
      const delta = e.deltaY > 0 ? 0.9 : 1.1
      zoom.value = Math.max(0.3, Math.min(3, zoom.value * delta))
    }

    function resetZoom() {
      zoom.value = 1
      panX.value = 0
      panY.value = 0
    }

    // ── 数据加载 ──────────────────────────────────────────
    async function loadGraph() {
      loading.value = true
      stopSimulation()
      try {
        const distRes = await api.getLogDistribution({ period: '7d' })
        const distData = distRes.data || {}

        const byLevel = distData.by_level || []
        const byCategory = distData.by_category || []
        const byErrorCode = distData.by_error_code || []

        const cx = svgWidth.value / 2
        const cy = svgHeight.value / 2
        const newNodes = []
        const newEdges = []
        let edgeIdx = 0

        // 中心节点
        const centerNode = {
          id: 'center', name: 'MySQL 错误', type: 'center',
          color: typeColors.center, x: cx, y: cy, vx: 0, vy: 0, fixed: false, count: 0
        }
        newNodes.push(centerNode)

        // 级别节点
        byLevel.forEach((item, i) => {
          const angle = (2 * Math.PI * i) / Math.max(byLevel.length, 1) - Math.PI / 2
          const r = 160
          const node = {
            id: 'level_' + item.level, name: item.level, type: 'level',
            color: typeColors.level, count: item.count,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // 类别节点
        byCategory.forEach((item, i) => {
          const angle = (2 * Math.PI * i) / Math.max(byCategory.length, 1)
          const r = 260
          const node = {
            id: 'cat_' + item.category, name: item.category, type: 'category',
            color: typeColors.category, count: item.count,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // 错误码节点 - 连接到对应类别
        const catNodeMap = {}
        newNodes.forEach(n => { if (n.type === 'category') catNodeMap[n.name] = n })

        byErrorCode.slice(0, 20).forEach((item, i) => {
          const angle = (2 * Math.PI * i) / Math.max(Math.min(byErrorCode.length, 20), 1) + 0.5
          const r = 340
          const node = {
            id: 'code_' + item.error_code, name: item.error_code, type: 'error_code',
            color: typeColors.error_code, count: item.count,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          // 连接到中心
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // 建议节点
        try {
          const analysisRes = await api.getAnalysisResults()
          const analysisData = analysisRes.data || {}
          const suggestions = analysisData.suggestions || []
          suggestions.slice(0, 8).forEach((s, i) => {
            const angle = (2 * Math.PI * i) / Math.max(Math.min(suggestions.length, 8), 1) + Math.PI
            const r = 200
            const node = {
              id: 'sug_' + i, name: (s.suggestion || s.category || '').substring(0, 20),
              type: 'suggestion', color: typeColors.suggestion,
              suggestion: s.suggestion, description: s.description,
              x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
              vx: 0, vy: 0, fixed: false
            }
            newNodes.push(node)
            newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
          })
        } catch { /* ignore */ }

        nodes.value = newNodes
        edges.value = newEdges
        selectedNode.value = null

        await nextTick()
        startSimulation()
      } catch (e) {
        console.error('loadGraph error', e)
      } finally {
        loading.value = false
      }
    }

    // ── 尺寸自适应 ────────────────────────────────────────
    function updateSize() {
      if (containerRef.value) {
        svgWidth.value = containerRef.value.clientWidth
        svgHeight.value = Math.max(400, containerRef.value.clientHeight)
      }
    }

    onMounted(() => {
      updateSize()
      window.addEventListener('resize', updateSize)
      loadGraph()
    })

    onUnmounted(() => {
      stopSimulation()
      window.removeEventListener('resize', updateSize)
    })

    return {
      svgRef, containerRef, selectedNode, embeddingAvailable, loading,
      nodes, edges, svgWidth, svgHeight, zoom, panX, panY,
      typeColors, typeLabels, edgeColor, relatedNodes,
      truncate, nodeRadius, selectNode, loadGraph, resetZoom,
      onWheel, onSvgMouseDown, onSvgMouseMove, onSvgMouseUp,
      onTouchStart, onTouchMove, onTouchEnd,
      onNodeMouseDown, onNodeTouchStart
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
  height: 100%;
}

.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
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

.embedding-status {
  font-size: 11px;
  color: var(--accent-yellow, #f59e0b);
  padding: 2px 8px;
  background: rgba(245,158,11,0.1);
  border-radius: 3px;
}

.embedding-status.success {
  color: var(--accent-green, #10b981);
  background: rgba(16,185,129,0.1);
}

.graph-container {
  flex: 1;
  min-height: 420px;
  background: var(--bg-card, #1a1a2e);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  overflow: hidden;
  position: relative;
}

.graph-container svg {
  display: block;
  cursor: grab;
}

.graph-container svg:active {
  cursor: grabbing;
}

.graph-node {
  cursor: pointer;
  transition: opacity 0.2s;
}

.graph-node:hover circle {
  stroke-opacity: 0.8;
  stroke-width: 3;
}

.graph-node.selected circle {
  stroke-opacity: 1;
  stroke-width: 3;
}

.graph-node.highlighted circle {
  fill-opacity: 1;
}

/* 图例 */
.graph-legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: rgba(0,0,0,0.6);
  padding: 8px 12px;
  border-radius: 6px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  font-size: 11px;
  color: #ccc;
}

/* 空状态 / 加载 */
.empty-state, .loading-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-muted);
}

.loading-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border-color, #333);
  border-top-color: var(--accent-blue, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 详情面板 */
.detail-panel {
  position: absolute;
  top: 60px;
  right: 20px;
  width: 300px;
  background: var(--bg-card, #1e1e2e);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  z-index: 50;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #333);
}

.detail-type-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.detail-name {
  flex: 1;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.close-btn:hover {
  color: var(--text-primary);
}

.detail-body {
  padding: 12px 16px;
}

.detail-row {
  padding: 6px 0;
  font-size: 13px;
}

.detail-label {
  color: var(--text-muted);
  margin-right: 8px;
}

.detail-value {
  color: var(--text-primary);
  word-break: break-all;
}

.related-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.related-tag {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.2s;
}

.related-tag:hover {
  background: rgba(255,255,255,0.08);
}

/* 移动端适配 */
@media (max-width: 768px) {
  .graph-toolbar {
    flex-wrap: wrap;
    gap: 6px;
  }

  .toolbar-hint {
    display: none;
  }

  .graph-container {
    min-height: 320px;
  }

  .detail-panel {
    position: fixed;
    top: auto;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    border-radius: 12px 12px 0 0;
    max-height: 50vh;
    overflow-y: auto;
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }

  .graph-legend {
    bottom: 8px;
    left: 8px;
    padding: 6px 8px;
    gap: 6px;
  }

  .legend-label {
    font-size: 10px;
  }
}
</style>
