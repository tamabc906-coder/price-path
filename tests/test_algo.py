from zone import algo


def tk(sec, price, vol, side):
    return {"time": f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}", "price": price, "vol": vol, "side": side, "acc": 0}


def noise(n=120, start=9 * 3600 + 20 * 60):
    """Lệnh nhỏ lẻ xen kẽ, cỡ lệnh khác nhau để không tự tạo chuỗi."""
    return [tk(start + 37 * i, 20.0, 100 + 100 * (i % 7), "PS" if i % 3 else "PB") for i in range(n)]


def test_events_merge_same_second_and_passive_naming():
    ev, atc = algo.events([tk(36000, 20.0, 300, "PB"), tk(36000, 19.95, 200, "PB"), tk(36000, 20.0, 100, "PS"),
                           tk(53100, 20.1, 900, "ATC")])
    assert ev == [[36000, "S", 500, 19.95], [36000, "B", 100, 20.0]]
    assert atc == 20.1


def test_regular_twap_chain_found():
    ticks = sorted(noise() + [tk(10 * 3600 + 100 * i, 20.0, 1800, "PS") for i in range(12)], key=lambda t: t["time"])
    rec = algo.symbol_day(ticks)
    assert [(c["side"], c["size"], len(c["t"])) for c in rec["chains"]] == [("B", 1800, 12)]
    assert rec["chains"][0]["cv"] == 0


def test_irregular_chain_rejected():
    gaps = [10, 170, 15, 160, 20, 150, 12, 175, 30, 140, 11]
    ts, t = [], 10 * 3600
    for g in gaps:
        ts.append(t)
        t += g
    ticks = sorted(noise() + [tk(x, 20.0, 1800, "PS") for x in ts], key=lambda t: t["time"])
    assert algo.symbol_day(ticks)["chains"] == []


def test_too_few_events_returns_none():
    assert algo.symbol_day(noise(50)) is None


def rec(big):
    return {"n": 200, "open": 10, "close": 10, "vwap": 10, "val": 100.0, "whale": [0, 0], "chains": [],
            "fake": 0, "big": big, "c5": []}


def test_basket_needs_five_symbols_and_skips_open():
    t = 10 * 3600
    doc = {s: rec([[t, "B", 150, 0], [13 * 3600, "B", 150, 0]]) for s in "ABCD"}
    assert algo.basket_keys(doc) == {}
    doc["E"] = rec([[t, "B", 150, 0], [13 * 3600, "B", 150, 0]])
    keys = algo.basket_keys(doc)
    assert list(keys) == [(t, "B")]          # 13:00:00 bị bỏ


def test_combined_whale_subtracts_basket_part():
    t = 10 * 3600
    doc = {s: rec([[t, "S", 600, 1]]) for s in "ABCDE"}
    doc["A"]["whale"] = [0, 0.6]
    v = algo.day_view("2026-10-02", doc, None, {})
    a = next(s for s in v["stocks"] if s["sym"] == "A")
    assert a["whale"] == -0.6 and a["bk"] == -0.6 and a["comb"] == 0
    assert v["test"]["bk_real"] == 1
