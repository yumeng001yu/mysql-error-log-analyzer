"""配置加载模块"""

import os
import yaml
from pathlib import Path
from typing import Any


_DEFAULT_CONFIG = {
    "llm": {
        "provider": "openai",
        "model": "gpt-4",
        "api_base": "",
        "api_key": "",
        "timeout": 60,
        "temperature": 0.3,
    },
    "mysql": {
        "auto_discover": True,
        "instances": [],
    },
    "collector": {
        "watch_interval": 5,
        "batch_size": 1000,
        "stream_chunk_size_mb": 10,
        "full_analysis_warning_mb": 500,
    },
    "analyzer": {
        "auto_analyze": True,
        "auto_analyze_interval": 60,
        "critical_levels": ["CRITICAL", "ERROR"],
        "critical_keywords": [
            "crash", "shutdown", "abort",
            "InnoDB: corruption", "replication",
            "slave_io_running", "deadlock",
        ],
    },
    "storage": {
        "db_path": "./data/logs.db",
        "retention_days": 90,
    },
    "web": {
        "host": "127.0.0.1",
        "port": 8080,
        "allow_remote": False,
        "auth": {
            "enabled": False,
            "username": "admin",
            "password_hash": "",
            "jwt_secret": "",
        },
    },
    "cli": {
        "prompt": "mysql-analyzer> ",
        "history_file": ".cli_history",
    },
    "status": {
        "refresh_interval": 10,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """全局配置管理器"""

    _instance = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def load(cls, config_path: str | None = None) -> "Config":
        """加载配置文件，与默认配置合并"""
        instance = cls()
        instance._data = _DEFAULT_CONFIG.copy()

        if config_path is None:
            # 按优先级查找配置文件
            search_paths = [
                Path.cwd() / "config.yaml",
                Path.cwd() / "config" / "config.yaml",
                Path(__file__).parent.parent / "config" / "config.yaml",
            ]
            for p in search_paths:
                if p.exists():
                    config_path = str(p)
                    break

        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            instance._data = _deep_merge(instance._data, user_config)

        # 环境变量覆盖（MYSQL_ANALYZER_ 前缀）
        instance._load_env_overrides()
        return instance

    def _load_env_overrides(self):
        """从环境变量加载覆盖配置"""
        env_mappings = {
            "MYSQL_ANALYZER_LLM_PROVIDER": ("llm", "provider"),
            "MYSQL_ANALYZER_LLM_MODEL": ("llm", "model"),
            "MYSQL_ANALYZER_LLM_API_BASE": ("llm", "api_base"),
            "MYSQL_ANALYZER_LLM_API_KEY": ("llm", "api_key"),
            "MYSQL_ANALYZER_WEB_HOST": ("web", "host"),
            "MYSQL_ANALYZER_WEB_PORT": ("web", "port"),
            "MYSQL_ANALYZER_DB_PATH": ("storage", "db_path"),
        }
        for env_key, path in env_mappings.items():
            value = os.environ.get(env_key)
            if value is not None:
                self._set_nested(path, value)

    def _set_nested(self, path: tuple, value: Any):
        """设置嵌套字典值"""
        d = self._data
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    def get(self, *keys, default=None) -> Any:
        """获取配置值，支持多级键路径"""
        d = self._data
        for key in keys:
            if not isinstance(d, dict) or key not in d:
                return default
            d = d[key]
        return d

    @property
    def data(self) -> dict:
        return self._data

    def to_dict(self) -> dict:
        return self._data.copy()
