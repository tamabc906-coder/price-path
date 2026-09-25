"""Chỉ báo vùng giá: các phiên đã gộp theo mức giá → profile KL theo ô giá, POC, Value Area, vùng mua/bán nhiều.
Thuần hàm, không I/O — job đưa dữ liệu vào, test đưa số liệu tổng hợp vào.

Thuật toán
1. Hệ số điều chỉnh mỗi phiên = close kho nến DNSE (đã điều chỉnh, data/history.json) / close lưu trong phiên.
   Tick VNDirect là giá thô nên sau ngày GDKHQ mọi mức giá cũ phải nhân hệ số (FPT 18/09: 71.7 → 65.18, ×0,909);
   không thì vùng 2 tháng nằm lệch hẳn giá hiện tại. Lệch < 0,5 % coi như 1 (sai số làm tròn 2 chữ số).
2. Gộp mức giá thành ≤ MAX_BINS ô đều nhau (bước = bội của bước giá): mã 10 đ/bước sau 2 tháng có > 300 mức, và
   sau khi nhân hệ số giá không còn nằm trên lưới bước giá.
3. POC = ô có tổng KL lớn nhất; Value Area = mở rộng từ POC về phía ô kề lớn hơn tới khi ≥ 70 % tổng KL.
4. Vùng mua nhiều = các ô LIỀN KỀ có tổng ≥ zone_vol_mult × KL trung bình ô VÀ tỷ lệ mua = mua/(mua+bán) ≥
   buy_share_min; vùng bán nhiều đối xứng với sell_share_max. x (ATO/ATC) tính vào tổng/POC, KHÔNG vào tỷ lệ.
5. Vùng cá mập: như (4) nhưng trên cột mua_lớn/bán_lớn, trung bình tính riêng trên KL lệnh lớn.
Mỗi ô/vùng nhớ phần KL đến từ phiên ước lượng (est) để giao diện tô nhạt và nói thật.
"""
from __future__ import annotations

from .collect import BIG_BUY, BIG_SELL, BUY, OTHER, SELL

DEFAULT_SETTINGS = {
    "windows": [10, 20, 40],
    "max_bins": 60,
    "va_pct": 0.70,
    "zone_vol_mult": 1.2,
    "buy_share_min": 0.58,
    "sell_share_max": 0.42,
    "big_lot_value_vnd": 500_000_000,
    "top_n": 5,
}
# Hệ số điều chỉnh lệch dưới mức này coi như 1 (DNSE làm tròn 2 chữ số; 0,5 % còn xa mức chia cổ tức nhỏ nhất ~2 %).
FACTOR_NOISE = 0.005
# Chỉ số cột trong mỗi ô: 5 cột như session + KL từ phiên ước lượng.
EST = 5


def adjust_factor(session: dict, hist_close: float | None) -> float:
    """Hệ số nhân vào mức giá của phiên để về thang giá điều chỉnh hiện hành. Không có nến kho → 1."""
    close = session.get("close") or 0
    if not hist_close or close <= 0:
        return 1.0
    f = hist_close / close
    return 1.0 if abs(f - 1) < FACTOR_NOISE else f


def tick_size(price: float) -> float:
    """Bước giá HOSE theo dải (nghìn đồng) — chỉ để chọn bề rộng ô 'đẹp'; HNX 100 đ thì ô rộng hơn cũng không sao."""
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    return 0.1


