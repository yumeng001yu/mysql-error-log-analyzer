"""全文本搜索 API

支持语法高亮、正则过滤、时间范围筛选的日志搜索引擎。
"""
import re
from datetime import datetime, timedelta
from html import escape as html_escape
from typing import Optional

from fastapi import APIRouter, Query

from src.web.api.deps import get_db as _get_db

router = APIRouter(prefix="/api/search", tags=["search"])


# ── MySQL 常见错误模式（用于搜索建议）──────────────────────────

_MYSQL_ERROR_PATTERNS = [
    "ER_ACCESS_DENIED_ERROR",
    "ER_CON_COUNT_ERROR",
    "ER_TOO_MANY_CONNECTIONS",
    "ER_HOST_IS_BLOCKED",
    "ER_HOST_NOT_PRIVILEGED",
    "ER_DBACCESS_DENIED_ERROR",
    "ER_BAD_DB_ERROR",
    "ER_BAD_TABLE_ERROR",
    "ER_DUP_ENTRY",
    "ER_NO_REFERENCED_ROW",
    "ER_ROW_IS_REFERENCED",
    "ER_CANNOT_ADD_FOREIGN",
    "ER_LOCK_DEADLOCK",
    "ER_LOCK_WAIT_TIMEOUT",
    "ER_LOCK_TABLE_FULL",
    "ER_TOO_MANY_LOCKS",
    "ER_TABLE_EXISTS_ERROR",
    "ER_NO_SUCH_TABLE",
    "ER_BAD_FIELD_ERROR",
    "ER_PARSE_ERROR",
    "ER_SYNTAX_ERROR",
    "ER_WRONG_VALUE_COUNT",
    "ER_OUT_OF_RESOURCES",
    "ER_OUTOFMEMORY",
    "ER_DISK_FULL",
    "ER_RECORD_FILE_FULL",
    "ER_FILSORT_ABORT",
    "ER_SLAVE_THREAD",
    "ER_SLAVE_FATAL_ERROR",
    "ER_SLAVE_RELAY_LOG_READ_FAILURE",
    "ER_SLAVE_RELAY_LOG_WRITE_FAILURE",
    "ER_SLAVE_MASTER_FATAL_ERROR_READING_BINLOG",
    "ER_NET_READ_ERROR",
    "ER_NET_READ_INTERRUPTED",
    "ER_NET_ERROR_ON_WRITE",
    "ER_NET_WRITE_INTERRUPTED",
    "ER_NET_PACKET_TOO_LARGE",
    "ER_ABORTING_CONNECTION",
    "ER_CLIENT_INTERACTION_TIMEOUT",
    "InnoDB",
    "Deadlock",
    "connection",
    "timeout",
    "denied",
    "buffer pool",
    "redo log",
    "undo log",
    "replication",
    "slave",
    "master",
    "binlog",
    "relay log",
    "crash recovery",
    "shutdown",
    "startup",
    "ready for connections",
]


