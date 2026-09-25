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


def _plant_gap_fill(st, sym, days):
    """Ghi đè 12 nến cuối của một mã: 10 phiên giảm sâu xuống dưới đáy 60p, nến đỏ mở gap −2 %, nến xanh lấp gap."""
    rows = st["bars"][sym]
    low60 = min(r[3] for r in rows[-72:-12])
    c = low60 * 1.25
    for j in range(10):
        o, c = c, c * 0.95
        rows[-12 + j] = [rows[-12 + j][0], o, o * 1.005, c * 0.995, c, 100000]
    a = c
    rows[-2] = [rows[-2][0], a * 0.98, a * 0.985, a * 0.955, a * 0.96, 150000]
    rows[-1] = [rows[-1][0], a * 0.96, a * 0.995, a * 0.955, a * 0.99, 150000]


def test_event_today_triggers_alert_in_events_mode():
    st, days = _store()
    _plant_gap_fill(st, "AAA", days)
    items = [{"symbol": s} for s in ("AAA", "BBB")]
    cfg = dict(settings.DEFAULTS, events_enabled=["gap_fill_demand"], events_push=["gap_fill_demand"])
    fc, _, info = forecast.forecast_all(st, items, days[-1], cfg, conformal.new_state(forecast.HS), n_sim=100)
    a, b = fc
    assert [e["code"] for e in a["events"]] == ["gap_fill_demand"] and a["events"][0]["age"] == 0
    assert a["alert"] and a["alert_events"] == ["gap_fill_demand"]
    assert a["events"][0]["path"] == [round(a["price"], 2)]
    assert b["events"] == [] and not b["alert"]
    assert info["events_meta"]["alert_mode"] == "events" and info["events_meta"]["push"] == ["gap_fill_demand"]
    # sự kiện bật nhưng không nằm trong events_push → hiện, không réo
    cfg2 = dict(cfg, events_push=[])
    fc2, _, _ = forecast.forecast_all(st, items, days[-1], cfg2, conformal.new_state(forecast.HS), n_sim=100)
    assert fc2[0]["events"] and not fc2[0]["alert"]


def test_p10_mode_keeps_old_rule():
    st, days = _store()
    _plant_gap_fill(st, "AAA", days)
    items = [{"symbol": "AAA"}]
    cfg = dict(settings.DEFAULTS, alert_mode="p10", p_min=0.0, n_min=0, events_enabled=["gap_fill_demand"])
    fc, _, _ = forecast.forecast_all(st, items, days[-1], cfg, conformal.new_state(forecast.HS), n_sim=100)
    assert fc[0]["alert"] is True                         # p10 ≥ 0 luôn đúng → luật cũ
    cfg["p_min"] = 1.01
    fc, _, _ = forecast.forecast_all(st, items, days[-1], cfg, conformal.new_state(forecast.HS), n_sim=100)
    assert fc[0]["alert"] is False and fc[0]["events"]    # có sự kiện nhưng chế độ p10 không réo theo sự kiện


def test_event_payload_fields():
    from job import push
    it = {"symbol": "AAA", "price": 12.34}
    ev = {"code": "gap_fill_demand", "name": "Gap giảm được lấp tại đáy", "p_touch": 0.47,
          "q": {"10": {"10": 11.0, "90": 14.2}}, "stats": {"ex10": 0.0417, "years_win": 5, "years": 7}}
    p = push.event_payload(it, ev, "2026-09-24")
    assert p["tag"] == "pp-ev-AAA" and p["hot"] and "24/09" in p["title"] and "Gap giảm" in p["title"]
    assert "+4,2 %" in p["body"] and "5/7" in p["body"] and "47 %" in p["body"] and "11.0 – 14.2" in p["body"]


def test_event_log_lists_recent_events():
    st, days = _store()
    _plant_gap_fill(st, "AAA", days)
    cfg = dict(settings.DEFAULTS, events_enabled=["gap_fill_demand"])
    _, _, info = forecast.forecast_all(st, [{"symbol": "AAA", "company_name": "A"}], days[-1], cfg,
                                       conformal.new_state(forecast.HS), n_sim=50)
    log = info["event_log"]
    assert log and log[0]["symbol"] == "AAA" and log[0]["age"] == 0 and log[0]["ret10"] is None
    assert log[0]["date"] == days[-1].isoformat() and log[0]["ret_now"] == 0
