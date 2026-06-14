"""MySQL 连接管理器 - 用于实时状态采集"""

import logging
import asyncio
from typing import Any, Optional

from src.config import Config

logger = logging.getLogger(__name__)

# 尝试导入 pymysql
try:
    import pymysql
    _PYMYSQL_AVAILABLE = True
except ImportError:
    _PYMYSQL_AVAILABLE = False
    logger.warning("pymysql 未安装，MySQL 实时监控将不可用")


class MySQLConnector:
    """MySQL 连接器，用于执行 SHOW STATUS/PROCESSLIST/SLAVE STATUS 等命令"""

    def __init__(self, host='localhost', port=3306, user='root', password='', charset='utf8mb4'):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.charset = charset
        self._conn = None
        self._available = _PYMYSQL_AVAILABLE

    def _get_connection(self):
        """获取 pymysql 同步连接"""
        if not self._available:
            raise RuntimeError("pymysql 未安装，无法连接 MySQL")
        if self._conn is None or not self._conn.open:
            self._conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
                read_timeout=10,
            )
        return self._conn

    def _execute_query(self, sql: str, params=None) -> list[dict]:
        """同步执行查询并返回结果"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except pymysql.err.OperationalError:
            # 连接可能已断开，重试一次
            self._conn = None
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()

    def _execute_query_single(self, sql: str, params=None) -> Optional[dict]:
        """同步执行查询并返回单条结果"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()
        except pymysql.err.OperationalError:
            self._conn = None
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()

    async def get_global_status(self) -> dict:
        """执行 SHOW GLOBAL STATUS，返回关键指标"""
        if not self._available:
            return {}

        try:
            rows = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query, "SHOW GLOBAL STATUS"
            )
        except Exception as e:
            logger.warning("获取 GLOBAL STATUS 失败: %s", e)
            return {}

        status = {row['Variable_name']: row['Value'] for row in rows}

        def _int(key, default=0):
            try:
                return int(status.get(key, default))
            except (ValueError, TypeError):
                return default

        def _float(key, default=0.0):
            try:
                return float(status.get(key, default))
            except (ValueError, TypeError):
                return default

        uptime = _int('Uptime', 1)
        if uptime == 0:
            uptime = 1

        # QPS & TPS
        qps = round(_int('Queries') / uptime, 2)
        tps = round((_int('Com_commit') + _int('Com_rollback')) / uptime, 2)

        # Buffer Pool 命中率
        bp_read_requests = _int('Innodb_buffer_pool_read_requests')
        bp_reads = _int('Innodb_buffer_pool_reads')
        if bp_read_requests > 0:
            bp_hit_rate = round((bp_read_requests - bp_reads) / bp_read_requests * 100, 2)
        else:
            bp_hit_rate = 100.0

        # 流量（每秒）
        bytes_received_per_sec = round(_int('Bytes_received') / uptime, 2)
        bytes_sent_per_sec = round(_int('Bytes_sent') / uptime, 2)

        # 行锁
        row_lock_waits = _int('Innodb_row_lock_waits')
        row_lock_time_avg_ms = round(_int('Innodb_row_lock_time') / 1000, 2) if row_lock_waits > 0 else 0.0
        if row_lock_waits > 0:
            row_lock_time_avg_ms = round(_int('Innodb_row_lock_time') / row_lock_waits / 1000, 2)
        row_lock_time_total_ms = round(_int('Innodb_row_lock_time') / 1000, 2)

        return {
            'Uptime': uptime,
            'Connections': _int('Connections'),
            'Max_used_connections': _int('Max_used_connections'),
            'Threads_connected': _int('Threads_connected'),
            'Threads_running': _int('Threads_running'),
            'Threads_cached': _int('Threads_cached'),
            'QPS': qps,
            'TPS': tps,
            'Buffer_pool_hit_rate': bp_hit_rate,
            'Innodb_buffer_pool_read_requests': bp_read_requests,
            'Innodb_buffer_pool_reads': bp_reads,
            'Innodb_buffer_pool_pages_total': _int('Innodb_buffer_pool_pages_total'),
            'Innodb_buffer_pool_pages_free': _int('Innodb_buffer_pool_pages_free'),
            'Innodb_row_lock_waits': row_lock_waits,
            'Innodb_row_lock_time_avg_ms': row_lock_time_avg_ms,
            'Innodb_row_lock_time_total_ms': row_lock_time_total_ms,
            'Bytes_received_per_sec': bytes_received_per_sec,
            'Bytes_sent_per_sec': bytes_sent_per_sec,
            'Slow_queries': _int('Slow_queries'),
            'Open_tables': _int('Open_tables'),
            'Opened_tables': _int('Opened_tables'),
            'Table_open_cache': _int('Table_open_cache'),
            'Select_full_join': _int('Select_full_join'),
            'Select_scan': _int('Select_scan'),
        }

    async def get_processlist(self) -> list[dict]:
        """执行 SHOW FULL PROCESSLIST"""
        if not self._available:
            return []

        try:
            rows = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query, "SHOW FULL PROCESSLIST"
            )
        except Exception as e:
            logger.warning("获取 PROCESSLIST 失败: %s", e)
            return []

        result = []
        for row in rows:
            result.append({
                'id': row.get('Id'),
                'user': row.get('User', ''),
                'host': row.get('Host', ''),
                'db': row.get('db'),
                'command': row.get('Command', ''),
                'time': row.get('Time', 0),
                'state': row.get('State', ''),
                'info': row.get('Info', ''),
            })
        return result

    async def get_slave_status(self) -> Optional[dict]:
        """执行 SHOW SLAVE STATUS"""
        if not self._available:
            return None

        try:
            row = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query_single, "SHOW SLAVE STATUS"
            )
        except Exception as e:
            logger.warning("获取 SLAVE STATUS 失败: %s", e)
            return None

        if row is None:
            return None

        return {
            'Master_Host': row.get('Master_Host', ''),
            'Master_Port': row.get('Master_Port', 3306),
            'Master_User': row.get('Master_User', ''),
            'Slave_IO_Running': row.get('Slave_IO_Running', 'No'),
            'Slave_SQL_Running': row.get('Slave_SQL_Running', 'No'),
            'Seconds_Behind_Master': row.get('Seconds_Behind_Master'),
            'Last_IO_Error': row.get('Last_IO_Error', ''),
            'Last_SQL_Error': row.get('Last_SQL_Error', ''),
            'Exec_Master_Log_Pos': row.get('Exec_Master_Log_Pos', 0),
            'Read_Master_Log_Pos': row.get('Read_Master_Log_Pos', 0),
            'Relay_Master_Log_File': row.get('Relay_Master_Log_File', ''),
            'Exec_Relay_Log_Pos': row.get('Exec_Relay_Log_Pos', 0),
            'Auto_Position': row.get('Auto_Position', 0),
            'Replicate_Do_DB': row.get('Replicate_Do_DB', ''),
            'Replicate_Ignore_DB': row.get('Replicate_Ignore_DB', ''),
            'Slave_SQL_Running_State': row.get('Slave_SQL_Running_State', ''),
            'Master_Log_File': row.get('Master_Log_File', ''),
            'Relay_Log_File': row.get('Relay_Log_File', ''),
        }

    async def get_master_status(self) -> Optional[dict]:
        """执行 SHOW MASTER STATUS"""
        if not self._available:
            return None

        try:
            row = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query_single, "SHOW MASTER STATUS"
            )
        except Exception as e:
            logger.warning("获取 MASTER STATUS 失败: %s", e)
            return None

        if row is None:
            return None

        return {
            'File': row.get('File', ''),
            'Position': row.get('Position', 0),
            'Binlog_Do_DB': row.get('Binlog_Do_DB', ''),
            'Binlog_Ignore_DB': row.get('Binlog_Ignore_DB', ''),
        }

    async def get_innodb_status(self) -> str:
        """执行 SHOW ENGINE INNODB STATUS"""
        if not self._available:
            return ''

        try:
            rows = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query, "SHOW ENGINE INNODB STATUS"
            )
        except Exception as e:
            logger.warning("获取 INNODB STATUS 失败: %s", e)
            return ''

        if rows:
            return rows[0].get('Status', '')
        return ''

    async def get_variables(self, like_pattern=None) -> dict:
        """执行 SHOW VARIABLES"""
        if not self._available:
            return {}

        sql = "SHOW VARIABLES"
        params = None
        if like_pattern:
            sql = "SHOW VARIABLES LIKE %s"
            params = (like_pattern,)

        try:
            rows = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query, sql, params
            )
        except Exception as e:
            logger.warning("获取 VARIABLES 失败: %s", e)
            return {}

        return {row['Variable_name']: row['Value'] for row in rows}

    async def test_connection(self) -> dict:
        """测试连接"""
        if not self._available:
            return {
                'success': False,
                'message': 'pymysql 未安装，请执行 pip install pymysql',
                'version': '',
            }

        try:
            rows = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_query, "SELECT VERSION() as ver"
            )
            version = rows[0]['ver'] if rows else ''
            return {
                'success': True,
                'message': '连接成功',
                'version': version,
            }
        except Exception as e:
            error_msg = str(e)[:200]
            logger.warning("MySQL 连接测试失败: %s", error_msg)
            return {
                'success': False,
                'message': f'连接失败: {error_msg}',
                'version': '',
            }

    async def close(self):
        """关闭连接"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    @staticmethod
    def get_instance_connection(instance_id: int) -> Optional['MySQLConnector']:
        """根据 instance_id 从配置创建连接器"""
        config = Config()

        # 先从配置文件中的 mysql.instances 查找
        instances = config.get("mysql", "instances", default=[])
        for inst in instances:
            if inst.get("id") == instance_id:
                return MySQLConnector(
                    host=inst.get("host", "localhost"),
                    port=inst.get("port", 3306),
                    user=inst.get("user", "root"),
                    password=inst.get("password", ""),
                )

        # 尝试从数据库读取实例信息
        try:
            import sqlite3
            import json as _json
            db_path = config.get("storage", "db_path", default="./data/logs.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT host, port, credentials FROM instances WHERE id = ?",
                (instance_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                user = 'root'
                password = ''
                creds_raw = row['credentials']
                if creds_raw:
                    try:
                        creds = _json.loads(creds_raw)
                        user = creds.get('user', 'root')
                        password = creds.get('password', '')
                    except (_json.JSONDecodeError, TypeError):
                        pass
                return MySQLConnector(
                    host=row['host'] or 'localhost',
                    port=row['port'] or 3306,
                    user=user,
                    password=password,
                )
        except Exception as e:
            logger.warning("从数据库读取实例信息失败: %s", e)

        return None
