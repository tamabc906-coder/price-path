from job import smc


def bar(d, o, h, l, c, v=1000):
    return [f"2026-01-{d:02d}" if d <= 31 else f"2026-02-{d - 31:02d}", o, h, l, c, v]


def flat(n, p=10.0):
    """n phiên dao động nhẹ quanh p: nến xen kẽ xanh/đỏ, biên 0,2."""
    rows = []
    for i in range(n):
        o, c = (p - 0.05, p + 0.05) if i % 2 else (p + 0.05, p - 0.05)
        rows.append([f"d{i:03d}", o, p + 0.1, p - 0.1, c, 1000])
    return rows


def test_fractal_known_only_after_two_bars():
    h = [1, 2, 5, 3, 2, 1, 1]
    l = [0, 1, 4, 2, 1, 0, 0]
    c = [0.5, 1.5, 4.5, 2.5, 1.5, 0.5, 0.5]
    sh, _ = smc.structure_levels(h, l, c)
    assert sh[3] is None and sh[4] == 5          # đỉnh ở phiên 2 chỉ biết từ phiên 4


def test_bos_then_choch_direction():
    h = [5, 5, 5, 6, 5, 4, 4, 4.5, 7, 6, 6, 5, 3, 2]
    l = [4, 4, 4, 5, 4, 3, 2, 3.5, 6, 5, 5, 4, 2, 1]
    c = [4.5, 4.5, 4.5, 5.5, 4.5, 3.5, 3, 4, 6.5, 5.5, 5.5, 4.5, 2.5, 1.5]
    _, breaks = smc.structure_events(h, l, c)
    labs = [(b["lab"], b["up"]) for b in breaks]
    assert labs[0] == ("BOS", True)              # lần phá đầu tiên luôn là BOS
    assert ("CHoCH", False) in labs              # sau nhịp tăng, phá đáy = đổi chiều


def test_fvg_filled_on_right_bar():
    h = [10, 10, 10, 12, 13, 13, 13, 13]
    l = [9, 9, 9, 9.8, 11, 11, 10.9, 9.5]
    a = [1.0] * len(h)
    f = [x for x in smc.fvg_events(h, l, a) if x["up"]]
    assert f[0]["lo"] == 10 and f[0]["hi"] == 11 and f[0]["i"] == 3
    assert f[0]["end"] == 7                      # phiên 7 lấp kín (Low ≤ đáy FVG)


def test_bull_ob_zone_is_last_red_candle():
    rows = flat(30)
    rows += [["x0", 10.0, 10.6, 9.9, 10.5, 1000],     # đỉnh swing 10,6
             ["x1", 10.5, 10.5, 10.0, 10.1, 1000],
             ["x2", 10.1, 10.2, 9.8, 9.9, 1000],
             ["x3", 9.9, 10.0, 9.6, 9.7, 1000],       # nến đỏ cuối
             ["x4", 9.7, 10.4, 9.7, 10.3, 1000],      # xanh
             ["x5", 10.3, 11.2, 10.3, 11.1, 1000],    # phá đỉnh 10,6, nhịp ≥ 1,5 ATR
             ["x6", 11.1, 11.5, 11.0, 11.4, 1000]]
    rows += [[f"y{i}", 11.4, 11.6, 11.2, 11.5, 1000] for i in range(5)]
    an = smc.analyze(rows)
    bulls = [o for o in an["obs"] if o["bull"]]
    assert bulls, "phải có OB tăng"
    ob = bulls[-1]
    assert rows[ob["k"]][0] == "x3" and ob["lo"] == 9.6 and ob["hi"] == 10.0


def test_scan_shape_and_zones():
    rows = flat(80)
    out = smc.scan({"bars": {"AAA": rows}}, [{"symbol": "AAA", "company_name": "A"}], "2026-10-06")
    s = out["symbols"][0]
    assert s["symbol"] == "AAA" and len(s["chart"]["ohlc"]) == 80
    assert isinstance(s["zones"], list)
