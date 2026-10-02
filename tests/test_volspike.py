from job import push, volspike

CFG = {"spike_vol_mult": 2.0, "spike_min_pct": 0.03}


def rows_with(last, n=25, vol=1000, close=10.0):
    """n phiên phẳng (o=c=close, KL vol) + nến cuối `last` = (o, c, v)."""
    rows = [[f"2026-08-{i + 1:02d}", close, close, close, close, vol] for i in range(n)]
    o, c, v = last
    rows.append(["2026-10-02", o, max(o, c), min(o, c), c, v])
    return rows


def scan(rows):
    return volspike.scan({"bars": {"AAA": rows}}, [{"symbol": "AAA", "company_name": "A"}], "2026-10-02", CFG)


def test_hit_exact_thresholds():
    out = scan(rows_with((10.0, 10.3, 2000)))
    assert [h["symbol"] for h in out["today"]] == ["AAA"]
    h = out["today"][0]
    assert h["ratio"] == 2.0 and abs(h["pct"] - 0.03) < 1e-9 and h["avg20"] == 1000 and len(h["bars"]) == 26 and h["bars"][-1][0] == "2026-10-02"


def test_red_candle_not_hit():
    assert scan(rows_with((10.5, 10.4, 3000)))["today"] == []


def test_rise_below_3pct_not_hit():
    assert scan(rows_with((10.0, 10.29, 3000)))["today"] == []


def test_volume_below_2x_not_hit():
    assert scan(rows_with((10.0, 10.5, 1999)))["today"] == []


def test_needs_20_prior_sessions():
    assert scan(rows_with((10.0, 10.5, 5000), n=19))["today"] == []
    assert len(scan(rows_with((10.0, 10.5, 5000), n=20))["today"]) == 1


def test_avg_excludes_today():
    # TB20 gồm cả hôm nay sẽ là (19·1000 + 2000)/20 = 1050 → 2000 < 2,1k; luật đúng dùng 20 phiên TRƯỚC = 1000
    assert len(scan(rows_with((10.0, 10.5, 2000)))["today"]) == 1


def test_stale_symbol_not_today():
    rows = rows_with((10.0, 10.5, 5000))
    rows[-1][0] = "2026-10-01"           # mã không có nến hôm nay
    out = scan(rows)
    assert out["today"] == [] and len(out["log"]) == 1


def test_forward_returns_in_log():
    rows = rows_with((10.0, 10.5, 5000))
    rows[-1][0] = "2026-09-01"
    rows += [[f"2026-09-{i + 2:02d}", 11, 11, 11, 11, 1000] for i in range(10)]
    h = scan(rows)["log"][0]
    assert abs(h["r5"] - (11 / 10.5 - 1)) < 1e-3 and h["r10"] is not None


def test_payloads():
    h = scan(rows_with((10.0, 10.42, 2600)))["today"][0]
    p = push.spike_payload(h, "2026-10-02")
    assert p["title"] == "🔥 AAA · KL 2,6× TB20 · +4,2 % · phiên 02/10" and p["url"] == "./#spike"
    d = push.spike_digest_payload([h] * 7, "2026-10-02")
    assert d["title"].startswith("🔥 7 mã KL đột biến") and "AAA +4,2 % 2,6×" in d["body"]
