"""单个压测客户端：连上去、收推送、量延迟。

两种形态：
- 正常客户端：持续 recv 并测量延迟
- 停滞客户端（stall）：连上、订阅，然后**再也不读**，模拟弱网/卡死的消费者
  它本身测不到延迟，但会把服务端的广播循环拖住（仅 naive 实现）

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
    stalled: bool = False


async def run_client(
    url: str,
    total_seconds: float,
    connect_timeout: float = 5.0,
    stall: bool = False,
) -> ClientOutcome:
    deadline = time.monotonic() + total_seconds
    outcome = ClientOutcome(stalled=stall)

    try:
        async with websockets.connect(url, open_timeout=connect_timeout) as ws:
            await ws.send(json.dumps({"action": "subscribe", "metrics": ["cpu", "mem"]}))

            if stall:
                # 关键：不读。服务端 write buffer 一旦写满，naive 的广播循环就会卡死。
                await asyncio.sleep(max(0.0, deadline - time.monotonic()))
                return outcome

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
