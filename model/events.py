"""Sự kiện có điều kiện — thứ DUY NHẤT đo ra có hướng (nón chế độ, LightGBM, KL × thân nến đều ≈ mốc chung).

Bốn sự kiện, định nghĩa cố định trước khi đo lại trong khung price-path (scripts/measure_events.py):

    climax           Trần + KL bùng nổ + phá đỉnh 20p — cùng 5 điều kiện model/features.py (≡ candle-radar)
    sc               Bán tháo cao trào Wyckoff — model/wyckoff.py (chép nguyên wyckoff-radar)
    red_vol_demand   Nến đỏ, KL ≥ 1,5× TB20 trước, tại vùng cầu — price-path-flow-lab trạng thái B2
    gap_fill_demand  Nến đỏ gap giảm ≥ 1 % rồi nến xanh lấp gap, cả mẫu 3 nến tại vùng cầu — demand-candle-lab

Mọi cột tại nến i chỉ dùng nến ≤ i. Chống đếm trùng: sự kiện chỉ được tính khi 5 phiên trước đó chưa có lần nào
của CÙNG loại (một đợt bán tháo kéo 3 phiên là một sự kiện, không phải ba).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import wyckoff
from .features import LIMIT_PCT

CODES = ("climax", "sc", "red_vol_demand", "gap_fill_demand")
NAMES = {
    "climax": "Trần + KL bùng nổ + phá đỉnh 20p",
    "sc": "Bán tháo cao trào (Wyckoff SC)",
    "red_vol_demand": "Nến đỏ KL lớn tại đáy",
    "gap_fill_demand": "Gap giảm được lấp tại đáy",
}
DEDUP = 5
ZONE_WIN, ZONE_TOL, DROP_WIN, DROP_PCT = 60, 0.03, 10, 0.05
VOL_MULT = 1.5
GAP_PCT = 0.01


def detect(bars: list[dict]) -> pd.DataFrame:
    """bars: list[dict] khuôn dnse (cũ → mới). Trả DataFrame d + 4 cột bool (đã chống đếm trùng)."""
    df = pd.DataFrame(bars)[["d", "o", "h", "l", "c", "v"]].copy()
    df["d"] = pd.to_datetime(df["d"])
    o, h, l, c, v = df["o"], df["h"], df["l"], df["c"], df["v"].astype(float)
    c1 = c.shift(1)
    out = pd.DataFrame({"d": df["d"]})

    # climax: chép 5 điều kiện của model/features.py (vma20 gồm hôm nay, shift(1) = 20 phiên trước)
    chg = c / c1 - 1
    body = (c - o).abs()
    avg_body = body.rolling(10).mean().shift(1)
    rng = (h - l).replace(0, np.nan)
    vma20 = v.rolling(20).mean()
    out["climax"] = ((chg >= LIMIT_PCT) & (c > o) & (body >= 2 * avg_body) & ((c - l) / rng >= 0.8)
                     & (v >= 2 * vma20.shift(1)) & (c > c.shift(1).rolling(20).max()))

    # sc: sự kiện Wyckoff gắn tại nến phát hiện
    sc = np.zeros(len(df), dtype=bool)
    for e in wyckoff.analyze(bars).events:
        if e["id"] == "sc":
            sc[e["at"]] = True
    out["sc"] = sc

    # red_vol_demand: vùng cầu 1 nến (flow-lab: đáy hôm nay ≤ 1,03 × đáy 60p trước, lợi suất 10p tới hôm nay ≤ −5 %)
    vprev = v.shift(1).rolling(20).mean()
    min60 = l.shift(1).rolling(ZONE_WIN).min()
    demand1 = (l <= (1 + ZONE_TOL) * min60) & (c / c.shift(DROP_WIN) - 1 <= -DROP_PCT)
    out["red_vol_demand"] = (c < o) & (v >= VOL_MULT * vprev) & demand1

    # gap_fill_demand: a = i−2, p = i−1 (đỏ, mở gap xuống ≥ 1 % so đóng a), c = i (xanh, đóng trên mở của p).
    # Vùng cầu của mẫu 3 nến (demand-candle-lab::in_demand, nb = 3): đáy mẫu ≤ 1,03 × đáy 60p TRƯỚC mẫu,
    # giá giảm ≥ 5 % trong 10 phiên trước mẫu.
    po, pc = o.shift(1), c.shift(1)
    gap = (pc < po) & (po <= c.shift(2) * (1 - GAP_PCT)) & (c > o) & (c > po)
    low_pat = l.rolling(3).min()
    low_prev = l.shift(3).rolling(ZONE_WIN).min()
    drop = c.shift(3) / c.shift(3 + DROP_WIN) - 1
    out["gap_fill_demand"] = gap & (low_pat <= (1 + ZONE_TOL) * low_prev) & (drop <= -DROP_PCT)

    for k in CODES:
        raw = out[k].fillna(False).astype(bool).to_numpy()
        out[k] = dedup(raw)
    return out


def dedup(raw: np.ndarray, n: int = DEDUP) -> np.ndarray:
    """Giữ lần đầu: nến i được tính nếu raw[i] và n nến trước không có lần nào ĐÃ ĐƯỢC TÍNH (nhân quả)."""
    keep = np.zeros(len(raw), dtype=bool)
    last = -10 ** 9
    for i in np.flatnonzero(raw):
        if i - last > n:
            keep[i] = True
            last = i
    return keep
