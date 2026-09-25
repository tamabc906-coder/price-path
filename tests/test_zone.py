from datetime import datetime

from common import vndirect
from common.config import TZ
from zone import backfill, collect, profile, store


def tick(time, price, vol, side, acc):
    return {"date": "2026-09-18", "time": time, "price": price, "vol": vol, "side": side, "acc": acc}


# ---- common/vndirect -------------------------------------------------------------------------------

def test_parse_rows_skips_bad_and_keeps_acc():
    rows = [
        {"tradingDate": "2026-09-18", "time": "09:25:39", "last": 74.1, "lastVol": 600.0, "side": "PB", "accumulatedVol": 476200.0},
        {"tradingDate": "2026-09-18", "time": "09:25:40", "last": "x", "lastVol": 600.0, "side": "PB", "accumulatedVol": 1},
        {"tradingDate": "2026-09-18", "time": "09:25:41", "last": 74.1, "lastVol": 0, "side": "PB", "accumulatedVol": 2},
    ]
    out = vndirect.parse_rows(rows)
    assert len(out) == 1
    assert out[0]["vol"] == 600 and out[0]["acc"] == 476200 and out[0]["side"] == "PB"


def test_shortfall_zero_when_sum_equals_last_accumulated():
    ok = [tick("09:15:00", 74, 100, "ATO", 100), tick("09:16:00", 74.1, 50, "PS", 150)]
    assert vndirect.shortfall(ok) == 0
    assert vndirect.shortfall(ok[1:]) is None  # thiếu tick đầu → hụt 100/150 = 67 %, quá xa
    assert vndirect.shortfall([]) is None


def test_shortfall_accepts_one_tiny_missing_tick():
    # Đúng ca TCB phiên 23/09/2026: nguồn bỏ một tick 500 cp giữa phiên, hụt 0,0013 %.
    ticks = [tick("09:15:00", 32.0, 6188700, "ATO", 6188700),
             tick("09:50:47", 32.9, 43800, "PS", 6233000),          # 6.188.700 + 43.800 = 6.232.500 ≠ acc
             tick("14:45:00", 33.35, 32774100, "ATC", 39007100)]
    assert vndirect.shortfall(ticks) == 500
    assert vndirect.gap_points(ticks) == 1


def test_shortfall_rejects_scattered_gaps_and_overcount():
    # Bệnh phân trang 20/09/2026: hụt nhỏ nhưng rải nhiều chỗ → vẫn phải từ chối.
    scattered = [tick("09:1%d:00" % (i % 10), 32.0, 1_000_000, "PS", (i + 1) * 1_000_000 + i) for i in range(10)]
    assert vndirect.gap_points(scattered) > vndirect.MAX_GAP_POINTS
    assert vndirect.shortfall(scattered) is None
    # Σ KL VƯỢT luỹ kế (trùng tick/dữ liệu hỏng) là bệnh khác — không bao giờ nhận.
    over = [tick("09:15:00", 74, 100, "ATO", 100), tick("09:16:00", 74.1, 500, "PS", 150)]
    assert vndirect.shortfall(over) is None


# ---- zone/collect ----------------------------------------------------------------------------------

def test_side_mapping_is_passive_naming():
    # VNDirect PB = bên mua bị động = BÁN chủ động; PS = MUA chủ động (đối chiếu Vietcap 100 %).
    assert collect.SIDE_INDEX["PB"] == collect.SELL
    assert collect.SIDE_INDEX["PS"] == collect.BUY


def test_orders_merges_consecutive_fills_of_one_order():
    # 14:29:42 73.9 5000 B trên app CTCK = 7 tick PB liên tiếp trên VNDirect.
    fills = [500, 100, 100, 500, 700, 2000, 1100]
    ticks = [tick("14:29:42", 73.9, v, "PB", i) for i, v in enumerate(fills)]
    ticks.append(tick("14:29:45", 74.0, 3000, "PS", 99))
    o = collect.orders(ticks)
    assert [x["vol"] for x in o] == [5000, 3000]


def test_aggregate_levels_sides_and_big_lots():
    ticks = [
        tick("09:15:00", 74.5, 62300, "ATO", 62300),
        tick("10:00:00", 74.2, 8000, "PS", 70300),      # mua 8.000 × 74,2 = 593 tr → lệnh lớn
        tick("10:00:00", 74.2, 100, "PB", 70400),
        tick("10:00:01", 74.2, 100, "PB", 70500),
        tick("14:45:00", 71.7, 8520100, "ATC", 8590600),
    ]
    s = collect.aggregate(ticks, big_value_vnd=500_000_000)
    assert s["total"] == 8590600 and s["close"] == 71.7 and s["ticks"] == 5 and s["est"] is False
    assert s["levels"]["74.2"] == [8000, 200, 0, 8000, 0]
    assert s["levels"]["74.5"] == [0, 0, 62300, 0, 0]
    assert s["levels"]["71.7"] == [0, 0, 8520100, 0, 0]
    assert list(s["levels"]) == ["71.7", "74.2", "74.5"]


