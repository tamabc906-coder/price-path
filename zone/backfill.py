"""Dựng tạm phiên từ nến 1 phút DNSE cho những ngày CHƯA có tick thật — để có vùng giá 2 tháng ngay từ ngày đầu
thay vì chờ 40 phiên tích luỹ. Đánh dấu `est: true`, giao diện tô nhạt và ghi rõ "ước lượng".

Quy tắc (thô, nói thẳng): KL mỗi nến chia đều cho các bước giá trong [l, h]; hướng cả nến = mua nếu c > o, bán
nếu c < o, c == o thì so với close nến trước, vẫn bằng thì theo nến trước; nến 09:15 (có ATO) và 14:45 (ATC) → x.
Đây là quy tắc tick (Lee–Ready rút gọn) trên nến 1', không phải Mua/Bán chủ động thật. Không có "lệnh lớn".

    python -m zone.backfill               # 39 mã danh mục, 70 ngày lịch (~47 phiên), chỉ ghi ngày chưa có tick thật
    python -m zone.backfill FPT --days 30

Chạy lại bất kỳ lúc nào: phiên thật không bao giờ bị ghi đè (zone/store.py::put).
"""
from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import datetime, time as dtime

from common import dnse
from common.config import TZ
from job import watchlist

from . import store
from .collect import BUY, OTHER, SELL, price_key

log = logging.getLogger("zone.backfill")

DEFAULT_DAYS = 70
ATO_TIME = dtime(9, 15)
ATC_TIME = dtime(14, 44)


def tick_size(price: float, exchange: str = "HOSE") -> float:
    """Bước giá (nghìn đồng). HOSE: 10 đ dưới 10.000, 50 đ tới 49.950, 100 đ từ 50.000; HNX/UPCOM: 100 đ."""
    if (exchange or "HOSE").upper() != "HOSE":
        return 0.1
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    return 0.1


def levels_between(low: float, high: float, step: float) -> list[float]:
    """Các mức giá từ low tới high theo bước step (làm tròn theo bước). Ít nhất một mức."""
    lo = round(round(low / step) * step, 3)
    hi = round(round(high / step) * step, 3)
    out = []
    p = lo
    while p <= hi + 1e-9:
        out.append(round(p, 3))
        p += step
    return out or [round(low, 3)]


def estimate_session(bars: list[dict], exchange: str = "HOSE") -> dict | None:
    """Nến 1' của MỘT phiên (cũ → mới) → session ước lượng cùng khuôn zone/collect.py."""
    if not bars:
        return None
    levels: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    prev_close = None
    prev_dir = BUY
    total = 0
    for b in bars:
        t = datetime.fromtimestamp(b["t"], TZ).time()
        if t <= ATO_TIME or t >= ATC_TIME:
            side = OTHER
        elif b["c"] > b["o"]:
            side = BUY
        elif b["c"] < b["o"]:
            side = SELL
        elif prev_close is not None and b["c"] != prev_close:
            side = BUY if b["c"] > prev_close else SELL
        else:
            side = prev_dir
        if side != OTHER:
            prev_dir = side
        prev_close = b["c"]
        v = int(b["v"])
        total += v
        if v <= 0:
            continue
        grid = levels_between(b["l"], b["h"], tick_size(b["c"], exchange))
        share, rem = divmod(v, len(grid))
        # Phần dư dồn vào mức gần giá đóng cửa nến nhất để tổng KL khớp tuyệt đối.
        nearest = min(range(len(grid)), key=lambda i: abs(grid[i] - b["c"]))
        for i, p in enumerate(grid):
            levels[price_key(p)][side] += share + (rem if i == nearest else 0)
    if total <= 0:
        return None
    return {
        "src": "dnse1m",
        "est": True,
        "close": bars[-1]["c"],
        "total": total,
        "ticks": len(bars),
        "levels": {k: levels[k] for k in sorted(levels, key=float)},
    }


def by_day(bars: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for b in bars:
        out[b["d"].isoformat()].append(b)
    return out


def backfill_symbol(client: dnse.DnseClient, symbol: str, exchange: str, days: int) -> tuple[int, int]:
    """Trả (số phiên ghi mới, số phiên bỏ qua vì đã có)."""
    st = store.load(symbol)
    written = skipped = 0
    bars = client.minutes(symbol, days)
    if not bars:
        log.warning("%s: DNSE không trả nến 1'", symbol)
        return 0, 0
    for day, day_bars in sorted(by_day(bars).items()):
        if not dnse.session_settled(day_bars) and day != max(by_day(bars)):
            # Ngày cũ mà thiếu nến ATC là ngày nguồn trả thiếu — không dựng từ bản thiếu.
            log.warning("%s %s: nến 1' thiếu ATC, bỏ qua", symbol, day)
            continue
        sess = estimate_session(day_bars, exchange)
        if sess is None:
            continue
        if store.put(st, day, sess):
            written += 1
        else:
            skipped += 1
    if written:
        store.save(st)
    return written, skipped


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="mặc định: cả danh mục KingStock")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help="số ngày lịch lùi lại (DNSE tối đa ~70)")
    a = ap.parse_args()
    items, src = watchlist.load()
    exch = {it["symbol"]: it.get("exchange") or "HOSE" for it in items}
    syms = [s.upper() for s in a.symbols] or [it["symbol"] for it in items]
    log.info("danh mục %s: %d mã, lùi %d ngày", src, len(syms), a.days)
    with dnse.DnseClient() as c:
        for sym in syms:
            w, s = backfill_symbol(c, sym, exch.get(sym, "HOSE"), a.days)
            log.info("%s: ghi %d phiên ước lượng, giữ nguyên %d", sym, w, s)


if __name__ == "__main__":
    main()
