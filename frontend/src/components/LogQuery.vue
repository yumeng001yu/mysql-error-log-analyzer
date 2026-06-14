<template>
  <div class="log-query">
    <!-- 筛选条件 -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>实例</label>
        <select v-model="filters.instance">
          <option value="">全部实例</option>
          <option v-for="inst in instances" :key="inst" :value="inst">{{ inst }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>级别</label>
        <select v-model="filters.level">
          <option value="">全部级别</option>
          <option value="ERROR">ERROR</option>
          <option value="WARNING">WARNING</option>
          <option value="NOTE">NOTE</option>
          <option value="INFO">INFO</option>
          <option value="SYSTEM">SYSTEM</option>
        </select>
      </div>
      <div class="filter-group">
        <label>开始时间</label>
        <input type="datetime-local" v-model="filters.start_time" />
      </div>
      <div class="filter-group">
        <label>结束时间</label>
        <input type="datetime-local" v-model="filters.end_time" />
      </div>
      <div class="filter-group">
        <label>关键词</label>
        <input type="text" v-model="filters.keyword" placeholder="搜索关键词" />
      </div>
      <div class="filter-group">
        <label>快捷时段</label>
        <select v-model="filters.period" @change="applyPeriod">
          <option value="">自定义时间</option>
          <option value="1h">最近1小时</option>
          <option value="3h">最近3小时</option>
          <option value="5h">最近5小时</option>
          <option value="12h">最近12小时</option>
          <option value="24h">最近24小时</option>
          <option value="7d">最近7天</option>
          <option value="30d">最近30天</option>
        </select>
      </div>
      <button class="btn-semantic" @click="semanticSearch" :disabled="!filters.keyword">🔍 语义搜索</button>
      <button class="btn-primary" @click="search">查询</button>
      <button class="btn-secondary" @click="exportLogs">导出</button>
    </div>

    <!-- 日志表格 -->
    <div class="table-wrapper">
      <table class="log-table">
        <thead>
          <tr>
            <th class="col-time" @click="sortBy('timestamp')">
              时间 {{ sortKey === 'timestamp' ? (sortAsc ? '↑' : '↓') : '' }}
            </th>
            <th class="col-instance">实例</th>
            <th class="col-level">级别</th>
            <th class="col-msg">消息</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(log, idx) in logs" :key="idx">
            <tr @click="toggleExpand(idx)" class="log-row">
              <td class="col-time">{{ formatTime(log.timestamp) }}</td>
              <td class="col-instance">{{ log.instance || '-' }}</td>
              <td>
                <span class="level-tag" :class="log.level?.toLowerCase()">{{ log.level }}</span>
              </td>
              <td class="col-msg">{{ truncate(log.message || log.content, 100) }}</td>
            </tr>
            <tr v-if="expanded === idx" class="detail-row">
              <td colspan="4">
                <div class="log-detail">
                  <div v-if="log.timestamp"><strong>时间：</strong>{{ log.timestamp }}</div>
                  <div v-if="log.instance"><strong>实例：</strong>{{ log.instance }}</div>
                  <div v-if="log.level"><strong>级别：</strong>{{ log.level }}</div>
                  <div v-if="log.error_code"><strong>错误码：</strong>{{ log.error_code }}</div>
                  <div v-if="log.category"><strong>类别：</strong>{{ log.category }}</div>
                  <div v-if="log.message || log.content">
                    <strong>消息：</strong>
                    <pre class="msg-pre">{{ log.message || log.content }}</pre>
                  </div>
                  <div v-if="log.suggestion"><strong>建议：</strong>{{ log.suggestion }}</div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-if="logs.length === 0" class="empty-text">暂无日志数据</div>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <span class="page-info">共 {{ total }} 条，第 {{ page }} / {{ totalPages }} 页</span>
      <button :disabled="page <= 1" @click="page = 1; search()">首页</button>
      <button :disabled="page <= 1" @click="page--; search()">上一页</button>
      <button :disabled="page >= totalPages" @click="page++; search()">下一页</button>
      <button :disabled="page >= totalPages" @click="page = totalPages; search()">末页</button>
      <select v-model.number="pageSize" @change="page = 1; search()">
        <option :value="20">20条/页</option>
        <option :value="50">50条/页</option>
        <option :value="100">100条/页</option>
      </select>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'

export default {
  name: 'LogQuery',
  setup() {
    const instances = ref([])
    const logs = ref([])
    const total = ref(0)
    const page = ref(1)
    const pageSize = ref(20)
    const expanded = ref(null)
    const sortKey = ref('timestamp')
    const sortAsc = ref(false)

    const filters = ref({
      instance: '',
      level: '',
      start_time: '',
      end_time: '',
      keyword: '',
      period: ''
    })

    const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

    function formatTime(t) {
      if (!t) return '-'
      const d = new Date(t)
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
    }

    function truncate(str, len) {
      if (!str) return ''
      return str.length > len ? str.substring(0, len) + '...' : str
    }

    function toggleExpand(idx) {
      expanded.value = expanded.value === idx ? null : idx
    }

    function sortBy(key) {
      if (sortKey.value === key) {
        sortAsc.value = !sortAsc.value
      } else {
        sortKey.value = key
        sortAsc.value = false
      }
      search()
    }

    function applyPeriod() {
      const p = filters.value.period
      if (!p) return

      const now = new Date()
      let start = new Date()

      const match = p.match(/^(\d+)(h|d)$/)
      if (match) {
        const value = parseInt(match[1])
        const unit = match[2]
        if (unit === 'h') {
          start.setHours(start.getHours() - value)
        } else {
          start.setDate(start.getDate() - value)
        }
      } else if (p === 'all') {
        start = new Date(2000, 0, 1)
      }

      // 格式化为 datetime-local 格式
      const format = (d) => {
        return d.getFullYear() + '-' +
          String(d.getMonth() + 1).padStart(2, '0') + '-' +
          String(d.getDate()).padStart(2, '0') + 'T' +
          String(d.getHours()).padStart(2, '0') + ':' +
          String(d.getMinutes()).padStart(2, '0')
      }

      filters.value.start_time = format(start)
      filters.value.end_time = format(now)
      search()
    }

    async function loadInstances() {
      try {
        const res = await api.getInstances()
        const data = res.data || []
        instances.value = Array.isArray(data)
          ? data.map(i => typeof i === 'string' ? i : (i.name || i.instance || i.host))
          : []
      } catch (e) { /* ignore */ }
    }

    async function search() {
      try {
        const params = {
          page: page.value,
          page_size: pageSize.value,
          sort_by: sortKey.value,
          sort_order: sortAsc.value ? 'asc' : 'desc',
          ...filters.value
        }
        // 移除空值
        Object.keys(params).forEach(k => {
          if (params[k] === '' || params[k] === null || params[k] === undefined) {
            delete params[k]
          }
        })
        const res = await api.getLogs(params)
        const data = res.data || {}
        logs.value = data.logs || data.items || data.data || (Array.isArray(data) ? data : [])
        total.value = data.total || logs.value.length
      } catch (e) { /* ignore */ }
    }

    async function semanticSearch() {
      const query = filters.value.keyword
      if (!query) return

      try {
        const res = await api.semanticSearch({ query, k: 20 })
        const data = res.data || {}
        if (data.items && data.items.length > 0) {
          logs.value = data.items
          total.value = data.total || data.items.length
        } else {
          logs.value = []
          total.value = 0
          if (data.message) {
            alert(data.message)
          }
        }
      } catch (e) {
        logs.value = []
      }
    }

    function exportLogs() {
      const header = '时间,实例,级别,消息\n'
      const rows = logs.value.map(l =>
        `"${l.timestamp || ''}","${l.instance || ''}","${l.level || ''}","${(l.message || l.content || '').replace(/"/g, '""')}"`
      ).join('\n')
      const csv = header + rows
      const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `logs_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    }

    onMounted(() => {
      loadInstances()
      search()
    })

    return {
      instances, logs, total, page, pageSize, totalPages,
      expanded, sortKey, sortAsc, filters,
      formatTime, truncate, toggleExpand, sortBy, search, semanticSearch, exportLogs, applyPeriod
    }
  }
}
</script>

<style scoped>
.log-query {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-group label {
  font-size: 12px;
  color: var(--text-muted);
}

.filter-group select,
.filter-group input {
  padding: 6px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.filter-group select:focus,
.filter-group input:focus {
  border-color: var(--accent-blue);
}

.btn-primary {
  padding: 6px 20px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-semantic {
  padding: 6px 20px;
  background: var(--accent-purple, #8b5cf6);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-semantic:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-semantic:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-secondary {
  padding: 6px 20px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.table-wrapper {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow-x: auto;
}

.log-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.log-table th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.log-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.log-row {
  cursor: pointer;
  transition: background 0.15s;
}

.log-row:hover {
  background: var(--bg-hover);
}

.col-time { width: 140px; }
.col-instance { width: 120px; }
.col-level { width: 80px; }
.col-msg { }

.level-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.level-tag.error { background: rgba(239,68,68,0.2); color: var(--accent-red); }
.level-tag.warning { background: rgba(245,158,11,0.2); color: var(--accent-yellow); }
.level-tag.note { background: rgba(6,182,212,0.2); color: var(--accent-cyan); }
.level-tag.info { background: rgba(100,116,139,0.2); color: var(--text-muted); }
.level-tag.system { background: rgba(139,92,246,0.2); color: var(--accent-purple); }

.detail-row td {
  background: var(--bg-secondary);
}

.log-detail {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.log-detail strong {
  color: var(--text-primary);
}

.msg-pre {
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 4px;
  padding: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-primary);
  max-height: 200px;
  overflow-y: auto;
}

.pagination {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.pagination button {
  padding: 4px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pagination select {
  padding: 4px 8px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 4px;
  font-size: 12px;
}

.empty-text {
  color: var(--text-muted);
  text-align: center;
  padding: 40px;
  font-size: 14px;
}

/* ── 移动端适配 ────────────────────────────────────────── */
@media (max-width: 768px) {
  .filter-bar {
    padding: 12px;
    gap: 8px;
  }

  .filter-group {
    width: 100%;
  }

  .filter-group select,
  .filter-group input {
    width: 100%;
    font-size: 14px;
    padding: 8px 10px;
  }

  .btn-primary,
  .btn-semantic,
  .btn-secondary {
    width: 100%;
    padding: 10px;
    font-size: 14px;
  }

  /* 移动端：隐藏表格，显示卡片列表 */
  .log-table thead {
    display: none;
  }

  .log-table,
  .log-table tbody,
  .log-table tr,
  .log-table td {
    display: block;
    width: 100%;
  }

  .log-row {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    margin-bottom: 8px;
    padding: 10px 12px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }

  .log-row td {
    border: none;
    padding: 0;
    font-size: 13px;
  }

  .col-time {
    width: auto;
    color: var(--text-muted);
    font-size: 12px;
  }

  .col-instance {
    width: auto;
    color: var(--accent-cyan);
    font-size: 12px;
  }

  .col-level {
    width: auto;
  }

  .col-msg {
    width: 100%;
    margin-top: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .detail-row td {
    background: none;
    padding: 0;
  }

  .log-detail {
    padding: 8px 0 0;
  }

  .pagination {
    flex-wrap: wrap;
    gap: 6px;
    justify-content: center;
  }

  .page-info {
    width: 100%;
    text-align: center;
  }

  .pagination button {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>
