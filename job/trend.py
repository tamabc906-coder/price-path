"""Tín hiệu xu hướng: Supertrend (10, 3) kết hợp EMA10 — Python thuần, chép từ supertrend-lab/engine.js
(bản JS đã đối chiếu tay và chạy lưới 18 tổ hợp, xem reports/replay-trend-2026-09-18.md).

Hai tín hiệu, chỉ chiều mua vì VN không bán khống:
  * st_buy  — Supertrend xanh và đóng cửa > EMA10, LẦN ĐẦU kể từ đợt đỏ gần nhất (có thể là ngay phiên
              lật xanh, hoặc vài phiên sau khi giá mới vượt EMA10).
  * st_exit — Supertrend lật đỏ (đóng cửa xuyên xuống dải dưới). Đây là điểm thoát DUY NHẤT: thoát sớm
              hơn khi rớt EMA10 đã đo là hại nhiều hơn lợi (+1,24 %/lệnh so với +6,63 %/lệnh).

ATR tính kiểu Wilder (RMA) như TradingView — bản dùng SMA của True Range cho ngày lật màu lệch 1–2 phiên.
Cần ≥ WARMUP nến trước phiên xét; job lấy 200 ngày lịch (~135 phiên) nên dư.
"""
from __future__ import annotations

ATR_PERIOD = 10
ATR_MULT = 3.0
EMA_PERIOD = 10
WARMUP = 40                 # ATR/EMA đã ổn định sau ~30 phiên; thêm dư để đợt đỏ trước đó lọt vào cửa sổ
BARS_IN_CARD = 22           # nến gửi kèm thẻ xu hướng (có cả dải Supertrend + EMA để vẽ)

# Meta cùng khuôn với patterns.PATTERNS để giao diện/push dùng chung; `kind` để tách khỏi mẫu nến.
SIGNALS: dict[str, dict] = {
    "st_buy": {
        "name": "Supertrend xanh + trên EMA10", "direction": "buy", "bars": 1, "kind": "trend",
        "hint": "Supertrend vừa xanh (hoặc đang xanh) và giá đóng cửa vượt EMA10 — lần đầu sau đợt đỏ.",
        "advice": "Mua phiên sau; dừng lỗ đặt tại dải Supertrend; khối lượng = 1 % vốn ÷ khoảng cách tới dừng lỗ.",
        "caution": "",
    },
    "st_exit": {
        "name": "Supertrend lật đỏ", "direction": "sell", "bars": 1, "kind": "trend",
        "hint": "Giá đóng cửa xuyên xuống dải Supertrend — xu hướng tăng đã gãy, thoát hàng.",
        "advice": "Bán phiên sau nếu đang giữ; không mua lại cho tới khi Supertrend xanh trở lại.",
        "caution": "",
    },
}


def ema(bars: list[dict], n: int = EMA_PERIOD) -> list[float | None]:
    """EMA đóng cửa, mồi bằng SMA n phiên đầu. Cùng độ dài với bars, warm-up là None."""
    out: list[float | None] = [None] * len(bars)
    if n < 1 or len(bars) < n:
        return out
    v = sum(b["c"] for b in bars[:n]) / n
    out[n - 1] = v
    a = 2.0 / (n + 1)
    for i in range(n, len(bars)):
        v = a * bars[i]["c"] + (1 - a) * v
        out[i] = v
    return out


def atr_wilder(bars: list[dict], n: int = ATR_PERIOD) -> list[float | None]:
    """ATR làm mượt kiểu Wilder: atr = (atr₋₁·(n−1) + TR)/n, mồi bằng SMA của TR."""
    out: list[float | None] = [None] * len(bars)
    if len(bars) < n:
        return out
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b["h"] - b["l"])
        else:
            pc = bars[i - 1]["c"]
            tr.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    v = sum(tr[:n]) / n
    out[n - 1] = v
    for i in range(n, len(bars)):
        v = (v * (n - 1) + tr[i]) / n
        out[i] = v
    return out


