"""Order Block / SMC (người dùng yêu cầu 06/10/2026): bản đồ ký hiệu SMC trên nến ngày cho tab "Order BK".

Chép luật từ bản mẫu c:\\Claude code\\order-block-lab\\measure.py (cùng ngưỡng để tab khớp trang nghiên cứu):
  swing = fractal 2 nến mỗi bên (biết sau 2 phiên); phá cấu trúc = đóng cửa vượt đỉnh/đáy swing chưa bị phá —
  cùng chiều lần phá trước là BOS, đổi chiều là CHoCH.
  OB tăng = nến đỏ k, nến k+1 xanh, ≤ 3 phiên sau đóng cửa ≥ C[k] + 1,5 ATR14 và đã phá đỉnh cấu trúc; vùng [L, H]
  của nến k, MT = giữa vùng. OB giảm đối xứng. Chạm lần đầu (mitigation) = sau khi giá rời hẳn vùng, phiên đầu tiên
  quay lại; OB sống 60 phiên. Breaker = OB tăng bị đóng cửa thủng, giá rời hẳn xuống dưới rồi hồi lên chạm lại.
  FVG ≥ 0,5 ATR, kéo tới khi giá lấp kín hoặc hết 20 phiên.

Lab đo 39 mã 2016–2026: chạm OB KHÔNG có lợi thế hơn mua bừa (0/7 giả thuyết qua cổng) → chỉ hiển thị, không push.
Hàm thuần trên hàng kho [d, o, h, l, c, v] (data/history.json), không gọi mạng. Kết quả → docs/data/smc.json.
"""
from __future__ import annotations

DISP = 1.5        # nhịp tăng/giảm tính bằng ATR
DISP_WIN = 3      # số phiên tối đa cho nhịp
LIFE = 60         # OB sống bao nhiêu phiên
FVG_MIN, FVG_LIFE = 0.5, 20
NEAR_ATR = 1.0    # "gần vùng" khi giá đóng cửa cách mép vùng ≤ 1 ATR
CALC_N = 400      # số phiên cuối dùng để tính (đủ cho ATR + cấu trúc)
CHART_N = 120     # số nến gửi xuống app


def atr14(h: list, l: list, c: list) -> list:
    """ATR Wilder (EWM alpha 1/14, adjust=False) — y hệt pandas trong lab."""
    out = []
    a = None
    for t in range(len(h)):
        tr = h[t] - l[t] if t == 0 else max(h[t] - l[t], abs(h[t] - c[t - 1]), abs(l[t] - c[t - 1]))
        a = tr if a is None else a + (tr - a) / 14
        out.append(a)
    return out


def _is_high(h: list, i: int) -> bool:
    return h[i] > max(h[i - 1], h[i - 2]) and h[i] >= max(h[i + 1], h[i + 2])


def _is_low(l: list, i: int) -> bool:
    return l[i] < min(l[i - 1], l[i - 2]) and l[i] <= min(l[i + 1], l[i + 2])


def structure_levels(h: list, l: list, c: list) -> tuple[list, list]:
    """Đỉnh/đáy cấu trúc chưa bị phá, biết tại phiên t (None = không có)."""
    sh, sl = [], []
    hi = lo = None
    for t in range(len(h)):
        i = t - 2
        if i >= 2:
            if _is_high(h, i):
                hi = h[i]
            if _is_low(l, i):
                lo = l[i]
        if hi is not None and c[t] > hi:
            hi = None
        if lo is not None and c[t] < lo:
            lo = None
        sh.append(hi)
        sl.append(lo)
    return sh, sl


def structure_events(h: list, l: list, c: list) -> tuple[list, list]:
    """Swing (HH/LH/HL/LL) và các lần phá cấu trúc (BOS/CHoCH)."""
    swings, breaks = [], []
    hi = lo = None
    last_hi = last_lo = None
    trend = 0
    for t in range(len(h)):
        i = t - 2
        if i >= 2:
            if _is_high(h, i):
                swings.append({"i": i, "p": h[i], "lab": "HH" if last_hi is None or h[i] > last_hi else "LH", "up": True})
                last_hi, hi = h[i], (i, h[i])
            if _is_low(l, i):
                swings.append({"i": i, "p": l[i], "lab": "LL" if last_lo is None or l[i] < last_lo else "HL", "up": False})
                last_lo, lo = l[i], (i, l[i])
        if hi is not None and c[t] > hi[1]:
            breaks.append({"s": hi[0], "t": t, "p": hi[1], "up": True, "lab": "CHoCH" if trend == -1 else "BOS"})
            trend, hi = 1, None
        if lo is not None and c[t] < lo[1]:
            breaks.append({"s": lo[0], "t": t, "p": lo[1], "up": False, "lab": "CHoCH" if trend == 1 else "BOS"})
            trend, lo = -1, None
    return swings, breaks


