"""Sinh docs/data/smc.json từ kho nến hiện có (không gọi DNSE): python -m scripts.smc_seed

Chạy một lần để tab "Order BK" có dữ liệu ngay; từ phiên sau job daily 15:40 tự ghi.
"""
from __future__ import annotations

import json
from datetime import datetime

from common import store
from common.config import HISTORY, SITE_DATA, TZ
from job import smc, watchlist


def main() -> None:
    items, src = watchlist.load()
    hist = store.load(HISTORY)
    syms = {it["symbol"] for it in items}
    trade = max(hist["bars"][s][-1][0] for s in syms if hist["bars"].get(s))
    out = smc.scan(hist, items, trade)
    out["generated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    p = SITE_DATA / "smc.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    near = [f"{x['symbol']}:{z['kind']}/{z['pos']}" for x in out["symbols"] for z in x["zones"] if z["pos"] != "far"]
    print(f"phiên {trade} · {len(out['symbols'])} mã · {p.stat().st_size // 1024} KB · danh mục từ {src}")
    print("trong/gần vùng:", ", ".join(near) or "không có")


if __name__ == "__main__":
    main()
