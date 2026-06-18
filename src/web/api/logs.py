"""日志数据接口模块"""

from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.config import Config
from src.vector.manager import VectorSearchManager
from src.web.api.auth import get_current_user
from src.utils import parse_time_range_datetime
from src.web.api.common import resolve_time_range as _resolve_time_range
from src.web.api.deps import get_db as _get_db

router = APIRouter(prefix="/api/logs", tags=["日志"])


# ── Pydantic 模型 ───────────────────────────────────────────

class LogEntry(BaseModel):
    id: int
    instance_id: int
    timestamp: str
    level: str
    error_code: Optional[str] = None
    thread_id: Optional[str] = None
    message: Optional[str] = None
    raw_line: Optional[str] = None
    created_at: str


class LogListResponse(BaseModel):
    items: list[LogEntry]
    total: int
    limit: int
    offset: int


class LevelCount(BaseModel):
    level: str
    count: int


class LogStatsResponse(BaseModel):
    total_errors: int = 0
    today_errors: int = 0
    critical_alerts: int = 0
    instance_count: int = 0
    levels: list[LevelCount] = []
    total: int = 0


class DistributionResponse(BaseModel):
    by_level: list[dict[str, Any]]
    by_category: list[dict[str, Any]]
    by_error_code: list[dict[str, Any]]


class TrendBucket(BaseModel):
    time: str
    count: int


class TrendResponse(BaseModel):
    interval: str
    data: list[TrendBucket]


# ── 数据库实例 ──────────────────────────────────────────────

_vector_search: VectorSearchManager | None = None


def _get_vector_search() -> VectorSearchManager:
    global _vector_search
    if _vector_search is None:
        _vector_search = VectorSearchManager()
    return _vector_search


# ── API 端点 ────────────────────────────────────────────────