def test_aggregate_records_gap_only_when_source_missed_ticks():
    full = [tick("09:15:00", 74.5, 62300, "ATO", 62300), tick("10:00:00", 74.2, 100, "PB", 62400)]
    assert "gap" not in collect.aggregate(full)  # phiên đủ → không đẻ "gap":0 làm phình diff git
    holed = [tick("09:15:00", 74.5, 62300, "ATO", 62300), tick("10:00:00", 74.2, 100, "PB", 62900)]
    s = collect.aggregate(holed)
    assert s["gap"] == 500 and s["total"] == 62400


def test_check_volume_tolerance():
    s = {"total": 1000}
    assert collect.check_volume(s, None) == ""
    assert collect.check_volume(s, 1010) == ""
    assert "lệch" in collect.check_volume(s, 1500)


# ---- zone/store ------------------------------------------------------------------------------------

def test_store_real_beats_estimate_and_trims(tmp_path):
    st = store.load("ABC", tmp_path)
    est = {"src": "dnse1m", "est": True, "close": 1, "total": 1, "levels": {}}
    real = {"src": "vnd", "est": False, "close": 1, "total": 1, "levels": {}}
    assert store.put(st, "2026-09-18", est)
    assert store.put(st, "2026-09-18", real)          # thật ghi đè ước lượng
    assert not store.put(st, "2026-09-18", est)       # ước lượng không ghi đè thật
    assert not store.put(st, "2026-09-18", real)      # thật không ghi đè thật (idempotent)
    assert store.has_real(st, "2026-09-18")
    for i in range(1, store.MAX_SESSIONS + 10):
        store.put(st, f"2020-01-{i:02d}" if i < 30 else f"2021-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", est)
    store.save(st, tmp_path)
    again = store.load("ABC", tmp_path)
    assert len(again["sessions"]) == store.MAX_SESSIONS
    assert "2026-09-18" in again["sessions"]          # giữ phiên mới nhất, cắt phiên cũ
    assert [d for d, _ in store.recent(again, 2)][-1] == "2026-09-18"


# ---- zone/backfill ---------------------------------------------------------------------------------

def bar(hh, mm, o, h, l, c, v):
    return {"d": datetime(2026, 9, 18, tzinfo=TZ).date(), "o": o, "h": h, "l": l, "c": c, "v": v,
            "t": int(datetime(2026, 9, 18, hh, mm, tzinfo=TZ).timestamp())}


def test_estimate_session_direction_and_volume_split():
    bars = [
        bar(9, 15, 74.0, 74.0, 74.0, 74.0, 1000),     # ATO → x
        bar(9, 16, 74.0, 74.2, 74.0, 74.2, 300),      # tăng → mua, chia 3 mức 74.0/74.1/74.2
        bar(9, 17, 74.2, 74.2, 74.2, 74.2, 100),      # bằng, so close trước cũng bằng → theo nến trước (mua)
        bar(9, 18, 74.2, 74.2, 74.0, 74.0, 200),      # giảm → bán
        bar(14, 45, 73.9, 73.9, 73.9, 73.9, 5000),    # ATC → x
    ]
    s = backfill.estimate_session(bars, "HOSE")
    assert s["est"] is True and s["src"] == "dnse1m" and s["close"] == 73.9
    assert s["total"] == 6600 == sum(sum(v[:3]) for v in s["levels"].values())
    assert s["levels"]["74"] == [100, 68, 1000, 0, 0]     # 200 bán / 3 mức, dư 2 dồn vào mức đóng cửa 74.0
    assert s["levels"]["74.1"] == [100, 66, 0, 0, 0]
    assert s["levels"]["74.2"] == [200, 66, 0, 0, 0]
    assert s["levels"]["73.9"] == [0, 0, 5000, 0, 0]


def test_tick_size_bands():
    assert backfill.tick_size(9.99) == 0.01 and backfill.tick_size(10) == 0.05
    assert backfill.tick_size(49.95) == 0.05 and backfill.tick_size(50) == 0.1
    assert backfill.tick_size(5, "HNX") == 0.1


# ---- zone/profile ----------------------------------------------------------------------------------

def sess(levels, close, est=False):
    return {"src": "dnse1m" if est else "vnd", "est": est, "close": close, "total": 0, "levels": levels}


