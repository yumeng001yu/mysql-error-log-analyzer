"""Redis 集群/哨兵监控 API

端点:
- GET /api/redis/cluster/info       — 集群状态概览
- GET /api/redis/cluster/nodes      — 集群节点列表
- GET /api/redis/sentinel/masters   — Sentinel 监控的主节点
- GET /api/redis/sentinel/slaves    — Sentinel 从节点列表
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from src.collector.redis_connector import RedisConnector
from src.web.api.redis_monitor import _get_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis", tags=["Redis 集群/哨兵"])


@router.get("/cluster/info")
async def get_cluster_info(instance_id: Optional[int] = Query(None)):
    """获取 Redis Cluster 状态概览"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        # 先检查是否是集群模式
        info = await connector.get_info('server')
        redis_mode = info.get('redis_mode', 'standalone')

        if redis_mode != 'cluster':
            return {
                "is_cluster": False,
                "mode": redis_mode,
                "message": f"当前实例不是集群模式（当前模式: {redis_mode}）",
            }

        # 获取集群信息
        cluster_info = await connector.get_cluster_info_detail()
        nodes = await connector.get_cluster_nodes()

        # 统计节点状态
        master_count = sum(1 for n in nodes if n.get('is_master'))
        slave_count = len(nodes) - master_count
        connected_count = sum(1 for n in nodes if n.get('is_connected'))

        return {
            "is_cluster": True,
            "mode": "cluster",
            "cluster_state": cluster_info.get('cluster_state', 'unknown'),
            "cluster_slots_ok": cluster_info.get('cluster_slots_ok', 0),
            "cluster_slots_assigned": cluster_info.get('cluster_slots_assigned', 0),
            "cluster_slots_pfail": cluster_info.get('cluster_slots_pfail', 0),
            "cluster_slots_fail": cluster_info.get('cluster_slots_fail', 0),
            "cluster_known_nodes": cluster_info.get('cluster_known_nodes', len(nodes)),
            "cluster_size": cluster_info.get('cluster_size', 0),
            "master_count": master_count,
            "slave_count": slave_count,
            "connected_count": connected_count,
            "total_count": len(nodes),
            "health": "ok" if cluster_info.get('cluster_state') == 'ok' else "error",
        }
    except Exception as e:
        return {"error": str(e)[:200], "is_cluster": False}
    finally:
        await connector.close()


@router.get("/cluster/nodes")
async def get_cluster_nodes(instance_id: Optional[int] = Query(None)):
    """获取集群节点列表"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        info = await connector.get_info('server')
        redis_mode = info.get('redis_mode', 'standalone')

        if redis_mode != 'cluster':
            return {"is_cluster": False, "nodes": [], "message": f"当前模式: {redis_mode}"}

        nodes = await connector.get_cluster_nodes()
        return {
            "is_cluster": True,
            "total": len(nodes),
            "nodes": nodes,
        }
    except Exception as e:
        return {"error": str(e)[:200], "is_cluster": False, "nodes": []}
    finally:
        await connector.close()


@router.get("/sentinel/masters")
async def get_sentinel_masters(instance_id: Optional[int] = Query(None)):
    """获取 Sentinel 监控的主节点列表"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        info = await connector.get_info('server')
        redis_mode = info.get('redis_mode', 'standalone')

        if redis_mode != 'sentinel':
            return {
                "is_sentinel": False,
                "mode": redis_mode,
                "message": f"当前实例不是 Sentinel 模式（当前模式: {redis_mode}）",
                "masters": [],
            }

        masters = await connector.get_sentinel_masters()

        # 格式化主节点信息
        result = []
        if isinstance(masters, list):
            for master in masters:
                if isinstance(master, dict):
                    result.append({
                        "name": master.get('name', ''),
                        "ip": master.get('ip', ''),
                        "port": master.get('port', 0),
                        "flags": master.get('flags', ''),
                        "num_slaves": master.get('num-slaves', master.get('num_slaves', 0)),
                        "num_other_sentinels": master.get('num-other-sentinels', master.get('num_other_sentinels', 0)),
                        "quorum": master.get('quorum', 0),
                        "ok": master.get('flags', '').find('o_down') < 0 if master.get('flags') else True,
                    })

        return {
            "is_sentinel": True,
            "mode": "sentinel",
            "total_masters": len(result),
            "masters": result,
        }
    except Exception as e:
        return {"error": str(e)[:200], "is_sentinel": False, "masters": []}
    finally:
        await connector.close()


@router.get("/sentinel/slaves")
async def get_sentinel_slaves(
    instance_id: Optional[int] = Query(None),
    master_name: str = Query("mymaster"),
):
    """获取 Sentinel 监控的从节点列表"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        slaves = await connector.get_sentinel_slaves(master_name)

        result = []
        if isinstance(slaves, list):
            for slave in slaves:
                if isinstance(slave, dict):
                    result.append({
                        "ip": slave.get('ip', ''),
                        "port": slave.get('port', 0),
                        "flags": slave.get('flags', ''),
                        "master_host": slave.get('master-host', slave.get('master_host', '')),
                        "master_port": slave.get('master-port', slave.get('master_port', 0)),
                        "ok": slave.get('flags', '').find('o_down') < 0 if slave.get('flags') else True,
                    })

        return {
            "master_name": master_name,
            "total_slaves": len(result),
            "slaves": result,
        }
    except Exception as e:
        return {"error": str(e)[:200], "slaves": []}
    finally:
        await connector.close()
