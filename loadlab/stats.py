"""统计工具：分位数与汇总。

分位数用线性插值，和大多数监控系统（Prometheus summary）口径一致，
避免"p95 到底是第几个样本"这种对不上数的问题。
"""
from __future__ import annotations


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if not 0 <= p <= 100:
        raise ValueError("p 必须在 0..100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (p / 100)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


def summarize(
    *,
    clients: int,
    latencies: list[float],
    messages: int,
    errors: int,
    duration_s: float,
    drops: int = 0,
    loop_lag_ms: float = 0.0,
) -> dict:
    return {
        "clients": clients,
        "durationS": round(duration_s, 2),
        "messages": messages,
        "throughput": round(messages / duration_s, 1) if duration_s else 0.0,
        "errors": errors,
        "errorRate": round(errors / clients, 4) if clients else 0.0,
        "dropped": drops,
        "loopLagMs": round(loop_lag_ms, 2),
        "p50": round(percentile(latencies, 50), 1),
        "p95": round(percentile(latencies, 95), 1),
        "p99": round(percentile(latencies, 99), 1),
        "max": round(max(latencies), 1) if latencies else 0.0,
    }


def find_knee(stages: list[dict]) -> dict | None:
    """找容量拐点：p95 相对上一档翻倍且超过 50ms，或者开始出现错误。

    只看绝对值不够 —— 不同机器的基线不一样，看的是「相对自己翻倍」。
    """
    previous: dict | None = None
    for stage in stages:
        if stage["errorRate"] > 0:
            return stage
        if previous and previous["p95"] > 0 and stage["p95"] > max(50.0, previous["p95"] * 2):
            return stage
        previous = stage
    return None
