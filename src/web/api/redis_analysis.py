"""Redis 内存分析 + Key 分析 + 持久化监控 API

端点:
- GET /api/redis/memory           — 内存详细分析
- GET /api/redis/memory/trend     — 内存使用趋势
- POST /api/redis/keys/scan       — 扫描 Key（手动触发）
- GET /api/redis/keys/top         — 大 Key 排行
- GET /api/redis/keyspace         — Key 空间分布
- GET /api/redis/key/{key}        — 单个 Key 详情
- GET /api/redis/persistence/detail — 持久化详细状态
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from src.collector.redis_connector import RedisConnector
from src.web.api.redis_monitor import _get_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis", tags=["Redis 分析"])


@router.get("/memory")
async def get_memory_analysis(instance_id: Optional[int] = Query(None)):
    """获取 Redis 内存详细分析"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        info = await connector.get_memory_info()
        stats = await connector.get_stats_info()

        used_memory = info.get('used_memory', 0)
        used_memory_peak = info.get('used_memory_peak', 0)
        maxmemory = info.get('maxmemory', 0)

        # 内存使用率
        usage_percent = None
        if maxmemory > 0:
            usage_percent = round(used_memory / maxmemory * 100, 2)

        # 碎片率分析
        frag_ratio = info.get('mem_fragmentation_ratio', 0)
        frag_status = "healthy"
        if frag_ratio > 1.5:
            frag_status = "warning"
        elif frag_ratio > 2.0:
            frag_status = "critical"
        elif frag_ratio < 1.0:
            frag_status = "low"  # 内存分配不足

        # 淘汰分析
        evicted_keys = stats.get('evicted_keys', 0)
        expired_keys = stats.get('expired_keys', 0)
        maxmemory_policy = info.get('maxmemory_policy', 'noeviction')

        return {
            "overview": {
                "used_memory": used_memory,
                "used_memory_human": info.get('used_memory_human', '0B'),
                "used_memory_peak": used_memory_peak,
                "used_memory_peak_human": info.get('used_memory_peak_human', '0B'),
                "maxmemory": maxmemory,
                "maxmemory_human": info.get('maxmemory_human', '0B'),
                "usage_percent": usage_percent,
            },
            "fragmentation": {
                "ratio": frag_ratio,
                "bytes": info.get('mem_fragmentation_bytes', 0),
                "status": frag_status,
                "recommendation": _frag_recommendation(frag_ratio),
            },
            "composition": {
                "used_memory_dataset": info.get('used_memory_dataset', 0),
                "used_memory_overhead": info.get('used_memory_overhead', 0),
                "used_memory_startup": info.get('used_memory_startup', 0),
                "dataset_percent": info.get('dataset_percent', 0),
                "objects": info.get('used_memory_objects', info.get('db0_keys', 0)),
            },
            "eviction": {
                "policy": maxmemory_policy,
                "evicted_keys": evicted_keys,
                "expired_keys": expired_keys,
                "policy_description": _policy_description(maxmemory_policy),
            },
            "lua": {
                "used_memory_lua": info.get('used_memory_lua', 0),
                "used_memory_scripts": info.get('used_memory_scripts', 0),
            },
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


def _frag_recommendation(ratio: float) -> str:
    """碎片率建议"""
    if ratio < 1.0:
        return "内存分配不足，Redis 可能使用 swap，建议增加可用内存"
    elif ratio <= 1.5:
        return "碎片率正常"
    elif ratio <= 2.0:
        return "碎片率偏高，建议关注。可考虑执行 MEMORY PURGE 或重启实例"
    else:
        return "碎片率过高！建议执行 MEMORY PURGE、开启 activedefrag 或重启实例"


def _policy_description(policy: str) -> str:
    """淘汰策略说明"""
    policies = {
        'noeviction': '不淘汰，内存满时写入操作返回错误',
        'allkeys-lru': '从所有 Key 中淘汰最近最少使用的',
        'allkeys-lfu': '从所有 Key 中淘汰最不经常使用的',
        'allkeys-random': '从所有 Key 中随机淘汰',
        'volatile-lru': '从设置了过期时间的 Key 中淘汰最近最少使用的',
        'volatile-lfu': '从设置了过期时间的 Key 中淘汰最不经常使用的',
        'volatile-random': '从设置了过期时间的 Key 中随机淘汰',
        'volatile-ttl': '从设置了过期时间的 Key 中淘汰 TTL 最短的',
    }
    return policies.get(policy, f'未知策略: {policy}')


@router.post("/keys/scan")
async def scan_keys(
    instance_id: Optional[int] = Query(None),
    pattern: str = Query("*"),
    sample_count: int = Query(100, ge=1, le=5000),
):
    """扫描 Key 并分析（手动触发，默认关闭）

    注意：大 Key 扫描在生产环境有性能风险，请谨慎使用。
    """
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        start_time = time.time()

        # 扫描 Key
        keys = await connector.scan_keys(pattern, count=sample_count)

        # 获取 Key 空间信息
        keyspace = await connector.get_keyspace_info()

        # 分析前 N 个 Key 的详情
        top_keys = []
        analyze_limit = min(len(keys), 100)
        for key in keys[:analyze_limit]:
            key_info = await connector.get_key_info(key)
            top_keys.append(key_info)

        # 按内存排序
        top_keys.sort(key=lambda x: x.get('memory_bytes', 0), reverse=True)

        elapsed = round(time.time() - start_time, 2)

        return {
            "pattern": pattern,
            "total_scanned": len(keys),
            "analyzed": analyze_limit,
            "elapsed_seconds": elapsed,
            "top_keys_by_memory": top_keys[:20],
            "keyspace": keyspace,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/keys/top")
async def get_top_keys(
    instance_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """获取大 Key 排行（基于上次扫描结果或实时轻量扫描）"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        # 获取 Key 空间
        keyspace = await connector.get_keyspace_info()
        db_size = await connector.get_dbsize()

        # 轻量扫描：只扫描少量 Key
        keys = await connector.scan_keys(count=limit)

        # 分析每个 Key
        top_keys = []
        for key in keys[:limit]:
            key_info = await connector.get_key_info(key)
            top_keys.append(key_info)

        # 按内存排序
        top_keys.sort(key=lambda x: x.get('memory_bytes', 0), reverse=True)

        return {
            "total_keys": db_size,
            "top_keys": top_keys,
            "keyspace": keyspace,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/keyspace")
async def get_keyspace(instance_id: Optional[int] = Query(None)):
    """获取 Key 空间分布"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        keyspace = await connector.get_keyspace_info()
        db_size = await connector.get_dbsize()

        # 解析 keyspace 信息
        # 格式: db0:keys=1000,expires=500,avg_ttl=3600
        databases = []
        for key, value in keyspace.items():
            if key.startswith('db'):
                db_info = {"name": key}
                if isinstance(value, str):
                    parts = value.split(',')
                    for part in parts:
                        if '=' in part:
                            k, v = part.split('=', 1)
                            try:
                                db_info[k] = int(v)
                            except ValueError:
                                db_info[k] = v
                elif isinstance(value, dict):
                    db_info.update(value)
                databases.append(db_info)

        return {
            "total_keys": db_size,
            "databases": databases,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/key/{key:path}")
async def get_key_detail(
    key: str,
    instance_id: Optional[int] = Query(None),
):
    """获取单个 Key 的详细信息"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        key_info = await connector.get_key_info(key)
        return key_info
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/persistence/detail")
async def get_persistence_detail(instance_id: Optional[int] = Query(None)):
    """获取持久化详细状态"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        info = await connector.get_persistence_info()
        server_info = await connector.get_server_info()

        # RDB 分析
        rdb_last_save = info.get('rdb_last_save_time', 0)
        rdb_changes = info.get('rdb_changes_since_last_save', 0)
        rdb_bgsave_in_progress = info.get('rdb_bgsave_in_progress', 0)
        rdb_last_bgsave_status = info.get('rdb_last_bgsave_status', 'ok')
        rdb_last_bgsave_time_sec = info.get('rdb_last_bgsave_time_sec', 0)

        # AOF 分析
        aof_enabled = info.get('aof_enabled', 0)
        aof_rewrite_in_progress = info.get('aof_rewrite_in_progress', 0)
        aof_last_write_status = info.get('aof_last_write_status', 'ok')
        aof_current_size = info.get('aof_current_size', 0)
        aof_base_size = info.get('aof_base_size', 0)

        # AOF 重写百分比
        aof_rewrite_percent = 0
        if aof_base_size > 0:
            aof_rewrite_percent = round((aof_current_size - aof_base_size) / aof_base_size * 100, 2)

        # 当前时间
        current_time = int(time.time())
        seconds_since_save = current_time - rdb_last_save if rdb_last_save > 0 else 0

        return {
            "rdb": {
                "last_save_time": rdb_last_save,
                "seconds_since_last_save": seconds_since_save,
                "changes_since_last_save": rdb_changes,
                "bgsave_in_progress": rdb_bgsave_in_progress,
                "last_bgsave_status": rdb_last_bgsave_status,
                "last_bgsave_time_sec": rdb_last_bgsave_time_sec,
                "last_cow_size": info.get('rdb_last_cow_size', 0),
                "health": "ok" if rdb_last_bgsave_status == "ok" else "error",
                "warning": _rdb_warning(seconds_since_save, rdb_changes),
            },
            "aof": {
                "enabled": bool(aof_enabled),
                "rewrite_in_progress": bool(aof_rewrite_in_progress),
                "last_write_status": aof_last_write_status,
                "current_size": aof_current_size,
                "base_size": aof_base_size,
                "rewrite_percent": aof_rewrite_percent,
                "rewrite_scheduled": bool(info.get('aof_rewrite_scheduled', 0)),
                "health": "ok" if aof_last_write_status == "ok" else "error",
                "warning": _aof_warning(aof_enabled, aof_rewrite_percent),
            },
            "loading": bool(info.get('loading', 0)),
            "recommendation": _persistence_recommendation(
                aof_enabled, seconds_since_save, rdb_changes, aof_rewrite_percent
            ),
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


def _rdb_warning(seconds_since_save: int, changes: int) -> str:
    """RDB 告警"""
    if seconds_since_save > 3600 and changes > 1000:
        return f"距上次保存已 {seconds_since_save // 60} 分钟，有 {changes} 次变更未持久化"
    if seconds_since_save > 7200:
        return f"距上次保存已超过 {seconds_since_save // 3600} 小时"
    return ""


def _aof_warning(aof_enabled: int, rewrite_percent: float) -> str:
    """AOF 告警"""
    if not aof_enabled:
        return "AOF 未启用，崩溃时可能丢失数据"
    if rewrite_percent > 200:
        return f"AOF 重写增长 {rewrite_percent}%，建议触发重写"
    return ""


def _persistence_recommendation(
    aof_enabled: int, seconds_since_save: int, changes: int, aof_rewrite_percent: float
) -> str:
    """持久化建议"""
    recommendations = []
    if not aof_enabled:
        recommendations.append("建议启用 AOF 持久化以提高数据安全性")
    if seconds_since_save > 3600 and changes > 100:
        recommendations.append("RDB 保存间隔过长，建议调整 save 配置")
    if aof_rewrite_percent > 200:
        recommendations.append("AOF 文件增长过大，建议触发 BGREWRITEAOF")
    if not recommendations:
        recommendations.append("持久化配置正常")
    return "；".join(recommendations)