def test_adjust_factor_noise_and_event():
    assert profile.adjust_factor(sess({}, 71.7), 71.7) == 1.0
    assert profile.adjust_factor(sess({}, 71.7), 71.9) == 1.0          # 0,28 % → làm tròn, coi như 1
    f = profile.adjust_factor(sess({}, 71.7), 65.18)                  # chia 10 % cổ phiếu
    assert abs(f - 0.909) < 0.001
    assert profile.adjust_factor(sess({}, 71.7), None) == 1.0


def test_build_adjusts_prices_finds_poc_va_and_zones():
    # Phiên thô ở 74.x với hệ số 0,909 phải về ~67.x; phiên đã điều chỉnh ở 67.x nằm cùng ô.
    raw = sess({"74.2": [100000, 20000, 0, 60000, 0], "74.5": [0, 0, 50000, 0, 0]}, 74.2)
    adj = sess({"67.45": [10000, 90000, 0, 0, 0], "66.0": [1000, 1000, 0, 0, 0]}, 67.45, est=True)
    p = profile.build([("2026-09-17", adj, 1.0), ("2026-09-18", raw, 65.18 / 71.7)], {"max_bins": 60})
    assert p["n"] == 2 and p["n_real"] == 1
    assert p["bin"] == 0.1
    poc_lo = p["bins"][p["poc"]][0]
    assert 67.3 <= poc_lo <= 67.5                       # 74.2×0,909 = 67.45 và 67.45 gộp chung một ô
    assert p["total"] == 100000 + 20000 + 50000 + 100000 + 2000
    assert p["x"] == 50000
    lo, hi = p["va"]
    assert lo <= p["poc"] <= hi
    # Ô 67.4–67.5: mua 110.000 / bán 110.000 → 0,5 → không phải vùng; hạ ngưỡng để thấy vùng mua
    p2 = profile.build([("2026-09-18", raw, 65.18 / 71.7)], {"buy_share_min": 0.58})
    assert len(p2["buy_zones"]) == 1 and p2["sell_zones"] == []
    z = p2["buy_zones"][0]
    assert z["lo"] <= 67.45 < z["hi"] and z["share"] == round(100000 / 120000, 3)
    assert z["sessions"] == 1 and z["last"] == "2026-09-18" and z["est_share"] == 0.0
    assert p2["big_buy_zones"] and p2["big_buy_zones"][0]["vol"] == 60000


def test_build_marks_estimated_share_and_distance():
    # Thêm một mức giá xa để profile có nhiều ô (một ô duy nhất thì không bao giờ vượt trung bình × 1,2).
    est = sess({"20": [50000, 10000, 0, 0, 0], "19": [100, 100, 0, 0, 0]}, 20, est=True)
    real = sess({"20": [50000, 10000, 0, 0, 0]}, 20)
    p = profile.build([("2026-09-17", est, 1.0), ("2026-09-18", real, 1.0)])
    z = p["buy_zones"][0]
    assert z["est_share"] == 0.5 and z["sessions"] == 2
    profile.with_distance(p, 19.0)
    assert p["buy_zones"][0]["dist"] > 0


def test_value_area_expands_toward_bigger_neighbor():
    totals = [1, 5, 50, 10, 30, 2]
    lo, hi = profile.value_area(totals, 2, 0.7)
    assert (lo, hi) == (2, 4)          # 50 + 10 + 30 = 90 ≥ 68,6


def test_bin_width_respects_max_bins():
    assert profile.bin_width(20.0, 21.0, 60) == 0.05
    assert profile.bin_width(60.0, 80.0, 60) == 0.4     # 200 bước / 60 → bội 4 của 0,1


# ---- thống kê mua/bán chủ động theo phiên ------------------------------------------------------------

def _sess(levels, est=False):
    return {"est": est, "close": 65.0, "total": 0, "levels": levels}


def test_session_stats_sums_sides_and_big_value_in_billion():
    s = _sess({"64.7": [79300, 157800, 180300, 22100, 78000], "65": [166000, 682900, 0, 50000, 521200]})
    r = profile.session_stats("2026-09-25", s)
    assert (r["buy"], r["sell"], r["x"]) == (245300, 840700, 180300)
    assert r["total"] == 245300 + 840700 + 180300
    assert r["net"] == 245300 - 840700
    assert abs(r["buy_share"] - 245300 / (245300 + 840700)) < 1e-4
    # 22.100 cp × 64,7 + 50.000 × 65 = 4.679,87 triệu đ nghìn → 4,68 tỷ
    assert r["big_buy_val"] == round((22100 * 64.7 + 50000 * 65) / 1e6, 2)
    assert r["big_net_val"] == round((22100 * 64.7 + 50000 * 65 - 78000 * 64.7 - 521200 * 65) / 1e6, 2)


