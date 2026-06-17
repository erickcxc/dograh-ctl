"""Tests for the latency summary — the real logic behind `dograh-ctl runs latency`."""
from dograh_ctl.stats import latency_summary


def test_computes_stats_from_call_duration_seconds():
    runs = [{"call_duration_seconds": d} for d in (10, 20, 30, 40)]
    s = latency_summary(runs)
    assert s["count"] == 4
    assert s["with_duration"] == 4
    assert s["avg"] == 25.0
    assert s["p50"] == 20.0
    assert s["p95"] == 40.0
    assert s["min"] == 10.0
    assert s["max"] == 40.0


def test_ignores_runs_without_a_numeric_duration():
    runs = [
        {"call_duration_seconds": 12},
        {"call_duration_seconds": None},   # connected but no duration
        {"disposition": "no-answer"},      # never connected
        {"call_duration_seconds": "n/a"},  # bad data
    ]
    s = latency_summary(runs)
    assert s["count"] == 4
    assert s["with_duration"] == 1
    assert s["avg"] == 12.0


def test_empty_sample_returns_none_stats():
    s = latency_summary([])
    assert s["count"] == 0
    assert s["with_duration"] == 0
    assert s["avg"] is None
    assert s["p95"] is None