def supertrend(bars: list[dict], n: int = ATR_PERIOD, mult: float = ATR_MULT) -> list[dict | None]:
    """Mỗi phần tử: {"up": bool, "line": float, "fu": float, "fl": float} hoặc None khi chưa đủ dữ liệu.
    Dải "final" chỉ siết vào, không nới ra, trừ khi giá đã vượt qua nó (thuật toán chuẩn/TradingView)."""
    atr = atr_wilder(bars, n)
    out: list[dict | None] = [None] * len(bars)
    prev: dict | None = None
    for i, b in enumerate(bars):
        if atr[i] is None:
            continue
        hl2 = (b["h"] + b["l"]) / 2
        bu, bl = hl2 + mult * atr[i], hl2 - mult * atr[i]
        if prev is None:
            fu, fl, up = bu, bl, False          # TradingView khởi tạo hướng xuống
        else:
            pc = bars[i - 1]["c"]
            fu = bu if (bu < prev["fu"] or pc > prev["fu"]) else prev["fu"]
            fl = bl if (bl > prev["fl"] or pc < prev["fl"]) else prev["fl"]
            up = (not (b["c"] < fl)) if prev["up"] else (b["c"] > fu)
        prev = {"up": up, "line": fl if up else fu, "fu": fu, "fl": fl}
        out[i] = prev
    return out


def _armed(st: list[dict | None], em: list[float | None], bars: list[dict], i: int) -> bool:
    """Trước phiên i đã có đợt đỏ, và từ đó chưa phiên nào thoả 'xanh + trên EMA' (chưa mua)."""
    j = i - 1
    while j >= 0 and st[j] is not None and st[j]["up"]:
        if em[j] is not None and bars[j]["c"] > em[j]:
            return False
        j -= 1
    return j >= 0 and st[j] is not None and not st[j]["up"]


def detect_at(bars: list[dict], i: int, disabled: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """Tín hiệu xu hướng kết thúc tại nến i. Trả [] khi chưa đủ warm-up."""
    if i < 0:
        i += len(bars)
    if i < WARMUP or i >= len(bars):
        return []
    st, em = supertrend(bars), ema(bars)
    if st[i] is None or st[i - 1] is None or em[i] is None:
        return []
    out: list[str] = []
    if "st_exit" not in disabled and not st[i]["up"] and st[i - 1]["up"]:
        out.append("st_exit")
    if "st_buy" not in disabled and st[i]["up"] and bars[i]["c"] > em[i] and _armed(st, em, bars, i):
        out.append("st_buy")
    return out


def state_at(bars: list[dict], i: int = -1) -> dict | None:
    """Trạng thái Supertrend của một mã tại nến i: màu, dải, từ phiên nào, EMA — cho bảng xu hướng
    và dòng 'Xu hướng' trong thẻ mẫu nến. None khi chưa đủ dữ liệu."""
    if i < 0:
        i += len(bars)
    st, em = supertrend(bars), ema(bars)
    if i < 0 or i >= len(bars) or st[i] is None or em[i] is None:
        return None
    k = i
    while k > 0 and st[k - 1] is not None and st[k - 1]["up"] == st[i]["up"]:
        k -= 1
    return {
        "up": st[i]["up"], "line": round(st[i]["line"], 2), "since": bars[k]["d"].isoformat(),
        "days": i - k + 1, "ema": round(em[i], 2), "above_ema": bars[i]["c"] > em[i],
    }


def candles_for_card(bars: list[dict], i: int = -1, n: int = BARS_IN_CARD) -> list[dict]:
    """n nến tới nến i, kèm dải Supertrend/màu/EMA từng nến để giao diện vẽ đường, và `sig`
    ("buy" / "exit" / None) — cùng quy tắc detect_at, tính trên toàn chuỗi nên đúng cả ở đầu cửa sổ —
    để vẽ mũi tên mua/thoát trên biểu đồ trong thẻ."""
    if i < 0:
        i += len(bars)
    st, em = supertrend(bars), ema(bars)
    out = []
    for j in range(max(0, i - n + 1), i + 1):
        b = bars[j]
        sig = None
        if j >= WARMUP and st[j] and st[j - 1] and em[j] is not None:
            if not st[j]["up"] and st[j - 1]["up"]:
                sig = "exit"
            elif st[j]["up"] and b["c"] > em[j] and _armed(st, em, bars, j):
                sig = "buy"
        out.append({"d": b["d"].isoformat(), "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"],
                    "st": round(st[j]["line"], 2) if st[j] else None, "up": st[j]["up"] if st[j] else None,
                    "ema": round(em[j], 2) if em[j] is not None else None, "sig": sig})
    return out
