"""分析接口模块"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import Config
from src.storage.database import DatabaseManager
from src.web.api.auth import get_current_user

router = APIRouter(prefix="/api", tags=["分析"])


# ── Pydantic 模型 ───────────────────────────────────────────

class AnalysisRunRequest(BaseModel):
    instance_id: str
    time_range: str = "7d"  # all | 7d | 24h | 1h
    confirm_large_analysis: bool = False


class AnalysisRunResponse(BaseModel):
    instance_id: str
    time_range_start: str
    time_range_end: str
    category: str
    summary: Optional[str] = None
    suggestion: Optional[str] = None
    severity: Optional[str] = None
    warning: Optional[str] = None


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


class ChatRequest(BaseModel):
    message: str
    context: Optional[dict] = None


class ChatResponse(BaseModel):
    response: str


# ── 工具函数 ────────────────────────────────────────────────

def _parse_time_range(time_range: str) -> tuple[str, str]:
    """将 time_range 字符串转换为 (start_time, end_time) ISO 格式"""
    now = datetime.now(timezone.utc)
    end = now.isoformat()

    if time_range == "1h":
        start = (now - timedelta(hours=1)).isoformat()
    elif time_range == "24h":
        start = (now - timedelta(hours=24)).isoformat()
    elif time_range == "7d":
        start = (now - timedelta(days=7)).isoformat()
    elif time_range == "all":
        start = ""
    else:
        start = (now - timedelta(days=7)).isoformat()

    return start, end


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

    start_time, end_time = _parse_time_range(body.time_range)

    # 全量分析时检查日志大小
    if body.time_range == "all" and not body.confirm_large_analysis:
        try:
            instance_id_int = int(body.instance_id)
            size_info = await db.get_log_file_size_info(instance_id_int)
            warning_threshold_mb = config.get(
                "collector", "full_analysis_warning_mb", default=500
            )
            file_size_mb = size_info.get("file_size_mb", 0)
            if size_info.get("found") and file_size_mb > warning_threshold_mb:
                return AnalysisRunResponse(
                    instance_id=body.instance_id,
                    time_range_start=start_time,
                    time_range_end=end_time,
                    category="",
                    summary="",
                    suggestion="",
                    severity="warning",
                    warning=(
                        f"日志文件大小为 {file_size_mb} MB，超过阈值 {warning_threshold_mb} MB。"
                        "全量分析可能耗时较长，请确认是否继续。"
                        "设置 confirm_large_analysis=true 以确认。"
                    ),
                )
        except (ValueError, Exception):
            pass

    # 执行分析
    try:
        from src.analyzer.graph import AnalysisGraph

        analysis_graph = AnalysisGraph(config)
        result = await analysis_graph.run_analysis(
            instance_id=body.instance_id,
            time_range={"start": start_time, "end": end_time},
        )

        # 存储分析结果
        analysis_result = {
            "instance_id": int(body.instance_id),
            "time_range_start": start_time,
            "time_range_end": end_time,
            "category": result.get("classified_logs", [{}])[0].get("category", "unknown") if result.get("classified_logs") else "unknown",
            "summary": result.get("summary", ""),
            "suggestion": result.get("suggestions", [{}])[0].get("suggestion", "") if result.get("suggestions") else "",
            "severity": result.get("classified_logs", [{}])[0].get("severity", "info") if result.get("classified_logs") else "info",
        }
        await db.insert_analysis_result(analysis_result)

        return AnalysisRunResponse(
            instance_id=body.instance_id,
            time_range_start=start_time,
            time_range_end=end_time,
            category=analysis_result["category"],
            summary=analysis_result["summary"],
            suggestion=analysis_result["suggestion"],
            severity=analysis_result["severity"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析执行失败: {str(e)}")


@router.get("/analysis/results", response_model=AnalysisResultsResponse)
async def get_analysis_results(
    instance_id: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user: Optional[str] = Depends(get_current_user),
):
    """获取分析结果"""
    db = _get_db()
    results = await db.query_analysis(
        instance_id=instance_id,
        start_time=start_time,
        end_time=end_time,
    )

    items = [AnalysisResultItem(**item) for item in results]
    return AnalysisResultsResponse(items=items)


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
        response_text = await analysis_graph.run_chat(
            messages=messages,
            context=body.context,
        )

        return ChatResponse(response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话执行失败: {str(e)}")
