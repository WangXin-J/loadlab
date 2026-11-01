"""LoadLab —— WebSocket 长连接压测与容量拐点分析。"""
from .stats import find_knee, percentile, summarize
from .runner import run_stage, run_stages

__version__ = "0.1.0"

__all__ = ["percentile", "summarize", "find_knee", "run_stage", "run_stages", "__version__"]
