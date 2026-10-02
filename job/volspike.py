"""KL đột biến (người dùng yêu cầu 02/10/2026): phiên có KL ≥ vol_mult × TB 20 phiên TRƯỚC, nến xanh (đóng > mở)
và giá tăng ≥ min_pct so với đóng cửa phiên trước. Chạy trong job daily ngay sau khi nối nến hôm nay vào kho.

Hàm thuần trên hàng kho [d, o, h, l, c, v] (data/history.json) — không gọi mạng. Kết quả → docs/data/spike.json
(tab "KL đột biến") + push (job/push.spike_payload).

Chưa đo lợi thế: đây là chuông theo dõi theo ý người dùng. Nhật ký có +5p/+10p để tự xem tín hiệu đi tiếp hay xả.
"""
from __future__ import annotations

AVG_N = 20
LOG_DAYS = 60      # số phiên gần nhất quét cho nhật ký
CHART_N = 30       # số nến kèm theo mỗi mã đạt hôm nay
FWD = (5, 10)


def hit_at(rows: list[list], i: int, vol_mult: float, min_pct: float) -> dict | None:
    """Nến rows[i] đạt luật? Cần đủ AVG_N phiên trước; TB20 không gồm phiên i."""
    if i < AVG_N or i >= len(rows):
        return None
    _, o, _, _, c, v = rows[i]
    pc = rows[i - 1][4]
    avg = sum(r[5] for r in rows[i - AVG_N:i]) / AVG_N
    if not (avg > 0 and pc > 0):
        return None
    pct = c / pc - 1
    if v >= vol_mult * avg and c > o and pct >= min_pct - 1e-12:
        return {"date": rows[i][0], "close": round(c, 4), "pct": round(pct, 4), "vol": int(v),
                "avg20": int(round(avg)), "ratio": round(v / avg, 2)}
    return None


def scan(hist: dict, items: list[dict], trade_iso: str, cfg: dict) -> dict:
    """{trade_date, rule, today: [...], log: [...]} cho các mã trong danh mục."""
    vm, mp = float(cfg.get("spike_vol_mult", 2.0)), float(cfg.get("spike_min_pct", 0.03))
    names = {it["symbol"]: it.get("company_name") or "" for it in items}
    today, log = [], []
    for sym in sorted(names):
        rows = hist["bars"].get(sym) or []
        if len(rows) <= AVG_N:
            continue
        for i in range(max(AVG_N, len(rows) - LOG_DAYS), len(rows)):
            h = hit_at(rows, i, vm, mp)
            if not h:
                continue
            h["symbol"], h["name"] = sym, names[sym]
            for k in FWD:
                h[f"r{k}"] = round(rows[i + k][4] / rows[i][4] - 1, 4) if i + k < len(rows) else None
            # 30 nến tới phiên đạt + tối đa 10 nến sau (để thấy giá đi tiếp hay xả), thêm 20 nến đầu chỉ để giao diện
            # tính đường TB20 KL; `at` = vị trí phiên đạt trong `bars`
            a = max(0, i - CHART_N + 1 - AVG_N)
            h["bars"] = [[r[0], r[1], r[2], r[3], r[4], int(r[5])] for r in rows[a:i + 1 + max(FWD)]]
            h["at"] = i - a
            log.append(h)
            if rows[i][0] == trade_iso:
                today.append(h)
    today.sort(key=lambda x: -x["pct"])
    log.sort(key=lambda x: (x["date"], x["pct"]), reverse=True)
    return {"trade_date": trade_iso, "rule": {"vol_mult": vm, "min_pct": mp, "avg_n": AVG_N, "log_days": LOG_DAYS},
            "today": today, "log": log}
