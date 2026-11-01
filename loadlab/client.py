"""单个压测客户端：连上去、收推送、量延迟。

延迟 = 客户端收到时刻 - 服务端写进消息的 sentAt。
同机压测时可以这么算；跨机要额外做时钟同步，这一点在报告里会写明。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

import websockets
from websockets.exceptions import ConnectionClosed


@dataclass
class ClientOutcome:
    latencies: list[float] = field(default_factory=list)
    messages: int = 0
    errors: int = 0


async def run_client(url: str, total_seconds: float, connect_timeout: float = 5.0) -> ClientOutcome:
    deadline = time.monotonic() + total_seconds
    outcome = ClientOutcome()

    try:
        async with websockets.connect(url, open_timeout=connect_timeout) as ws:
            await ws.send(json.dumps({"action": "subscribe", "metrics": ["cpu", "mem"]}))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                except ConnectionClosed:
                    outcome.errors += 1
                    break

                outcome.messages += 1
                try:
                    payload = json.loads(raw)
                    sent_at = payload.get("sentAt")
                    if sent_at is not None:
                        outcome.latencies.append(max(0.0, time.time() * 1000 - sent_at))
                except (json.JSONDecodeError, TypeError):
                    outcome.errors += 1
    except Exception:  # 连接失败、握手超时都算一次错误
        outcome.errors += 1

    return outcome
