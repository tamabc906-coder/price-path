"""Đặc trưng từ nến ngày — mọi cột tại hàng t chỉ dùng nến ≤ t; nhãn dùng shift(-h).

Công thức chép từ vn-stock-app/backend/app/indicators/ta.py (ATR Wilder, Donchian shift(1)) và
job/trend.py (Supertrend/EMA, list-dict — gọi thẳng rồi gắn cột để khớp 100 % với candle-radar).
Trục chế độ (model/regime.py) chỉ dùng: vol20_rank, upvol_share, st_up, spike3, climax3, gap_big.
Các cột còn lại là feature cho LightGBM (model/direction.py). Đường đi 20 phiên sau (p1..p20, lợi
suất log cộng dồn) là nguyên liệu dựng pool cho nón.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from job import trend

HORIZON = 20
LIMIT_PCT = 0.065          # trần/sàn: ±6,5 % (HOSE ±7 %)
GAP_BIG = 0.01             # |gap mở cửa| > 1 % = "vừa có chuyện"
SPIKE_RATIO = 2.0          # KL ≥ 2× trung bình 20 phiên
RANK_WINDOW = 250          # phân vị biến động so 1 năm
PATH_COLS = [f"p{k}" for k in range(1, HORIZON + 1)]


def frame(bars: list[dict]) -> pd.DataFrame:
    """list[dict] khuôn dnse → DataFrame d,o,h,l,c,v (d là Timestamp)."""
    df = pd.DataFrame(bars)[["d", "o", "h", "l", "c", "v"]].copy()
    df["d"] = pd.to_datetime(df["d"])
    df["v"] = df["v"].astype(float)
    return df.reset_index(drop=True)


def _rolling_rank(s: pd.Series, n: int) -> pd.Series:
    """Phân vị của giá trị hôm nay trong n phiên TRƯỚC (0..1). NaN khi chưa đủ n."""
    return s.rolling(n + 1).apply(lambda x: float((x[-1] > x[:-1]).mean()), raw=True)


def build_features(df: pd.DataFrame, idx: pd.DataFrame | None = None) -> pd.DataFrame:
    """df: nến một mã (frame()). idx: nến VNINDEX (frame()) hoặc None.
    Trả DataFrame cùng số hàng, cột d, c và các đặc trưng/nhãn; hàng warm-up là NaN."""
    c, o, h, l, v = df["c"], df["o"], df["h"], df["l"], df["v"]
    r1 = np.log(c / c.shift(1))
    f = pd.DataFrame({"d": df["d"], "c": c, "v": v})

    # --- lợi suất & biến động ---
    for k in (1, 5, 10, 20):
        f[f"r{k}"] = np.log(c / c.shift(k))
    f["vol20"] = r1.rolling(20).std()
    f["vol20_rank"] = _rolling_rank(f["vol20"], RANK_WINDOW)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    f["atr_pct"] = tr.ewm(alpha=1 / 14, adjust=False).mean() / c
    for k in (5, 10, 20):
        f[f"z{k}"] = f[f"r{k}"] / (f["vol20"] * np.sqrt(k))

    # --- xu hướng (Supertrend/EMA list-dict, khớp candle-radar) ---
    bars = df.rename(columns={"d": "d"}).to_dict("records")
    st = trend.supertrend(bars)
    em10, em50 = trend.ema(bars, 10), trend.ema(bars, 50)
    f["st_up"] = [x["up"] if x else np.nan for x in st]
    f["st_dist"] = [(b["c"] - x["line"]) / b["c"] if x else np.nan for b, x in zip(bars, st)]
    f["ema10_pos"] = [b["c"] / e - 1 if e is not None else np.nan for b, e in zip(bars, em10)]
    f["ema50_pos"] = [b["c"] / e - 1 if e is not None else np.nan for b, e in zip(bars, em50)]

    # --- vị trí ---
    hi20, lo20 = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    f["don20_pos"] = (c - lo20) / (hi20 - lo20).replace(0, np.nan)
    f["dd_from_high60"] = c / c.rolling(60).max() - 1

    # --- khối lượng ---
    vma20 = v.rolling(20).mean()
    f["vol_ratio"] = v / vma20.replace(0, np.nan)
    f["vol_z20"] = (v - vma20) / v.rolling(20).std().replace(0, np.nan)
    f["spike3"] = f["vol_ratio"].rolling(3).max() >= SPIKE_RATIO
    up = (c > c.shift(1)).astype(float)
    f["upvol_share"] = (v * up).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)

    # --- biên độ & sự kiện ---
    chg = c / c.shift(1) - 1
    f["hit_ceiling"] = chg >= LIMIT_PCT
    f["hit_floor"] = chg <= -LIMIT_PCT
    f["n_ceiling5"] = f["hit_ceiling"].astype(float).rolling(5).sum()
    f["gap"] = o / c.shift(1) - 1
    f["gap_big"] = f["gap"].abs() > GAP_BIG
    body = (c - o).abs()
    avg_body = body.rolling(10).mean().shift(1)
    rng = (h - l).replace(0, np.nan)
    # cùng 5 điều kiện với job/patterns.py::_limit_up_climax (vector hoá)
    climax = ((chg >= LIMIT_PCT) & (c > o) & (body >= 2 * avg_body) & ((c - l) / rng >= 0.8)
              & (v >= 2 * vma20.shift(1)) & (c > c.shift(1).rolling(20).max()))
    f["climax"] = climax
    f["climax3"] = climax.rolling(3).max().astype(bool)

    # --- thị trường (chỉ cho LightGBM) ---
    if idx is not None and len(idx):
        ic = idx["c"]
        ib = idx.to_dict("records")
        ist, iem50 = trend.supertrend(ib), trend.ema(ib, 50)
        g = pd.DataFrame({
            "d": idx["d"],
            "idx_r5": np.log(ic / ic.shift(5)), "idx_r20": np.log(ic / ic.shift(20)),
            "idx_vol20": np.log(ic / ic.shift(1)).rolling(20).std(),
            "idx_st_up": [x["up"] if x else np.nan for x in ist],
            "idx_above_ema50": [(b["c"] > e) if e is not None else np.nan for b, e in zip(ib, iem50)],
        })
        f = f.merge(g, on="d", how="left")
        for col in ("idx_r5", "idx_r20", "idx_vol20", "idx_st_up", "idx_above_ema50"):
            f[col] = f[col].ffill(limit=3)
    f["dow"] = f["d"].dt.dayofweek

    # --- nhãn & đường đi tương lai (chỉ dùng khi đo/huấn luyện) ---
    for k in (5, 10, 20):
        f[f"fr{k}"] = np.log(c.shift(-k) / c)
        f[f"y{k}"] = f[f"fr{k}"] > 0
    for k in range(1, HORIZON + 1):
        f[f"p{k}"] = np.log(c.shift(-k) / c)
    return f


def build_all(store: dict, symbols: list[str], index_symbol: str, bars_fn) -> pd.DataFrame:
    """Đặc trưng cho nhiều mã, gộp một DataFrame có cột `symbol`. bars_fn(store, sym) → list[dict]."""
    idx_bars = bars_fn(store, index_symbol)
    idx = frame(idx_bars) if idx_bars else None
    parts = []
    for sym in symbols:
        b = bars_fn(store, sym)
        if len(b) < 60:
            continue
        f = build_features(frame(b), idx)
        f.insert(0, "symbol", sym)
        parts.append(f)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
