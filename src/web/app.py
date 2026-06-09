"""FastAPI 应用入口"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import Config
from src.storage.database import DatabaseManager
from src.status import StatusTracker

logger = logging.getLogger(__name__)

# 全局引用，供生命周期事件使用
_db: DatabaseManager | None = None
_watcher = None


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="MySQL Error Log Analyzer",
        description="MySQL 错误日志自动分析工具 Web 后端",
        version="1.0.0",
    )

    # ── CORS 配置（开发模式允许所有来源）────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 注册 API 路由 ─────────────────────────────────────
    from src.web.api.auth import router as auth_router
    from src.web.api.logs import router as logs_router
    from src.web.api.analysis import router as analysis_router
    from src.web.api.status import router as status_router
    from src.web.websocket import router as ws_router

    app.include_router(auth_router)
    app.include_router(logs_router)
    app.include_router(analysis_router)
    app.include_router(status_router)
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

                async def on_log_change(instance_id: str, new_lines: list[str]):
                    """日志变化回调"""
                    try:
                        entries = []
                        for line in new_lines:
                            parsed = parser.parse_line(line)
                            if parsed:
                                parsed["instance_id"] = instance_id
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

    # ── 挂载静态文件（前端构建产物）────────────────────────
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")

    return app
