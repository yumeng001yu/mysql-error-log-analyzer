"""WebSocket 推送模块"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import Config
from src.notifier.alert import AlertNotifier
from src.status import StatusTracker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """关键错误实时推送

    客户端连接后接收实时告警，与 AlertNotifier 的 WebSocket 列表集成。
    """
    await websocket.accept()
    notifier = AlertNotifier()
    notifier.add_websocket(websocket)

    try:
        while True:
            # 保持连接，等待客户端消息（心跳或断开）
            try:
                data = await websocket.receive_text()
                # 处理心跳 ping
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.warning("WebSocket alerts 连接异常: %s", e)
    finally:
        notifier.remove_websocket(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    """状态实时推送

    定期推送程序状态（每 10 秒）。
    """
    await websocket.accept()
    tracker = StatusTracker()
    config = Config()
    interval = config.get("status", "refresh_interval", default=10)

    try:
        while True:
            status = tracker.get_status()
            try:
                await websocket.send_json(status)
            except Exception:
                break

            # 等待下一次推送，同时检测客户端断开
            try:
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(asyncio.sleep(interval)),
                        asyncio.create_task(websocket.receive_text()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # 取消未完成的任务
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # 检查是否有客户端消息（可能是断开）
                for task in done:
                    if task.exception():
                        return
            except WebSocketDisconnect:
                break
            except Exception:
                break
    except Exception as e:
        logger.warning("WebSocket status 连接异常: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
