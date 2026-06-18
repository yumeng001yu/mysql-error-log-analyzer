"""Redis 运维对话 API

端点:
- POST /api/redis/chat — Redis 运维对话
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.collector.redis_connector import RedisConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/redis", tags=["Redis 对话"])


# ── Pydantic 模型 ───────────────────────────────────────────

class RedisChatRequest(BaseModel):
    message: str
    context: Optional[dict] = None
    history: Optional[list[dict]] = None


class RedisChatResponse(BaseModel):
    response: str


# ── Redis 上下文构建 ────────────────────────────────────────

async def _build_redis_context() -> str:
    """尝试从 Redis 实例获取实时数据构建上下文"""
    connector = None
    parts = []

    try:
        # 尝试获取默认 Redis 连接器
        try:
            import sqlite3
            import json as _json
            from src.config import Config
            config = Config()
            db_path = config.get("storage", "db_path", default="./data/logs.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, host, port, credentials FROM instances WHERE db_type = 'redis' ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                password, username, ssl = None, None, False
                try:
                    creds = _json.loads(row['credentials'])
                    password = creds.get('password')
                    username = creds.get('username')
                    ssl = creds.get('ssl', False)
                except (_json.JSONDecodeError, TypeError):
                    pass

                connector = RedisConnector(
                    host=row['host'] or 'localhost',
                    port=row['port'] or 6379,
                    password=password,
                    username=username,
                    ssl=ssl,
                )
        except Exception as e:
            logger.warning("获取 Redis 实例信息失败: %s", e)
            return ""

        if not connector:
            return ""

        # 获取服务器信息
        try:
            info = await connector.get_info()
            if info:
                server_section = (
                    f"Redis 版本: {info.get('redis_version', 'unknown')}\n"
                    f"运行模式: {info.get('redis_mode', 'unknown')}\n"
                    f"运行时间(秒): {info.get('uptime_in_seconds', 0)}\n"
                    f"连接客户端数: {info.get('connected_clients', 0)}\n"
                    f"已用内存: {info.get('used_memory_human', 'unknown')}\n"
                    f"内存峰值: {info.get('used_memory_peak_human', 'unknown')}\n"
                    f"最大内存限制: {info.get('maxmemory_human', '0B')}\n"
                    f"内存碎片率: {info.get('mem_fragmentation_ratio', 0)}\n"
                    f"淘汰策略: {info.get('maxmemory_policy', 'noeviction')}\n"
                    f"每秒操作数: {info.get('instantaneous_ops_per_sec', 0)}\n"
                    f"Key 命中率: {info.get('keyspace_hits', 0)}/{info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0)}\n"
                    f"角色: {info.get('role', 'master')}\n"
                    f"从节点数: {info.get('connected_slaves', 0)}\n"
                )
                parts.append(f"## 服务器信息\n{server_section}")
        except Exception as e:
            logger.warning("获取 Redis INFO 失败: %s", e)

        # 获取内存统计
        try:
            memory_stats = await connector.get_memory_stats()
            if memory_stats:
                memory_section = f"内存统计: {memory_stats}"
                parts.append(f"## 内存统计\n{memory_section}")
        except Exception as e:
            logger.warning("获取 Redis MEMORY STATS 失败: %s", e)

        # 获取慢查询
        try:
            slowlog = await connector.get_slowlog(count=10)
            if slowlog:
                slowlog_lines = []
                for entry in slowlog:
                    slowlog_lines.append(
                        f"- ID: {entry.get('id')}, 命令: {entry.get('command', '')}, "
                        f"耗时: {entry.get('duration_us', 0)}μs, "
                        f"客户端: {entry.get('client_ip', '')}"
                    )
                parts.append(f"## 最近慢查询\n" + "\n".join(slowlog_lines))
        except Exception as e:
            logger.warning("获取 Redis SLOWLOG 失败: %s", e)

    except Exception as e:
        logger.warning("构建 Redis 上下文失败: %s", e)
    finally:
        if connector:
            try:
                await connector.close()
            except Exception:
                pass

    return "\n\n".join(parts)


# ── 规则引擎回答 ────────────────────────────────────────────

def _rule_based_answer(message: str) -> str:
    """基于规则的回答（当 LLM 不可用时使用）"""
    msg_lower = message.lower()

    if "碎片" in message or "fragmentation" in msg_lower:
        return (
            "## Redis 内存碎片率优化建议\n\n"
            "1. **理解碎片率**：`mem_fragmentation_ratio` = `used_memory_rss` / `used_memory`\n"
            "   - **< 1.0**：Redis 使用了 swap，需要立即处理\n"
            "   - **1.0 ~ 1.5**：正常范围\n"
            "   - **> 1.5**：碎片率较高，需要优化\n"
            "2. **开启自动碎片整理**：`CONFIG SET activedefrag yes`\n"
            "3. **调整碎片整理参数**：\n"
            "   - `active-defrag-threshold-lower 10`：碎片率超过 10% 开始整理\n"
            "   - `active-defrag-threshold-upper 100`：碎片率超过 100% 积极整理\n"
            "4. **重启 Redis**：如果碎片率极高且自动整理无效，可在低峰期重启释放内存\n"
            "5. **避免频繁删除和创建**：大量 Key 的创建和删除会导致内存碎片\n"
            "6. **使用合适的数据结构**：Hash 编码优化（`hash-max-ziplist-entries`、`hash-max-ziplist-value`）"
        )

    if "内存" in message or "memory" in msg_lower:
        return (
            "## Redis 内存使用建议\n\n"
            "1. **监控内存使用**：使用 `INFO memory` 查看内存使用情况，关注 `used_memory` 和 `used_memory_peak`\n"
            "2. **设置 maxmemory**：建议设置最大内存限制，防止 Redis 占用过多系统内存导致 OOM\n"
            "3. **选择合适的淘汰策略**：\n"
            "   - `allkeys-lru`：适合缓存场景\n"
            "   - `volatile-lru`：只淘汰设置了 TTL 的 key\n"
            "   - `noeviction`：适合数据不能丢失的场景\n"
            "4. **避免大 Key**：单个 Key 的 Value 不宜过大（建议 < 10KB），大 Key 会导致内存分配和释放效率低下\n"
            "5. **使用 Hash 优化**：将多个小字段存储为 Hash，比多个独立 String Key 更节省内存\n"
            "6. **定期清理过期 Key**：确保设置了合理的 TTL，避免无用数据长期占用内存\n"
            "7. **开启 lazyfree**：`lazyfree-lazy-eviction yes` 避免删除大 Key 时阻塞主线程"
        )

    if "慢查询" in message or "slowlog" in msg_lower:
        return (
            "## Redis 慢查询优化建议\n\n"
            "1. **设置合理的慢查询阈值**：`CONFIG SET slowlog-log-slower-than 10000`（单位：微秒）\n"
            "2. **避免大 Key 操作**：大 Key 的读写会阻塞 Redis，使用 `redis-cli --bigkeys` 扫描\n"
            "3. **使用 SCAN 代替 KEYS**：`KEYS *` 会阻塞 Redis，应使用 `SCAN` 命令渐进式遍历\n"
            "4. **批量操作使用 Pipeline**：减少网络往返，提升吞吐量\n"
            "5. **避免复杂度高的命令**：如 `SORT`、`SINTER`、`LRANGE 0 -1` 等在大集合上执行会很慢\n"
            "6. **定期查看慢查询**：`SLOWLOG GET 10` 查看最近的慢查询，分析并优化\n"
            "7. **设置慢查询日志长度**：`CONFIG SET slowlog-max-len 128` 保留足够的历史记录"
        )

    if "持久化" in message or "persistence" in msg_lower:
        return (
            "## Redis 持久化配置建议\n\n"
            "1. **RDB 快照**：\n"
            "   - 优点：文件紧凑、恢复速度快\n"
            "   - 缺点：可能丢失最近的数据\n"
            "   - 配置示例：`save 900 1` `save 300 10` `save 60 10000`\n"
            "2. **AOF 追加日志**：\n"
            "   - 优点：数据安全性高，最多丢失 1 秒数据\n"
            "   - 缺点：文件较大、恢复速度较慢\n"
            "   - 建议使用 `appendonly yes` + `appendfsync everysec`\n"
            "3. **RDB + AOF 混合持久化**（Redis 4.0+）：\n"
            "   - `aof-use-rdb-preamble yes`：AOF 重写时先写 RDB 格式，再写 AOF 增量\n"
            "   - 兼顾恢复速度和数据安全\n"
            "4. **AOF 重写优化**：\n"
            "   - `auto-aof-rewrite-percentage 100`\n"
            "   - `auto-aof-rewrite-min-size 64mb`\n"
            "5. **避免 RDB 和 AOF 同时重写**：`no-appendfsync-on-rewrite no`（数据安全优先）\n"
            "6. **监控持久化状态**：`INFO persistence` 查看 `rdb_last_save_time`、`aof_current_size` 等"
        )

    if "性能" in message or "优化" in message:
        return (
            "## Redis 性能优化建议\n\n"
            "1. **网络优化**：\n"
            "   - 启用 Pipeline 减少网络往返\n"
            "   - 考虑使用 Unix Socket（本地连接）\n"
            "2. **内存优化**：\n"
            "   - 使用合适的数据结构和编码\n"
            "   - 开启 `activedefrag` 自动碎片整理\n"
            "   - 设置合理的 `maxmemory` 和淘汰策略\n"
            "3. **命令优化**：\n"
            "   - 避免使用 `KEYS *`，改用 `SCAN`\n"
            "   - 避免大 Key 操作\n"
            "   - 使用 `MULTI/EXEC` 或 Lua 脚本保证原子性\n"
            "4. **持久化优化**：\n"
            "   - 纯缓存场景可关闭持久化\n"
            "   - 使用 `everysec` 策略平衡性能和数据安全\n"
            "5. **连接管理**：\n"
            "   - 设置合理的 `timeout` 释放空闲连接\n"
            "   - 监控 `rejected_connections` 调整 `maxclients`\n"
            "6. **监控与告警**：\n"
            "   - 持续监控内存使用、QPS、延迟\n"
            "   - 设置慢查询告警\n"
            "   - 关注 `evicted_keys` 和 `expired_keys` 变化"
        )

    return (
        "## Redis 运维通用建议\n\n"
        "1. **监控关键指标**：内存使用、QPS、连接数、慢查询、Key 命中率\n"
        "2. **设置合理的内存限制和淘汰策略**：避免 OOM 和性能下降\n"
        "3. **定期检查慢查询**：使用 `SLOWLOG GET` 分析并优化\n"
        "4. **关注内存碎片率**：碎片率 > 1.5 时需要优化\n"
        "5. **配置持久化**：根据业务需求选择 RDB/AOF/混合模式\n"
        "6. **避免大 Key**：使用 `redis-cli --bigkeys` 扫描\n"
        "7. **使用 Pipeline**：减少网络往返，提升吞吐量\n"
        "8. **定期备份**：确保数据安全\n\n"
        "您可以进一步询问内存、慢查询、碎片率、持久化、性能优化等具体问题。"
    )


# ── API 端点 ────────────────────────────────────────────────

@router.post("/chat", response_model=RedisChatResponse)
async def redis_chat(body: RedisChatRequest):
    """Redis 运维对话接口"""
    # 先尝试使用 LLM
    try:
        from src.analyzer.graph import AnalysisGraph
        from src.analyzer.llm import LLMManager
        from src.config import Config

        config = Config()
        llm_manager = LLMManager(config)

        # 检查 LLM 是否真正可用（需要有效的 API key 或 Ollama 地址）
        import os
        api_key = (
            os.environ.get("MYSQL_ANALYZER_LLM_API_KEY")
            or config.get("llm", "api_key")
            or ""
        )
        provider = (
            os.environ.get("MYSQL_ANALYZER_LLM_PROVIDER")
            or config.get("llm", "provider")
            or "openai"
        )
        if provider == "openai" and not api_key:
            raise RuntimeError("LLM API key 未配置")

        analysis_graph = AnalysisGraph(config)

        # 构建 Redis 实时上下文
        redis_context = await _build_redis_context()

        # 构建消息列表
        system_prompt = (
            "你是一个 Redis 数据库运维专家。请根据提供的 Redis 运维数据，"
            "回答用户关于 Redis 运维的问题。回答应该专业、准确、有针对性。"
        )

        messages = [{"role": "system", "content": system_prompt}]

        # 添加 Redis 上下文
        if redis_context:
            messages.append({"role": "system", "content": f"当前 Redis 运维数据：\n\n{redis_context}"})

        # 添加历史消息
        if body.history:
            messages.extend(body.history)

        # 添加当前消息
        messages.append({"role": "user", "content": body.message})

        response_text = await analysis_graph.run_chat(
            messages=messages,
            context=body.context,
        )

        # 检查 LLM 返回是否包含错误信息
        if "错误" in response_text and ("Connection" in response_text or "连接" in response_text):
            raise RuntimeError(f"LLM 连接失败: {response_text}")

        return RedisChatResponse(response=response_text)

    except Exception as e:
        logger.warning("LLM 不可用，使用规则引擎回答: %s", e)

        # LLM 不可用时使用规则引擎
        try:
            # 构建包含实时数据的规则引擎回答
            redis_context = ""
            try:
                redis_context = await _build_redis_context()
            except Exception:
                pass

            response_text = _rule_based_answer(body.message)

            # 如果有实时数据，附加到回答中
            if redis_context:
                response_text += f"\n\n---\n\n**当前 Redis 实时数据：**\n\n{redis_context}"

            return RedisChatResponse(response=response_text)
        except Exception as rule_err:
            logger.error("规则引擎回答也失败: %s", rule_err)
            raise HTTPException(status_code=500, detail=f"对话执行失败: {str(rule_err)}")
