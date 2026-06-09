"""关键错误通知模块"""

import asyncio
import json
import logging
from datetime import datetime

from src.config import Config

logger = logging.getLogger(__name__)


class AlertNotifier:
    """关键错误通知器，负责检测关键错误并推送到 Web / CLI"""

    def __init__(self):
        Config.load()
        config = Config()
        self._critical_levels: list[str] = config.get(
            "analyzer", "critical_levels", default=["CRITICAL", "ERROR"]
        )
        self._critical_keywords: list[str] = config.get(
            "analyzer", "critical_keywords", default=[]
        )

        self._websockets: list = []
        self._cli_callback = None

        # 延迟导入，避免循环依赖；在首次使用时初始化
        self._llm_manager = None
        self._db_manager = None

    # ── 内部懒加载 ────────────────────────────────────────────

    def _get_llm_manager(self):
        """懒加载 LLMManager"""
        if self._llm_manager is None:
            try:
                from src.analyzer.llm import LLMManager

                self._llm_manager = LLMManager()
            except ImportError:
                logger.warning("LLMManager 不可用，跳过 LLM 建议生成")
            except Exception as exc:
                logger.warning("初始化 LLMManager 失败: %s", exc)
        return self._llm_manager

    async def _get_db_manager(self):
        """懒加载 DatabaseManager"""
        if self._db_manager is None:
            try:
                from src.storage.database import DatabaseManager

                self._db_manager = DatabaseManager()
                await self._db_manager.initialize()
            except Exception as exc:
                logger.warning("初始化 DatabaseManager 失败: %s", exc)
        return self._db_manager

    # ── WebSocket / CLI 注册 ─────────────────────────────────

    def add_websocket(self, websocket):
        """注册 WebSocket 连接"""
        if websocket not in self._websockets:
            self._websockets.append(websocket)
            logger.info("WebSocket 已注册，当前连接数: %d", len(self._websockets))

    def remove_websocket(self, websocket):
        """移除 WebSocket 连接"""
        if websocket in self._websockets:
            self._websockets.remove(websocket)
            logger.info("WebSocket 已移除，当前连接数: %d", len(self._websockets))

    def set_cli_callback(self, callback):
        """设置 CLI 通知回调"""
        self._cli_callback = callback

    # ── 推送方法 ──────────────────────────────────────────────

    async def push_to_web(self, alert: dict):
        """推送告警到所有 WebSocket 连接"""
        if not self._websockets:
            return

        message = json.dumps(alert, ensure_ascii=False)
        disconnected = []

        for ws in self._websockets:
            try:
                await ws.send(message)
                logger.debug("告警已推送到 WebSocket: %s", alert.get("alert_type"))
            except Exception as exc:
                logger.warning("WebSocket 推送失败: %s", exc)
                disconnected.append(ws)

        for ws in disconnected:
            self._websockets.remove(ws)

    async def push_to_cli(self, alert: dict):
        """推送告警到 CLI"""
        if self._cli_callback is None:
            return

        try:
            if asyncio.iscoroutinefunction(self._cli_callback):
                await self._cli_callback(alert)
            else:
                self._cli_callback(alert)
            logger.debug("告警已推送到 CLI: %s", alert.get("alert_type"))
        except Exception as exc:
            logger.warning("CLI 推送失败: %s", exc)

    # ── 核心检测与通知 ────────────────────────────────────────

    def _is_critical(self, log_entry: dict) -> tuple[bool, str]:
        """判断日志条目是否为关键错误，返回 (是否关键, 告警类型)"""
        level = (log_entry.get("level") or "").upper()
        message = log_entry.get("message") or ""

        # 级别匹配
        for critical_level in self._critical_levels:
            if level == critical_level.upper():
                return True, "critical"

        # 关键词匹配
        message_lower = message.lower()
        for keyword in self._critical_keywords:
            if keyword.lower() in message_lower:
                return True, "warning"

        return False, ""

    async def _generate_llm_suggestion(self, log_entry: dict) -> str:
        """调用 LLM 生成建议"""
        llm = self._get_llm_manager()
        if llm is None:
            return ""

        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一位 MySQL 数据库专家，请针对以下错误日志给出简要的排查建议。",
                },
                {
                    "role": "user",
                    "content": (
                        f"级别: {log_entry.get('level', '')}\n"
                        f"错误码: {log_entry.get('error_code', '')}\n"
                        f"消息: {log_entry.get('message', '')}"
                    ),
                },
            ]
            result = await llm.ainvoke(messages)
            return result if isinstance(result, str) else str(result)
        except Exception as exc:
            logger.warning("LLM 建议生成失败: %s", exc)
            return ""

    async def _store_alert(self, alert: dict):
        """存储告警到数据库"""
        db = await self._get_db_manager()
        if db is None:
            return

        try:
            await db.insert_critical_alert(alert)
            logger.info("告警已存储到数据库: %s", alert.get("alert_type"))
        except Exception as exc:
            logger.warning("告警存储失败: %s", exc)

    async def check_and_notify(self, log_entry: dict, instance_id: str) -> dict | None:
        """检查日志条目是否为关键错误，若是则通知并返回告警信息"""
        is_critical, alert_type = self._is_critical(log_entry)
        if not is_critical:
            return None

        # 构建 alert
        alert = {
            "instance_id": instance_id,
            "alert_type": alert_type,
            "level": log_entry.get("level", ""),
            "error_code": log_entry.get("error_code", ""),
            "message": log_entry.get("message", ""),
            "timestamp": log_entry.get("timestamp", datetime.now().isoformat()),
            "llm_suggestion": "",
        }

        # 调用 LLM 生成建议（异步，不阻塞主流程）
        try:
            alert["llm_suggestion"] = await self._generate_llm_suggestion(log_entry)
        except Exception as exc:
            logger.warning("LLM 建议生成异常: %s", exc)

        # 存储到数据库
        asyncio.create_task(self._safe_store(alert))

        # 推送到 Web 和 CLI（异步，不阻塞主流程）
        asyncio.create_task(self._safe_push_web(alert))
        asyncio.create_task(self._safe_push_cli(alert))

        logger.info(
            "检测到关键错误 [%s]: instance=%s level=%s",
            alert_type,
            instance_id,
            alert["level"],
        )

        return alert

    async def _safe_store(self, alert: dict):
        """安全存储告警"""
        try:
            await self._store_alert(alert)
        except Exception as exc:
            logger.warning("告警存储异常: %s", exc)

    async def _safe_push_web(self, alert: dict):
        """安全推送告警到 Web"""
        try:
            await self.push_to_web(alert)
        except Exception as exc:
            logger.warning("Web 推送异常: %s", exc)

    async def _safe_push_cli(self, alert: dict):
        """安全推送告警到 CLI"""
        try:
            await self.push_to_cli(alert)
        except Exception as exc:
            logger.warning("CLI 推送异常: %s", exc)
