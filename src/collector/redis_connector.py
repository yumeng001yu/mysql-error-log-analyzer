"""Redis 连接管理器 - 用于实时状态采集、慢查询、Key 分析

支持:
- Standalone / Master-Slave / Sentinel / Cluster
- 密码认证 / ACL 用户名+密码 (Redis 6.0+) / TLS/SSL
- INFO / SLOWLOG / CLIENT LIST / LATENCY / MEMORY 等命令
"""

import logging
import asyncio
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis
        _REDIS_AVAILABLE = True
    except ImportError:
        _REDIS_AVAILABLE = False
        logger.warning("redis 未安装，Redis 监控将不可用。请执行 pip install redis")


class RedisConnector:
    """Redis 异步连接器

    支持所有部署模式和认证方式。
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        password: Optional[str] = None,
        username: Optional[str] = None,  # ACL 用户名 (Redis 6.0+)
        db: int = 0,
        ssl: bool = False,
        ssl_cert_reqs: Optional[str] = None,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        ssl_ca_certs: Optional[str] = None,
        # Sentinel 配置
        sentinel_hosts: Optional[list[tuple[str, int]]] = None,
        sentinel_master: Optional[str] = None,
        sentinel_password: Optional[str] = None,
        # Cluster 配置
        cluster_mode: bool = False,
        # 通用
        decode_responses: bool = True,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.username = username
        self.db = db
        self.ssl = ssl
        self.ssl_cert_reqs = ssl_cert_reqs
        self.ssl_certfile = ssl_certfile
        self.ssl_keyfile = ssl_keyfile
        self.ssl_ca_certs = ssl_ca_certs
        self.sentinel_hosts = sentinel_hosts
        self.sentinel_master = sentinel_master
        self.sentinel_password = sentinel_password
        self.cluster_mode = cluster_mode
        self.decode_responses = decode_responses
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout

        self._conn = None
        self._available = _REDIS_AVAILABLE

    def _build_connection_params(self) -> dict:
        """构建连接参数"""
        params = {
            'decode_responses': self.decode_responses,
            'socket_timeout': self.socket_timeout,
            'socket_connect_timeout': self.socket_connect_timeout,
        }

        if self.password:
            params['password'] = self.password
        if self.username:
            params['username'] = self.username
        if self.db:
            params['db'] = self.db

        # SSL/TLS
        if self.ssl:
            params['ssl'] = True
            if self.ssl_cert_reqs:
                params['ssl_cert_reqs'] = self.ssl_cert_reqs
            if self.ssl_certfile:
                params['ssl_certfile'] = self.ssl_certfile
            if self.ssl_keyfile:
                params['ssl_keyfile'] = self.ssl_keyfile
            if self.ssl_ca_certs:
                params['ssl_ca_certs'] = self.ssl_ca_certs

        return params

    async def _get_connection(self):
        """获取异步 Redis 连接"""
        if not self._available:
            raise RuntimeError("redis 未安装，无法连接 Redis")

        if self._conn is not None:
            try:
                # 测试连接是否存活
                await self._conn.ping()
                return self._conn
            except Exception:
                self._conn = None

        params = self._build_connection_params()

        # Sentinel 模式
        if self.sentinel_hosts and self.sentinel_master:
            from redis.asyncio.sentinel import Sentinel
            sentinel = Sentinel(
                self.sentinel_hosts,
                sentinel_kwargs={
                    'password': self.sentinel_password,
                    'decode_responses': self.decode_responses,
                    'socket_timeout': self.socket_timeout,
                },
            )
            self._conn = sentinel.master_for(self.sentinel_master, **params)
            return self._conn

        # Cluster 模式
        if self.cluster_mode:
            from redis.asyncio.cluster import RedisCluster
            params.pop('db', None)  # Cluster 不支持 db 参数
            self._conn = RedisCluster(
                host=self.host,
                port=self.port,
                **params,
            )
            return self._conn

        # Standalone / Master-Slave
        self._conn = aioredis.Redis(
            host=self.host,
            port=self.port,
            **params,
        )
        return self._conn

    async def close(self):
        """关闭连接"""
        if self._conn is not None:
            try:
                await self._conn.aclose()
            except Exception:
                pass
            self._conn = None

    # ── 基础操作 ──────────────────────────────────────────

    async def test_connection(self) -> dict:
        """测试连接"""
        if not self._available:
            return {
                'success': False,
                'message': 'redis 未安装，请执行 pip install redis',
                'version': '',
            }
        try:
            conn = await self._get_connection()
            info = await conn.info('server')
            version = info.get('redis_version', '')
            return {
                'success': True,
                'message': '连接成功',
                'version': version,
                'mode': info.get('redis_mode', 'standalone'),
                'os': info.get('os', ''),
                'process_id': info.get('process_id', ''),
                'uptime_in_seconds': info.get('uptime_in_seconds', 0),
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'连接失败: {str(e)[:200]}',
                'version': '',
            }

    # ── INFO 命令 ─────────────────────────────────────────

    async def get_info(self, section: Optional[str] = None) -> dict:
        """执行 INFO 命令

        Args:
            section: server/clients/memory/persistence/stats/replication/cpu/keyspace/cmdstats/cluster/all
        """
        conn = await self._get_connection()
        if section:
            return await conn.info(section)
        return await conn.info()

    async def get_server_info(self) -> dict:
        """获取 Server 信息"""
        return await self.get_info('server')

    async def get_clients_info(self) -> dict:
        """获取客户端连接信息"""
        return await self.get_info('clients')

    async def get_memory_info(self) -> dict:
        """获取内存信息"""
        return await self.get_info('memory')

    async def get_stats_info(self) -> dict:
        """获取统计信息"""
        return await self.get_info('stats')

    async def get_replication_info(self) -> dict:
        """获取复制信息"""
        return await self.get_info('replication')

    async def get_persistence_info(self) -> dict:
        """获取持久化信息"""
        return await self.get_info('persistence')

    async def get_keyspace_info(self) -> dict:
        """获取键空间信息"""
        return await self.get_info('keyspace')

    async def get_cluster_info(self) -> dict:
        """获取集群信息"""
        try:
            conn = await self._get_connection()
            return await conn.info('cluster')
        except Exception:
            return {}

    # ── 实时指标 ──────────────────────────────────────────

    async def get_metrics(self) -> dict:
        """获取所有关键实时指标，结构化返回"""
        try:
            info_all = await self.get_info('all')
        except Exception:
            try:
                info_all = await self.get_info()
            except Exception as e:
                logger.warning("获取 Redis INFO 失败: %s", e)
                return {}

        # 解析 key 指标
        def _int(key, default=0):
            try:
                return int(info_all.get(key, default))
            except (ValueError, TypeError):
                return default

        def _float(key, default=0.0):
            try:
                return float(info_all.get(key, default))
            except (ValueError, TypeError):
                return default

        uptime = _int('uptime_in_seconds', 1)
        if uptime == 0:
            uptime = 1

        # QPS: instantaneous_ops_per_sec
        qps = _int('instantaneous_ops_per_sec')

        # 连接数
        connected_clients = _int('connected_clients')
        maxclients = _int('maxclients')

        # 内存
        used_memory = _int('used_memory')
        used_memory_human = info_all.get('used_memory_human', '0B')
        used_memory_peak = _int('used_memory_peak')
        used_memory_peak_human = info_all.get('used_memory_peak_human', '0B')
        maxmemory = _int('maxmemory')
        maxmemory_human = info_all.get('maxmemory_human', '0B')
        mem_fragmentation_ratio = _float('mem_fragmentation_ratio')
        mem_fragmentation_bytes = _int('mem_fragmentation_bytes')

        # 键命中率
        keyspace_hits = _int('keyspace_hits')
        keyspace_misses = _int('keyspace_misses')
        total_accesses = keyspace_hits + keyspace_misses
        hit_rate = round(keyspace_hits / total_accesses * 100, 2) if total_accesses > 0 else 100.0

        # 网络
        total_net_input_bytes = _int('total_net_input_bytes')
        total_net_output_bytes = _int('total_net_output_bytes')
        net_input_per_sec = round(total_net_input_bytes / uptime, 2)
        net_output_per_sec = round(total_net_output_bytes / uptime, 2)

        # 淘汰/过期
        evicted_keys = _int('evicted_keys')
        expired_keys = _int('expired_keys')

        # 持久化
        rdb_last_save_time = _int('rdb_last_save_time')
        rdb_changes_since_last_save = _int('rdb_changes_since_last_save')
        aof_enabled = _int('aof_enabled')
        aof_rewrite_in_progress = _int('aof_rewrite_in_progress')
        rdb_bgsave_in_progress = _int('rdb_bgsave_in_progress')

        # 复制
        role = info_all.get('role', 'master')
        connected_slaves = _int('connected_slaves')

        # 慢查询
        slowlog_count = _int('slowlog_count') if 'slowlog_count' in info_all else 0

        return {
            'server': {
                'version': info_all.get('redis_version', ''),
                'mode': info_all.get('redis_mode', 'standalone'),
                'os': info_all.get('os', ''),
                'uptime': uptime,
                'process_id': _int('process_id'),
            },
            'clients': {
                'connected': connected_clients,
                'maxclients': maxclients,
                'blocked': _int('blocked_clients'),
                'tracking_clients': _int('tracking_clients', 0),
            },
            'memory': {
                'used_memory': used_memory,
                'used_memory_human': used_memory_human,
                'used_memory_peak': used_memory_peak,
                'used_memory_peak_human': used_memory_peak_human,
                'maxmemory': maxmemory,
                'maxmemory_human': maxmemory_human,
                'fragmentation_ratio': mem_fragmentation_ratio,
                'fragmentation_bytes': mem_fragmentation_bytes,
                'used_memory_lua': _int('used_memory_lua'),
                'used_memory_scripts': _int('used_memory_scripts', 0),
                'maxmemory_policy': info_all.get('maxmemory_policy', 'noeviction'),
            },
            'stats': {
                'qps': qps,
                'total_commands_processed': _int('total_commands_processed'),
                'keyspace_hits': keyspace_hits,
                'keyspace_misses': keyspace_misses,
                'hit_rate': hit_rate,
                'evicted_keys': evicted_keys,
                'expired_keys': expired_keys,
                'rejected_connections': _int('rejected_connections'),
                'sync_full': _int('sync_full'),
                'sync_partial_ok': _int('sync_partial_ok'),
                'sync_partial_err': _int('sync_partial_err'),
            },
            'network': {
                'total_input_bytes': total_net_input_bytes,
                'total_output_bytes': total_net_output_bytes,
                'input_per_sec': net_input_per_sec,
                'output_per_sec': net_output_per_sec,
                'instantaneous_input': _int('instantaneous_input_kbps') * 1024,
                'instantaneous_output': _int('instantaneous_output_kbps') * 1024,
            },
            'persistence': {
                'rdb_last_save_time': rdb_last_save_time,
                'rdb_changes_since_last_save': rdb_changes_since_last_save,
                'rdb_bgsave_in_progress': rdb_bgsave_in_progress,
                'aof_enabled': aof_enabled,
                'aof_rewrite_in_progress': aof_rewrite_in_progress,
                'aof_current_size': _int('aof_current_size', 0),
                'aof_base_size': _int('aof_base_size', 0),
            },
            'replication': {
                'role': role,
                'connected_slaves': connected_slaves,
            },
        }

    # ── SLOWLOG ──────────────────────────────────────────

    async def get_slowlog(self, count: int = 100) -> list[dict]:
        """获取慢查询日志

        Args:
            count: 获取条数

        Returns:
            慢查询列表
        """
        conn = await self._get_connection()
        entries = await conn.slowlog_get(count)

        result = []
        for entry in entries:
            # 处理 bytes 类型的字段
            def _decode(val):
                if isinstance(val, bytes):
                    return val.decode('utf-8', errors='replace')
                return val

            item = {
                'id': entry.get('id', 0),
                'start_time': entry.get('start_time', 0),
                'duration_us': entry.get('duration', 0),
                'command': '',
                'client_ip': '',
                'client_name': '',
            }

            # 解析命令
            command = entry.get('command', [])
            if isinstance(command, (list, tuple)):
                item['command'] = ' '.join(str(_decode(c)) for c in command)[:500]
            elif isinstance(command, bytes):
                item['command'] = command.decode('utf-8', errors='replace')[:500]
            elif isinstance(command, str):
                item['command'] = command[:500]

            # 客户端信息
            client = entry.get('client_address', '') or entry.get('client_ip', '')
            item['client_ip'] = str(_decode(client))
            item['client_name'] = str(_decode(entry.get('client_name', '')))

            result.append(item)

        return result

    async def get_slowlog_len(self) -> int:
        """获取慢查询日志长度"""
        conn = await self._get_connection()
        return await conn.slowlog_len()

    async def get_slowlog_config(self) -> dict:
        """获取慢查询配置"""
        conn = await self._get_connection()
        slowlog_log_slower_than = await conn.config_get('slowlog-log-slower-than')
        slowlog_max_len = await conn.config_get('slowlog-max-len')
        return {
            'slowlog_log_slower_than': int(slowlog_log_slower_than.get('slowlog-log-slower-than', -1)),
            'slowlog_max_len': int(slowlog_max_len.get('slowlog-max-len', 128)),
        }

    # ── CLIENT LIST ──────────────────────────────────────

    async def get_client_list(self) -> list[dict]:
        """获取客户端列表"""
        conn = await self._get_connection()
        clients = await conn.client_list()

        result = []
        if isinstance(clients, list):
            for client in clients:
                if isinstance(client, dict):
                    result.append(client)
                elif isinstance(client, str):
                    # 旧版 redis-py 返回字符串格式
                    parts = client.split()
                    client_dict = {}
                    for part in parts:
                        if '=' in part:
                            k, v = part.split('=', 1)
                            client_dict[k] = v
                    result.append(client_dict)
        return result

    # ── LATENCY ──────────────────────────────────────────

    async def get_latency_latest(self) -> list[dict]:
        """获取最近延迟事件"""
        conn = await self._get_connection()
        try:
            events = await conn.execute_command('LATENCY LATEST')
            result = []
            for event in events:
                if isinstance(event, (list, tuple)) and len(event) >= 4:
                    result.append({
                        'event_name': event[0],
                        'timestamp': event[1],
                        'latest_latency_ms': event[2] / 1000 if event[2] > 1000 else event[2],
                        'max_latency_ms': event[3] / 1000 if event[3] > 1000 else event[3],
                    })
            return result
        except Exception as e:
            logger.warning("LATENCY LATEST 失败: %s", e)
            return []

    async def get_latency_history(self, event_name: str) -> list[dict]:
        """获取指定事件的延迟历史"""
        conn = await self._get_connection()
        try:
            history = await conn.execute_command('LATENCY HISTORY', event_name)
            result = []
            for entry in history:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    result.append({
                        'timestamp': entry[0],
                        'latency_ms': entry[1] / 1000 if entry[1] > 1000 else entry[1],
                    })
            return result
        except Exception as e:
            logger.warning("LATENCY HISTORY %s 失败: %s", event_name, e)
            return []

    async def get_latency_events(self) -> list[str]:
        """获取所有延迟事件名称"""
        conn = await self._get_connection()
        try:
            events = await conn.execute_command('LATENCY EVENTS')
            return list(events) if events else []
        except Exception:
            return []

    # ── MEMORY 分析 ──────────────────────────────────────

    async def get_memory_stats(self) -> dict:
        """获取详细内存统计"""
        conn = await self._get_connection()
        try:
            return await conn.memory_stats()
        except Exception as e:
            logger.warning("MEMORY STATS 失败: %s", e)
            return {}

    async def get_memory_usage(self, key: str) -> int:
        """获取指定 Key 的内存使用量（字节）"""
        conn = await self._get_connection()
        try:
            return await conn.memory_usage(key) or 0
        except Exception:
            return 0

    # ── KEY 分析 ──────────────────────────────────────────

    async def get_dbsize(self) -> int:
        """获取 Key 总数"""
        conn = await self._get_connection()
        return await conn.dbsize()

    async def scan_keys(self, pattern: str = '*', count: int = 1000) -> list[str]:
        """扫描匹配的 Key（轻量级，使用 SCAN）

        Args:
            pattern: Key 匹配模式
            count: 每次 SCAN 建议数量

        Returns:
            Key 列表
        """
        conn = await self._get_connection()
        keys = []
        cursor = 0
        while True:
            cursor, batch = await conn.scan(cursor=cursor, match=pattern, count=count)
            keys.extend(batch)
            if cursor == 0:
                break
            # 安全限制
            if len(keys) >= 10000:
                break
        return keys

    async def get_key_info(self, key: str) -> dict:
        """获取单个 Key 的详细信息"""
        conn = await self._get_connection()
        try:
            key_type = await conn.type(key)
            ttl = await conn.ttl(key)
            memory = await conn.memory_usage(key) or 0

            result = {
                'key': key,
                'type': key_type,
                'ttl': ttl,
                'memory_bytes': memory,
            }

            # 根据类型获取额外信息
            if key_type == 'string':
                str_len = await conn.strlen(key)
                result['length'] = str_len
            elif key_type == 'list':
                result['length'] = await conn.llen(key)
            elif key_type == 'set':
                result['length'] = await conn.scard(key)
            elif key_type == 'zset':
                result['length'] = await conn.zcard(key)
            elif key_type == 'hash':
                result['length'] = await conn.hlen(key)
            elif key_type == 'stream':
                result['length'] = await conn.xlen(key)

            return result
        except Exception as e:
            return {'key': key, 'type': 'unknown', 'ttl': -1, 'memory_bytes': 0, 'error': str(e)}

    # ── 复制/集群 ─────────────────────────────────────────

    async def get_replication_detail(self) -> dict:
        """获取复制详细信息"""
        info = await self.get_replication_info()
        return info

    async def get_cluster_nodes(self) -> list[dict]:
        """获取集群节点信息"""
        conn = await self._get_connection()
        try:
            nodes_raw = await conn.execute_command('CLUSTER NODES')
            nodes = []
            for line in nodes_raw.strip().split('\n'):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 8:
                    node = {
                        'id': parts[0],
                        'address': parts[1],
                        'flags': parts[2],
                        'master_id': parts[3] if parts[3] != '-' else None,
                        'ping_sent': parts[4],
                        'pong_recv': parts[5],
                        'config_epoch': parts[6],
                        'link_state': parts[7],
                        'slots': ' '.join(parts[8:]) if len(parts) > 8 else '',
                    }
                    node['is_master'] = 'master' in parts[2]
                    node['is_connected'] = 'connected' in parts[7]
                    nodes.append(node)
            return nodes
        except Exception as e:
            logger.warning("CLUSTER NODES 失败: %s", e)
            return []

    async def get_cluster_info_detail(self) -> dict:
        """获取集群状态"""
        conn = await self._get_connection()
        try:
            return await conn.cluster_info()
        except Exception as e:
            logger.warning("CLUSTER INFO 失败: %s", e)
            return {}

    # ── Sentinel ─────────────────────────────────────────

    async def get_sentinel_masters(self) -> list[dict]:
        """获取 Sentinel 监控的主节点列表"""
        conn = await self._get_connection()
        try:
            return await conn.execute_command('SENTINEL MASTERS')
        except Exception as e:
            logger.warning("SENTINEL MASTERS 失败: %s", e)
            return []

    async def get_sentinel_slaves(self, master_name: str) -> list[dict]:
        """获取指定主节点的从节点列表"""
        conn = await self._get_connection()
        try:
            return await conn.execute_command('SENTINEL SLAVES', master_name)
        except Exception as e:
            logger.warning("SENTINEL SLAVES 失败: %s", e)
            return []

    # ── CONFIG ────────────────────────────────────────────

    async def get_config(self, pattern: str = '*') -> dict:
        """获取配置"""
        conn = await self._get_connection()
        try:
            config_list = await conn.config_get(pattern)
            if isinstance(config_list, dict):
                return config_list
            # 旧版可能返回 list
            if isinstance(config_list, list):
                result = {}
                for i in range(0, len(config_list) - 1, 2):
                    result[config_list[i]] = config_list[i + 1]
                return result
            return {}
        except Exception as e:
            logger.warning("CONFIG GET 失败: %s", e)
            return {}

    # ── 静态方法 ──────────────────────────────────────────

    @staticmethod
    def get_instance_connection(instance_id: int) -> Optional['RedisConnector']:
        """根据 instance_id 从数据库创建连接器"""
        try:
            import sqlite3
            import json as _json
            from src.config import Config
            config = Config()
            db_path = config.get("storage", "db_path", default="./data/logs.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT host, port, credentials, db_type FROM instances WHERE id = ?",
                (instance_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            # 只处理 Redis 类型
            db_type = row['db_type'] or 'mysql'
            if db_type != 'redis':
                return None

            host = row['host'] or 'localhost'
            port = row['port'] or 6379
            password = None
            username = None
            ssl = False

            creds_raw = row['credentials']
            if creds_raw:
                try:
                    creds = _json.loads(creds_raw)
                    password = creds.get('password')
                    username = creds.get('username')
                    ssl = creds.get('ssl', False)
                except (_json.JSONDecodeError, TypeError):
                    pass

            return RedisConnector(
                host=host,
                port=port,
                password=password,
                username=username,
                ssl=ssl,
            )
        except Exception as e:
            logger.warning("从数据库读取 Redis 实例信息失败: %s", e)
            return None
