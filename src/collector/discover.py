"""MySQL 日志自动发现模块"""

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from src.config import Config

logger = logging.getLogger(__name__)

# 常见 MySQL 配置文件路径
_CNF_PATHS = [
    "/etc/my.cnf",
    "/etc/mysql/my.cnf",
    "/etc/mysql/mysql.conf.d/mysqld.cnf",
    "/etc/mysql/conf.d/mysql.cnf",
    os.path.expanduser("~/.my.cnf"),
]

# 常见默认日志路径
_DEFAULT_LOG_PATHS = [
    "/var/log/mysql/error.log",
    "/var/log/mysqld.log",
    "/var/lib/mysql/error.log",
]

# MySQL 数据目录下常见错误日志模式
_MYSQL_DATA_DIRS = [
    "/var/lib/mysql",
    "/var/lib/mysql-data",
]


class MySQLLogDiscover:
    """自动发现本机 MySQL 实例及其错误日志路径"""

    def __init__(self):
        self._config = Config()

    async def discover(self) -> list[dict]:
        """自动发现本机 MySQL 实例及其错误日志路径

        Returns:
            实例列表，每项包含 name, log_path, host, port
        """
        discovered: list[dict] = []
        seen_paths: set[str] = set()

        # 方法1：从配置文件中发现
        cnf_instances = await self._discover_from_cnf()
        for inst in cnf_instances:
            if inst["log_path"] not in seen_paths:
                seen_paths.add(inst["log_path"])
                discovered.append(inst)

        # 方法2：通过 mysqladmin 命令获取
        admin_instances = await self._discover_from_mysqladmin()
        for inst in admin_instances:
            if inst["log_path"] not in seen_paths:
                seen_paths.add(inst["log_path"])
                discovered.append(inst)

        # 方法3：检查常见默认路径
        default_instances = await self._discover_from_defaults()
        for inst in default_instances:
            if inst["log_path"] not in seen_paths:
                seen_paths.add(inst["log_path"])
                discovered.append(inst)

        # 合并手动配置的实例
        manual_instances = self._get_manual_instances()
        for inst in manual_instances:
            if inst["log_path"] not in seen_paths:
                seen_paths.add(inst["log_path"])
                discovered.append(inst)

        if not discovered:
            logger.warning("未发现任何 MySQL 实例或错误日志，请检查 MySQL 是否运行或手动配置实例")

        return discovered

    async def _discover_from_cnf(self) -> list[dict]:
        """从 MySQL 配置文件中发现日志路径"""
        instances = []

        for cnf_path in _CNF_PATHS:
            try:
                path = Path(cnf_path)
                if not path.exists():
                    continue

                content = path.read_text(encoding="utf-8", errors="ignore")

                # 解析 log_error 变量
                log_error = self._parse_cnf_log_error(content)
                if not log_error:
                    continue

                # 解析 port
                port = self._parse_cnf_port(content)

                # 解析 !includedir 引入的额外配置
                included_logs = self._parse_included_dirs(content)

                all_logs = [log_error] + included_logs
                for i, log_path in enumerate(all_logs):
                    if self._is_valid_log(log_path):
                        name = f"mysql-{path.stem}" if i == 0 else f"mysql-{path.stem}-inc{i}"
                        instances.append({
                            "name": name,
                            "log_path": log_path,
                            "host": "localhost",
                            "port": port,
                        })
                        logger.info("从配置文件 %s 发现日志: %s", cnf_path, log_path)

            except PermissionError:
                logger.warning("权限不足，无法读取配置文件: %s", cnf_path)
            except Exception as e:
                logger.warning("读取配置文件 %s 时出错: %s", cnf_path, e)

        return instances

    async def _discover_from_mysqladmin(self) -> list[dict]:
        """通过 mysqladmin variables 命令获取日志路径"""
        instances = []

        # 检查 mysqladmin 是否可用
        mysqladmin = shutil.which("mysqladmin")
        if not mysqladmin:
            logger.debug("未找到 mysqladmin 命令")
            return instances

        try:
            proc = await asyncio.create_subprocess_exec(
                mysqladmin, "variables",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="ignore").strip()
                if "Access denied" in stderr_text:
                    logger.warning("mysqladmin 权限不足，请检查 MySQL 用户权限")
                elif "connect" in stderr_text.lower():
                    logger.warning("MySQL 服务未运行或无法连接: %s", stderr_text)
                else:
                    logger.warning("mysqladmin 执行失败: %s", stderr_text)
                return instances

            output = stdout.decode("utf-8", errors="ignore")
            log_error = self._parse_mysqladmin_variable(output, "log_error")
            port_str = self._parse_mysqladmin_variable(output, "port")
            port = int(port_str) if port_str and port_str.isdigit() else 3306

            if log_error and self._is_valid_log(log_error):
                instances.append({
                    "name": "mysql-admin",
                    "log_path": log_error,
                    "host": "localhost",
                    "port": port,
                })
                logger.info("从 mysqladmin 发现日志: %s", log_error)

        except asyncio.TimeoutError:
            logger.warning("mysqladmin 命令执行超时")
        except FileNotFoundError:
            logger.debug("mysqladmin 命令不存在")
        except Exception as e:
            logger.warning("执行 mysqladmin 时出错: %s", e)

        return instances

    async def _discover_from_defaults(self) -> list[dict]:
        """检查常见默认路径"""
        instances = []

        # 检查固定默认路径
        for log_path in _DEFAULT_LOG_PATHS:
            if self._is_valid_log(log_path):
                instances.append({
                    "name": f"mysql-default",
                    "log_path": log_path,
                    "host": "localhost",
                    "port": 3306,
                })
                logger.info("从默认路径发现日志: %s", log_path)

        # 检查 MySQL 数据目录下的 .err 文件
        for data_dir in _MYSQL_DATA_DIRS:
            data_path = Path(data_dir)
            if not data_path.exists():
                continue
            try:
                for err_file in data_path.glob("*.err"):
                    if self._is_valid_log(str(err_file)):
                        instances.append({
                            "name": f"mysql-{err_file.stem}",
                            "log_path": str(err_file),
                            "host": "localhost",
                            "port": 3306,
                        })
                        logger.info("从数据目录发现日志: %s", err_file)
            except PermissionError:
                logger.warning("权限不足，无法扫描目录: %s", data_dir)
            except Exception as e:
                logger.warning("扫描目录 %s 时出错: %s", data_dir, e)

        return instances

    def _get_manual_instances(self) -> list[dict]:
        """从 Config 获取手动配置的实例"""
        manual = self._config.get("mysql", "instances", default=[])
        if not manual:
            return []

        instances = []
        for inst in manual:
            log_path = inst.get("log_path", "")
            if log_path and self._is_valid_log(log_path):
                instances.append({
                    "name": inst.get("name", "mysql-manual"),
                    "log_path": log_path,
                    "host": inst.get("host", "localhost"),
                    "port": inst.get("port", 3306),
                })
                logger.info("从手动配置发现实例: %s (%s)", inst.get("name"), log_path)
            elif log_path:
                logger.warning("手动配置的日志路径不存在或不可读: %s", log_path)

        return instances

    @staticmethod
    def _parse_cnf_log_error(content: str) -> str | None:
        """从配置文件内容中解析 log_error 变量"""
        # 匹配 log_error = /path 或 log-error = /path
        match = re.search(
            r'(?:log[_-]error)\s*=\s*["\']?([^\s"\';]+)["\']?',
            content, re.IGNORECASE,
        )
        return match.group(1) if match else None

    @staticmethod
    def _parse_cnf_port(content: str) -> int:
        """从配置文件内容中解析 port"""
        match = re.search(r'port\s*=\s*(\d+)', content, re.IGNORECASE)
        return int(match.group(1)) if match else 3306

    @staticmethod
    def _parse_included_dirs(content: str) -> list[str]:
        """解析 !includedir 引入的配置目录中的 log_error"""
        log_paths = []
        for match in re.finditer(r'!includedir\s+(.+)', content):
            dir_path = match.group(1).strip()
            dir_path_obj = Path(dir_path)
            if not dir_path_obj.is_dir():
                continue
            try:
                for cnf in dir_path_obj.glob("*.cnf"):
                    sub_content = cnf.read_text(encoding="utf-8", errors="ignore")
                    log_error = MySQLLogDiscover._parse_cnf_log_error(sub_content)
                    if log_error:
                        log_paths.append(log_error)
            except (PermissionError, OSError):
                pass
        return log_paths

    @staticmethod
    def _parse_mysqladmin_variable(output: str, var_name: str) -> str | None:
        """从 mysqladmin variables 输出中解析指定变量"""
        # mysqladmin variables 输出格式:
        # | log_error                                | /var/log/mysql/error.log
        # 或
        # | log_error       | /var/log/mysql/error.log
        pattern = rf'\|\s*{var_name}\s*\|\s*([^\|\n]+)'
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _is_valid_log(path: str) -> bool:
        """检查日志路径是否有效（文件存在且可读）"""
        try:
            return Path(path).is_file() and os.access(path, os.R_OK)
        except OSError:
            return False
