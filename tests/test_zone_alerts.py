from zone import alerts, run_daily

CFG = {"windows": [3], "max_bins": 60, "va_pct": 0.70, "zone_vol_mult": 1.2, "buy_share_min": 0.58,
       "sell_share_max": 0.42, "big_lot_value_vnd": 500_000_000, "top_n": 5, "whale_gap": 0.3, "alert_digest": 6}
DAYS = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]


def s(levels, est=False):
    # close 0 → adjust_factor = 1: test không phụ thuộc hệ số điều chỉnh
    return {"est": est, "close": 0, "levels": levels}


BASE = {"10.0": [100, 100, 0, 0, 0], "10.1": [300, 300, 0, 0, 0], "10.2": [100, 100, 0, 0, 0]}


def store_with(today_levels, today_close, prev_close=10.1, est=False, base=BASE):
    st = {"sessions": {d: s(dict(base)) for d in DAYS[:3]}}
    st["sessions"][DAYS[3]] = s(today_levels, est)
    closes = {DAYS[0]: 10.1, DAYS[1]: 10.1, DAYS[2]: prev_close, DAYS[3]: today_close}
    return st, closes


def test_break_up_with_whale_buying():
    st, closes = store_with({"10.5": [100000, 0, 0, 100000, 0]}, 10.5)
    a = alerts.evaluate("AAA", st, closes, DAYS[3], CFG)
    assert a["breaks"] == [{"w": 3, "dir": "up", "level": a["breaks"][0]["level"]}]
    assert 10.1 <= a["breaks"][0]["level"] < 10.5 and a["big_net_val"] > 0 and a["whale"] == []


def test_break_down_with_whale_selling():
    st, closes = store_with({"9.6": [0, 100000, 0, 0, 100000]}, 9.6)
    a = alerts.evaluate("AAA", st, closes, DAYS[3], CFG)
    assert [b["dir"] for b in a["breaks"]] == ["down"] and a["big_net_val"] < 0


def test_no_alert_when_already_outside_opposite_whale_or_estimated():
    st, closes = store_with({"10.5": [100000, 0, 0, 100000, 0]}, 10.5, prev_close=10.45)   # hôm qua đã trên VAH
    assert alerts.evaluate("AAA", st, closes, DAYS[3], CFG) is None
    st, closes = store_with({"10.5": [100000, 0, 0, 0, 100000]}, 10.5)                     # cá mập bán ròng
    assert alerts.evaluate("AAA", st, closes, DAYS[3], CFG) is None
    st, closes = store_with({"10.5": [100000, 0, 0, 0, 0]}, 10.5, est=True)                # phiên ước lượng
    assert alerts.evaluate("AAA", st, closes, DAYS[3], CFG) is None


def test_whale_same_price_only_when_new():
    far = dict(BASE, **{"10.0": [100, 100, 0, 500, 0], "10.6": [0, 0, 1, 0, 400]})         # mua lớn 10.0, bán lớn 10.6
    st, closes = store_with({"10.1": [0, 5000, 0, 0, 5000]}, 10.1, base=far)                # bán lớn dồn về 10.1
    a = alerts.evaluate("AAA", st, closes, DAYS[3], CFG)
    assert a["breaks"] == [] and a["whale"] == [{"w": 3, "buy_p": 10.0, "sell_p": 10.1}]
    near = dict(BASE, **{"10.0": [100, 100, 0, 500, 0], "10.2": [100, 100, 0, 0, 400]})    # hôm qua đã ≤ 0,3
    st, closes = store_with({"10.1": [0, 5000, 0, 0, 5000]}, 10.1, base=near)
    assert alerts.evaluate("AAA", st, closes, DAYS[3], CFG) is None


def test_payloads_single_and_digest():
    up = {"symbol": "TCB", "day": "2026-09-25", "close": 33.25, "big_net_val": 106.6,
          "breaks": [{"w": 10, "dir": "up", "level": 33.15}, {"w": 20, "dir": "up", "level": 33.1}], "whale": []}
    wh = {"symbol": "DXG", "day": "2026-09-25", "close": 10.1, "big_net_val": 1.0, "breaks": [],
          "whale": [{"w": 10, "buy_p": 10.2, "sell_p": 10.2}]}
    p = alerts.symbol_payload(up)
    assert p["title"] == "▲ TCB · phá VAH 10p, 20p · phiên 25/09" and "+106,6 tỷ" in p["body"] and p["url"] == "./#zone"
    assert alerts.symbol_payload(wh)["title"].startswith("⇄ DXG · cá mập dồn giá 10,20 ·")
    assert len(alerts.payloads([up, wh], "2026-09-25", 6)) == 2
    d = alerts.payloads([up] * 4 + [wh] * 3, "2026-09-25", 6)
    assert len(d) == 1 and d[0]["title"] == "7 mã vùng giá · phiên 25/09" and "Cá mập dồn giá: DXG" in d[0]["body"]


def test_handle_alerts_never_resends_same_symbol_same_session(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "ALERTS", tmp_path / "alerts.json")
    found = [{"symbol": "TCB", "day": "2026-09-25", "close": 33.25, "big_net_val": 1.0,
              "breaks": [{"w": 10, "dir": "up", "level": 33.1}], "whale": []}]
    monkeypatch.setattr(run_daily.alerts, "evaluate_all", lambda *a, **k: list(found))
    monkeypatch.setattr(run_daily, "closes_of", lambda h, s: {})
    r1 = run_daily.handle_alerts(["TCB"], {}, "2026-09-25", CFG, send=False)
    r2 = run_daily.handle_alerts(["TCB"], {}, "2026-09-25", CFG, send=False)
    assert r1["n_symbols"] == 1 and r2["n_symbols"] == 0 and r2["skipped_already"] == 1
    found.append(dict(found[0], symbol="VPB"))            # mã gom trễ ở lượt sau vẫn được báo
    assert run_daily.handle_alerts(["TCB", "VPB"], {}, "2026-09-25", CFG, send=False)["n_symbols"] == 1
