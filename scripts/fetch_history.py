"""Tải trọn lịch sử nến ngày 39 mã KingStock + VNINDEX từ DNSE → data/history.json. Chạy tay, một lần
(hoặc khi muốn làm mới kho). Job hằng ngày chỉ nối thêm nến mới qua common/store.py.

    venv\\Scripts\\python -m scripts.fetch_history                 # 4000 ngày (tối đa DNSE cho tới đâu lấy tới đó)
    venv\\Scripts\\python -m scripts.fetch_history --days 2500 --symbols HPG,VNM
    venv\\Scripts\\python -m scripts.fetch_history --refresh      # tải lại cả mã đã có

Chép khuôn supertrend-lab/fetch_data.py; dùng common/dnse.py (một client, nghỉ 0,3 s/mã). Nến hôm nay
KHÔNG được ghi vào kho nếu chạy trong giờ giao dịch — nến chưa chốt (bẫy DNSE 14/09/2026); job daily
mới có cơ chế kiểm tra ATC. Ở đây đơn giản bỏ nến có ngày = hôm nay khi giờ chạy < 15:30.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, time as dtime

from common import dnse, store
from common.config import HISTORY, INDEX_SYMBOL, TZ
from job import watchlist

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

SETTLED_TIME = dtime(15, 30)


def _drop_unsettled_today(bars: list[dict]) -> list[dict]:
    now = datetime.now(TZ)
    if bars and bars[-1]["d"] == now.date() and now.time() < SETTLED_TIME:
        return bars[:-1]
    return bars


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=store.FULL_DAYS)
    ap.add_argument("--symbols", default="", help="chỉ tải các mã này (phẩy), ví dụ HPG,VNM")
    ap.add_argument("--refresh", action="store_true", help="tải lại cả mã đã có trong kho")
    a = ap.parse_args()

    items, src = watchlist.load()
    print(f"Danh mục {len(items)} mã (nguồn: {src})", file=sys.stderr)
    if not items:
        return 2
    syms = [it["symbol"] for it in items] + [INDEX_SYMBOL]
    if a.symbols:
        want = {s.strip().upper() for s in a.symbols.split(",")}
        syms = [s for s in syms if s in want]
    names = {it["symbol"]: (it.get("company_name") or "", it.get("exchange") or "") for it in items}
    names[INDEX_SYMBOL] = ("VN-Index", "index")

    st = store.load(HISTORY)
    ok = 0
    with dnse.DnseClient(days=a.days) as c:
        for k, sym in enumerate(syms, 1):
            st["symbols"].setdefault(sym, {"name": names[sym][0], "exchange": names[sym][1]})
            if st["bars"].get(sym) and not a.refresh:
                first, last, n = store.span(st, sym)
                print(f"  {k:>2}/{len(syms)} {sym:<8} đã có {n:>5} nến ({first} → {last}) — bỏ qua", file=sys.stderr)
                ok += 1
                continue
            b = c.index(sym) if sym == INDEX_SYMBOL else c.daily(sym)
            b = _drop_unsettled_today(b)
            if not b:
                print(f"  {k:>2}/{len(syms)} {sym:<8} LỖI: {dnse.last_error}", file=sys.stderr)
                continue
            if a.refresh:
                st["bars"][sym] = []
            store.merge(st, sym, b)
            ok += 1
            print(f"  {k:>2}/{len(syms)} {sym:<8} {len(b):>5} nến, {b[0]['d']} → {b[-1]['d']}", file=sys.stderr)
    if ok:
        store.save(st, HISTORY)
        size = HISTORY.stat().st_size / 1e6
        print(f"Ghi {HISTORY} ({size:.1f} MB): {len(st['bars'])} mã", file=sys.stderr)
    return 0 if ok == len(syms) else 1


if __name__ == "__main__":
    sys.exit(main())
