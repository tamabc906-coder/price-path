"""Mồi kho Cá mập ẩn từ tick đã tải tay (bản mẫu algo-radar-lab): python -m scripts.algo_seed [THƯ_MỤC_TICK]

Mỗi phiên một thư mục <ngày>/<MÃ>.json.gz dạng {"ticks": [[hh:mm:ss, giá, KL, side, luỹ kế], ...]} (khuôn
Release của order-flow-live). Chỉ lấy mã trong danh mục KingStock. Chạy một lần; job zone tự ghi các phiên sau.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from common import store as hist
from job import watchlist
from zone import algo

DEFAULT = Path(__file__).resolve().parents[2] / "algo-radar-lab" / "ticks"


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    items, _ = watchlist.load()
    syms = {it["symbol"] for it in items}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        n = 0
        for f in sorted(d.glob("*.json.gz")):
            sym = f.name[:-8]
            if sym not in syms:
                continue
            rows = json.load(gzip.open(f))["ticks"]
            ticks = [{"time": t, "price": p, "vol": v, "side": s, "acc": a} for t, p, v, s, a in rows]
            algo.put(d.name, sym, algo.symbol_day(ticks))
            n += 1
        print(d.name, n, "mã")
    h = hist.load()
    closes = {s: {r[0]: float(r[4]) for r in h["bars"].get(s, [])} for s in syms}
    print("dựng", algo.build_site(closes), "phiên")


if __name__ == "__main__":
    main()
