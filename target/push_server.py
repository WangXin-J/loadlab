"""压测目标：模拟 cloud-monitor 的指标推送服务。

两种广播实现，用来复现真实世界里最常见的一个坑：

- naive     ：广播循环里逐个 `await ws.send()`，一个慢客户端会阻塞整轮广播，
              全体客户端的延迟一起被拉高（队头阻塞）。
- optimized ：每个连接独立发送队列 + 独立发送协程，队列满则丢帧并计数，
              慢客户端只影响自己。

    python target/push_server.py --port 8765 --mode naive
    python target/push_server.py --port 8765 --mode optimized

每秒往 --stats 指定的文件追加一行 JSON，供报告读取。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from functools import partial
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

CLIENTS: dict = {}
COUNTER = {"sent": 0, "dropped": 0}


def build_payload(seq: int, pad_bytes: int = 0) -> str:
    payload = {
        "type": "metric",
        "seq": seq,
        "sentAt": int(time.time() * 1000),
        "hostId": "h1",
        "metrics": {
            "cpu": round(10 + (seq % 50) * 0.7, 1),
            "mem": 63.2,
            "disk": 71.0,
            "net": 1.2,
        },
    }
    if pad_bytes:
        # 用大报文尽快填满慢消费者的 socket 缓冲区，把「卡住」在几秒内复现出来
        payload["pad"] = "x" * pad_bytes
    return json.dumps(payload, ensure_ascii=False)


class Client:
    """一个下行的消费者。optimized 模式下有自己的队列和发送协程。"""

    def __init__(self, ws, queue_size: int = 0):
        self.ws = ws
        self.queue: asyncio.Queue | None = asyncio.Queue(maxsize=queue_size) if queue_size else None
        self.consumer: asyncio.Task | None = None

    async def drain(self) -> None:
        """独立发送协程：只关心自己这个连接，慢也不影响别人。"""
        assert self.queue is not None
        while True:
            payload = await self.queue.get()
            try:
                await self.ws.send(payload)
                COUNTER["sent"] += 1
            except Exception:
                return

    def offer(self, payload: str) -> None:
        assert self.queue is not None
        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            COUNTER["dropped"] += 1


async def handler(ws, path=None, *, mode: str = "naive", queue_size: int = 200):
    client = Client(ws, queue_size if mode == "optimized" else 0)
    CLIENTS[id(ws)] = client

    if mode == "optimized":
        client.consumer = asyncio.create_task(client.drain())

    try:
        async for _ in ws:
            pass
    except ConnectionClosed:
        pass
    finally:
        CLIENTS.pop(id(ws), None)
        if client.consumer:
            client.consumer.cancel()


async def broadcaster(mode: str, interval: float, work_ms: float, pad_bytes: int = 0):
    seq = 0
    while True:
        seq += 1
        payload = build_payload(seq, pad_bytes)

        if mode == "naive":
            for client in list(CLIENTS.values()):
                try:
                    await client.ws.send(payload)
                    COUNTER["sent"] += 1
                except Exception:
                    CLIENTS.pop(id(client.ws), None)
        else:
            for client in list(CLIENTS.values()):
                client.offer(payload)

        if work_ms:
            await asyncio.sleep(work_ms / 1000)
        await asyncio.sleep(interval)


async def stats_writer(path: Path, interval: float = 1.0):
    last = time.perf_counter()
    while True:
        await asyncio.sleep(interval)
        now = time.perf_counter()
        expected = now - last - interval
        last = now
        row = {
            "ts": int(time.time() * 1000),
            "clients": len(CLIENTS),
            "sent": COUNTER["sent"],
            "dropped": COUNTER["dropped"],
            "loopLagMs": round(max(0.0, expected) * 1000, 2),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


async def main_async(args) -> None:
    stats_path = Path(args.stats)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text("", encoding="utf-8")

    handler_with_mode = partial(handler, mode=args.mode, queue_size=args.queue_size)
    async with websockets.serve(handler_with_mode, "127.0.0.1", args.port):
        print(f"push server on ws://127.0.0.1:{args.port} mode={args.mode}", flush=True)
        await asyncio.gather(
            broadcaster(args.mode, args.interval, args.work_ms, args.payload_bytes),
            stats_writer(stats_path),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--mode", choices=["naive", "optimized"], default="naive")
    parser.add_argument("--interval", type=float, default=0.2, help="广播间隔（秒）")
    parser.add_argument("--work-ms", type=float, default=0.0, help="每帧额外占用（毫秒），模拟编码开销")
    parser.add_argument("--queue-size", type=int, default=200, help="optimized 模式每连接队列长度")
    parser.add_argument("--payload-bytes", type=int, default=0, help="报文填充字节数，用于放大慢消费者的影响")
    parser.add_argument("--stats", default="report/server-stats.jsonl")
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
