import json
import math
from datetime import date, timedelta

import numpy as np

from common import store
from job import forecast, settings
from model import conformal


def _store(n=700, syms=("AAA", "BBB", "CCC"), seed=3):
    """Kho giả: nến ngày liên tiếp (bỏ T7/CN) cho vài mã + VNINDEX."""
    st = store.empty()
    d0 = date(2023, 1, 2)
    days = []
    d = d0
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    for k, sym in enumerate(list(syms) + ["VNINDEX"]):
        rnd = np.random.default_rng(seed + k)
        c, rows = 20.0 + k, []
        for dd in days:
            o = c
            c = o * math.exp(rnd.normal(0, 0.02))
            rows.append({"d": dd, "o": o, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99, "c": c,
                         "v": int(1e5 * (1 + rnd.random())), "t": 0})
        store.merge(st, sym, rows)
    return st, days


def test_forecast_all_and_score_roundtrip(tmp_path):
    st, days = _store()
    items = [{"symbol": s, "company_name": s} for s in ("AAA", "BBB", "CCC")]
    cfg = dict(settings.DEFAULTS)
    conf = conformal.new_state(forecast.HS)
    td = days[-1]
    fc, stale, info = forecast.forecast_all(st, items, td, cfg, conf, n_sim=200)
    assert stale == [] and len(fc) == 3 and all(it["ok"] for it in fc)
    it = fc[0]
    assert set(it["q"]) == {"5", "10", "20"} and it["q"]["10"]["5"] < it["q"]["10"]["50"] < it["q"]["10"]["95"]
    assert 0 <= it["p10"] <= 1 and it["level"] <= 6 and it["n"] > 0 and it["p_src"] == "regime_freq"
    assert len(it["scenarios"]) == 2 and it["scenarios"][0]["weight"] >= it["scenarios"][1]["weight"]
    # tái lập: cùng (mã, ngày) → cùng nón
    fc2, _, _ = forecast.forecast_all(st, items, td, cfg, conf, n_sim=200)
    assert fc2[0]["q"] == it["q"]

    # chấm điểm: giả lập nón phát 10 phiên trước, giá thật là close hôm nay → hit_rate ∈ [0,1], s thay đổi
    cal = forecast.calendar(st)
    d0 = cal[cal.index(td.isoformat()) - 10]
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / f"{d0}.json").write_text(json.dumps({"trade_date": d0, "forecasts": {
        s: {"price": 20.0, "q_log": {"10": {"5": -0.5, "10": -0.4, "25": -0.2, "50": 0.0, "75": 0.2, "90": 0.4, "95": 0.5}}}
        for s in ("AAA", "BBB", "CCC")}}), encoding="utf-8")
    scored = set()
    res = forecast.score_matured(st, cal, td, daily, conf, scored)
    assert {r["h"] for r in res} == {10} and len(res) == 3 and f"{d0}|10" in scored
    assert all(0 <= r["hit"] <= 1 and r["n"] == 3 for r in res)
    assert forecast.score_matured(st, cal, td, daily, conf, scored) == []      # không chấm hai lần


def test_stale_symbol_not_forecast():
    st, days = _store()
    st["bars"]["BBB"] = st["bars"]["BBB"][:-3]                                   # BBB thiếu 3 phiên cuối
    items = [{"symbol": s} for s in ("AAA", "BBB")]
    fc, stale, _ = forecast.forecast_all(st, items, days[-1], dict(settings.DEFAULTS), conformal.new_state(forecast.HS), n_sim=100)
    assert [s["symbol"] for s in stale] == ["BBB"] and [it["symbol"] for it in fc] == ["AAA"]


def test_verdict_bands():
    conf = conformal.new_state(forecast.HS)
    assert forecast.verdict(conf)["status"] == "pending"
    for _ in range(60):
        conformal.update(conf, 10, 80, 0.80)
    assert forecast.verdict(conf)["status"] == "ok"
    for _ in range(60):
        conformal.update(conf, 10, 80, 0.60)
    assert forecast.verdict(conf)["status"] == "narrow"
