<template>
  <div class="knowledge-graph">
    <div class="graph-toolbar">
      <button class="btn-secondary" @click="loadGraph">刷新</button>
      <button class="btn-secondary" @click="resetZoom">重置视图</button>
      <span class="toolbar-hint">拖拽节点 | 滚轮缩放 | 点击查看详情</span>
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
          <marker id="arrowhead-redis" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" :fill="edgeColor" />
          </marker>
          <!-- 发光效果 -->
          <filter id="glow-redis">
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
              :marker-end="edge.highlight ? 'url(#arrowhead-redis)' : ''"
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
              filter="url(#glow-redis)"
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
      <p class="hint">请先确保 Redis 实例已连接，然后点击刷新</p>
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
        <div class="detail-row" v-if="selectedNode.value !== undefined && selectedNode.value !== null">
          <span class="detail-label">数值</span>
          <span class="detail-value">{{ selectedNode.value }}</span>
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
import { truncate } from '../utils/format.js'

export default {
  name: 'RedisKnowledgeGraph',
  setup() {
    const svgRef = ref(null)
    const containerRef = ref(null)
    const selectedNode = ref(null)
    const loading = ref(false)
    const nodes = ref([])
    const edges = ref([])
    const svgWidth = ref(800)
    const svgHeight = ref(500)
    const zoom = ref(1)
    const panX = ref(0)
    const panY = ref(0)

    const typeColors = {
      center: '#dc2626',
      server: '#3b82f6',
      memory: '#f59e0b',
      slowlog: '#ef4444',
      keyspace: '#10b981',
      persistence: '#8b5cf6',
      replication: '#06b6d4',
      client: '#ec4899'
    }

    const typeLabels = {
      center: '中心',
      server: '服务器',
      memory: '内存',
      slowlog: '慢查询',
      keyspace: '键空间',
      persistence: '持久化',
      replication: '复制',
      client: '客户端'
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

    function nodeRadius(node) {
      if (node.type === 'center') return 28
      if (node.count > 50) return 22
      if (node.count > 20) return 18
      if (node.count > 5) return 15
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
        const cx = svgWidth.value / 2
        const cy = svgHeight.value / 2
        const newNodes = []
        const newEdges = []
        let edgeIdx = 0

        // 中心节点
        const centerNode = {
          id: 'center', name: 'Redis 运维', type: 'center',
          color: typeColors.center, x: cx, y: cy, vx: 0, vy: 0, fixed: false, count: 0
        }
        newNodes.push(centerNode)

        // 并行请求数据
        const [statusRes, memoryRes, slowlogRes, keyspaceRes] = await Promise.allSettled([
          api.getRedisStatus(),
          api.getRedisMemory(),
          api.getRedisSlowlogStats(),
          api.getRedisKeyspace()
        ])

        const statusData = statusRes.status === 'fulfilled' ? (statusRes.value.data || {}) : {}
        const memoryData = memoryRes.status === 'fulfilled' ? (memoryRes.value.data || {}) : {}
        const slowlogData = slowlogRes.status === 'fulfilled' ? (slowlogRes.value.data || {}) : {}
        const keyspaceData = keyspaceRes.status === 'fulfilled' ? (keyspaceRes.value.data || {}) : {}

        let nodeIdx = 0
        const typeAngles = {
          server: -Math.PI / 2,
          memory: -Math.PI / 6,
          slowlog: Math.PI / 6,
          keyspace: Math.PI / 2,
          persistence: 5 * Math.PI / 6,
          replication: 7 * Math.PI / 6,
          client: -5 * Math.PI / 6
        }
        const typeRadius = 180

        // ── server 节点 ──────────────────────────────────
        const serverInfo = statusData.server || statusData.Server || {}
        const serverItems = []

        if (serverInfo.redis_version || serverInfo.version) {
          serverItems.push({
            name: '版本 ' + (serverInfo.redis_version || serverInfo.version),
            value: serverInfo.redis_version || serverInfo.version,
            suggestion: '建议使用 Redis 6.0+ 以获得更好的性能和安全性'
          })
        }
        if (serverInfo.redis_mode || serverInfo.mode) {
          serverItems.push({
            name: '模式 ' + (serverInfo.redis_mode || serverInfo.mode),
            value: serverInfo.redis_mode || serverInfo.mode,
            suggestion: 'Cluster 模式支持水平扩展，Standalone 适合小规模场景'
          })
        }
        if (serverInfo.uptime_in_seconds || serverInfo.uptime) {
          const uptime = parseInt(serverInfo.uptime_in_seconds || serverInfo.uptime)
          const days = Math.floor(uptime / 86400)
          serverItems.push({
            name: '运行 ' + days + ' 天',
            value: days + ' 天 (' + uptime + ' 秒)',
            suggestion: days < 1 ? 'Redis 刚重启，请关注是否有异常崩溃' : '运行稳定'
          })
        }

        serverItems.forEach((item, i) => {
          const angle = typeAngles.server + (i - (serverItems.length - 1) / 2) * 0.3
          const r = typeRadius
          const node = {
            id: 'server_' + nodeIdx++, name: item.name, type: 'server',
            color: typeColors.server, value: item.value, suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // ── memory 节点 ──────────────────────────────────
        const memItems = []

        const usedMemory = memoryData.used_memory_human || memoryData.used_memory
        if (usedMemory) {
          const usedBytes = memoryData.used_memory || 0
          const maxMemory = memoryData.maxmemory || 0
          let suggestion = '关注内存使用趋势'
          if (maxMemory > 0) {
            const usagePercent = ((usedBytes / maxMemory) * 100).toFixed(1)
            if (parseFloat(usagePercent) > 80) {
              suggestion = '内存使用率 ' + usagePercent + '%，建议扩容或优化淘汰策略'
            } else {
              suggestion = '内存使用率 ' + usagePercent + '%，状态正常'
            }
          }
          memItems.push({
            name: '使用 ' + (memoryData.used_memory_human || usedMemory),
            value: memoryData.used_memory_human || usedMemory,
            suggestion
          })
        }

        const fragRatio = memoryData.mem_fragmentation_ratio || memoryData.fragmentation_ratio
        if (fragRatio) {
          const ratio = parseFloat(fragRatio)
          let suggestion = '碎片率正常'
          if (ratio > 1.5) {
            suggestion = '碎片率过高 (' + ratio + ')，建议开启 activedefrag 或重启 Redis'
          } else if (ratio < 1.0) {
            suggestion = '碎片率低于 1.0，可能存在 swap 风险'
          }
          memItems.push({
            name: '碎片率 ' + fragRatio,
            value: fragRatio,
            suggestion
          })
        }

        const evictionPolicy = memoryData.maxmemory_policy || memoryData.eviction_policy
        if (evictionPolicy) {
          memItems.push({
            name: '淘汰 ' + evictionPolicy,
            value: evictionPolicy,
            suggestion: evictionPolicy === 'noeviction' ? '无淘汰策略，内存满时写入会报错' : '当前淘汰策略: ' + evictionPolicy
          })
        }

        memItems.forEach((item, i) => {
          const angle = typeAngles.memory + (i - (memItems.length - 1) / 2) * 0.3
          const r = typeRadius
          const node = {
            id: 'memory_' + nodeIdx++, name: item.name, type: 'memory',
            color: typeColors.memory, value: item.value, suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // ── slowlog 节点 ──────────────────────────────────
        const slowlogItems = []
        const commandDist = slowlogData.command_distribution || slowlogData.by_command || slowlogData.commands || []
        const topCommands = Array.isArray(commandDist) ? commandDist.slice(0, 5) : []

        topCommands.forEach(item => {
          const cmd = item.command || item.name || item.cmd
          const cnt = item.count || item.total || 0
          if (cmd) {
            slowlogItems.push({
              name: cmd,
              value: cnt + ' 次',
              count: cnt,
              suggestion: '频繁执行的慢命令，建议优化或拆分'
            })
          }
        })

        // Top 慢查询
        const topSlow = slowlogData.top_slow || slowlogData.top || []
        if (Array.isArray(topSlow) && topSlow.length > 0) {
          topSlow.slice(0, 3).forEach((item, i) => {
            const duration = item.duration || item.time || item.elapsed
            const cmd = item.command || item.cmd || ''
            if (duration || cmd) {
              slowlogItems.push({
                name: 'Top' + (i + 1) + ' ' + (cmd || '').substring(0, 8),
                value: duration ? duration + ' μs' : cmd,
                suggestion: '耗时较长，建议检查是否可以使用更高效的命令替代'
              })
            }
          })
        }

        slowlogItems.forEach((item, i) => {
          const angle = typeAngles.slowlog + (i - (slowlogItems.length - 1) / 2) * 0.25
          const r = typeRadius + 40
          const node = {
            id: 'slowlog_' + nodeIdx++, name: item.name, type: 'slowlog',
            color: typeColors.slowlog, value: item.value, count: item.count,
            suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // ── keyspace 节点 ──────────────────────────────────
        const keyspaceItems = []
        const dbs = keyspaceData.databases || keyspaceData.db || keyspaceData

        if (Array.isArray(dbs)) {
          dbs.forEach(item => {
            const dbName = item.db || item.name || ''
            const keys = item.keys || item.key_count || 0
            if (dbName) {
              keyspaceItems.push({
                name: dbName,
                value: keys + ' keys',
                count: keys,
                suggestion: keys > 1000000 ? 'Key 数量超过百万，建议关注过期策略和内存使用' : 'Key 数量正常'
              })
            }
          })
        } else if (typeof dbs === 'object') {
          Object.keys(dbs).forEach(dbName => {
            const dbInfo = dbs[dbName]
            const keys = dbInfo.keys || (typeof dbInfo === 'string' ? dbInfo : 0)
            keyspaceItems.push({
              name: dbName,
              value: keys + ' keys',
              count: typeof keys === 'number' ? keys : 0,
              suggestion: '关注该 DB 的 Key 增长趋势'
            })
          })
        }

        keyspaceItems.forEach((item, i) => {
          const angle = typeAngles.keyspace + (i - (keyspaceItems.length - 1) / 2) * 0.3
          const r = typeRadius
          const node = {
            id: 'keyspace_' + nodeIdx++, name: item.name, type: 'keyspace',
            color: typeColors.keyspace, value: item.value, count: item.count,
            suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // ── persistence 节点 ──────────────────────────────
        const persistenceInfo = statusData.persistence || statusData.Persistence || {}
        const persistenceItems = []

        const rdbStatus = persistenceInfo.rdb_last_bgsave_status || persistenceInfo.rdb_status
        if (rdbStatus) {
          persistenceItems.push({
            name: 'RDB ' + rdbStatus,
            value: rdbStatus,
            suggestion: rdbStatus === 'ok' ? 'RDB 快照正常' : 'RDB 快照异常，请检查磁盘空间和权限'
          })
        }

        const aofEnabled = persistenceInfo.aof_enabled || persistenceInfo.aof_status
        if (aofEnabled !== undefined) {
          const aofVal = aofEnabled === 1 || aofEnabled === '1' || aofEnabled === true || aofEnabled === 'ok'
          persistenceItems.push({
            name: 'AOF ' + (aofVal ? '已开启' : '未开启'),
            value: aofVal ? 'enabled' : 'disabled',
            suggestion: aofVal ? 'AOF 持久化已开启，数据安全性较高' : '建议开启 AOF 以提高数据持久性保障'
          })
        }

        persistenceItems.forEach((item, i) => {
          const angle = typeAngles.persistence + (i - (persistenceItems.length - 1) / 2) * 0.3
          const r = typeRadius
          const node = {
            id: 'persistence_' + nodeIdx++, name: item.name, type: 'persistence',
            color: typeColors.persistence, value: item.value, suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // ── replication 节点 ──────────────────────────────
        const replicationInfo = statusData.replication || statusData.Replication || {}
        const replicationItems = []

        const role = replicationInfo.role
        if (role) {
          replicationItems.push({
            name: '角色 ' + role,
            value: role,
            suggestion: role === 'master' ? '当前为主节点，关注从节点同步状态' : '当前为从节点，关注与主节点的连接状态'
          })
        }

        const connectedSlaves = replicationInfo.connected_slaves
        if (connectedSlaves !== undefined) {
          const slaveCount = parseInt(connectedSlaves)
          replicationItems.push({
            name: '从节点 ' + slaveCount,
            value: slaveCount + ' 个',
            suggestion: slaveCount === 0 ? '无从节点连接，如需高可用请配置从节点' : '从节点连接正常'
          })
        }

        replicationItems.forEach((item, i) => {
          const angle = typeAngles.replication + (i - (replicationItems.length - 1) / 2) * 0.3
          const r = typeRadius
          const node = {
            id: 'replication_' + nodeIdx++, name: item.name, type: 'replication',
            color: typeColors.replication, value: item.value, suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

        // ── client 节点 ──────────────────────────────────
        const clientsInfo = statusData.clients || statusData.Clients || {}
        const clientItems = []

        const connectedClients = clientsInfo.connected_clients || clientsInfo.count
        if (connectedClients !== undefined) {
          const count = parseInt(connectedClients)
          let suggestion = '客户端连接数正常'
          if (count > 500) {
            suggestion = '连接数较多 (' + count + ')，建议检查是否有连接泄漏'
          }
          clientItems.push({
            name: '连接 ' + count,
            value: count + ' 个',
            suggestion
          })
        }

        const blockedClients = clientsInfo.blocked_clients || clientsInfo.blocked
        if (blockedClients !== undefined) {
          const count = parseInt(blockedClients)
          clientItems.push({
            name: '阻塞 ' + count,
            value: count + ' 个',
            suggestion: count > 0 ? '存在阻塞客户端，可能是 BLPOP/BRPOP 等阻塞命令导致，或存在性能瓶颈' : '无阻塞客户端'
          })
        }

        clientItems.forEach((item, i) => {
          const angle = typeAngles.client + (i - (clientItems.length - 1) / 2) * 0.3
          const r = typeRadius
          const node = {
            id: 'client_' + nodeIdx++, name: item.name, type: 'client',
            color: typeColors.client, value: item.value, suggestion: item.suggestion,
            x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r,
            vx: 0, vy: 0, fixed: false
          }
          newNodes.push(node)
          newEdges.push({ id: 'e_' + edgeIdx++, source: centerNode, target: node, highlight: false })
        })

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
      svgRef, containerRef, selectedNode, loading,
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
  border-top-color: #dc2626;
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
