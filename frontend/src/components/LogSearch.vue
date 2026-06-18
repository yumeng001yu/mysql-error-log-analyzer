<template>
  <div class="log-search">
    <!-- 搜索栏 -->
    <div class="search-bar">
      <div class="search-input-wrapper">
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="搜索日志内容..."
          @input="onSearchInput"
          @keydown.enter="doSearch"
          @keydown.esc="showSuggestions = false"
        />
        <!-- 搜索建议下拉 -->
        <div v-if="showSuggestions && suggestions.length > 0" class="suggestions-dropdown">
          <div
            v-for="(s, i) in suggestions"
            :key="i"
            class="suggestion-item"
            @mousedown.prevent="applySuggestion(s)"
          >
            {{ s }}
          </div>
        </div>
      </div>
      <div class="search-controls">
        <div class="mode-toggle">
          <button
            v-for="m in searchModes"
            :key="m.value"
            :class="['mode-btn', { active: searchMode === m.value }]"
            @click="searchMode = m.value"
          >{{ m.label }}</button>
        </div>
        <label class="case-check">
          <input type="checkbox" v-model="caseSensitive" />
          <span>区分大小写</span>
        </label>
        <button class="btn-search" @click="doSearch">搜索</button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>级别</label>
        <div class="level-checkboxes">
          <label v-for="lv in levelOptions" :key="lv" class="level-check">
            <input type="checkbox" :value="lv" v-model="selectedLevels" />
            <span class="level-dot" :class="lv.toLowerCase()"></span>
            <span>{{ lv }}</span>
          </label>
        </div>
      </div>
      <div class="filter-group">
        <label>分类</label>
        <select v-model="selectedCategory">
          <option value="">全部分类</option>
          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>开始时间</label>
        <input type="datetime-local" v-model="startTime" />
      </div>
      <div class="filter-group">
        <label>结束时间</label>
        <input type="datetime-local" v-model="endTime" />
      </div>
      <div class="filter-group">
        <label>排序方式</label>
        <select v-model="sortBy">
          <option value="relevance">相关性</option>
          <option value="timestamp">时间</option>
        </select>
      </div>
      <div class="filter-group">
        <label>排序方向</label>
        <select v-model="sortOrder">
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
      </div>
    </div>

    <!-- 结果区域 -->
    <div v-if="searched" class="results-area">
      <!-- 总数 -->
      <div class="results-header">
        <span class="results-count">找到 {{ total }} 条结果</span>
      </div>

      <!-- 聚合摘要 -->
      <div class="aggregation-bar" v-if="levelAgg.length > 0 || timelineAgg.length > 0">
        <div class="agg-levels" v-if="levelAgg.length > 0">
          <span
            v-for="item in levelAgg"
            :key="item.level"
            class="agg-level-item"
          >
            <span class="level-dot" :class="item.level.toLowerCase()"></span>
            {{ item.level }}: {{ item.count }}
          </span>
        </div>
        <div class="agg-timeline" v-if="timelineAgg.length > 0">
          <span class="agg-timeline-label">时间分布:</span>
          <span v-for="t in timelineAgg" :key="t.hour" class="agg-timeline-item">
            {{ t.hour }}时({{ t.count }})
          </span>
        </div>
      </div>

      <!-- 结果列表 -->
      <div class="result-list">
        <div v-if="results.length === 0" class="empty-text">未找到匹配的日志</div>
        <div
          v-for="(item, idx) in results"
          :key="item.id || idx"
          class="result-card"
        >
          <div class="result-card-main">
            <div class="result-card-left">
              <span class="level-badge" :class="item.level?.toLowerCase()">{{ item.level }}</span>
              <span class="result-timestamp">{{ formatTime(item.timestamp) }}</span>
              <span v-if="item.error_code" class="result-error-code">{{ item.error_code }}</span>
              <span v-if="item.category" class="result-category">{{ item.category }}</span>
            </div>
            <div class="result-card-right">
              <span class="result-score">{{ item.score != null ? item.score.toFixed(2) : '' }}</span>
              <button class="btn-context" @click="toggleContext(item)">查看上下文</button>
            </div>
          </div>
          <div class="result-message" v-html="item.highlight || item.message || item.content || ''"></div>

          <!-- 上下文视图 -->
          <div v-if="contextExpandedId === item.id" class="context-view">
            <div v-if="contextLoading" class="context-loading">加载中...</div>
            <template v-else>
              <div
                v-for="(ctx, ci) in contextEntries"
                :key="ci"
                class="context-entry"
                :class="{ 'context-target': ctx.id === item.id }"
              >
                <span class="ctx-timestamp">{{ formatTime(ctx.timestamp) }}</span>
                <span class="level-badge small" :class="ctx.level?.toLowerCase()">{{ ctx.level }}</span>
                <span class="ctx-message">{{ truncate(ctx.message || ctx.content, 120) }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" v-if="total > 0">
        <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
        <button :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <button :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
        <select v-model.number="pageSize" @change="onPageSizeChange">
          <option :value="25">25条/页</option>
          <option :value="50">50条/页</option>
          <option :value="100">100条/页</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'
import { formatDateTime as formatTime } from '../utils/datetime.js'
import { truncate } from '../utils/format.js'

// ── 搜索状态 ──────────────────────────────────────────
const searchQuery = ref('')
const searchMode = ref('simple')
const caseSensitive = ref(false)
const searched = ref(false)

const searchModes = [
  { label: '简单', value: 'simple' },
  { label: '正则', value: 'regex' },
  { label: '模糊', value: 'fuzzy' }
]

// ── 筛选状态 ──────────────────────────────────────────
const levelOptions = ['ERROR', 'WARNING', 'INFO', 'NOTE', 'SYSTEM']
const selectedLevels = ref([])
const selectedCategory = ref('')
const startTime = ref('')
const endTime = ref('')
const sortBy = ref('relevance')
const sortOrder = ref('desc')
const categories = ref([])

// ── 结果状态 ──────────────────────────────────────────
const results = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(25)
const levelAgg = ref([])
const timelineAgg = ref([])

// ── 上下文状态 ────────────────────────────────────────
const contextExpandedId = ref(null)
const contextEntries = ref([])
const contextLoading = ref(false)

// ── 搜索建议状态 ──────────────────────────────────────
const showSuggestions = ref(false)
const suggestions = ref([])
const searchInputRef = ref(null)
let debounceTimer = null

// ── 计算属性 ──────────────────────────────────────────
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

// ── 搜索建议 ──────────────────────────────────────────
function onSearchInput() {
  clearTimeout(debounceTimer)
  if (!searchQuery.value.trim()) {
    showSuggestions.value = false
    suggestions.value = []
    return
  }
  debounceTimer = setTimeout(async () => {
    try {
      const res = await api.searchSuggest({ q: searchQuery.value, mode: searchMode.value })
      const data = res.data
      suggestions.value = Array.isArray(data)
        ? data
        : (data?.suggestions || data?.items || [])
      showSuggestions.value = suggestions.value.length > 0
    } catch {
      suggestions.value = []
      showSuggestions.value = false
    }
  }, 300)
}

function applySuggestion(text) {
  searchQuery.value = text
  showSuggestions.value = false
  suggestions.value = []
}

// ── 执行搜索 ──────────────────────────────────────────
async function doSearch() {
  showSuggestions.value = false
  page.value = 1
  await fetchResults()
  searched.value = true
}

async function fetchResults() {
  try {
    const params = {
      q: searchQuery.value,
      mode: searchMode.value,
      case_sensitive: caseSensitive.value,
      page: page.value,
      page_size: pageSize.value,
      sort_by: sortBy.value,
      sort_order: sortOrder.value
    }
    if (selectedLevels.value.length > 0) {
      params.levels = selectedLevels.value.join(',')
    }
    if (selectedCategory.value) {
      params.category = selectedCategory.value
    }
    if (startTime.value) {
      params.start_time = startTime.value
    }
    if (endTime.value) {
      params.end_time = endTime.value
    }

    const res = await api.searchLogs(params)
    const data = res.data || {}
    results.value = data.items || data.results || data.data || []
    total.value = data.total || 0
    levelAgg.value = data.level_aggregation || data.level_agg || []
    timelineAgg.value = data.timeline || data.timeline_aggregations || []
  } catch {
    results.value = []
    total.value = 0
    levelAgg.value = []
    timelineAgg.value = []
  }
}

// ── 上下文 ────────────────────────────────────────────
async function toggleContext(item) {
  if (contextExpandedId.value === item.id) {
    contextExpandedId.value = null
    contextEntries.value = []
    return
  }
  contextExpandedId.value = item.id
  contextLoading.value = true
  contextEntries.value = []
  try {
    const res = await api.getLogContext(item.id, { before: 5, after: 5 })
    const data = res.data || {}
    contextEntries.value = data.entries || data.items || data.context || []
  } catch {
    contextEntries.value = []
  }
  contextLoading.value = false
}

// ── 分页 ──────────────────────────────────────────────
function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  fetchResults()
}

