"""InnoDB 死锁深度分析 API"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.analyzer.deadlock_analyzer import DeadlockAnalyzer
from src.storage.database import DatabaseManager
from src.web.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deadlock", tags=["deadlock"])


# ── 数据库实例 ──────────────────────────────────────────────

_db: DatabaseManager | None = None
_analyzer: DeadlockAnalyzer | None = None


def _get_db() -> DatabaseManager:
    """获取数据库管理器单例"""
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


def _get_analyzer() -> DeadlockAnalyzer:
    """获取死锁分析器单例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = DeadlockAnalyzer()
    return _analyzer


async def _ensure_table(db: DatabaseManager):
    """确保 deadlock_analyses 表存在"""
    analyzer = _get_analyzer()
    await analyzer._ensure_deadlock_table(db)


# ── API 端点 ────────────────────────────────────────────────

@router.get("/list")
async def list_deadlocks(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    severity: Optional[str] = Query(None, description="严重程度 (low/medium/high/critical)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: Optional[str] = Depends(get_current_user),
):
    """列出死锁分析结果"""
    db = _get_db()
    await _ensure_table(db)

    conn = await db._get_conn()

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
    if severity is not None:
        conditions.append("severity = ?")
        params.append(severity)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 查询总数
    cursor = await conn.execute(
        f"SELECT COUNT(*) as cnt FROM deadlock_analyses WHERE {where_clause}",
        params,
    )
    row = await cursor.fetchone()
    total = row["cnt"] if row else 0

    # 分页查询
    offset = (page - 1) * page_size
    query_params = params + [page_size, offset]

    cursor = await conn.execute(
        f"""SELECT id, instance_id, timestamp, root_cause, severity,
                   affected_tables_json, suggestions_json, index_suggestions_json
            FROM deadlock_analyses
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?""",
        query_params,
    )
    rows = await cursor.fetchall()

    items = []
    for row in rows:
        # 解析 JSON 字段
        affected_tables = []
        try:
            affected_tables = json.loads(row["affected_tables_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        suggestions = []
        try:
            suggestions = json.loads(row["suggestions_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        index_suggestions = []
        try:
            index_suggestions = json.loads(row["index_suggestions_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        items.append({
            "id": row["id"],
            "instance_id": row["instance_id"],
            "timestamp": row["timestamp"],
            "root_cause": row["root_cause"],
            "severity": row["severity"],
            "affected_tables": affected_tables,
            "suggestions": suggestions,
            "index_suggestions": index_suggestions,
        })

    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
async def deadlock_stats(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    user: Optional[str] = Depends(get_current_user),
):
    """获取死锁统计信息"""
    db = _get_db()
    await _ensure_table(db)

    conn = await db._get_conn()

    conditions = []
    params: list = []

    if instance_id is not None:
        conditions.append("instance_id = ?")
        params.append(instance_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 总数
    cursor = await conn.execute(
        f"SELECT COUNT(*) as cnt FROM deadlock_analyses WHERE {where_clause}",
        params,
    )
    row = await cursor.fetchone()
    total_count = row["cnt"] if row else 0

    # 按严重程度分布
    cursor = await conn.execute(
        f"""SELECT severity, COUNT(*) as count
            FROM deadlock_analyses
            WHERE {where_clause}
            GROUP BY severity""",
        params.copy(),
    )
    by_severity = {row["severity"]: row["count"] for row in await cursor.fetchall()}

    # 按表分布
    cursor = await conn.execute(
        f"""SELECT affected_tables_json
            FROM deadlock_analyses
            WHERE {where_clause}""",
        params.copy(),
    )
    table_counts: dict[str, int] = {}
    for row in await cursor.fetchall():
        try:
            tables = json.loads(row["affected_tables_json"] or "[]")
            for t in tables:
                table_counts[t] = table_counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

    by_table = [{"table": k, "count": v} for k, v in sorted(table_counts.items(), key=lambda x: -x[1])]

    # 最近 30 天趋势（按天统计）
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    trend_conditions = conditions.copy()
    trend_conditions.append("timestamp >= ?")
    trend_params = params.copy() + [thirty_days_ago]
    trend_where = " AND ".join(trend_conditions)

    cursor = await conn.execute(
        f"""SELECT strftime('%Y-%m-%d', timestamp) AS day, COUNT(*) as count
            FROM deadlock_analyses
            WHERE {trend_where}
            GROUP BY day
            ORDER BY day""",
        trend_params,
    )
    trend = [{"date": row["day"], "count": row["count"]} for row in await cursor.fetchall()]

    # 平均频率（每天）
    avg_frequency = 0.0
    if total_count > 0:
        # 获取最早和最晚的时间戳
        cursor = await conn.execute(
            f"""SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts
                FROM deadlock_analyses
                WHERE {where_clause}""",
            params.copy(),
        )
        range_row = await cursor.fetchone()
        if range_row and range_row["first_ts"] and range_row["last_ts"]:
            try:
                first_dt = datetime.fromisoformat(range_row["first_ts"])
                last_dt = datetime.fromisoformat(range_row["last_ts"])
                days = max((last_dt - first_dt).total_seconds() / 86400, 1)
                avg_frequency = round(total_count / days, 2)
            except (ValueError, TypeError):
                avg_frequency = round(total_count / 30, 2)

    return {
        "total_count": total_count,
        "by_severity": by_severity,
        "by_table": by_table,
        "trend": trend,
        "avg_frequency": avg_frequency,
    }


@router.get("/{deadlock_id}")
async def get_deadlock_detail(
    deadlock_id: str,
    user: Optional[str] = Depends(get_current_user),
):
    """获取指定死锁分析详情"""
    db = _get_db()
    await _ensure_table(db)

    conn = await db._get_conn()

    cursor = await conn.execute(
        """SELECT id, instance_id, timestamp, raw_text, root_cause,
                  suggestions_json, severity, affected_tables_json,
                  index_suggestions_json, transactions_json, lock_chain_json,
                  created_at
           FROM deadlock_analyses
           WHERE id = ?""",
        (deadlock_id,),
    )
    row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"死锁分析 {deadlock_id} 不存在")

    # 解析 JSON 字段
    def _safe_json_loads(text, default=None):
        try:
            return json.loads(text or "null") or default
        except (json.JSONDecodeError, TypeError):
            return default

    return {
        "id": row["id"],
        "instance_id": row["instance_id"],
        "timestamp": row["timestamp"],
        "raw_text": row["raw_text"],
        "root_cause": row["root_cause"],
        "suggestions": _safe_json_loads(row["suggestions_json"], []),
        "severity": row["severity"],
        "affected_tables": _safe_json_loads(row["affected_tables_json"], []),
        "index_suggestions": _safe_json_loads(row["index_suggestions_json"], []),
        "transactions": _safe_json_loads(row["transactions_json"], []),
        "lock_chain": _safe_json_loads(row["lock_chain_json"], {}),
        "created_at": row["created_at"],
    }


@router.post("/analyze")
async def analyze_deadlocks(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """手动触发死锁分析"""
    db = _get_db()
    analyzer = _get_analyzer()

    try:
        results = await analyzer.analyze_from_logs(
            db=db,
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
        )

        # 转换为可序列化的字典
        items = [analyzer.to_dict(analysis) for analysis in results]

        return {
            "total": len(items),
            "items": items,
        }
    except Exception as e:
        logger.error("死锁分析失败: %s", e)
        raise HTTPException(status_code=500, detail=f"死锁分析失败: {str(e)}")


@router.get("/lock-chain/{deadlock_id}")
async def get_lock_chain(
    deadlock_id: str,
    user: Optional[str] = Depends(get_current_user),
):
    """获取锁等待链可视化数据

    返回格式适合前端图可视化组件（如 G6/ECharts graph）：
    - nodes: 事务节点列表
    - edges: 等待关系边列表
    """
    db = _get_db()
    await _ensure_table(db)

    conn = await db._get_conn()

    cursor = await conn.execute(
        """SELECT transactions_json, lock_chain_json
           FROM deadlock_analyses
           WHERE id = ?""",
        (deadlock_id,),
    )
    row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"死锁分析 {deadlock_id} 不存在")

    # 解析事务和锁链数据
    try:
        transactions = json.loads(row["transactions_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        transactions = []

    try:
        lock_chain = json.loads(row["lock_chain_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        lock_chain = {}

    # 构建节点列表
    nodes = []
    for tx in transactions:
        tx_id = tx.get("transaction_id", "")
        # 判断是否为被回滚的事务（victim）
        is_victim = lock_chain.get("victim") == tx_id
        nodes.append({
            "id": tx_id,
            "label": f"TX {tx_id}",
            "type": "victim" if is_victim else "transaction",
            "query": tx.get("query", ""),
            "thread_id": tx.get("thread_id", ""),
            "rollback_weight": tx.get("rollback_weight", 0),
        })

    # 构建边列表
    edges = []
    chain_list = lock_chain.get("chain", [])
    for from_tx, to_tx, resource in chain_list:
        edges.append({
            "from": from_tx,
            "to": to_tx,
            "label": "等待锁",
            "resource": resource,
        })

    return {
        "nodes": nodes,
        "edges": edges,
    }