def fvg_events(h: list, l: list, a: list) -> list:
    out = []
    n = len(h)
    for i in range(n - 2):
        if l[i + 2] - h[i] >= FVG_MIN * a[i]:
            bot, top, up = h[i], l[i + 2], True
        elif l[i] - h[i + 2] >= FVG_MIN * a[i]:
            bot, top, up = h[i + 2], l[i], False
        else:
            continue
        end = min(i + 2 + FVG_LIFE, n - 1)
        for t in range(i + 3, end + 1):
            if (up and l[t] <= bot) or (not up and h[t] >= top):
                end = t
                break
        out.append({"i": i + 1, "end": end, "lo": bot, "hi": top, "up": up})
    return out


def find_obs(o: list, h: list, l: list, c: list, a: list, bull: bool) -> list:
    """OB có BOS (luật H1 của lab). Trả {k, m, lo, hi}; m = phiên OB được biết."""
    sh, sl = structure_levels(h, l, c)
    s = 1 if bull else -1
    n = len(c)
    out = []
    for k in range(20, n - 1):
        if not (s * (c[k] - o[k]) < 0 and s * (c[k + 1] - o[k + 1]) > 0):
            continue
        lvl = sh[k] if bull else sl[k]
        bos = False
        for j in range(k + 1, min(k + DISP_WIN, n - 1) + 1):
            if lvl is not None and s * (c[j] - lvl) > 0:
                bos = True
            if s * (c[j] - c[k]) >= DISP * a[k] and bos:
                out.append({"k": k, "m": j, "lo": l[k], "hi": h[k], "bull": bull})
                break
    return out


def first_touch(h: list, l: list, ob: dict) -> int | None:
    armed = False
    n = len(h)
    for t in range(ob["m"] + 1, min(ob["m"] + LIFE, n - 1) + 1):
        if ob["bull"]:
            if armed and l[t] <= ob["hi"]:
                return t
            if l[t] > ob["hi"]:
                armed = True
        else:
            if armed and h[t] >= ob["lo"]:
                return t
            if h[t] < ob["lo"]:
                armed = True
    return None


def breaker(h: list, c: list, ob: dict) -> tuple[int | None, int | None]:
    """(phiên đóng cửa thủng đáy OB tăng, phiên hồi lên chạm lại sau khi đã rời hẳn xuống dưới)."""
    n = len(c)
    lo = ob["lo"]
    end = min(ob["m"] + LIFE, n - 1)
    b = next((t for t in range(ob["m"] + 1, end + 1) if c[t] < lo), None)
    if b is None:
        return None, None
    away = False
    for t in range(b + 1, min(b + LIFE, n - 1) + 1):
        if away and h[t] >= lo:
            return b, t
        if h[t] < lo:
            away = True
    return b, None


def analyze(rows: list[list]) -> dict:
    """Mọi ký hiệu SMC trên chuỗi nến (chỉ số theo rows)."""
    o = [r[1] for r in rows]
    h = [r[2] for r in rows]
    l = [r[3] for r in rows]
    c = [r[4] for r in rows]
    a = atr14(h, l, c)
    obs = []
    for bull in (True, False):
        for ob in find_obs(o, h, l, c, a, bull):
            t = first_touch(h, l, ob)
            ob["t"] = t
            ob["res"] = None if t is None else ("giữ" if (c[t] >= ob["lo"] if bull else c[t] < ob["hi"]) else "thủng")
            ob["brk_close"], ob["brk"] = breaker(h, c, ob) if bull else (None, None)
            obs.append(ob)
    swings, breaks = structure_events(h, l, c)
    return {"obs": obs, "swings": swings, "breaks": breaks, "fvgs": fvg_events(h, l, a), "atr": a}


