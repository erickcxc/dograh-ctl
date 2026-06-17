"""Latency stats over call runs. Pure, no I/O — the logic behind `runs latency`."""
from __future__ import annotations

import math
from typing import Optional, Sequence

# Duration key spellings, most-likely first (the live API uses call_duration_seconds).
_DURATION_KEYS = ("call_duration_seconds", "duration_seconds", "duration")


def _duration(run: dict) -> Optional[float]:
    for k in _DURATION_KEYS:
        v = run.get(k)
        if isinstance(v, bool):  # bool is an int subclass; never a duration
            continue
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100). Assumes non-empty, sorted input."""
    k = max(1, math.ceil(p / 100 * len(sorted_vals)))
    return sorted_vals[k - 1]


def latency_summary(runs: Sequence[dict]) -> dict:
    """Summarize call durations: total, how many had a usable duration, and
    avg/p50/p95/min/max in seconds (None when no run carried a duration)."""
    durations = sorted(d for d in (_duration(r) for r in runs) if d is not None)
    if not durations:
        return {"count": len(runs), "with_duration": 0,
                "avg": None, "p50": None, "p95": None, "min": None, "max": None}
    return {
        "count": len(runs),
        "with_duration": len(durations),
        "avg": round(sum(durations) / len(durations), 1),
        "p50": round(_percentile(durations, 50), 1),
        "p95": round(_percentile(durations, 95), 1),
        "min": round(durations[0], 1),
        "max": round(durations[-1], 1),
    }
