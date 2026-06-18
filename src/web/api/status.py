"""状态接口模块"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.config import Config
from src.status import StatusTracker
from src.web.api.auth import get_current_user
from src.web.api.deps import get_db as _get_db

router = APIRouter(tags=["状态"])


# ── Pydantic 模型 ───────────────────────────────────────────

class StatusResponse(BaseModel):
    start_time: Optional[str] = None
    uptime_seconds: float
    monitored_instances: list[dict]
    last_analysis_time: dict[str, str]
    processing_progress: dict[str, float]
    cpu_percent: float
    memory_mb: float
    total_logs_processed: int
    total_alerts: int
    is_running: bool


class SummaryResponse(BaseModel):
    summary: str


class AlertItem(BaseModel):
    id: int
    instance_id: int
    log_entry_id: Optional[int] = None
    alert_type: str
    llm_suggestion: Optional[str] = None
    is_read: int
    created_at: str


class AlertsResponse(BaseModel):
    items: list[AlertItem]


class AlertReadResponse(BaseModel):
    success: bool
    alert_id: int


# ── API 端点 ────────────────────────────────────────────────

@router.get("/api/status", response_model=StatusResponse)
async def get_status(
    user: Optional[str] = Depends(get_current_user),
):
    """获取程序状态"""
    tracker = StatusTracker()
    status = tracker.get_status()
    return StatusResponse(**status)


@router.get("/api/status/summary", response_model=SummaryResponse)
async def get_status_summary(
    user: Optional[str] = Depends(get_current_user),
):
    """获取简要状态文本"""
    tracker = StatusTracker()
    summary = tracker.get_summary()
    return SummaryResponse(summary=summary)


@router.get("/api/alerts", response_model=AlertsResponse)
async def get_alerts(
    is_read: Optional[bool] = Query(None, description="是否已读"),
    limit: int = Query(50, ge=1, le=500, description="数量限制"),
    user: Optional[str] = Depends(get_current_user),
):
    """获取告警列表"""
    db = _get_db()
    alerts = await db.query_alerts(is_read=is_read, limit=limit)

    items = [AlertItem(**alert) for alert in alerts]
    return AlertsResponse(items=items)


@router.put("/api/alerts/{alert_id}/read", response_model=AlertReadResponse)
async def mark_alert_read(
    alert_id: int,
    user: Optional[str] = Depends(get_current_user),
):
    """标记告警已读"""
    db = _get_db()
    await db.mark_alert_read(alert_id)
    return AlertReadResponse(success=True, alert_id=alert_id)
