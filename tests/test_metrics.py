"""S3 用量聚合纯逻辑单测"""
import json
from datetime import date, datetime, timedelta

from smartoken_gui.metrics import aggregate, last_n_days, read_live


def _rec(model, prompt, comp, cost=0.0, saving=0.0, ts=1_700_000_000.0, tps=10.0, ttft=100):
    return {"model_id": model, "prompt_tokens": prompt, "completion_tokens": comp,
            "actual_cost_usd": cost, "saving_usd": saving, "ts": ts,
            "decode_tps": tps, "ttft_ms": ttft}


def _write(tmp_path, day, recs):
    audit = tmp_path / "audit"
    audit.mkdir(exist_ok=True)
    with open(audit / f"{day.isoformat()}.ndjson", "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


def _midnight(d: date) -> float:
    return datetime(d.year, d.month, d.day).timestamp()


def test_aggregate_sums_and_days(tmp_path):
    today = date.today()
    d1 = today - timedelta(days=1)
    d5 = today - timedelta(days=5)
    _write(tmp_path, d1, [
        _rec("a", 10, 20, cost=0.1, saving=0.5, ts=_midnight(d1) + 60),
        _rec("a", 5, 5, cost=0.01, saving=0.02, ts=_midnight(d1) + 120),
        "not-json-line",
    ])
    _write(tmp_path, d5, [_rec("b", 100, 200, cost=2.0, ts=_midnight(d5))])
    agg = aggregate(str(tmp_path), today - timedelta(days=7), today)
    a = agg["models"]["a"]
    assert a["requests"] == 2
    assert a["prompt_tokens"] == 15
    assert a["completion_tokens"] == 25
    assert round(a["cost_usd"], 4) == round(0.11, 4)
    assert {p["date"] for p in agg["per_day"]} == {d1.isoformat(), d5.isoformat()}
    assert agg["totals"]["requests"] == 3


def test_aggregate_respects_range(tmp_path):
    today = date.today()
    old_day = today - timedelta(days=20)
    _write(tmp_path, old_day, [_rec("old", 9, 9, ts=_midnight(old_day))])
    agg = aggregate(str(tmp_path), *last_n_days(7))
    assert agg["totals"]["requests"] == 0
    assert "old" not in agg["models"]


def test_read_live_missing(tmp_path):
    assert read_live(str(tmp_path)) == {"current": None, "last": None}
