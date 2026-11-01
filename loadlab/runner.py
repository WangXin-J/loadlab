"""压测编排：分级加压，逐档采集，输出可复现的 JSON。"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from .client import run_client
from .stats import find_knee, summarize


def read_server_stats(path: str | Path | None) -> list[dict]:
    if not path:
        return []
    file = Path(path)
    if not file.exists():
        return []
    rows = []
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _slice(rows: list[dict], start_ms: int, end_ms: int) -> tuple[int, int, float]:
    window = [r for r in rows if start_ms <= r.get("ts", 0) <= end_ms]
    if not window:
        return 0, 0, 0.0
    dropped = window[-1].get("dropped", 0) - window[0].get("dropped", 0)
    return (
        max(r.get("clients", 0) for r in window),
        max(0, dropped),
        max(r.get("loopLagMs", 0.0) for r in window),
    )


async def run_stage(url: str, clients: int, duration: float, server_rows: list[dict] | None = None) -> dict:
    start_ms = int(time.time() * 1000)
    started = time.perf_counter()

    outcomes = await asyncio.gather(
        *(run_client(url, duration) for _ in range(clients)),
        return_exceptions=True,
    )

    elapsed = time.perf_counter() - started
    end_ms = int(time.time() * 1000)

    latencies: list[float] = []
    messages = errors = 0
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            errors += 1
            continue
        latencies.extend(outcome.latencies)
        messages += outcome.messages
        errors += outcome.errors

    _, drops, loop_lag = _slice(server_rows or [], start_ms, end_ms)

    return summarize(
        clients=clients,
        latencies=latencies,
        messages=messages,
        errors=errors,
        duration_s=elapsed,
        drops=drops,
        loop_lag_ms=loop_lag,
    )


async def run_stages(
    url: str,
    stages: list[int],
    duration: float,
    server_stats: str | Path | None = None,
    cooldown: float = 1.0,
) -> dict:
    rows = read_server_stats(server_stats)
    results = []
    for index, clients in enumerate(stages, start=1):
        print(f"[stage {index}/{len(stages)}] {clients} 并发，持续 {duration}s", flush=True)
        stage = await run_stage(url, clients, duration, rows)
        print(
            f"   messages={stage['messages']} throughput={stage['throughput']}/s "
            f"p95={stage['p95']}ms errors={stage['errors']} drops={stage['dropped']}",
            flush=True,
        )
        results.append(stage)
        if index < len(stages):
            await asyncio.sleep(cooldown)

    return {
        "target": url,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "durationPerStage": duration,
        "stages": results,
        "knee": find_knee(results),
    }
