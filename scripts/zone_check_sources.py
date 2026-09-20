"""Đối chiếu phân loại Mua/Bán chủ động giữa VNDirect (side PB/PS — nguồn chính của zone/) và Vietcap
(matchType b/s — khớp đúng từng lệnh với app CTCK người dùng chụp 18/09/2026). Chạy MỘT LẦN khi
chọn nguồn; Vietcap chỉ trả 100 lệnh/lần nên không dùng để gom cả phiên.

    python -m scripts.zone_check_sources FPT HPG        # mặc định 5 trang Vietcap = 500 lệnh cuối phiên

Ghép hai bên theo (giờ HH:MM:SS, giá, KL) sau khi gộp tick VNDirect thành lệnh (zone/collect.py::orders);
in tỷ lệ trùng PS↔b (mua), PB↔s (bán). Dưới 90 % thì quy tắc phân loại hai bên khác nhau — phải xem lại.

Kết quả 20/09/2026 (phiên 18/09, 500 lệnh cuối mỗi mã): FPT/HPG/VNM đều 100 % — với điều kiện đọc PB là BÁN
chủ động, PS là MUA chủ động (tên side của VNDirect là bên bị động). Trước khi phát hiện, đọc xuôi cho 0 %.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime

import httpx

from common.config import BROWSER_HEADERS, HTTP_TIMEOUT, TZ
from common.vndirect import VndirectClient
from zone.collect import orders

VCI_URL = "https://trading.vietcap.com.vn/api/market-watch/LEData/getAll"


def vietcap(symbol: str, pages: int) -> list[dict]:
    out: list[dict] = []
    trunc = None
    h = dict(BROWSER_HEADERS, **{"Content-Type": "application/json", "Origin": "https://trading.vietcap.com.vn"})
    with httpx.Client(headers=h, timeout=HTTP_TIMEOUT) as c:
        for _ in range(pages):
            r = c.post(VCI_URL, json={"symbol": symbol, "limit": 100, "truncTime": trunc})
            r.raise_for_status()
            rows = r.json()
            if not rows:
                break
            for x in rows:
                t = datetime.fromtimestamp(int(x["truncTime"]), TZ).strftime("%H:%M:%S")
                out.append({"time": t, "price": float(x["matchPrice"]) / 1000, "vol": int(float(x["matchVol"])),
                            "side": x["matchType"]})
            trunc = rows[-1]["truncTime"]
    return out


def compare(vnd: list[dict], vci: list[dict]) -> tuple[Counter, int]:
    """Ghép theo (giờ, giá, KL) — mỗi tick VNDirect chỉ ghép một lần. Trả (đếm cặp side, số không ghép được)."""
    pool: dict[tuple, list[str]] = {}
    for t in orders(vnd):
        pool.setdefault((t["time"], round(t["price"], 3), t["vol"]), []).append(t["side"])
    pairs: Counter = Counter()
    unmatched = 0
    for x in vci:
        k = (x["time"], round(x["price"], 3), x["vol"])
        sides = pool.get(k)
        if not sides:
            unmatched += 1
            continue
        pairs[(sides.pop(), x["side"])] += 1
    return pairs, unmatched


def main() -> None:
    syms = sys.argv[1:] or ["FPT"]
    for sym in syms:
        with VndirectClient() as c:
            vnd = c.latest_session(sym)
        vci = vietcap(sym, pages=5)
        pairs, unmatched = compare(vnd, vci)
        agree = pairs[("PS", "b")] + pairs[("PB", "s")]
        judged = sum(v for (a, b), v in pairs.items() if a in ("PB", "PS") and b in ("b", "s"))
        print(f"{sym}: VNDirect {len(vnd)} tick, Vietcap {len(vci)} lệnh, không ghép được {unmatched}")
        for k, v in sorted(pairs.items(), key=lambda kv: -kv[1]):
            print(f"   {k[0]:>4} ↔ {k[1]:<8} {v}")
        print(f"   trùng hướng {agree}/{judged} = {agree / judged:.1%}" if judged else "   không có cặp nào để so")


if __name__ == "__main__":
    main()