def zones_now(rows: list[list], an: dict) -> list:
    """Vùng còn hiệu lực ở phiên cuối: OB ≤ 60 phiên chưa bị đóng cửa xuyên qua, và Breaker chưa được chạm lại."""
    n = len(rows)
    c = [r[4] for r in rows]
    last, atr = c[-1], an["atr"][-1]
    out = []
    for ob in an["obs"]:
        if n - 1 - ob["m"] > LIFE:
            continue
        after = c[ob["m"] + 1:]
        if ob["bull"] and ob["brk_close"] is not None:
            if ob["brk"] is not None:
                continue
            kind = "bb"
        elif not ob["bull"] and any(x > ob["hi"] for x in after):
            continue
        else:
            kind = "bull" if ob["bull"] else "bear"
        if ob["lo"] <= last <= ob["hi"]:
            dist = 0.0
        else:
            dist = (ob["lo"] - last) if last < ob["lo"] else (last - ob["hi"])
        pos = "in" if dist == 0 else ("near" if dist <= NEAR_ATR * atr else "far")
        out.append({"kind": kind, "lo": round(ob["lo"], 4), "hi": round(ob["hi"], 4), "pos": pos,
                    "dist_atr": round(dist / atr, 2) if atr > 0 else None, "dist_pct": round(dist / last, 4),
                    "above": ob["lo"] > last, "age": n - 1 - ob["m"], "touched": ob["t"] is not None})
    out.sort(key=lambda z: (z["dist_atr"] if z["dist_atr"] is not None else 99))
    return out


def chart(rows: list[list], an: dict, span: int = CHART_N) -> dict:
    n = len(rows)
    s0 = max(0, n - span)
    rel = lambda i: None if i is None else i - s0
    obs = []
    for ob in an["obs"]:
        if ob["k"] < s0:
            continue
        end = ob["t"] if ob["t"] is not None else min(ob["m"] + LIFE, n - 1)
        obs.append({"k": ob["k"] - s0, "m": ob["m"] - s0, "end": end - s0, "lo": round(ob["lo"], 4),
                    "hi": round(ob["hi"], 4), "bull": ob["bull"], "t": rel(ob["t"]), "res": ob["res"],
                    "brk": rel(ob["brk"]), "brk_close": rel(ob["brk_close"])})
    r4 = lambda x: round(x, 4)
    return {"dates": [r[0] for r in rows[s0:]],
            "ohlc": [[r4(r[1]), r4(r[2]), r4(r[3]), r4(r[4])] for r in rows[s0:]],
            "obs": obs,
            "swings": [{"i": s["i"] - s0, "p": r4(s["p"]), "lab": s["lab"], "up": s["up"]} for s in an["swings"] if s["i"] >= s0],
            "breaks": [{"s": b["s"] - s0, "t": b["t"] - s0, "p": r4(b["p"]), "up": b["up"], "lab": b["lab"]}
                       for b in an["breaks"] if b["s"] >= s0],
            "fvgs": [{"i": f["i"] - s0, "end": f["end"] - s0, "lo": r4(f["lo"]), "hi": r4(f["hi"]), "up": f["up"]}
                     for f in an["fvgs"] if f["i"] >= s0]}


def scan(hist: dict, items: list[dict], trade_iso: str) -> dict:
    """{trade_date, rule, symbols: [...]} cho các mã trong danh mục."""
    names = {it["symbol"]: it.get("company_name") or "" for it in items}
    out = []
    for sym in sorted(names):
        rows = (hist["bars"].get(sym) or [])[-CALC_N:]
        if len(rows) < 60:
            continue
        an = analyze(rows)
        n = len(rows)
        lb = an["breaks"][-1] if an["breaks"] else None
        out.append({"symbol": sym, "name": names[sym], "date": rows[-1][0], "close": rows[-1][4],
                    "prev": rows[-2][4], "atr": round(an["atr"][-1], 4), "zones": zones_now(rows, an),
                    "last_break": None if lb is None else {"lab": lb["lab"], "up": lb["up"], "p": round(lb["p"], 4),
                                                           "age": n - 1 - lb["t"], "date": rows[lb["t"]][0]},
                    "chart": chart(rows, an)})
    return {"trade_date": trade_iso,
            "rule": {"disp_atr": DISP, "disp_win": DISP_WIN, "life": LIFE, "fvg_min_atr": FVG_MIN, "near_atr": NEAR_ATR},
            "symbols": out}