def test_session_stats_estimated_has_no_big_lots():
    r = profile.session_stats("2026-08-01", _sess({"65": [1000, 500, 0, 0, 0]}, est=True))
    assert r["est"] is True and r["big_buy_val"] is None and r["big_net_val"] is None
    assert r["buy_share"] == round(1000 / 1500, 4)


def test_sum_stats_counts_big_lots_only_on_real_sessions():
    rows = [profile.session_stats("d1", _sess({"10": [100, 300, 0, 0, 0]}, est=True)),
            profile.session_stats("d2", _sess({"10": [500, 100, 50, 200, 0]}))]
    t = profile.sum_stats(rows)
    assert (t["n"], t["n_real"], t["buy"], t["sell"], t["net"]) == (2, 1, 600, 400, 200)
    assert t["big_net_val"] == round(200 * 10 / 1e6, 2)
    assert profile.sum_stats([rows[0]])["big_net_val"] is None


def test_build_symbol_daily_and_market_row():
    from zone import run_daily
    st = {"sessions": {
        "2026-09-23": _sess({"65": [100, 300, 10, 0, 0]}),
        "2026-09-24": _sess({"65": [400, 100, 10, 0, 0]}),
        "2026-09-25": _sess({"65": [200, 800, 10, 0, 100]}),
    }}
    cfg = dict(profile.DEFAULT_SETTINGS, windows=[2, 3])
    out = run_daily.build_symbol(st, {"2026-09-25": 65.0}, cfg)
    assert [r["d"] for r in out["daily"]] == ["2026-09-23", "2026-09-24", "2026-09-25"]   # cũ → mới
    assert out["profiles"]["2"]["flow"]["net"] == (400 - 100) + (200 - 800)
    m = run_daily.market_row(out["daily"])
    assert m["d"] == "2026-09-25" and m["net"] == -600 and m["net_pct"] == -0.6
    assert m["big_net_val"] == round(-100 * 65 / 1e6, 2)
    assert m["w5"]["n"] == 3 and m["w5"]["net"] == (100 - 300) + (400 - 100) + (200 - 800)
    assert run_daily.market_row([]) is None


def test_session_stats_flags_source_without_side():
    r = profile.session_stats("2026-09-25", _sess({"35.25": [0, 0, 18200, 0, 0]}))
    assert r["no_side"] is True and r["buy_share"] is None and r["big_net_val"] is None
    assert profile.session_stats("d", _sess({"10": [1, 0, 5, 0, 0]}))["no_side"] is False


def test_top_levels_rank_exact_prices_after_adjustment():
    # Phiên thô 74.2 × 0,909 = 67.45 → làm tròn bước 0,1 về 67.5, gộp chung với phiên đã điều chỉnh ở 67.5.
    raw = sess({"74.2": [100000, 20000, 0, 60000, 0], "75.0": [5000, 80000, 0, 0, 30000]}, 74.2)
    est = sess({"67.5": [10000, 10000, 0, 0, 0], "66.0": [40000, 1000, 0, 0, 0]}, 67.5, est=True)
    p = profile.build([("2026-09-17", est, 1.0), ("2026-09-18", raw, 65.18 / 71.7)], {"top_n": 2})
    t = p["top"]
    assert [r["p"] for r in t["buy"]] == [67.5, 66.0]
    top = t["buy"][0]
    assert top["vol"] == 110000 and top["sessions"] == 2 and top["last"] == "2026-09-18"
    assert top["pct"] == round(110000 / 155000, 4)
    assert top["share"] == round(110000 / 140000, 3)
    assert top["est_share"] == round(20000 / 140000, 3)
    assert t["sell"][0]["p"] == 68.2                                  # 75.0 × 0,909 = 68.18 → 68.2
    assert t["sell"][0]["vol"] == 80000
    assert len(t["buy"]) == 2                                        # top_n
    # Lệnh lớn: chỉ phiên tick thật, est_share 0
    assert [r["vol"] for r in t["big_buy"]] == [60000] and t["big_buy"][0]["est_share"] == 0.0
    assert [r["vol"] for r in t["big_sell"]] == [30000]
    profile.with_distance(p, 67.5)
    assert t["buy"][0]["dist"] == 0.0 and t["buy"][1]["dist"] < 0


def test_top_levels_empty_when_source_has_no_side():
    s = sess({"50": [0, 0, 1000, 0, 0]}, 50)
    p = profile.build([("2026-09-18", s, 1.0)])
    assert p["top"] == {"buy": [], "sell": [], "big_buy": [], "big_sell": []}
