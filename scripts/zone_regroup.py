"""Dựng lại phiên vùng giá từ tick thô đã lưu, theo cách gộp lệnh quét mới (zone/collect.sweeps, 04/10/2026).

    venv\\Scripts\\python -m scripts.zone_regroup [THƯ_MỤC_TICK]

Thư mục: <ngày>/<MÃ>.json.gz dạng {"ticks": [[hh:mm:ss, giá, KL, side, luỹ kế], ...]} (Release order-flow-live,
mặc định ../algo-radar-lab/ticks). Chỉ thay phiên THẬT đã có trong kho và chỉ khi tổng KL khớp đúng — tick tải
lúc khác của cùng phiên phải ra cùng tổng; lệch thì giữ bản cũ và in ra. Phiên không còn tick giữ nguyên.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from zone import collect, profile, store

DEFAULT = Path(__file__).resolve().parents[2] / "algo-radar-lab" / "ticks"


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    changed = kept = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(d.glob("*.json.gz")):
            sym = f.name[:-8]
            st = store.load(sym)
            old = st["sessions"].get(d.name)
            if not old or old.get("est"):
                continue
            rows = json.load(gzip.open(f))["ticks"]
            ticks = [{"date": d.name, "time": t, "price": p, "vol": v, "side": s, "acc": a} for t, p, v, s, a in rows]
            new = collect.aggregate(ticks)
            if new is None or new["total"] != old["total"]:
                print(f"{sym} {d.name}: tổng KL lệch ({old['total']:,} vs {new and new['total']:,}) — giữ bản cũ")
                kept += 1
                continue
            a, b = profile.session_stats(d.name, old), profile.session_stats(d.name, new)
            if new["levels"] != old["levels"]:
                st["sessions"][d.name] = new
                store.save(st)
                changed += 1
                if b["big_buy_val"] is not None:
                    print(f"{sym} {d.name}: CM mua {a['big_buy_val']} → {b['big_buy_val']}, bán {a['big_sell_val']} → {b['big_sell_val']}")
    print(f"đổi {changed} phiên-mã, giữ {kept}")


if __name__ == "__main__":
    main()
