from __future__ import annotations

import asyncio
import json

from loadlab.client import run_client
from loadlab.report import render
from loadlab.runner import read_server_stats, run_stage, run_stages


def test_client_receives_messages(ws_server):
    url, _ = ws_server
    outcome = asyncio.run(run_client(url, total_seconds=1.5))
    assert outcome.messages > 0, "1.5 秒内一条推送都没收到"
    assert outcome.errors == 0
    assert all(lat >= 0 for lat in outcome.latencies)


def test_single_stage_aggregates(ws_server):
    url, _ = ws_server
    stage = asyncio.run(run_stage(url, clients=3, duration=1.5))
    assert stage["clients"] == 3
    assert stage["messages"] > 0
    assert stage["throughput"] > 0
    assert stage["errors"] == 0
    assert stage["p95"] >= 0


def test_multi_stage_has_knee_field(ws_server):
    url, stats = ws_server
    data = asyncio.run(run_stages(url, [2, 4], duration=1.5, server_stats=stats, cooldown=0.2))
    assert len(data["stages"]) == 2
    assert "knee" in data
    assert data["stages"][0]["clients"] == 2
    assert all(s["messages"] > 0 for s in data["stages"])


def test_server_stats_are_written(ws_server):
    url, stats = ws_server
    asyncio.run(run_stage(url, clients=2, duration=2.5))
    rows = read_server_stats(stats)
    assert rows, "服务端没有写出任何 stats 记录"
    assert any(r.get("sent", 0) > 0 for r in rows)


def test_report_renders(tmp_path, ws_server):
    url, _ = ws_server
    data = asyncio.run(run_stages(url, [2], duration=1.2, cooldown=0))
    report = render([("naive", data)], tmp_path / "report")
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "压测报告" in text
    assert (tmp_path / "report" / "latency.png").exists()
    assert (tmp_path / "report" / "throughput.png").exists()


def test_result_json_round_trip(tmp_path, ws_server):
    url, _ = ws_server
    data = asyncio.run(run_stages(url, [2], duration=1.2, cooldown=0))
    path = tmp_path / "r.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["stages"][0]["clients"] == 2
