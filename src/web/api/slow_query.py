"""慢查询日志分析 API"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.config import Config
from src.utils import is_valid_time_range, parse_time_range, parse_time_range_datetime
from src.web.api.auth import get_current_user
from src.web.api.common import resolve_time_range as _resolve_time_range
from src.web.api.deps import get_db as _get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["慢查询"])


# ── Pydantic 模型 ───────────────────────────────────────────

class SlowQueryAnalyzeRequest(BaseModel):
    period: str = "7d"
    sql_hash: Optional[str] = None


class SlowQueryAnalyzeResponse(BaseModel):
    summary: str = ""
    suggestions: list[dict] = []


class SlowQueryParseRequest(BaseModel):
    instance_id: Optional[int] = None


class SlowQueryParseResponse(BaseModel):
    parsed_count: int = 0
    new_count: int = 0


# ── API 端点 ────────────────────────────────────────────────

@router.get("/slow-query/stats")
async def slow_query_stats(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    period: Optional[str] = Query(None, description="时间段 (1h/24h/7d/all/Nh/Nd)"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """慢查询统计"""
    db = _get_db()
    st, et = _resolve_time_range(period, start_time, end_time)

    stats = await db.get_slow_query_stats(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
    )
    return stats


@router.get("/slow-query/list")
async def slow_query_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    period: Optional[str] = Query(None, description="时间段 (1h/24h/7d/all/Nh/Nd)"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    min_query_time: Optional[float] = Query(None, description="最小查询时间（秒）"),
    sql_type: Optional[str] = Query(None, description="SQL 类型 (SELECT/INSERT/UPDATE/DELETE/ALTER/CREATE/DROP/OTHER)"),
    sort_by: Optional[str] = Query("query_time", description="排序字段 (query_time/lock_time/rows_examined/slow_score)"),
    user: Optional[str] = Depends(get_current_user),
):
    """慢查询列表（分页）"""
    db = _get_db()
    st, et = _resolve_time_range(period, start_time, end_time)

    offset = (page - 1) * page_size

    items = await db.query_slow_queries(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
        min_query_time=min_query_time,
        sql_type=sql_type,
        sort_by=sort_by,
        limit=page_size,
        offset=offset,
    )

    total = await db.count_slow_queries(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
        min_query_time=min_query_time,
        sql_type=sql_type,
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/slow-query/distribution")
async def slow_query_distribution(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    period: Optional[str] = Query(None, description="时间段 (1h/24h/7d/all/Nh/Nd)"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    user: Optional[str] = Depends(get_current_user),
):
    """慢查询分布"""
    db = _get_db()
    st, et = _resolve_time_range(period, start_time, end_time)

    distribution = await db.get_slow_query_distribution(
        instance_id=instance_id,
        start_time=st,
        end_time=et,
    )
    return distribution


@router.post("/slow-query/analyze", response_model=SlowQueryAnalyzeResponse)
async def analyze_slow_queries(
    body: SlowQueryAnalyzeRequest,
    user: Optional[str] = Depends(get_current_user),
):
    """触发 LLM 分析慢查询"""
    config = Config()

    # 检查 LLM 是否配置
    api_key = config.get("llm", "api_key", default="")
    if not api_key:
        return SlowQueryAnalyzeResponse(
            summary="LLM 未配置，无法进行慢查询分析。请在配置文件中设置 llm.api_key。",
            suggestions=[],
        )

    db = _get_db()

    # 验证时间范围格式
    if not is_valid_time_range(body.period):
        raise HTTPException(
            status_code=400,
            detail=f"无效的时间范围: {body.period}，格式: Nh(如3h) 或 Nd(如3d) 或 all",
        )

    start_time, end_time = parse_time_range(body.period)

    # 获取慢查询统计数据
    stats = await db.get_slow_query_stats(
        start_time=start_time if start_time else None,
        end_time=end_time if end_time else None,
    )

    if stats["total_count"] == 0:
        return SlowQueryAnalyzeResponse(
            summary="指定时间段内没有发现慢查询记录。",
            suggestions=[],
        )

    # 获取分布数据
    distribution = await db.get_slow_query_distribution(
        start_time=start_time if start_time else None,
        end_time=end_time if end_time else None,
    )

    # 如果指定了 sql_hash，获取该查询的详细信息
    target_queries = []
    if body.sql_hash:
        queries = await db.query_slow_queries(
            start_time=start_time if start_time else None,
            end_time=end_time if end_time else None,
            limit=10,
        )
        target_queries = [q for q in queries if q.get("sql_hash") == body.sql_hash]

    # 构建分析提示
    top_slow = stats.get("top_slow", [])
    by_type = distribution.get("by_type", [])

    prompt_parts = [
        "请分析以下 MySQL 慢查询日志数据，给出优化建议：\n",
        f"总慢查询数: {stats['total_count']}",
        f"平均查询时间: {stats['avg_query_time']}秒",
        f"最大查询时间: {stats['max_query_time']}秒",
        f"平均锁等待时间: {stats['avg_lock_time']}秒",
        f"平均扫描行数: {stats['avg_rows_examined']}\n",
        "按 SQL 类型分布:",
    ]
    for item in by_type:
        prompt_parts.append(f"  {item['sql_type']}: {item['count']}次")

    prompt_parts.append("\nTop 慢查询（按总耗时排序）:")
    for item in top_slow[:5]:
        prompt_parts.append(
            f"  SQL模板: {item.get('sql_template', 'N/A')[:100]}\n"
            f"  执行次数: {item['count']}, 平均耗时: {round(item['avg_query_time'], 2)}秒, "
            f"最大耗时: {round(item['max_query_time'], 2)}秒, 总耗时: {round(item['total_query_time'], 2)}秒"
        )

    if target_queries:
        prompt_parts.append("\n指定查询详情:")
        for q in target_queries[:3]:
            prompt_parts.append(
                f"  SQL: {q.get('sql_text', '')[:200]}\n"
                f"  查询时间: {q.get('query_time')}秒, 锁时间: {q.get('lock_time')}秒, "
                f"扫描行数: {q.get('rows_examined')}"
            )

    prompt_text = "\n".join(prompt_parts)

    # 调用 LLM
    try:
        from src.analyzer.llm import LLMClient

        llm = LLMClient(config)
        llm_response = await llm.chat(
            messages=[
                {"role": "system", "content": "你是一个 MySQL 数据库性能优化专家。请根据慢查询日志数据给出具体的优化建议，包括索引优化、SQL 改写、配置调整等。"},
                {"role": "user", "content": prompt_text},
            ],
        )

        summary = llm_response if isinstance(llm_response, str) else str(llm_response)

        # 从 top_slow 中构建建议
        suggestions = []
        for item in top_slow[:5]:
            suggestions.append({
                "sql_template": item.get("sql_template", ""),
                "issue": f"累计耗时 {round(item.get('total_query_time', 0), 2)}秒，执行 {item['count']} 次",
                "suggestion": "建议检查该 SQL 的执行计划，添加合适的索引或优化查询逻辑",
                "priority": "high" if item.get("avg_query_time", 0) > 10 else "medium",
            })

        # 存储分析结果
        try:
            await db.insert_slow_query_analysis({
                "time_range_start": start_time,
                "time_range_end": end_time,
                "summary": summary,
                "suggestions": suggestions,
            })
        except Exception as e:
            logger.warning("存储慢查询分析结果失败: %s", e)

        return SlowQueryAnalyzeResponse(
            summary=summary,
            suggestions=suggestions,
        )

    except Exception as e:
        logger.error("LLM 分析慢查询失败: %s", e)
        raise HTTPException(status_code=500, detail=f"分析执行失败: {str(e)}")


@router.post("/slow-query/parse", response_model=SlowQueryParseResponse)
async def parse_slow_query_log(
    body: SlowQueryParseRequest,
    user: Optional[str] = Depends(get_current_user),
):
    """触发慢查询日志解析"""
    db = _get_db()
    config = Config()

    # 查找慢查询日志路径
    slow_query_log_path = None

    if body.instance_id:
        # 从数据库获取实例信息
        try:
            conn = await db._get_conn()
            cursor = await conn.execute(
                "SELECT id, name, log_path, host FROM instances WHERE id = ?",
                (body.instance_id,),
            )
            instance = await cursor.fetchone()
            if instance:
                # 尝试推断慢查询日志路径
                # 常见模式: /var/log/mysql/slow.log 或同目录下
                import os
                error_log_path = instance["log_path"]
                log_dir = os.path.dirname(error_log_path)
                candidates = [
                    os.path.join(log_dir, "slow.log"),
                    os.path.join(log_dir, "mysql-slow.log"),
                    os.path.join(log_dir, instance["name"] + "-slow.log"),
                ]
                for candidate in candidates:
                    if os.path.exists(candidate):
                        slow_query_log_path = candidate
                        break
        except Exception as e:
            logger.warning("查询实例信息失败: %s", e)
    else:
        # 尝试从配置获取
        instances = config.get("mysql", "instances", default=[])
        if instances:
            import os
            for inst in instances:
                log_path = inst.get("slow_query_log", "")
                if log_path and os.path.exists(log_path):
                    slow_query_log_path = log_path
                    break

                # 尝试推断
                error_log_path = inst.get("log_path", "")
                if error_log_path:
                    log_dir = os.path.dirname(error_log_path)
                    candidates = [
                        os.path.join(log_dir, "slow.log"),
                        os.path.join(log_dir, "mysql-slow.log"),
                    ]
                    for candidate in candidates:
                        if os.path.exists(candidate):
                            slow_query_log_path = candidate
                            break
                if slow_query_log_path:
                    break

    if not slow_query_log_path:
        return SlowQueryParseResponse(parsed_count=0, new_count=0)

    # 解析慢查询日志
    try:
        from src.collector.slow_query_parser import SlowQueryParser

        parser = SlowQueryParser()
        entries = parser.parse_file(slow_query_log_path)

        if not entries:
            return SlowQueryParseResponse(parsed_count=0, new_count=0)

        # 设置 instance_id
        instance_id = body.instance_id
        for entry in entries:
            if instance_id:
                entry["instance_id"] = instance_id

        # 获取已有记录数用于计算新增数
        existing_count = await db.count_slow_queries(instance_id=instance_id)

        # 批量插入
        await db.insert_slow_queries(entries)

        new_count = max(0, len(entries) - existing_count) if existing_count > 0 else len(entries)

        return SlowQueryParseResponse(
            parsed_count=len(entries),
            new_count=new_count,
        )

    except Exception as e:
        logger.error("解析慢查询日志失败: %s", e)
        raise HTTPException(status_code=500, detail=f"解析慢查询日志失败: {str(e)}")
