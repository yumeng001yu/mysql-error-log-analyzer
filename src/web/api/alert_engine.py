"""智能告警引擎核心逻辑

负责告警规则的评估、通知发送和数据库表管理。
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class AlertEngine:
    """智能告警引擎，负责规则评估与通知推送"""

    def __init__(self, db: DatabaseManager):
        self._db = db
        self._tables_ready = False

    async def ensure_tables(self):
        """懒加载创建告警相关表"""
        if self._tables_ready:
            return

        conn = await self._db._get_conn()

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                rule_type TEXT NOT NULL DEFAULT 'threshold',
                metric TEXT NOT NULL DEFAULT 'error_count',
                condition TEXT NOT NULL DEFAULT 'gt',
                threshold REAL NOT NULL DEFAULT 0,
                window INTEGER NOT NULL DEFAULT 5,
                level TEXT NOT NULL DEFAULT 'warning',
                channels TEXT DEFAULT '[]',
                cooldown INTEGER NOT NULL DEFAULT 300,
                last_triggered_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL,
                rule_name TEXT NOT NULL,
                level TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'firing',
                message TEXT DEFAULT '',
                detail TEXT DEFAULT '{}',
                triggered_at TEXT NOT NULL,
                acknowledged_at TEXT,
                resolved_at TEXT,
                channel_results TEXT DEFAULT '{}',
                FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
            );

            CREATE TABLE IF NOT EXISTS notification_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'webhook',
                enabled INTEGER NOT NULL DEFAULT 1,
                config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled
                ON alert_rules(enabled);
            CREATE INDEX IF NOT EXISTS idx_alert_rules_metric
                ON alert_rules(metric);

            CREATE INDEX IF NOT EXISTS idx_alert_history_rule_id
                ON alert_history(rule_id);
            CREATE INDEX IF NOT EXISTS idx_alert_history_level
                ON alert_history(level);
            CREATE INDEX IF NOT EXISTS idx_alert_history_status
                ON alert_history(status);
            CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at
                ON alert_history(triggered_at);

            CREATE INDEX IF NOT EXISTS idx_notification_channels_type
                ON notification_channels(type);
            CREATE INDEX IF NOT EXISTS idx_notification_channels_enabled
                ON notification_channels(enabled);
        """)

        await conn.commit()
        self._tables_ready = True
        logger.info("告警引擎数据表已就绪")

    # ── 指标数据采集 ──────────────────────────────────────────

    async def _collect_metrics(self, window_minutes: int) -> dict[str, Any]:
        """采集指定时间窗口内的各项指标数据

        Args:
            window_minutes: 时间窗口（分钟）

        Returns:
            包含各项指标值的字典
        """
        conn = await self._db._get_conn()
        cutoff = (datetime.now() - timedelta(minutes=window_minutes)).isoformat()

        metrics: dict[str, Any] = {}

        # 按级别统计日志数量
        cursor = await conn.execute(
            """SELECT level, COUNT(*) as count
               FROM log_entries
               WHERE timestamp >= ?
               GROUP BY level""",
            (cutoff,),
        )
        level_counts = {row["level"]: row["count"] for row in await cursor.fetchall()}

        # 错误总数（ERROR + FATAL）
        metrics["error_count"] = sum(
            level_counts.get(lv, 0) for lv in ("ERROR", "FATAL")
        )
        # 警告数
        metrics["warning_count"] = level_counts.get("WARNING", 0)
        # 全部日志数
        metrics["total_log_count"] = sum(level_counts.values())
        # 错误率（错误数 / 总数，百分比）
        total = metrics["total_log_count"]
        metrics["error_rate"] = round(metrics["error_count"] / total * 100, 2) if total > 0 else 0.0

        # 慢查询数量
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM slow_queries WHERE timestamp >= ?",
            (cutoff,),
        )
        row = await cursor.fetchone()
        metrics["slow_query_count"] = row["cnt"] if row else 0

        # 连接数（从最新监控指标获取）
        cursor = await conn.execute(
            """SELECT metric_value FROM monitor_metrics
               WHERE metric_name = 'connections'
               ORDER BY collected_at DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
        metrics["connection_count"] = row["metric_value"] if row else 0

        # 各级别明细
        metrics["level_counts"] = level_counts

        return metrics

    async def _collect_previous_metrics(self, window_minutes: int) -> dict[str, Any]:
        """采集上一个时间窗口的指标数据（用于计算增长率）

        Args:
            window_minutes: 时间窗口（分钟）

        Returns:
            包含各项指标值的字典
        """
        conn = await self._db._get_conn()
        now = datetime.now()
        window_end = now - timedelta(minutes=window_minutes)
        window_start = now - timedelta(minutes=window_minutes * 2)

        metrics: dict[str, Any] = {}

        cursor = await conn.execute(
            """SELECT level, COUNT(*) as count
               FROM log_entries
               WHERE timestamp >= ? AND timestamp < ?
               GROUP BY level""",
            (window_start.isoformat(), window_end.isoformat()),
        )
        level_counts = {row["level"]: row["count"] for row in await cursor.fetchall()}

        metrics["error_count"] = sum(
            level_counts.get(lv, 0) for lv in ("ERROR", "FATAL")
        )
        metrics["warning_count"] = level_counts.get("WARNING", 0)
        metrics["total_log_count"] = sum(level_counts.values())

        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM slow_queries WHERE timestamp >= ? AND timestamp < ?",
            (window_start.isoformat(), window_end.isoformat()),
        )
        row = await cursor.fetchone()
        metrics["slow_query_count"] = row["cnt"] if row else 0

        return metrics

    # ── 规则评估 ──────────────────────────────────────────────

    def _evaluate_condition(self, value: float, condition: str, threshold: float) -> bool:
        """评估单个条件

        Args:
            value: 当前指标值
            condition: 比较运算符
            threshold: 阈值

        Returns:
            条件是否满足
        """
        ops = {
            "gt": lambda v, t: v > t,
            "gte": lambda v, t: v >= t,
            "lt": lambda v, t: v < t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: v == t,
            "ne": lambda v, t: v != t,
        }
        op = ops.get(condition)
        if op is None:
            logger.warning("未知的条件运算符: %s", condition)
            return False
        return op(value, threshold)

    def _compute_increase_rate(self, current: float, previous: float) -> float:
        """计算增长率（百分比）

        Args:
            current: 当前值
            previous: 之前值

        Returns:
            增长率百分比，之前值为0时返回100.0
        """
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - previous) / previous * 100, 2)

    async def evaluate_rules(self) -> list[dict]:
        """评估所有启用的告警规则

        Returns:
            触发的告警列表
        """
        await self.ensure_tables()
        conn = await self._db._get_conn()
        now = datetime.now().isoformat()

        # 获取所有启用的规则
        cursor = await conn.execute(
            "SELECT * FROM alert_rules WHERE enabled = 1"
        )
        rules = [dict(row) for row in await cursor.fetchall()]

        if not rules:
            return []

        # 按时间窗口分组采集指标，避免重复查询
        metrics_cache: dict[int, dict] = {}
        prev_metrics_cache: dict[int, dict] = {}

        fired_alerts = []

        for rule in rules:
            window = rule["window"]
            rule_id = rule["id"]

            # 检查冷却时间
            if rule.get("last_triggered_at"):
                last_triggered = rule["last_triggered_at"]
                cooldown_seconds = rule.get("cooldown", 300)
                try:
                    last_dt = datetime.fromisoformat(last_triggered)
                    if (datetime.now() - last_dt).total_seconds() < cooldown_seconds:
                        continue  # 冷却期内，跳过
                except (ValueError, TypeError):
                    pass

            # 采集指标（按窗口缓存）
            if window not in metrics_cache:
                metrics_cache[window] = await self._collect_metrics(window)
            metrics = metrics_cache[window]

            # 获取指标值
            metric_name = rule["metric"]
            condition = rule["condition"]
            threshold = rule["threshold"]

            # 处理 increase_rate 类型条件
            if condition == "increase_rate":
                if window not in prev_metrics_cache:
                    prev_metrics_cache[window] = await self._collect_previous_metrics(window)
                prev_metrics = prev_metrics_cache[window]

                current_val = metrics.get(metric_name, 0)
                prev_val = prev_metrics.get(metric_name, 0)
                value = self._compute_increase_rate(float(current_val), float(prev_val))
                # increase_rate 使用 gt 比较
                triggered = value > threshold
            else:
                value = float(metrics.get(metric_name, 0))
                triggered = self._evaluate_condition(value, condition, threshold)

            if not triggered:
                continue

            # 构建告警消息
            level_labels = {"critical": "严重", "warning": "警告", "info": "信息"}
            level_label = level_labels.get(rule["level"], rule["level"])
            message = (
                f"[{level_label}] 规则「{rule['name']}」触发: "
                f"指标 {metric_name} 当前值 {value} {condition} 阈值 {threshold}"
                f"（时间窗口: {window} 分钟）"
            )

            detail = {
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "rule_type": rule["rule_type"],
                "metric": metric_name,
                "condition": condition,
                "threshold": threshold,
                "current_value": value,
                "window_minutes": window,
                "level_counts": metrics.get("level_counts", {}),
            }

            # 插入告警历史
            await conn.execute(
                """INSERT INTO alert_history
                   (rule_id, rule_name, level, status, message, detail,
                    triggered_at, channel_results)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule_id,
                    rule["name"],
                    rule["level"],
                    "firing",
                    message,
                    json.dumps(detail, ensure_ascii=False),
                    now,
                    "{}",
                ),
            )

            # 更新规则的最后触发时间
            await conn.execute(
                "UPDATE alert_rules SET last_triggered_at = ?, updated_at = ? WHERE id = ?",
                (now, now, rule_id),
            )

            await conn.commit()

            # 获取刚插入的告警ID
            cursor = await conn.execute(
                "SELECT last_insert_rowid() as id"
            )
            alert_row = await cursor.fetchone()
            alert_id = alert_row["id"] if alert_row else 0

            # 发送通知
            channel_ids = json.loads(rule.get("channels", "[]"))
            channel_results = await self._send_notifications(channel_ids, message, detail)

            # 更新通知结果
            await conn.execute(
                "UPDATE alert_history SET channel_results = ? WHERE id = ?",
                (json.dumps(channel_results, ensure_ascii=False), alert_id),
            )
            await conn.commit()

            fired_alerts.append({
                "id": alert_id,
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "level": rule["level"],
                "message": message,
                "detail": detail,
                "triggered_at": now,
                "channel_results": channel_results,
            })

            logger.info("告警触发: %s", message)

        return fired_alerts

    # ── 通知发送 ──────────────────────────────────────────────

    async def _send_notifications(
        self, channel_ids: list[int], message: str, detail: dict
    ) -> dict[str, Any]:
        """向指定渠道发送告警通知

        Args:
            channel_ids: 通知渠道 ID 列表
            message: 告警消息
            detail: 告警详情

        Returns:
            各渠道发送结果
        """
        if not channel_ids:
            return {}

        conn = await self._db._get_conn()
        results: dict[str, Any] = {}

        for ch_id in channel_ids:
            cursor = await conn.execute(
                "SELECT * FROM notification_channels WHERE id = ? AND enabled = 1",
                (ch_id,),
            )
            channel = await cursor.fetchone()
            if not channel:
                results[str(ch_id)] = {"success": False, "error": "渠道不存在或已禁用"}
                continue

            channel_dict = dict(channel)
            try:
                success = await self._send_to_channel(channel_dict, message, detail)
                results[str(ch_id)] = {"success": success}
            except Exception as e:
                results[str(ch_id)] = {"success": False, "error": str(e)[:200]}
                logger.warning("通知发送失败 (渠道 %s): %s", channel_dict["name"], e)

        return results

    async def _send_to_channel(
        self, channel: dict, message: str, detail: dict
    ) -> bool:
        """向单个渠道发送通知

        Args:
            channel: 渠道信息
            message: 告警消息
            detail: 告警详情

        Returns:
            是否发送成功
        """
        ch_type = channel["type"]
        config = json.loads(channel.get("config", "{}"))

        if ch_type == "webhook":
            return await self._send_webhook(config, message, detail)
        elif ch_type == "email":
            return await self._send_email(config, message, detail)
        elif ch_type == "dingtalk":
            return await self._send_dingtalk(config, message, detail)
        elif ch_type == "feishu":
            return await self._send_feishu(config, message, detail)
        elif ch_type == "slack":
            return await self._send_slack(config, message, detail)
        else:
            logger.warning("未知渠道类型: %s", ch_type)
            return False

    async def _send_email(
        self, config: dict, message: str, detail: dict
    ) -> bool:
        """发送邮件通知（通过 SMTP）

        config 字段:
            emails: 收件人列表
            smtp_host: SMTP 服务器地址（默认 smtp.163.com）
            smtp_port: SMTP 端口（默认 465）
            smtp_user: 发件人邮箱
            smtp_password: SMTP 授权码
            use_tls: 是否使用 TLS（默认 True）
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        recipients = config.get("emails", [])
        if not recipients:
            logger.warning("邮件通知: 无收件人")
            return False

        smtp_host = config.get("smtp_host", "smtp.163.com")
        smtp_port = config.get("smtp_port", 465)
        smtp_user = config.get("smtp_user", "")
        smtp_password = config.get("smtp_password", "")
        use_tls = config.get("use_tls", True)

        if not smtp_user or not smtp_password:
            logger.info("邮件通知 (模拟，未配置SMTP): %s -> %s", message[:50], recipients)
            return True

        # 构建邮件内容
        level = detail.get("level", "warning")
        rule_name = detail.get("rule_name", "")
        current_value = detail.get("current_value", "")
        threshold = detail.get("threshold", "")
        metric = detail.get("metric", "")

        html_body = f"""
        <html><body style="font-family: sans-serif; background: #1a1a2e; color: #e2e8f0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #1e1e2e; border: 1px solid #2a3a52; border-radius: 8px; padding: 24px;">
            <h2 style="color: {'#ef4444' if level == 'critical' else '#f59e0b' if level == 'warning' else '#06b6d4'}; margin-top: 0;">
                {'🔴' if level == 'critical' else '🟡' if level == 'warning' else '🔵'} MySQL 告警通知
            </h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 8px; color: #94a3b8;">规则名称</td><td style="padding: 8px;">{rule_name}</td></tr>
                <tr><td style="padding: 8px; color: #94a3b8;">告警级别</td><td style="padding: 8px; color: {'#ef4444' if level == 'critical' else '#f59e0b' if level == 'warning' else '#06b6d4'};">{level.upper()}</td></tr>
                <tr><td style="padding: 8px; color: #94a3b8;">监控指标</td><td style="padding: 8px;">{metric}</td></tr>
                <tr><td style="padding: 8px; color: #94a3b8;">当前值</td><td style="padding: 8px; font-weight: bold;">{current_value}</td></tr>
                <tr><td style="padding: 8px; color: #94a3b8;">阈值</td><td style="padding: 8px;">{threshold}</td></tr>
                <tr><td style="padding: 8px; color: #94a3b8;">触发时间</td><td style="padding: 8px;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
            </table>
            <p style="margin-top: 16px; padding: 12px; background: #0a0e17; border-radius: 4px; font-size: 13px;">
                {message}
            </p>
        </div>
        </body></html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[MySQL告警][{level.upper()}] {rule_name}"
        msg["From"] = smtp_user
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            if use_tls:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                server.starttls()

            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipients, msg.as_string())
            server.quit()
            logger.info("邮件通知发送成功: %s -> %s", message[:50], recipients)
            return True
        except Exception as e:
            logger.error("邮件通知发送失败: %s", e)
            return False

    async def _send_webhook(
        self, config: dict, message: str, detail: dict
    ) -> bool:
        """发送 Webhook 通知"""
        url = config.get("url", "")
        if not url:
            return False

        payload = {
            "text": message,
            "alert": detail,
        }
        headers = config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return resp.status_code < 400

    async def _send_dingtalk(
        self, config: dict, message: str, detail: dict
    ) -> bool:
        """发送钉钉机器人通知"""
        url = config.get("url", "")
        if not url:
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "MySQL 告警通知",
                "text": f"### MySQL 告警通知\n\n{message}\n\n> 规则: {detail.get('rule_name', '')}\n> 级别: {detail.get('level', '')}",
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            return data.get("errcode", -1) == 0

    async def _send_feishu(
        self, config: dict, message: str, detail: dict
    ) -> bool:
        """发送飞书机器人通知"""
        url = config.get("url", "")
        if not url:
            return False

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "MySQL 告警通知"},
                    "template": "red" if detail.get("level") == "critical" else "orange",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": message,
                    }
                ],
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            return data.get("code", -1) == 0

    async def _send_slack(
        self, config: dict, message: str, detail: dict
    ) -> bool:
        """发送 Slack 通知"""
        url = config.get("url", "")
        if not url:
            return False

        payload = {
            "text": f"⚠️ MySQL 告警通知",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message,
                    },
                }
            ],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200

    async def test_channel(self, channel_id: int) -> dict[str, Any]:
        """测试通知渠道连通性

        Args:
            channel_id: 渠道 ID

        Returns:
            测试结果
        """
        await self.ensure_tables()
        conn = await self._db._get_conn()

        cursor = await conn.execute(
            "SELECT * FROM notification_channels WHERE id = ?",
            (channel_id,),
        )
        channel = await cursor.fetchone()
        if not channel:
            return {"success": False, "message": "渠道不存在"}

        channel_dict = dict(channel)
        test_message = f"[测试] MySQL Error Log Analyzer 告警渠道测试 - {datetime.now().isoformat()}"
        test_detail = {
            "rule_name": "测试规则",
            "level": "info",
            "metric": "test",
            "current_value": 0,
            "threshold": 0,
        }

        try:
            success = await self._send_to_channel(channel_dict, test_message, test_detail)
            if success:
                return {"success": True, "message": f"渠道「{channel_dict['name']}」测试成功"}
            else:
                return {"success": False, "message": f"渠道「{channel_dict['name']}」测试失败，请检查配置"}
        except Exception as e:
            return {"success": False, "message": f"测试异常: {str(e)[:200]}"}
