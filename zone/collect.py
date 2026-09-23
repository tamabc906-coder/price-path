"""Gom tick một phiên thành bản tổng hợp theo mức giá: {giá: [mua, bán, x, mua_lớn, bán_lớn]}.

- mua/bán = KL khớp CHỦ ĐỘNG. VNDirect đặt tên theo bên BỊ ĐỘNG: side PB (passive buy) = người bán chủ động
  đập vào lệnh mua chờ → BÁN; PS = MUA. Đã đối chiếu 1.497 lệnh FPT/HPG/VNM với Vietcap (matchType b/s, trùng
  từng lệnh với app CTCK người dùng chụp 18/09/2026): ngược 100 % → scripts/zone_check_sources.py.
- x = ATO + ATC (không có hướng) — FPT 18/09 ATC chiếm 55 % KL phiên, gộp bừa vào một bên là hỏng tỷ lệ mua/bán.
- mua_lớn/bán_lớn = phần của mua/bán đến từ LỆNH có giá trị ≥ ngưỡng (mặc định 500 triệu đ) — lớp "cá mập".
  VNDirect tách một lệnh chủ động thành nhiều tick (mỗi lệnh chờ bị khớp một dòng: 14:29:42 · 73.9 · 5000 trên
  app = 7 tick 500+100+100+500+700+2000+1100), nên phải gộp tick cùng giây/giá/hướng lại thành lệnh trước khi xét.
- gap = số cp sàn đã đếm mà nguồn không trả tick, chỉ có mặt khi khác 0 (TCB 23/09/2026 hụt 500 cp).
- Không lưu tick thô: 12 k tick × 39 mã × 40 phiên quá nặng cho git; bản gộp mỗi phiên chỉ vài chục dòng.

Chạy tay: `python -m zone.collect FPT` → in bảng mức giá của phiên gần nhất để đối chiếu app CTCK.
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict

from common.vndirect import VndirectClient

logger = logging.getLogger(__name__)

# Chỉ số trong mảng mỗi mức giá.
BUY, SELL, OTHER, BIG_BUY, BIG_SELL = range(5)
# Giá ở nghìn đồng, KL ở cổ phiếu → giá × KL × 1000 = giá trị VND. 500 triệu đ ↔ giá × KL ≥ 500_000.
BIG_LOT_VALUE_VND = 500_000_000
# Tổng KL gộp lệch quá mức này so với nến ngày DNSE → cảnh báo (vẫn ghi: nguồn tick là bản đầy đủ hơn).
VOLUME_TOLERANCE = 0.02

# Tên side của VNDirect là bên BỊ ĐỘNG (xem docstring): PB → bán chủ động, PS → mua chủ động.
SIDE_INDEX = {"PS": BUY, "PB": SELL}


def price_key(price: float) -> str:
    """Khoá mức giá ổn định qua JSON: 74.2 → "74.2", 10.05 → "10.05" (tránh 74.200000001)."""
    return f"{round(price, 3):g}"


def orders(ticks: list[dict]) -> list[dict]:
    """Gộp tick LIÊN TIẾP cùng giây + giá + hướng thành một lệnh (khuôn app CTCK). ATO/ATC giữ nguyên."""
    out: list[dict] = []
    for t in ticks:
        last = out[-1] if out else None
        if (last and last["time"] == t["time"] and last["price"] == t["price"] and last["side"] == t["side"]
                and t["side"] in SIDE_INDEX):
            last["vol"] += t["vol"]
        else:
            out.append(dict(t))
    return out


def aggregate(ticks: list[dict], big_value_vnd: int = BIG_LOT_VALUE_VND) -> dict | None:
    """Tick (cũ → mới) → session dict; None nếu không có tick."""
    if not ticks:
        return None
    levels: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    big_threshold = big_value_vnd / 1000  # giá(nghìn) × KL
    total = 0
    for o in orders(ticks):
        row = levels[price_key(o["price"])]
        idx = SIDE_INDEX.get(o["side"], OTHER)
        row[idx] += o["vol"]
        if idx != OTHER and o["price"] * o["vol"] >= big_threshold:
            row[BIG_BUY if idx == BUY else BIG_SELL] += o["vol"]
        total += o["vol"]
    out = {
        "src": "vnd",
        "est": False,
        "close": ticks[-1]["price"],
        "total": total,
        "ticks": len(ticks),
        "levels": {k: levels[k] for k in sorted(levels, key=float)},
    }
    # Số cp sàn đã đếm mà nguồn không trả tick (common.vndirect.shortfall đã chặn nếu hụt quá ngưỡng).
    # Chỉ ghi khi khác 0 — thêm "gap":0 vào mọi phiên là làm phình diff git vô ích.
    gap = max((t.get("acc") or 0 for t in ticks), default=0) - total
    if gap > 0:
        out["gap"] = gap
    return out


def collect(client: VndirectClient, symbol: str, big_value_vnd: int = BIG_LOT_VALUE_VND) -> tuple[str, dict] | None:
    """(ngày phiên ISO, session) của phiên gần nhất trên VNDirect; None nếu nguồn lỗi/rỗng."""
    ticks = client.latest_session(symbol)
    if not ticks:
        return None
    sess = aggregate(ticks, big_value_vnd)
    return ticks[-1]["date"], sess


def check_volume(session: dict, daily_volume: int | None) -> str:
    """So tổng KL gộp với nến ngày DNSE cùng phiên. Trả "" nếu khớp/không có gì để so, ngược lại là câu cảnh báo."""
    if not daily_volume:
        return ""
    diff = abs(session["total"] - daily_volume) / daily_volume
    if diff <= VOLUME_TOLERANCE:
        return ""
    return f"KL tick {session['total']:,} lệch {diff:.1%} so với nến ngày {daily_volume:,}"


def _print(symbol: str, day: str, sess: dict) -> None:
    print(f"{symbol} phiên {day}: {sess['ticks']:,} tick, tổng {sess['total']:,} cp, đóng cửa {sess['close']}")
    print(f"{'giá':>8} {'mua':>12} {'bán':>12} {'ATO/ATC':>12} {'mua lớn':>12} {'bán lớn':>12}")
    for k, v in sess["levels"].items():
        print(f"{k:>8} {v[BUY]:>12,} {v[SELL]:>12,} {v[OTHER]:>12,} {v[BIG_BUY]:>12,} {v[BIG_SELL]:>12,}")
    buy = sum(v[BUY] for v in sess["levels"].values())
    sell = sum(v[SELL] for v in sess["levels"].values())
    print(f"mua chủ động {buy:,} | bán chủ động {sell:,} | ATO/ATC {sess['total'] - buy - sell:,}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for sym in sys.argv[1:] or ["FPT"]:
        with VndirectClient() as c:
            got = collect(c, sym)
        if got is None:
            print(f"{sym}: không lấy được tick")
        else:
            _print(sym, *got)
