"""日志数据接口模块"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.config import Config
from src.storage.database import DatabaseManager
from src.vector.manager import VectorSearchManager
from src.web.api.auth import get_current_user

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
    levels: list[LevelCount]
    total: int


class DistributionResponse(BaseModel):
    by_level: list[dict[str, Any]]
    by_category: list[dict[str, Any]]
    by_error_code: list[dict[str, Any]]


class TrendBucket(BaseModel):
    time: str
    levels: dict[str, int]
    total: int


class TrendResponse(BaseModel):
    interval: str
    data: list[TrendBucket]


# ── 数据库实例 ──────────────────────────────────────────────

_db: DatabaseManager | None = None

_vector_search: VectorSearchManager | None = None


def _get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


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
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """日志统计 - 各级别数量、总数"""
    db = _get_db()
    distribution = await db.get_error_distribution(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
    )

    levels = [LevelCount(level=item["level"], count=item["count"]) for item in distribution["by_level"]]
    total = sum(item.count for item in levels)

    return LogStatsResponse(levels=levels, total=total)


@router.get("/distribution", response_model=DistributionResponse)
async def log_distribution(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """错误分布 - 按级别、按类别、按错误码"""
    db = _get_db()
    distribution = await db.get_error_distribution(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
    )

    return DistributionResponse(
        by_level=distribution["by_level"],
        by_category=distribution["by_category"],
        by_error_code=distribution["by_error_code"],
    )


@router.get("/trend", response_model=TrendResponse)
async def log_trend(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    interval: str = Query("hour", description="时间间隔 (hour/day)"),
    user: Optional[str] = Depends(get_current_user),
):
    """错误趋势 - 时间序列数据"""
    db = _get_db()
    data = await db.get_error_trend(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
        interval=interval,
    )

    buckets = [
        TrendBucket(time=item["time"], levels=item["levels"], total=item["total"])
        for item in data
    ]

    return TrendResponse(interval=interval, data=buckets)


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
