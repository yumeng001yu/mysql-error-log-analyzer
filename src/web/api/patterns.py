"""日志模式识别 API"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from src.analyzer.pattern_recognizer import PatternRecognizer
from src.web.api.auth import get_current_user
from src.web.api.deps import get_db as _get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patterns", tags=["patterns"])

# ── 全局实例 ──────────────────────────────────────────────

_recognizer: PatternRecognizer | None = None


def _get_recognizer() -> PatternRecognizer:
    """获取模式识别器单例"""
    global _recognizer
    if _recognizer is None:
        _recognizer = PatternRecognizer()
    return _recognizer


# ── API 端点 ──────────────────────────────────────────────

@router.get("/recognize")
async def recognize_patterns(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    min_count: int = Query(2, ge=1, description="最小出现次数"),
    user: Optional[str] = None,
):
    """运行模式识别，返回所有模式及异常信息"""
    db = _get_db()
    recognizer = _get_recognizer()

    try:
        patterns = await recognizer.recognize_patterns(
            db=db,
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
            min_count=min_count,
        )
        return {"patterns": [p.to_dict() for p in patterns], "total": len(patterns)}
    except Exception as e:
        logger.error("模式识别失败: %s", e)
        return {"patterns": [], "total": 0, "error": str(e)}


@router.get("/anomalies")
async def get_anomalies(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = None,
):
    """获取异常模式列表（仅返回 is_anomaly=True 的模式）"""
    db = _get_db()
    recognizer = _get_recognizer()

    try:
        patterns = await recognizer.recognize_patterns(
            db=db,
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
            min_count=1,  # 异常模式可能只出现一次
        )
        anomalies = [p for p in patterns if p.is_anomaly]
        return {"patterns": [p.to_dict() for p in anomalies], "total": len(anomalies)}
    except Exception as e:
        logger.error("异常检测失败: %s", e)
        return {"patterns": [], "total": 0, "error": str(e)}


@router.get("/stats")
async def get_pattern_stats(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = None,
):
    """获取模式统计信息

    返回：
    - total_patterns: 模式总数
    - anomaly_count: 异常模式数
    - top_patterns: 出现次数最多的前 10 个模式
    - level_distribution: 按日志级别的模式分布
    """
    db = _get_db()
    recognizer = _get_recognizer()

    try:
        patterns = await recognizer.recognize_patterns(
            db=db,
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
            min_count=2,
        )

        # 统计异常模式数
        anomaly_count = sum(1 for p in patterns if p.is_anomaly)

        # 取 Top 10 模式
        top_patterns = [p.to_dict() for p in patterns[:10]]

        # 按级别分布
        level_dist: dict[str, int] = {}
        for p in patterns:
            level_dist[p.level] = level_dist.get(p.level, 0) + 1
        level_distribution = [
            {"level": level, "count": count}
            for level, count in sorted(level_dist.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "total_patterns": len(patterns),
            "anomaly_count": anomaly_count,
            "top_patterns": top_patterns,
            "level_distribution": level_distribution,
        }
    except Exception as e:
        logger.error("获取模式统计失败: %s", e)
        return {
            "total_patterns": 0,
            "anomaly_count": 0,
            "top_patterns": [],
            "level_distribution": [],
            "error": str(e),
        }


@router.get("/{pattern_id}/trend")
async def get_pattern_trend(
    pattern_id: str,
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    hours: int = Query(24, ge=1, le=168, description="回溯小时数"),
    user: Optional[str] = None,
):
    """获取指定模式的小时级趋势数据"""
    db = _get_db()
    recognizer = _get_recognizer()

    try:
        trend = await recognizer.get_pattern_trend(
            db=db,
            pattern_id=pattern_id,
            instance_id=instance_id,
            hours=hours,
        )
        return {"pattern_id": pattern_id, "trend": trend}
    except Exception as e:
        logger.error("获取模式趋势失败: %s", e)
        return {"pattern_id": pattern_id, "trend": [], "error": str(e)}
