"""分析接口模块"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.config import Config
from src.storage.database import DatabaseManager
from src.utils import is_valid_time_range, parse_time_range, parse_time_range_datetime
from src.web.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["分析"])


# ── Pydantic 模型 ───────────────────────────────────────────

class AnalysisRunRequest(BaseModel):
    period: str = "7d"  # all | Nh(如3h) | Nd(如3d)
    instance_id: Optional[str] = None
    confirm_large_analysis: bool = False


class AnalysisRunResponse(BaseModel):
    summary: str = ""
    suggestions: list[dict] = []
    correlations: list[dict] = []
    priorities: list[dict] = []


class AnalysisResultItem(BaseModel):
    id: int
    instance_id: int
    time_range_start: str
    time_range_end: str
    category: str
    summary: Optional[str] = None
    suggestion: Optional[str] = None
    severity: Optional[str] = None
    created_at: str


class AnalysisResultsResponse(BaseModel):
    items: list[AnalysisResultItem]
    # 前端期望的扁平字段
    summary: Optional[str] = None
    suggestions: list[dict] = []
    correlations: list[dict] = []
    priorities: list[dict] = []


class ChatRequest(BaseModel):
    message: str
    context: Optional[dict] = None
    history: Optional[list[dict]] = None


class ChatResponse(BaseModel):
    response: str


# ── 数据库实例 ──────────────────────────────────────────────

_db: DatabaseManager | None = None


def _get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


# ── API 端点 ────────────────────────────────────────────────

@router.post("/analysis/run", response_model=AnalysisRunResponse)
async def run_analysis(
    body: AnalysisRunRequest,
    user: Optional[str] = Depends(get_current_user),
):
    """触发分析"""
    config = Config()
    db = _get_db()

    # 验证时间范围格式
    if not is_valid_time_range(body.period):
        raise HTTPException(
            status_code=400,
            detail=f"无效的时间范围: {body.period}，格式: Nh(如3h) 或 Nd(如3d) 或 all",
        )

    start_time, end_time = parse_time_range(body.period)

    # 全量分析时检查日志大小
    if body.period == "all" and not body.confirm_large_analysis:
        try:
            stats = await db.get_stats()
            total_logs = stats.get("total_logs", 0)
            if total_logs > 10000:
                return AnalysisRunResponse(
                    summary="",
                    suggestions=[],
                    correlations=[],
                    priorities=[],
                )
        except Exception:
            pass

    # 获取日志数据
    try:
        logs = await db.query_logs(
            start_time=start_time if start_time else None,
            end_time=end_time if end_time else None,
            limit=1000,
        )
    except Exception as e:
        logger.warning("查询日志失败: %s", e)
        logs = []

    if not logs:
        return AnalysisRunResponse(
            summary="指定时间段内没有发现日志记录。",
            suggestions=[],
            correlations=[],
            priorities=[],
        )

    # 执行分析流程
    try:
        from src.analyzer.graph import AnalysisGraph

        analysis_graph = AnalysisGraph(config)
        result = await analysis_graph.run_analysis(
            instance_id=body.instance_id or "1",
            time_range={"start": start_time, "end": end_time},
        )

        summary = result.get("summary", "")
        suggestions = result.get("suggestions", [])
        classified_logs = result.get("classified_logs", [])
        correlations_data = result.get("correlations", {})

        # 构建关联分析列表
        correlations = []
        if isinstance(correlations_data, dict):
            for item in correlations_data.get("time_patterns", []):
                correlations.append({
                    "type": "time_pattern",
                    "category": item.get("category", ""),
                    "description": item.get("description", ""),
                })
            for item in correlations_data.get("cross_category", []):
                correlations.append({
                    "type": "cross_category",
                    "source": item.get("source_category", ""),
                    "target": item.get("target_category", ""),
                    "description": item.get("description", ""),
                })
            for item in correlations_data.get("anomalies", []):
                correlations.append({
                    "type": "anomaly",
                    "category": item.get("category", ""),
                    "description": item.get("description", ""),
                })

        # 构建优先级排序
        priorities = []
        if suggestions:
            for s in suggestions:
                priorities.append({
                    "level": s.get("priority", "medium"),
                    "issue": s.get("category", ""),
                    "description": s.get("suggestion", ""),
                })
        priorities.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("level", "medium"), 1))

        # 存储分析结果到数据库
        try:
            stats = await db.get_stats()
            instances = stats.get("instances", [])
            db_instance_id = instances[0]["id"] if instances else 1

            # 为每个 suggestion 存储一条记录
            for s in suggestions:
                await db.insert_analysis_result({
                    "instance_id": db_instance_id,
                    "time_range_start": start_time,
                    "time_range_end": end_time,
                    "category": s.get("category", "unknown"),
                    "summary": summary,
                    "suggestion": s.get("suggestion", ""),
                    "severity": s.get("priority", "medium"),
                })
        except Exception as e:
            logger.warning("存储分析结果失败: %s", e)

        return AnalysisRunResponse(
            summary=summary,
            suggestions=suggestions,
            correlations=correlations,
            priorities=priorities,
        )
    except Exception as e:
        logger.error("分析执行失败: %s", e)
        raise HTTPException(status_code=500, detail=f"分析执行失败: {str(e)}")


@router.get("/analysis/results")
async def get_analysis_results(
    period: Optional[str] = Query(None, description="时间段"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """获取分析结果"""
    db = _get_db()

    # 解析时间段
    if period and period != "all":
        result = parse_time_range_datetime(period)
        st = result.get("start")
        et = result.get("end")
        start_time = st.isoformat() if st else None
        end_time = et.isoformat() if et else None

    results = await db.query_analysis(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
    )

    items = [AnalysisResultItem(**item) for item in results]

    # 如果有结果，合并为前端期望的格式
    if items:
        # 合并所有分析结果的 summary
        summaries = [item.summary for item in items if item.summary]
        combined_summary = "\n".join(summaries) if summaries else ""

        # 从结果构建 suggestions 和 priorities
        suggestions = []
        priorities = []
        for item in items:
            if item.suggestion:
                suggestions.append({
                    "category": item.category,
                    "suggestion": item.suggestion,
                    "priority": item.severity or "medium",
                })
                priorities.append({
                    "level": item.severity or "medium",
                    "issue": item.category,
                    "description": item.suggestion,
                })

        return AnalysisResultsResponse(
            items=items,
            summary=combined_summary,
            suggestions=suggestions,
            correlations=[],
            priorities=priorities,
        )

    return AnalysisResultsResponse(items=[], summary="", suggestions=[], correlations=[], priorities=[])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: Optional[str] = Depends(get_current_user),
):
    """对话接口"""
    try:
        from src.analyzer.graph import AnalysisGraph

        config = Config()
        analysis_graph = AnalysisGraph(config)

        messages = [{"role": "user", "content": body.message}]
        # 添加历史消息
        if body.history:
            messages = body.history + messages

        response_text = await analysis_graph.run_chat(
            messages=messages,
            context=body.context,
        )

        return ChatResponse(response=response_text)
    except Exception as e:
        logger.error("对话执行失败: %s", e)
        raise HTTPException(status_code=500, detail=f"对话执行失败: {str(e)}")
