"""定期运维报表 API"""

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.analyzer.report_generator import ReportGenerator
from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])

# ── 数据库与生成器实例 ──────────────────────────────────

_db: DatabaseManager | None = None
_generator: ReportGenerator | None = None


def _get_db() -> DatabaseManager:
    """获取数据库管理器实例"""
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


def _get_generator() -> ReportGenerator:
    """获取报表生成器实例"""
    global _generator
    if _generator is None:
        _generator = ReportGenerator()
    return _generator


def _report_to_dict(report) -> dict:
    """将 OperationsReport 对象转换为可序列化的字典"""
    return {
        "id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "generated_at": report.generated_at,
        "instance_id": report.instance_id,
        "instance_name": report.instance_name,
        "sections": [
            {
                "title": s.title,
                "content_type": s.content_type,
                "data": s.data,
            }
            for s in report.sections
        ],
        "summary": report.summary,
        "health_score": report.health_score,
    }


# ── API 端点 ────────────────────────────────────────────


@router.post("/generate")
async def generate_report(
    report_type: str = Query(..., description="报表类型: daily/weekly/monthly"),
    instance_id: Optional[int] = Query(None, description="实例 ID，为空时汇总所有实例"),
    date: Optional[str] = Query(None, description="日报日期，格式: 2024-01-15"),
    week_start: Optional[str] = Query(None, description="周报起始日期（周一），格式: 2024-01-15"),
    month: Optional[str] = Query(None, description="月报月份，格式: 2024-01"),
):
    """生成运维报表"""
    # 参数校验
    valid_types = {"daily", "weekly", "monthly"}
    if report_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的报表类型，可选: {valid_types}")

    db = _get_db()
    generator = _get_generator()

    try:
        if report_type == "daily":
            report = await generator.generate_daily_report(
                db, instance_id=instance_id, date=date,
            )
        elif report_type == "weekly":
            report = await generator.generate_weekly_report(
                db, instance_id=instance_id, week_start=week_start,
            )
        else:  # monthly
            report = await generator.generate_monthly_report(
                db, instance_id=instance_id, month=month,
            )

        # 保存报表到数据库
        await generator.save_report(db, report)

        return _report_to_dict(report)

    except Exception as e:
        logger.error("生成报表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"生成报表失败: {str(e)[:200]}")


@router.get("/list")
async def list_reports(
    report_type: Optional[str] = Query(None, description="报表类型过滤: daily/weekly/monthly"),
    instance_id: Optional[int] = Query(None, description="实例 ID 过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
):
    """列出已保存的报表（仅摘要信息）"""
    db = _get_db()
    generator = _get_generator()

    try:
        reports = await generator.list_reports(
            db, report_type=report_type, instance_id=instance_id, limit=limit,
        )
        return {"items": reports, "total": len(reports)}
    except Exception as e:
        logger.error("查询报表列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"查询报表列表失败: {str(e)[:200]}")


@router.get("/latest/{report_type}")
async def get_latest_report(
    report_type: str,
    instance_id: Optional[int] = Query(None, description="实例 ID 过滤"),
):
    """获取指定类型的最新报表"""
    valid_types = {"daily", "weekly", "monthly"}
    if report_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的报表类型，可选: {valid_types}")

    db = _get_db()
    generator = _get_generator()

    try:
        report = await generator.get_latest_report(
            db, report_type=report_type, instance_id=instance_id,
        )
        if report is None:
            raise HTTPException(status_code=404, detail="未找到该类型的报表")

        return _report_to_dict(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询最新报表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"查询最新报表失败: {str(e)[:200]}")


@router.get("/{report_id}")
async def get_report(report_id: str):
    """获取指定 ID 的报表"""
    db = _get_db()
    generator = _get_generator()

    try:
        report = await generator.get_report(db, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报表不存在")

        return _report_to_dict(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询报表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"查询报表失败: {str(e)[:200]}")


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """删除指定 ID 的报表"""
    db = _get_db()
    generator = _get_generator()

    try:
        success = await generator.delete_report(db, report_id)
        if not success:
            raise HTTPException(status_code=404, detail="报表不存在")

        return {"message": "报表删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除报表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除报表失败: {str(e)[:200]}")
