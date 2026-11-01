from __future__ import annotations

import pytest

from loadlab.stats import find_knee, percentile, summarize


def test_percentile_empty():
    assert percentile([], 95) == 0.0


def test_percentile_single():
    assert percentile([42], 95) == 42.0


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile([1, 2, 3, 4], 0) == 1.0
    assert percentile([1, 2, 3, 4], 100) == 4.0


def test_percentile_p95_of_hundred():
    assert percentile(list(range(1, 101)), 95) == pytest.approx(95.05, abs=0.1)


def test_percentile_rejects_bad_p():
    with pytest.raises(ValueError):
        percentile([1], 120)


def test_summarize_shape():
    row = summarize(clients=10, latencies=[1, 2, 3, 4], messages=40, errors=1, duration_s=2.0, drops=3)
    assert row["clients"] == 10
    assert row["throughput"] == 20.0
    assert row["errorRate"] == 0.1
    assert row["p50"] == 2.5
    assert row["dropped"] == 3


def _stage(clients, p95, error_rate=0.0):
    return {"clients": clients, "p95": p95, "errorRate": error_rate, "throughput": 100}


def test_knee_none_when_flat():
    assert find_knee([_stage(10, 5), _stage(20, 6), _stage(40, 7)]) is None


def test_knee_when_latency_doubles():
    knee = find_knee([_stage(10, 20), _stage(20, 25), _stage(40, 120)])
    assert knee is not None and knee["clients"] == 40


def test_knee_on_first_error():
    knee = find_knee([_stage(10, 5), _stage(20, 6, error_rate=0.2)])
    assert knee is not None and knee["clients"] == 20


def test_knee_ignores_small_absolute_growth():
    # 20ms -> 30ms 是增长了 50%，但绝对值仍然很低，不该判为拐点
    assert find_knee([_stage(10, 20), _stage(20, 30)]) is None
