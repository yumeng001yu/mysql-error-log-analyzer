"""Redis 慢查询 API

端点:
- GET /api/redis/slowlog       — 慢查询列表
- GET /api/redis/slowlog/stats — 慢查询统计
- GET /api/redis/slowlog/config — 慢查询配置
"""

import logging
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Query

from src.collector.redis_connector import RedisConnector
from src.web.api.redis_monitor import _get_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis/slowlog", tags=["Redis 慢查询"])


@router.get("/")
async def get_slowlog(
    instance_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """获取慢查询列表"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        entries = await connector.get_slowlog(limit)
        total = await connector.get_slowlog_len()

        # 格式化输出
        result = []
        for entry in entries:
            result.append({
                "id": entry["id"],
                "timestamp": entry["start_time"],
                "duration_us": entry["duration_us"],
                "duration_ms": round(entry["duration_us"] / 1000, 2),
                "command": entry["command"],
                "client_ip": entry["client_ip"],
                "client_name": entry["client_name"],
            })

        return {
            "total": total,
            "items": result,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/stats")
async def get_slowlog_stats(
    instance_id: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """获取慢查询统计"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        entries = await connector.get_slowlog(limit)

        if not entries:
            return {
                "total_entries": 0,
                "command_distribution": {},
                "avg_duration_ms": 0,
                "max_duration_ms": 0,
                "top_slow": [],
            }

        # 命令分布
        command_counter = Counter()
        total_duration = 0
        max_duration = 0
        for entry in entries:
            # 提取命令类型（第一个词）
            cmd = entry["command"].split()[0] if entry["command"] else "unknown"
            command_counter[cmd] += 1
            duration_us = entry["duration_us"]
            total_duration += duration_us
            max_duration = max(max_duration, duration_us)

        # Top 慢查询
        sorted_entries = sorted(entries, key=lambda x: x["duration_us"], reverse=True)
        top_slow = []
        for entry in sorted_entries[:10]:
            top_slow.append({
                "id": entry["id"],
                "command": entry["command"][:100],
                "duration_ms": round(entry["duration_us"] / 1000, 2),
                "timestamp": entry["start_time"],
            })

        return {
            "total_entries": len(entries),
            "command_distribution": dict(command_counter.most_common(20)),
            "avg_duration_ms": round(total_duration / len(entries) / 1000, 2),
            "max_duration_ms": round(max_duration / 1000, 2),
            "top_slow": top_slow,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/config")
async def get_slowlog_config(instance_id: Optional[int] = Query(None)):
    """获取慢查询配置"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        config = await connector.get_slowlog_config()
        return config
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()
