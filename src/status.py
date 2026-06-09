"""程序状态追踪模块"""

import threading
import time
from datetime import datetime

from src.config import Config

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class StatusTracker:
    """程序状态追踪器（单例模式），线程安全"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._data_lock = threading.Lock()

        self._start_time: datetime | None = None
        self._is_running: bool = False
        self._monitored_instances: list[dict] = []
        self._last_analysis_time: dict[str, datetime] = {}
        self._processing_progress: dict[str, float] = {}
        self._total_logs_processed: int = 0
        self._total_alerts: int = 0

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        """记录启动时间，标记运行中"""
        with self._data_lock:
            self._start_time = datetime.now()
            self._is_running = True

    def stop(self):
        """标记停止"""
        with self._data_lock:
            self._is_running = False

    # ── 实例管理 ──────────────────────────────────────────────

    def update_instance(self, instance_id: str, info: dict):
        """更新实例信息（名称、日志路径、文件大小等）"""
        with self._data_lock:
            for inst in self._monitored_instances:
                if inst.get("instance_id") == instance_id:
                    inst.update(info)
                    return
            # 不存在则新增
            new_inst = {"instance_id": instance_id}
            new_inst.update(info)
            self._monitored_instances.append(new_inst)

    def update_progress(self, instance_id: str, progress: float):
        """更新处理进度（0.0-1.0）"""
        progress = max(0.0, min(1.0, progress))
        with self._data_lock:
            self._processing_progress[instance_id] = progress

    def update_analysis_time(self, instance_id: str):
        """更新最近分析时间"""
        with self._data_lock:
            self._last_analysis_time[instance_id] = datetime.now()

    # ── 计数器 ────────────────────────────────────────────────

    def increment_logs(self, count: int = 1):
        """增加处理日志计数"""
        with self._data_lock:
            self._total_logs_processed += count

    def increment_alerts(self):
        """增加告警计数"""
        with self._data_lock:
            self._total_alerts += 1

    # ── 状态查询 ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """获取完整状态信息（自动计算 uptime、CPU、内存）"""
        with self._data_lock:
            uptime = 0.0
            if self._start_time is not None and self._is_running:
                uptime = (datetime.now() - self._start_time).total_seconds()

            cpu_percent = 0.0
            memory_mb = 0.0
            if _HAS_PSUTIL:
                try:
                    process = psutil.Process()
                    cpu_percent = process.cpu_percent(interval=None)
                    memory_mb = process.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            return {
                "start_time": self._start_time.isoformat() if self._start_time else None,
                "uptime_seconds": uptime,
                "monitored_instances": list(self._monitored_instances),
                "last_analysis_time": {
                    k: v.isoformat() for k, v in self._last_analysis_time.items()
                },
                "processing_progress": dict(self._processing_progress),
                "cpu_percent": cpu_percent,
                "memory_mb": round(memory_mb, 2),
                "total_logs_processed": self._total_logs_processed,
                "total_alerts": self._total_alerts,
                "is_running": self._is_running,
            }

    def get_summary(self) -> str:
        """获取简要状态文本（用于 CLI 显示）"""
        with self._data_lock:
            if not self._is_running:
                return "[STOPPED] 程序未运行"

            uptime = 0.0
            if self._start_time is not None:
                uptime = (datetime.now() - self._start_time).total_seconds()

            hours, remainder = divmod(int(uptime), 3600)
            minutes, seconds = divmod(remainder, 60)

            instance_count = len(self._monitored_instances)
            progress_lines = []
            for iid, prog in self._processing_progress.items():
                pct = int(prog * 100)
                bar_len = 20
                filled = int(bar_len * prog)
                bar = "█" * filled + "░" * (bar_len - filled)
                progress_lines.append(f"  {iid}: [{bar}] {pct}%")

            progress_text = "\n".join(progress_lines) if progress_lines else "  (无活跃任务)"

            cpu = 0.0
            mem = 0.0
            if _HAS_PSUTIL:
                try:
                    process = psutil.Process()
                    cpu = process.cpu_percent(interval=None)
                    mem = process.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            summary = (
                f"[RUNNING] 运行时长: {hours}h {minutes}m {seconds}s\n"
                f"  监控实例: {instance_count} 个\n"
                f"  已处理日志: {self._total_logs_processed} 条\n"
                f"  告警数: {self._total_alerts} 条\n"
                f"  CPU: {cpu:.1f}%  内存: {mem:.1f} MB\n"
                f"  处理进度:\n{progress_text}"
            )
            return summary