function onPageSizeChange() {
  page.value = 1
  fetchResults()
}

// ── 加载分类字段 ──────────────────────────────────────
async function loadFields() {
  try {
    const res = await api.getSearchFields()
    const data = res.data || {}
    categories.value = data.categories || data.category || []
  } catch {
    categories.value = []
  }
}

// ── 点击外部关闭建议 ──────────────────────────────────
function onClickOutside(e) {
  if (searchInputRef.value && !searchInputRef.value.contains(e.target)) {
    showSuggestions.value = false
  }
}

onMounted(() => {
  loadFields()
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  clearTimeout(debounceTimer)
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.log-search {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 搜索栏 ──────────────────────────────────────────── */
.search-bar {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.search-input-wrapper {
  position: relative;
}

.search-input {
  width: 100%;
  padding: 14px 18px;
  font-size: 16px;
  background: var(--bg-secondary);
  border: 2px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.2s;
}

.search-input:focus {
  border-color: var(--accent-blue);
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.mode-toggle {
  display: flex;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}

.mode-btn {
  padding: 6px 14px;
  background: var(--bg-secondary);
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.mode-btn:not(:last-child) {
  border-right: 1px solid var(--border-color);
}

.mode-btn.active {
  background: var(--accent-blue);
  color: #fff;
}

.mode-btn:hover:not(.active) {
  background: var(--bg-hover);
}

.case-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.case-check input[type="checkbox"] {
  accent-color: var(--accent-blue);
}

.btn-search {
  padding: 8px 28px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: opacity 0.2s;
}

.btn-search:hover {
  opacity: 0.9;
}

/* ── 搜索建议 ────────────────────────────────────────── */
.suggestions-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-top: none;
  border-radius: 0 0 8px 8px;
  max-height: 240px;
  overflow-y: auto;
  z-index: 50;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.suggestion-item {
  padding: 10px 18px;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.suggestion-item:hover {
  background: var(--bg-hover);
}

/* ── 筛选栏 ──────────────────────────────────────────── */
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

.level-checkboxes {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.level-check {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.level-check input[type="checkbox"] {
  accent-color: var(--accent-blue);
}

.level-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.level-dot.error { background: var(--accent-red); }
.level-dot.warning { background: var(--accent-yellow); }
.level-dot.info { background: var(--text-muted); }
.level-dot.note { background: var(--accent-cyan); }
.level-dot.system { background: var(--accent-purple); }

/* ── 结果区域 ────────────────────────────────────────── */
.results-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.results-header {
  font-size: 14px;
  color: var(--text-secondary);
}

.results-count {
  font-weight: 600;
}

/* ── 聚合摘要 ────────────────────────────────────────── */
.aggregation-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.agg-levels {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}

.agg-level-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.agg-timeline {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.agg-timeline-label {
  color: var(--text-muted);
  font-size: 12px;
}

.agg-timeline-item {
  font-size: 12px;
  color: var(--text-muted);
}

/* ── 结果卡片 ────────────────────────────────────────── */
.result-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  transition: border-color 0.2s;
}

.result-card:hover {
  border-color: var(--accent-blue);
}

.result-card-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.result-card-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-card-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.level-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.level-badge.error { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }
.level-badge.warning { background: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); }
.level-badge.info { background: rgba(100, 116, 139, 0.2); color: var(--text-muted); }
.level-badge.note { background: rgba(6, 182, 212, 0.2); color: var(--accent-cyan); }
.level-badge.system { background: rgba(139, 92, 246, 0.2); color: var(--accent-purple); }

.level-badge.small {
  padding: 1px 6px;
  font-size: 10px;
}

.result-timestamp {
  font-size: 13px;
  color: var(--text-muted);
  font-family: monospace;
}

.result-error-code {
  font-size: 12px;
  color: var(--accent-yellow);
  background: rgba(245, 158, 11, 0.1);
  padding: 1px 8px;
  border-radius: 3px;
  font-family: monospace;
}

.result-category {
  font-size: 12px;
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.1);
  padding: 1px 8px;
  border-radius: 3px;
}

.result-score {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 36px;
  text-align: right;
}

.btn-context {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.btn-context:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent-blue);
}

.result-message {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  word-break: break-word;
}

.result-message :deep(mark) {
  background: #f59e0b;
  color: #000;
  padding: 0 2px;
  border-radius: 2px;
}

/* ── 上下文视图 ──────────────────────────────────────── */
.context-view {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.context-loading {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 12px;
}

.context-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  transition: background 0.15s;
}

.context-entry:hover {
  background: var(--bg-hover);
}

.context-entry.context-target {
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.ctx-timestamp {
  color: var(--text-muted);
  font-family: monospace;
  font-size: 11px;
  flex-shrink: 0;
}

.ctx-message {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 分页 ────────────────────────────────────────────── */
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

.page-info {
  font-size: 13px;
}

.empty-text {
  color: var(--text-muted);
  text-align: center;
  padding: 40px;
  font-size: 14px;
}

/* ── 移动端适配 ──────────────────────────────────────── */
@media (max-width: 768px) {
  .search-bar {
    padding: 14px;
  }

  .search-input {
    font-size: 16px;
    padding: 12px 14px;
  }

  .search-controls {
    gap: 10px;
  }

  .mode-toggle {
    flex: 1;
  }

  .mode-btn {
    flex: 1;
    text-align: center;
    padding: 6px 8px;
  }

  .btn-search {
    width: 100%;
    padding: 10px;
  }

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

  .level-checkboxes {
    gap: 8px;
  }

  .result-card-main {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .result-card-right {
    width: 100%;
    justify-content: space-between;
  }

  .result-message {
    font-size: 13px;
  }

  .context-entry {
    flex-wrap: wrap;
  }

  .ctx-message {
    width: 100%;
    margin-top: 2px;
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

  .aggregation-bar {
    flex-direction: column;
    gap: 8px;
  }

  .agg-levels {
    gap: 8px;
  }
}
</style>
