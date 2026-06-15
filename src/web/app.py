"""FastAPI 应用入口"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from src.config import Config
from src.storage.database import DatabaseManager
from src.status import StatusTracker

logger = logging.getLogger(__name__)

# 全局引用，供生命周期事件使用
_db: DatabaseManager | None = None
_watcher = None

# 前端构建产物路径
_FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


class SPAFallbackMiddleware:
    """原始 ASGI 中间件：拦截非 API 路径的 404 响应，返回 index.html

    BaseHTTPMiddleware 无法可靠拦截 404（Starlette 的已知问题），
    因此使用原始 ASGI 协议层中间件，直接缓冲响应判断状态码。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")

        # API / 文档 / 静态资源路径直接透传，不做拦截
        if any(path.startswith(p) for p in ("/api", "/assets", "/docs", "/openapi", "/redoc")):
            await self.app(scope, receive, send)
            return

        # 对其余路径（SPA 路由），缓冲响应以判断是否 404
        status_code = None
        headers = None
        body_parts = []

        async def send_wrapper(message):
            nonlocal status_code, headers, body_parts

            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.get("headers", [])
                # 暂不发送，等 body 完成后决定是否替换

            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
                more_body = message.get("more_body", False)

                if not more_body:
                    # 完整响应已接收
                    if status_code == 404:
                        index_path = _FRONTEND_DIST / "index.html"
                        if index_path.exists():
                            content = index_path.read_bytes()
                            await send({
                                "type": "http.response.start",
                                "status": 200,
                                "headers": [
                                    [b"content-type", b"text/html; charset=utf-8"],
                                    [b"content-length", str(len(content)).encode()],
                                ],
                            })
                            await send({
                                "type": "http.response.body",
                                "body": content,
                            })
                            return

                    # 非 404 或 index.html 不存在，转发原始响应
                    await send({
                        "type": "http.response.start",
                        "status": status_code,
                        "headers": headers,
                    })
                    for part in body_parts:
                        await send({
                            "type": "http.response.body",
                            "body": part,
                        })

        await self.app(scope, receive, send_wrapper)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="MySQL Error Log Analyzer",
        description="MySQL 错误日志自动分析工具 Web 后端",
        version="1.0.0",
    )

    # ── 健康检查 ────────────────────────────────────────────
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "mysql-error-log-analyzer"}

    # ── CORS 配置 ────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── SPA fallback 中间件（原始 ASGI，必须在 CORS 之后）────
    app.add_middleware(SPAFallbackMiddleware)

    # ── 注册 API 路由 ─────────────────────────────────────
    from src.web.api.auth import router as auth_router
    from src.web.api.logs import router as logs_router
    from src.web.api.analysis import router as analysis_router
    from src.web.api.status import router as status_router
    from src.web.api.settings import router as settings_router
    from src.web.api.slow_query import router as slow_query_router
    from src.web.api.monitor import router as monitor_router
    from src.web.api.alerts import router as alerts_router
    from src.web.api.patterns import router as patterns_router
    from src.web.api.search import router as search_router
    from src.web.api.instances import router as instances_router
    from src.web.api.baseline import router as baseline_router
    from src.web.api.reports import router as reports_router
    from src.web.api.deadlock import router as deadlock_router
    from src.web.api.redis_monitor import router as redis_monitor_router
    from src.web.api.redis_slowlog import router as redis_slowlog_router
    from src.web.api.redis_analysis import router as redis_analysis_router
    from src.web.api.redis_cluster import router as redis_cluster_router
    from src.web.websocket import router as ws_router

    app.include_router(auth_router)
    app.include_router(logs_router)
    app.include_router(analysis_router)
    app.include_router(status_router)
    app.include_router(settings_router)
    app.include_router(slow_query_router)
    app.include_router(monitor_router)
    app.include_router(alerts_router)
    app.include_router(patterns_router)
    app.include_router(search_router)
    app.include_router(instances_router)
    app.include_router(baseline_router)
    app.include_router(reports_router)
    app.include_router(deadlock_router)
    app.include_router(redis_monitor_router)
    app.include_router(redis_slowlog_router)
    app.include_router(redis_analysis_router)
    app.include_router(redis_cluster_router)
    app.include_router(ws_router)

    # ── 启动事件 ─────────────────────────────────────────
    @app.on_event("startup")
    async def on_startup():
        global _db, _watcher
        config = Config()

        # 初始化数据库
        _db = DatabaseManager()
        await _db.initialize()
        logger.info("数据库初始化完成")

        # 发现 MySQL 实例
        instances = []
        if config.get("mysql", "auto_discover", default=True):
            try:
                from src.collector.discover import MySQLLogDiscover
                discover = MySQLLogDiscover()
                instances = await discover.discover()
                logger.info("自动发现 %d 个 MySQL 实例", len(instances))

                # 将发现的实例写入数据库
                conn = await _db._get_conn()
                for inst in instances:
                    await conn.execute(
                        """INSERT OR IGNORE INTO instances (name, log_path, host, port, created_at)
                           VALUES (?, ?, ?, ?, datetime('now'))""",
                        (inst["name"], inst["log_path"], inst.get("host", "localhost"), inst.get("port", 3306)),
                    )
                await conn.commit()
            except Exception as e:
                logger.warning("自动发现 MySQL 实例失败: %s", e)

        # 启动监控
        if instances:
            try:
                from src.collector.watcher import LogWatcher
                from src.collector.parser import LogParser

                parser = LogParser()

                # 构建实例名称到数据库ID的映射
                instance_id_map: dict[str, int] = {}
                for inst in instances:
                    name = inst.get("name", "unknown")
                    # 查询数据库获取实例ID
                    conn = await _db._get_conn()
                    cursor = await conn.execute(
                        "SELECT id FROM instances WHERE name = ?", (name,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        instance_id_map[name] = row[0]

                async def on_log_change(instance_id: str, new_lines: list[str]):
                    """日志变化回调"""
                    try:
                        entries = []
                        db_id = instance_id_map.get(instance_id)
                        for line in new_lines:
                            parsed = parser.parse_line(line)
                            if parsed:
                                parsed["instance_id"] = db_id
                                parsed["category"] = parser.classify_error(
                                    parsed.get("message", ""), parsed.get("error_code")
                                )
                                entries.append(parsed)
                        if entries:
                            await _db.insert_log_entries(entries)
                            from src.status import StatusTracker
                            StatusTracker().increment_logs(len(entries))
                    except Exception as e:
                        logger.error("处理日志增量失败: %s", e)

                _watcher = LogWatcher(instances, on_log_change)
                await _watcher.start()
                logger.info("日志监控已启动")
            except Exception as e:
                logger.warning("启动日志监控失败: %s", e)

        # 标记状态运行中
        # 初始化向量搜索（可选）
        try:
            from src.vector.manager import VectorSearchManager
            vs = VectorSearchManager()
            if vs.is_available():
                await vs.initialize()
                logger.info("语义搜索已启用")
        except Exception as e:
            logger.info("语义搜索未启用: %s", e)

        StatusTracker().start()
        logger.info("应用启动完成")

    # ── 关闭事件 ─────────────────────────────────────────
    @app.on_event("shutdown")
    async def on_shutdown():
        global _db, _watcher

        # 停止监控
        if _watcher is not None:
            try:
                await _watcher.stop()
                logger.info("日志监控已停止")
            except Exception as e:
                logger.warning("停止日志监控失败: %s", e)

        # 关闭数据库
        # 关闭向量搜索
        try:
            from src.vector.manager import VectorSearchManager
            vs = VectorSearchManager()
            if vs.is_available():
                await vs.close()
        except Exception:
            pass

        if _db is not None:
            try:
                await _db.close()
                logger.info("数据库连接已关闭")
            except Exception as e:
                logger.warning("关闭数据库失败: %s", e)

        # 标记状态停止
        StatusTracker().stop()
        logger.info("应用已关闭")

    # ── 静态文件 ────────────────────────────────────────────
    if _FRONTEND_DIST.is_dir():
        assets_dir = _FRONTEND_DIST / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    return app


# 模块级 app 实例，供 uvicorn 直接引用
app = create_app()