# ── 工具函数 ────────────────────────────────────────────────


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符，防止 XSS"""
    return html_escape(text)


def _highlight_simple(text: str, query: str, case_sensitive: bool = False) -> str:
    """简单模式高亮：将匹配的查询文本包裹在 <mark> 标签中"""
    if not text or not query:
        return _escape_html(text) if text else ""

    flags = 0 if case_sensitive else re.IGNORECASE
    # 转义查询中的正则特殊字符
    escaped_query = re.escape(query)
    # 先转义 HTML，再插入高亮标记
    safe_text = _escape_html(text)
    # 转义后的查询（HTML 实体可能改变大小写映射，所以对原文做匹配再替换）
    parts = []
    last_end = 0
    for m in re.finditer(escaped_query, text, flags):
        # 转义匹配前、匹配中、匹配后的文本
        parts.append(_escape_html(text[last_end:m.start()]))
        parts.append(f"<mark>{_escape_html(m.group())}</mark>")
        last_end = m.end()
    parts.append(_escape_html(text[last_end:]))
    return "".join(parts)


def _highlight_regex(text: str, pattern: str, case_sensitive: bool = False) -> str:
    """正则模式高亮：将正则匹配的部分包裹在 <mark> 标签中"""
    if not text or not pattern:
        return _escape_html(text) if text else ""

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = re.compile(pattern, flags)
    except re.error:
        # 正则表达式无效，回退为普通文本
        return _escape_html(text)

    parts = []
    last_end = 0
    for m in compiled.finditer(text):
        parts.append(_escape_html(text[last_end:m.start()]))
        parts.append(f"<mark>{_escape_html(m.group())}</mark>")
        last_end = m.end()
    parts.append(_escape_html(text[last_end:]))
    return "".join(parts)


def _highlight_fuzzy(text: str, words: list[str], case_sensitive: bool = False) -> str:
    """模糊模式高亮：将每个词的匹配部分分别包裹在 <mark> 标签中"""
    if not text or not words:
        return _escape_html(text) if text else ""

    flags = 0 if case_sensitive else re.IGNORECASE
    # 收集所有匹配区间
    intervals = []
    for word in words:
        escaped = re.escape(word)
        for m in re.finditer(escaped, text, flags):
            intervals.append((m.start(), m.end()))

    if not intervals:
        return _escape_html(text)

    # 合并重叠区间
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # 构建高亮文本
    parts = []
    last_end = 0
    for start, end in merged:
        parts.append(_escape_html(text[last_end:start]))
        parts.append(f"<mark>{_escape_html(text[start:end])}</mark>")
        last_end = end
    parts.append(_escape_html(text[last_end:]))
    return "".join(parts)


def _compute_score(
    entry: dict,
    query: str,
    mode: str,
    case_sensitive: bool = False,
    words: Optional[list[str]] = None,
) -> float:
    """计算搜索结果的相关性评分

    评分规则：
    - message 精确匹配: +3
    - error_code 匹配: +2
    - raw_line 匹配: +1
    - 时间衰减: 1小时内 +1, 24小时内 +0.5
    """
    score = 0.0
    flags = 0 if case_sensitive else re.IGNORECASE

    if mode == "regex":
        try:
            pattern = re.compile(query, flags)
            if pattern.search(entry.get("message") or ""):
                score += 3
            if pattern.search(entry.get("error_code") or ""):
                score += 2
            if pattern.search(entry.get("raw_line") or ""):
                score += 1
        except re.error:
            pass
    elif mode == "fuzzy" and words:
        all_in_message = all(
            re.search(re.escape(w), entry.get("message") or "", flags) for w in words
        )
        all_in_error_code = all(
            re.search(re.escape(w), entry.get("error_code") or "", flags) for w in words
        )
        all_in_raw_line = all(
            re.search(re.escape(w), entry.get("raw_line") or "", flags) for w in words
        )
        if all_in_message:
            score += 3
        if all_in_error_code:
            score += 2
        if all_in_raw_line:
            score += 1
    else:
        # simple 模式
        if re.search(re.escape(query), entry.get("message") or "", flags):
            score += 3
        if re.search(re.escape(query), entry.get("error_code") or "", flags):
            score += 2
        if re.search(re.escape(query), entry.get("raw_line") or "", flags):
            score += 1

    # 时间衰减加成
    ts_str = entry.get("timestamp", "")
    if ts_str:
        try:
            # 兼容多种时间格式
            ts_str_clean = ts_str.replace("T", " ").split(".")[0]
            entry_time = datetime.strptime(ts_str_clean, "%Y-%m-%d %H:%M:%S")
            hours_ago = (datetime.now() - entry_time).total_seconds() / 3600
            if hours_ago < 1:
                score += 1
            elif hours_ago < 24:
                score += 0.5
        except (ValueError, TypeError):
            pass

    return score


def _fuzzy_match(text: str, words: list[str], case_sensitive: bool = False) -> bool:
    """模糊匹配：所有词都必须出现在文本中（顺序无关）"""
    if not words:
        return True
    flags = 0 if case_sensitive else re.IGNORECASE
    for word in words:
        if not re.search(re.escape(word), text, flags):
            return False
    return True


def _build_highlights(
    entry: dict,
    query: str,
    mode: str,
    case_sensitive: bool = False,
    words: Optional[list[str]] = None,
) -> dict[str, str]:
    """构建高亮结果"""
    message = entry.get("message") or ""
    raw_line = entry.get("raw_line") or ""

    if mode == "regex":
        hl_message = _highlight_regex(message, query, case_sensitive)
        hl_raw = _highlight_regex(raw_line, query, case_sensitive)
    elif mode == "fuzzy" and words:
        hl_message = _highlight_fuzzy(message, words, case_sensitive)
        hl_raw = _highlight_fuzzy(raw_line, words, case_sensitive)
    else:
        hl_message = _highlight_simple(message, query, case_sensitive)
        hl_raw = _highlight_simple(raw_line, query, case_sensitive)

    return {"message": hl_message, "raw_line": hl_raw}


# ── API 端点 ────────────────────────────────────────────────


@router.get("/")
async def full_text_search(
    q: str = Query(..., description="搜索查询字符串"),
    instance_id: Optional[int] = Query(None, description="实例 ID 过滤"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    level: Optional[str] = Query(None, description="日志级别过滤（逗号分隔，如 ERROR,WARNING）"),
    category: Optional[str] = Query(None, description="日志类别过滤"),
    mode: str = Query("simple", description="搜索模式: simple | regex | fuzzy"),
    case_sensitive: bool = Query(False, description="是否区分大小写"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    sort_by: str = Query("timestamp", description="排序方式: relevance | timestamp"),
    sort_order: str = Query("desc", description="排序方向: asc | desc"),
):
    """全文本搜索日志

    支持三种搜索模式：
    - simple: SQL LIKE 匹配，高亮查询词
    - regex: Python 正则表达式匹配，高亮正则匹配
    - fuzzy: 模糊匹配，所有词必须出现（顺序无关），高亮每个词
    """
    db = _get_db()
    conn = await db._get_conn()

    # 解析多级别过滤
    levels = None
    if level:
        levels = [l.strip().upper() for l in level.split(",") if l.strip()]

    # 验证搜索模式
    if mode not in ("simple", "regex", "fuzzy"):
        mode = "simple"

    # 验证正则表达式有效性
    if mode == "regex":
        try:
            re.compile(q)
        except re.error:
            return {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "results": [],
                "aggregations": {"by_level": [], "by_category": [], "timeline": []},
                "error": f"无效的正则表达式: {q}",
            }

    # 模糊模式拆分查询词
    words = q.split() if mode == "fuzzy" else None

    # ── 构建 SQL 查询 ─────────────────────────────────────
    conditions = []
    params: list = []

    if instance_id is not None:
        conditions.append("instance_id = ?")
        params.append(instance_id)
    if start_time is not None:
        conditions.append("timestamp >= ?")
        params.append(start_time)
    if end_time is not None:
        conditions.append("timestamp <= ?")
        params.append(end_time)
    if levels:
        placeholders = ",".join("?" for _ in levels)
        conditions.append(f"level IN ({placeholders})")
        params.extend(levels)
    if category is not None:
        conditions.append("category = ?")
        params.append(category)

    # simple 模式使用 SQL LIKE 加速初步过滤
    if mode == "simple":
        conditions.append("(message LIKE ? OR raw_line LIKE ? OR error_code LIKE ?)")
        like_pattern = f"%{q}%"
        params.extend([like_pattern, like_pattern, like_pattern])

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 查询所有匹配记录（后续在 Python 中做进一步过滤和评分）
    # 对于大数据集，先查总数再分页
    count_sql = f"SELECT COUNT(*) as cnt FROM log_entries WHERE {where_clause}"
    cursor = await conn.execute(count_sql, params)
    row = await cursor.fetchone()
    total_candidates = row["cnt"] if row else 0

    # 如果候选集过大，使用分页策略：先取足够多的候选记录
    # regex/fuzzy 模式需要更多候选集做 Python 端过滤
    if mode in ("regex", "fuzzy"):
        fetch_limit = min(total_candidates, 5000)
    else:
        fetch_limit = min(total_candidates, page_size * 5) if total_candidates > 0 else page_size

    data_sql = f"""SELECT id, instance_id, timestamp, level, error_code,
                          thread_id, category, message, raw_line, created_at
                   FROM log_entries
                   WHERE {where_clause}
                   ORDER BY timestamp DESC
                   LIMIT ?"""
    cursor = await conn.execute(data_sql, params + [fetch_limit])
    rows = await cursor.fetchall()
    candidates = [dict(r) for r in rows]

    # ── Python 端过滤（regex / fuzzy 模式）──────────────────
    if mode == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(q, flags)
        except re.error:
            compiled = None

        if compiled:
            filtered = []
            for entry in candidates:
                text = " ".join(
                    filter(None, [entry.get("message"), entry.get("raw_line"), entry.get("error_code")])
                )
                if compiled.search(text):
                    filtered.append(entry)
            candidates = filtered
        # 如果正则编译失败，保留所有候选（已在上方返回错误响应）

    elif mode == "fuzzy" and words:
        filtered = []
        for entry in candidates:
            text = " ".join(
                filter(None, [entry.get("message"), entry.get("raw_line"), entry.get("error_code")])
            )
            if _fuzzy_match(text, words, case_sensitive):
                filtered.append(entry)
        candidates = filtered

    # ── 评分 ───────────────────────────────────────────────
    for entry in candidates:
        entry["score"] = _compute_score(entry, q, mode, case_sensitive, words)

    # ── 排序 ───────────────────────────────────────────────
    reverse = sort_order == "desc"
    if sort_by == "relevance":
        candidates.sort(key=lambda x: x.get("score", 0), reverse=reverse)
    else:
        candidates.sort(key=lambda x: x.get("timestamp", ""), reverse=reverse)

    # ── 分页 ───────────────────────────────────────────────
    total = len(candidates)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = candidates[start_idx:end_idx]

    # ── 构建高亮和结果 ─────────────────────────────────────
    results = []
    for entry in page_items:
        highlights = _build_highlights(entry, q, mode, case_sensitive, words)
        results.append({
            "id": entry.get("id"),
            "instance_id": entry.get("instance_id"),
            "timestamp": entry.get("timestamp"),
            "level": entry.get("level"),
            "error_code": entry.get("error_code"),
            "thread_id": entry.get("thread_id"),
            "category": entry.get("category"),
            "message": entry.get("message"),
            "raw_line": entry.get("raw_line"),
            "highlights": highlights,
            "score": entry.get("score", 0),
        })

    # ── 聚合统计 ───────────────────────────────────────────
    # 按级别聚合
    level_counts: dict[str, int] = {}
    for entry in candidates:
        lv = entry.get("level", "UNKNOWN")
        level_counts[lv] = level_counts.get(lv, 0) + 1
    by_level = [{"level": lv, "count": cnt} for lv, cnt in sorted(level_counts.items(), key=lambda x: -x[1])]

    # 按类别聚合
    category_counts: dict[str, int] = {}
    for entry in candidates:
        cat = entry.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    by_category = [{"category": cat, "count": cnt} for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1])]

    # 时间线聚合（按小时）
    timeline_counts: dict[str, int] = {}
    for entry in candidates:
        ts = entry.get("timestamp", "")
        if ts:
            # 截取到小时精度
            hour_key = ts[:13].replace("T", " ") + ":00" if len(ts) >= 13 else ts[:10]
            timeline_counts[hour_key] = timeline_counts.get(hour_key, 0) + 1
    timeline = [{"hour": h, "count": c} for h, c in sorted(timeline_counts.items())]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
        "aggregations": {
            "by_level": by_level,
            "by_category": by_category,
            "timeline": timeline,
        },
    }


@router.get("/suggest")
async def search_suggest(
    q: str = Query("", description="部分查询字符串"),
    limit: int = Query(10, ge=1, le=50, description="返回建议数量"),
):
    """搜索建议 / 自动补全

    基于常见 MySQL 错误模式和关键词提供搜索建议。
    """
    q_lower = q.lower() if q else ""
    suggestions = []

    if not q_lower:
        # 无输入时返回热门建议
        suggestions = _MYSQL_ERROR_PATTERNS[:limit]
    else:
        # 过滤匹配的建议
        for pattern in _MYSQL_ERROR_PATTERNS:
            if q_lower in pattern.lower():
                suggestions.append(pattern)
            if len(suggestions) >= limit:
                break

        # 如果匹配不足，从数据库查询历史高频 error_code 补充
        if len(suggestions) < limit:
            db = _get_db()
            try:
                conn = await db._get_conn()
                cursor = await conn.execute(
                    """SELECT error_code, COUNT(*) as cnt
                       FROM log_entries
                       WHERE error_code IS NOT NULL AND error_code != ''
                         AND error_code LIKE ?
                       GROUP BY error_code
                       ORDER BY cnt DESC
                       LIMIT ?""",
                    (f"%{q}%", limit - len(suggestions)),
                )
                rows = await cursor.fetchall()
                for row in rows:
                    code = row["error_code"]
                    if code not in suggestions:
                        suggestions.append(code)
            except Exception:
                pass

    return suggestions


@router.get("/context/{log_id}")
async def get_context(
    log_id: int,
    before: int = Query(5, ge=0, le=50, description="向前获取的条目数"),
    after: int = Query(5, ge=0, le=50, description="向后获取的条目数"),
):
    """获取日志条目的上下文

    返回指定日志条目及其前后 N 条记录，便于理解错误的完整上下文。
    """
    db = _get_db()
    conn = await db._get_conn()

    # 查询目标日志条目
    cursor = await conn.execute(
        """SELECT id, instance_id, timestamp, level, error_code,
                  thread_id, category, message, raw_line, created_at
           FROM log_entries
           WHERE id = ?""",
        (log_id,),
    )
    target_row = await cursor.fetchone()

    if target_row is None:
        return {"error": "未找到指定日志条目", "target": None, "before": [], "after": []}

    target = dict(target_row)
    instance_id = target.get("instance_id")
    target_ts = target.get("timestamp", "")

    # 查询之前的条目（按时间倒序取 before 条，再反转为正序）
    before_entries = []
    if before > 0 and target_ts:
        cursor = await conn.execute(
            """SELECT id, instance_id, timestamp, level, error_code,
                      thread_id, category, message, raw_line, created_at
               FROM log_entries
               WHERE instance_id = ? AND (timestamp < ? OR (timestamp = ? AND id < ?))
               ORDER BY timestamp DESC, id DESC
               LIMIT ?""",
            (instance_id, target_ts, target_ts, log_id, before),
        )
        rows = await cursor.fetchall()
        before_entries = list(reversed([dict(r) for r in rows]))

    # 查询之后的条目
    after_entries = []
    if after > 0 and target_ts:
        cursor = await conn.execute(
            """SELECT id, instance_id, timestamp, level, error_code,
                      thread_id, category, message, raw_line, created_at
               FROM log_entries
               WHERE instance_id = ? AND (timestamp > ? OR (timestamp = ? AND id > ?))
               ORDER BY timestamp ASC, id ASC
               LIMIT ?""",
            (instance_id, target_ts, target_ts, log_id, after),
        )
        rows = await cursor.fetchall()
        after_entries = [dict(r) for r in rows]

    return {
        "target": target,
        "before": before_entries,
        "after": after_entries,
    }


@router.get("/fields")
async def get_search_fields():
    """获取可用的搜索字段值（用于前端过滤器）

    返回所有出现过的日志级别、类别、错误码和实例列表。
    """
    db = _get_db()
    conn = await db._get_conn()

    # 获取所有级别
    cursor = await conn.execute(
        "SELECT DISTINCT level FROM log_entries WHERE level IS NOT NULL ORDER BY level"
    )
    levels = [row["level"] for row in await cursor.fetchall()]

    # 获取所有类别
    cursor = await conn.execute(
        "SELECT DISTINCT category FROM log_entries WHERE category IS NOT NULL ORDER BY category"
    )
    categories = [row["category"] for row in await cursor.fetchall()]

    # 获取所有错误码
    cursor = await conn.execute(
        """SELECT DISTINCT error_code FROM log_entries
           WHERE error_code IS NOT NULL AND error_code != ''
           ORDER BY error_code"""
    )
    error_codes = [row["error_code"] for row in await cursor.fetchall()]

    # 获取所有实例
    cursor = await conn.execute(
        "SELECT id, name, host, port FROM instances ORDER BY id"
    )
    instances = [dict(r) for r in await cursor.fetchall()]

    return {
        "levels": levels,
        "categories": categories,
        "error_codes": error_codes,
        "instances": instances,
    }
