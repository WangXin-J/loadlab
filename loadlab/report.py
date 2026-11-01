"""报告生成：图表 + Markdown。

图表标签用英文，是为了避免在无中文字体的 CI 容器里出现豆腐块；
报告正文用中文。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _series(runs: list[tuple[str, dict]], key: str) -> list[tuple[str, list[int], list[float]]]:
    out = []
    for label, data in runs:
        stages = data.get("stages", [])
        out.append((label, [s["clients"] for s in stages], [s[key] for s in stages]))
    return out


def chart_latency(runs: list[tuple[str, dict]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for label, xs, _ in _series(runs, "p95"):
        stages = dict(runs)[label]["stages"]
        ax.plot(xs, [s["p95"] for s in stages], marker="o", label=f"{label} p95")
        ax.plot(xs, [s["p99"] for s in stages], marker="x", linestyle="--", label=f"{label} p99")
    ax.set_xlabel("concurrent clients")
    ax.set_ylabel("latency (ms)")
    ax.set_title("Push latency vs concurrency")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def chart_throughput(runs: list[tuple[str, dict]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for label, xs, ys in _series(runs, "throughput"):
        ax.plot(xs, ys, marker="o", label=label)
    ax.set_xlabel("concurrent clients")
    ax.set_ylabel("messages / second")
    ax.set_title("Throughput vs concurrency")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def _table(stages: list[dict]) -> str:
    head = "| 并发 | 停滞 | 吞吐(msg/s) | p50(ms) | p95(ms) | p99(ms) | 错误 | 丢帧 | 事件循环最大延迟 |\n"
    head += "|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    rows = [
        f"| {s['clients']} | {s.get('stalled', 0)} | {s['throughput']} | {s['p50']} | {s['p95']} | {s['p99']} | "
        f"{s['errors']} | {s['dropped']} | {s['loopLagMs']}ms |"
        for s in stages
    ]
    return head + "\n".join(rows) + "\n"


def render(runs: list[tuple[str, dict]], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chart_latency(runs, out_dir / "latency.png")
    chart_throughput(runs, out_dir / "throughput.png")

    lines = ["# 压测报告", ""]
    lines.append(f"生成时间：{runs[0][1].get('generatedAt', '-')}　目标：`{runs[0][1].get('target', '-')}`")
    lines.append("")
    lines.append("![latency](latency.png)")
    lines.append("")
    lines.append("![throughput](throughput.png)")
    lines.append("")

    for label, data in runs:
        stages = data.get("stages", [])
        lines.append(f"## {label}")
        lines.append("")
        lines.append(_table(stages))
        knee = data.get("knee")
        if knee:
            lines.append(
                f"**拐点：{knee['clients']} 并发**　p95 从上一档开始显著抬升（{knee['p95']}ms），"
                f"吞吐 {knee['throughput']} msg/s，错误 {knee['errors']}，丢帧 {knee['dropped']}。"
            )
        else:
            lines.append("**未在本次加压区间内观察到拐点**：p95 未出现相对翻倍，也没有错误。需要继续加压。")
        lines.append("")

    lines.append("## 结论怎么写")
    lines.append("")
    lines.append("- 拐点之前的最后一档，就是这个服务在当前配置下的**安全并发**；")
    lines.append("- p95 > 2 倍基线、或开始出现错误/丢帧，说明已经进入排队区；")
    lines.append("- 对比不同实现时，看的是**拐点位置后移了多少**，而不是单看某一档的 p95。")
    lines.append("")
    lines.append("## 复现")
    lines.append("")
    lines.append("```bash")
    lines.append("python target/push_server.py --port 8765 --mode naive &")
    lines.append("loadlab run --target ws://127.0.0.1:8765 --stages 10,50,100,200 --duration 8 \\")
    lines.append("            --server-stats report/server-stats.jsonl --out report/naive.json")
    lines.append("```")
    lines.append("")

    report = out_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
