"""命令行入口。"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from . import __version__
from .report import render
from .runner import run_stages


def _parse_stages(text: str) -> list[int]:
    try:
        stages = [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise SystemExit(f"--stages 格式错误: {text}，示例：10,50,100")
    if not stages or any(s <= 0 for s in stages):
        raise SystemExit("--stages 必须是正整数列表")
    return stages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loadlab", description="WebSocket 长连接压测与拐点分析")
    parser.add_argument("--version", action="version", version=f"loadlab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="分级加压并输出结果 JSON")
    run.add_argument("--target", required=True, help="ws://127.0.0.1:8765")
    run.add_argument("--stages", default="10,50,100", help="并发档位，逗号分隔")
    run.add_argument("--duration", type=float, default=8.0, help="每档持续秒数")
    run.add_argument("--cooldown", type=float, default=1.0, help="档位之间冷却秒数")
    run.add_argument("--server-stats", default=None, help="服务端 stats.jsonl 路径（可选）")
    run.add_argument("--stalled", type=int, default=0, help="其中多少个连接连上后不读取（模拟慢消费者）")
    run.add_argument("--out", default="report/results.json")

    rep = sub.add_parser("report", help="根据结果 JSON 生成图表与 Markdown")
    rep.add_argument("--inputs", nargs="+", required=True, help="一个或多个结果 JSON")
    rep.add_argument("--labels", nargs="*", default=None, help="与 inputs 对应的标签")
    rep.add_argument("--out", default="report")

    args = parser.parse_args(argv)

    if args.command == "run":
        stages = _parse_stages(args.stages)
        data = asyncio.run(
            run_stages(args.target, stages, args.duration, args.server_stats, args.cooldown, args.stalled)
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {out}")
        knee = data.get("knee")
        print(f"拐点：{knee['clients']} 并发" if knee else "拐点：本次未出现")
        return 0

    labels = args.labels or [Path(p).stem for p in args.inputs]
    if len(labels) != len(args.inputs):
        raise SystemExit("--labels 数量必须与 --inputs 一致")
    runs = [(label, json.loads(Path(path).read_text(encoding="utf-8"))) for label, path in zip(labels, args.inputs)]
    report = render(runs, args.out)
    print(f"报告已生成：{report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