@router.get("", response_model=LogListResponse)
async def query_logs(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    level: Optional[str] = Query(None, description="日志级别"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    limit: int = Query(100, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    user: Optional[str] = Depends(get_current_user),
):
    """查询日志列表"""
    db = _get_db()

    items = await db.query_logs(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
        level=level,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )

    total = await db.count_logs(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
        level=level,
        keyword=keyword,
    )

    return LogListResponse(
        items=[LogEntry(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=LogStatsResponse)
async def log_stats(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    period: Optional[str] = Query(None, description="时间段 (1h/24h/7d/all/Nh/Nd)"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """日志统计 - 总错误数、关键告警、今日错误等"""
    db = _get_db()
    st, et = _resolve_time_range(period, start_time, end_time)

    distribution = await db.get_error_distribution(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
    )

    levels = [LevelCount(level=item["level"], count=item["count"]) for item in distribution["by_level"]]
    total = sum(item.count for item in levels)

    # 计算总错误数（ERROR + FATAL 级别）
    total_errors = sum(l.count for l in levels if l.level.upper() in ("ERROR", "FATAL"))

    # 计算今日错误数
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_dist = await db.get_error_distribution(instance_id=instance_id, start_time=today_start)
    today_errors = sum(item["count"] for item in today_dist["by_level"] if item["level"].upper() in ("ERROR", "FATAL"))

    # 关键告警数
    alerts = await db.query_alerts(limit=10000)
    critical_alerts = len(alerts)

    # 实例数
    stats = await db.get_stats()
    instance_count = len(stats.get("instances", []))

    return LogStatsResponse(
        total_errors=total_errors,
        today_errors=today_errors,
        critical_alerts=critical_alerts,
        instance_count=instance_count,
        levels=levels,
        total=total,
    )


# 错误相关级别（用于分布和趋势的默认过滤）
_ERROR_LEVELS = ["ERROR", "WARNING", "FATAL", "System"]


@router.get("/distribution", response_model=DistributionResponse)
async def log_distribution(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    period: Optional[str] = Query(None, description="时间段 (1h/24h/7d/all/Nh/Nd)"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    level: Optional[str] = Query(None, description="级别过滤，逗号分隔 (如 ERROR,WARNING)，默认只显示错误相关级别"),
    user: Optional[str] = Depends(get_current_user),
):
    """错误分布 - 按级别、按类别、按错误码"""
    db = _get_db()
    st, et = _resolve_time_range(period, start_time, end_time)

    # 解析级别过滤
    if level is not None:
        levels = [l.strip().upper() for l in level.split(",") if l.strip()] if level else None
    else:
        levels = _ERROR_LEVELS

    distribution = await db.get_error_distribution(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
        levels=levels,
    )

    return DistributionResponse(
        by_level=distribution["by_level"],
        by_category=distribution["by_category"],
        by_error_code=distribution["by_error_code"],
    )


@router.get("/trend", response_model=TrendResponse)
async def log_trend(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    period: Optional[str] = Query(None, description="时间段 (1h/24h/7d/all/Nh/Nd)"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    interval: str = Query("hour", description="时间间隔 (hour/day)"),
    group_by: Optional[str] = Query(None, description="分组方式 (hour/day)"),
    level: Optional[str] = Query(None, description="级别过滤，逗号分隔 (如 ERROR,WARNING)，默认只显示错误相关级别"),
    user: Optional[str] = Depends(get_current_user),
):
    """错误趋势 - 时间序列数据"""
    db = _get_db()
    st, et = _resolve_time_range(period, start_time, end_time)

    # group_by 优先于 interval
    actual_interval = group_by if group_by else interval

    # 解析级别过滤
    if level is not None:
        levels = [l.strip().upper() for l in level.split(",") if l.strip()] if level else None
    else:
        levels = _ERROR_LEVELS

    data = await db.get_error_trend(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
        interval=actual_interval,
        levels=levels,
    )

    # 转换为前端期望的扁平格式 [{time, count}]
    buckets = [
        TrendBucket(time=item["time"], count=item["total"])
        for item in data
    ]

    return TrendResponse(interval=actual_interval, data=buckets)


@router.get("/semantic")
async def semantic_search(
    query: str = Query(..., description="语义搜索查询"),
    k: int = Query(10, ge=1, le=100, description="返回数量"),
    user: Optional[str] = Depends(get_current_user),
):
    """语义搜索日志 - 基于向量相似度"""
    vs = _get_vector_search()
    if not vs.is_available():
        return {"items": [], "message": "语义搜索未启用，请在配置中启用 embedding"}

    try:
        results = await vs.search_similar(query, k=k)
        return {"items": results, "total": len(results)}
    except Exception as e:
        return {"items": [], "message": f"语义搜索失败: {str(e)}"}


@router.get("/semantic/similar")
async def semantic_similar_edges(
    period: Optional[str] = Query("7d", description="时间段"),
    k: int = Query(5, ge=2, le=20, description="每个类别的相似日志数"),
    user: Optional[str] = Depends(get_current_user),
):
    """获取语义相似度关联边 - 用于知识图谱的 Embedding 增强边

    需要 Embedding 配置，否则返回空列表。
    返回格式: {edges: [{source, target, similarity}], available: bool}
    """
    vs = _get_vector_search()
    if not vs.is_available():
        return {"edges": [], "available": False, "message": "Embedding 未配置，语义相似度边不可用"}

    try:
        db = _get_db()
        st, et = _resolve_time_range(period)

        # 获取各类别的代表性日志
        distribution = await db.get_error_distribution(
            start_time=st, end_time=et, levels=_ERROR_LEVELS
        )
        by_category = distribution.get("by_category", [])

        edges = []
        for cat_item in by_category[:5]:  # 限制类别数量
            cat = cat_item["category"]
            # 获取该类别的日志
            logs = await db.query_logs(
                start_time=st, end_time=et,
                limit=k,
            )
            if not logs:
                continue

            # 对每条日志搜索相似日志
            for log in logs[:3]:  # 每类最多3条
                msg = log.get("message", "")
                if not msg.strip():
                    continue
                similar = await vs.search_similar(msg, k=k)
                for s in similar:
                    if s.get("id") != log.get("id") and s.get("score", 0) > 0.7:
                        edges.append({
                            "source": f"log_{log.get('id')}",
                            "target": f"log_{s.get('id')}",
                            "similarity": round(s.get("score", 0), 3),
                            "source_msg": msg[:50],
                            "target_msg": s.get("message", "")[:50],
                        })

        return {"edges": edges, "available": True}
    except Exception as e:
        return {"edges": [], "available": False, "message": f"获取语义相似度失败: {str(e)}"}