def bin_width(lo: float, hi: float, max_bins: int) -> float:
    """Bề rộng ô = bội nhỏ nhất của bước giá sao cho số ô ≤ max_bins."""
    step = tick_size(hi)
    span = max(hi - lo, step)
    k = max(1, int(-(-span // (step * max_bins))))  # ceil(span / (step*max_bins))
    return round(step * k, 4)


def build(sessions: list[tuple[str, dict, float]], settings: dict | None = None) -> dict | None:
    """sessions: (ngày, session, hệ số) CŨ → MỚI. Trả profile dict, None nếu không có KL."""
    cfg = dict(DEFAULT_SETTINGS, **(settings or {}))
    pts: list[tuple[float, list[int], bool, str]] = []
    for day, sess, f in sessions:
        est = bool(sess.get("est", False))
        for k, arr in sess.get("levels", {}).items():
            p = float(k) * f
            if p > 0 and sum(arr[:3]) > 0:
                pts.append((p, arr, est, day))
    if not pts:
        return None
    lo = min(p for p, *_ in pts)
    hi = max(p for p, *_ in pts)
    w = bin_width(lo, hi, int(cfg["max_bins"]))
    base = (lo // w) * w
    n = int((hi - base) // w) + 1
    bins = [[0, 0, 0, 0, 0, 0] for _ in range(n)]
    days_in: list[set[str]] = [set() for _ in range(n)]
    big_days_in: list[set[str]] = [set() for _ in range(n)]
    for p, arr, est, day in pts:
        i = min(n - 1, int((p - base) // w))
        b = bins[i]
        for c in range(5):
            b[c] += int(arr[c])
        if est:
            b[EST] += int(arr[BUY] + arr[SELL] + arr[OTHER])
        days_in[i].add(day)
        if arr[BIG_BUY] + arr[BIG_SELL] > 0:
            big_days_in[i].add(day)
    totals = [b[BUY] + b[SELL] + b[OTHER] for b in bins]
    grand = sum(totals)
    poc = max(range(n), key=lambda i: totals[i])
    va = value_area(totals, poc, float(cfg["va_pct"]))
    out = {
        "n": len(sessions),
        "n_real": sum(1 for _, s, _ in sessions if not s.get("est", False)),
        "from": sessions[0][0] if sessions else "",
        "to": sessions[-1][0] if sessions else "",
        "bin": w,
        "base": round(base, 4),
        "bins": [[round(base + i * w, 4)] + bins[i] for i in range(n)],
        "poc": poc,
        "va": list(va),
        "total": grand,
        "buy": sum(b[BUY] for b in bins),
        "sell": sum(b[SELL] for b in bins),
        "x": sum(b[OTHER] for b in bins),
        "buy_zones": [], "sell_zones": [], "big_buy_zones": [], "big_sell_zones": [],
    }
    mean = grand / n
    tag = [_tag(b[BUY], b[SELL], totals[i], mean, cfg) for i, b in enumerate(bins)]
    out["buy_zones"], out["sell_zones"] = _zones(tag, bins, days_in, base, w, BUY, SELL)
    big_totals = [b[BIG_BUY] + b[BIG_SELL] for b in bins]
    big_grand = sum(big_totals)
    if big_grand > 0:
        big_mean = big_grand / n
        btag = [_tag(b[BIG_BUY], b[BIG_SELL], big_totals[i], big_mean, cfg) for i, b in enumerate(bins)]
        out["big_buy_zones"], out["big_sell_zones"] = _zones(btag, bins, big_days_in, base, w, BIG_BUY, BIG_SELL, big=True)
    out["top"] = top_levels(pts, int(cfg["top_n"]))
    return out


def top_levels(pts: list[tuple[float, list[int], bool, str]], top_n: int) -> dict:
    """Các mức giá CHÍNH XÁC (không gộp ô) có KL mua / bán chủ động lớn nhất trong khung.

    Giá đã nhân hệ số điều chỉnh lệch khỏi lưới bước giá → làm tròn về bước giá của chính nó rồi mới gộp.
    pct = phần của mức trong tổng mua (bán) chủ động khung; big_* chỉ có ở phiên tick thật.
    """
    lv: dict[float, list] = {}  # giá → [mua, bán, x, mua_lớn, bán_lớn, KL est, {ngày}]
    for p, arr, est, day in pts:
        t = tick_size(p)
        k = round(round(p / t) * t, 4)
        r = lv.setdefault(k, [0, 0, 0, 0, 0, 0, set()])
        for c in range(5):
            r[c] += int(arr[c])
        if est:
            r[5] += int(arr[BUY] + arr[SELL])
        r[6].add(day)
    out = {}
    for key, col in (("buy", BUY), ("sell", SELL), ("big_buy", BIG_BUY), ("big_sell", BIG_SELL)):
        side_total = sum(r[col] for r in lv.values())
        rows = sorted(((k, r) for k, r in lv.items() if r[col] > 0), key=lambda kr: -kr[1][col])[:top_n]
        out[key] = [{
            "p": k, "vol": r[col],
            "pct": round(r[col] / side_total, 4),
            "share": round(r[BUY] / (r[BUY] + r[SELL]), 3) if r[BUY] + r[SELL] else None,
            "sessions": len(r[6]), "last": max(r[6]),
            "est_share": 0.0 if key.startswith("big") or not r[BUY] + r[SELL] else round(r[5] / (r[BUY] + r[SELL]), 3),
        } for k, r in rows]
    return out


def footprint(sessions: list[tuple[str, dict]], ohlc: dict[str, list[float]], n: int = 12) -> list:
    """Nến dòng tiền: n phiên gần nhất có nến kho, CŨ → MỚI.

    Mỗi phiên [ngày, est, O, H, L, C, [[giá, mua, bán, x, mua_lớn, bán_lớn], …]] — mức giá khớp nhân hệ số
    adjust_factor để cùng thang giá điều chỉnh với O/H/L/C của kho nến; bỏ mức không có KL.
    Phiên không có nến kho (chưa tải / nghỉ) bị bỏ: không có O/H/L/C thì không vẽ được nến.
    """
    out = []
    for day, sess in sessions:
        bar = ohlc.get(day)
        if not bar:
            continue
        f = adjust_factor(sess, bar[3])
        lv = sorted([round(float(p) * f, 3)] + [int(v) for v in arr[:5]]
                    for p, arr in sess.get("levels", {}).items() if sum(arr[:3]) > 0)
        out.append([day, 1 if sess.get("est", False) else 0] + [float(v) for v in bar[:4]] + [lv])
    return out[-n:]


def session_stats(day: str, sess: dict) -> dict:
    """Một dòng thống kê mua/bán chủ động của MỘT phiên (giá thô, không cần hệ số).

    Mỗi cổ phiếu khớp có đúng một bên chủ động và một bên bị động: mua bị động = bán chủ động và ngược lại,
    nên hai cột mua/bán chủ động là đủ. Giá trị lệnh lớn = Σ KL × giá thô (tiền thật đã khớp), đơn vị tỷ đồng;
    phiên ước lượng (est) không có lệnh lớn → None, không phải 0.
    """
    buy = sell = x = 0
    big_buy_val = big_sell_val = 0.0
    for k, arr in sess.get("levels", {}).items():
        p = float(k)
        buy += int(arr[BUY])
        sell += int(arr[SELL])
        x += int(arr[OTHER])
        big_buy_val += int(arr[BIG_BUY]) * p
        big_sell_val += int(arr[BIG_SELL]) * p
    est = bool(sess.get("est", False))
    out = {
        "d": day, "est": est, "buy": buy, "sell": sell, "x": x, "total": buy + sell + x, "net": buy - sell,
        "buy_share": round(buy / (buy + sell), 4) if buy + sell else None,
        "big_buy_val": None, "big_sell_val": None, "big_net_val": None,
        # Phiên thật mà cả phiên không tick nào có bên chủ động: nguồn không ghi `side` cho mã này
        # (DGC 09/2026: 0/667 tick có side) — không phải "mua = bán".
        "no_side": (not est) and buy + sell == 0 and x > 0,
    }
    if not est and buy + sell > 0:
        # nghìn đồng × cp = nghìn đồng → tỷ đồng: / 1e6
        out["big_buy_val"] = round(big_buy_val / 1e6, 2)
        out["big_sell_val"] = round(big_sell_val / 1e6, 2)
        out["big_net_val"] = round((big_buy_val - big_sell_val) / 1e6, 2)
    return out


def sum_stats(rows: list[dict]) -> dict:
    """Cộng các dòng session_stats (một khung phiên). Lệnh lớn chỉ cộng phiên tick thật."""
    buy = sum(r["buy"] for r in rows)
    sell = sum(r["sell"] for r in rows)
    real = [r for r in rows if r["big_net_val"] is not None]
    return {
        "n": len(rows), "n_real": len(real),
        "buy": buy, "sell": sell, "x": sum(r["x"] for r in rows), "net": buy - sell,
        "buy_share": round(buy / (buy + sell), 4) if buy + sell else None,
        "big_buy_val": round(sum(r["big_buy_val"] for r in real), 2) if real else None,
        "big_sell_val": round(sum(r["big_sell_val"] for r in real), 2) if real else None,
        "big_net_val": round(sum(r["big_net_val"] for r in real), 2) if real else None,
    }


def value_area(totals: list[int], poc: int, pct: float) -> tuple[int, int]:
    """(ô thấp, ô cao) bao ≥ pct tổng KL, mở rộng từ POC về phía ô kề có KL lớn hơn."""
    grand = sum(totals)
    lo = hi = poc
    acc = totals[poc]
    while acc < grand * pct and (lo > 0 or hi < len(totals) - 1):
        below = totals[lo - 1] if lo > 0 else -1
        above = totals[hi + 1] if hi < len(totals) - 1 else -1
        if above > below:
            hi += 1
            acc += above
        else:
            lo -= 1
            acc += below
    return lo, hi


def _tag(buy: int, sell: int, total: int, mean: float, cfg: dict) -> str:
    if total < mean * float(cfg["zone_vol_mult"]) or buy + sell <= 0:
        return ""
    share = buy / (buy + sell)
    if share >= float(cfg["buy_share_min"]):
        return "buy"
    if share <= float(cfg["sell_share_max"]):
        return "sell"
    return ""


def _zones(tag, bins, days_in, base, w, ib, isl, big: bool = False) -> tuple[list[dict], list[dict]]:
    """Gom ô liền kề cùng nhãn thành vùng. big=True: KL vùng là KL lệnh lớn (chỉ có ở phiên tick thật → est_share 0)."""
    buy_z: list[dict] = []
    sell_z: list[dict] = []
    i = 0
    n = len(bins)
    while i < n:
        t = tag[i]
        if not t:
            i += 1
            continue
        j = i
        while j + 1 < n and tag[j + 1] == t:
            j += 1
        seg = bins[i:j + 1]
        days: set[str] = set().union(*days_in[i:j + 1])
        buy = sum(b[ib] for b in seg)
        sell = sum(b[isl] for b in seg)
        vol = buy + sell if big else sum(b[BUY] + b[SELL] + b[OTHER] for b in seg)
        z = {
            "lo": round(base + i * w, 4), "hi": round(base + (j + 1) * w, 4),
            "vol": vol, "buy": buy, "sell": sell,
            "share": round(buy / (buy + sell), 3) if buy + sell else None,
            "sessions": len(days), "last": max(days) if days else "",
            "est_share": 0.0 if big or not vol else round(sum(b[EST] for b in seg) / vol, 3),
        }
        (buy_z if t == "buy" else sell_z).append(z)
        i = j + 1
    return buy_z, sell_z


def with_distance(profile: dict, price: float | None) -> dict:
    """Thêm `dist` (% từ giá hiện tại tới tâm vùng) vào mọi vùng; giá None → không thêm."""
    if not price:
        return profile
    for key in ("buy_zones", "sell_zones", "big_buy_zones", "big_sell_zones"):
        for z in profile.get(key, []):
            mid = (z["lo"] + z["hi"]) / 2
            z["dist"] = round((mid - price) / price * 100, 2)
    for rows in (profile.get("top") or {}).values():
        for r in rows:
            r["dist"] = round((r["p"] - price) / price * 100, 2)
    return profile
