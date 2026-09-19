"""Ô chế độ: gắn mỗi phiên vào một ô rời rạc, rồi gom "đường đi 20 phiên sau" của mọi phiên lịch sử cùng ô
thành pool để dựng nón. Trục chọn theo phép đo thật (reports/measure-20-phien-2026-09-19.md), thứ tự từ
quan trọng → ít quan trọng; thiếu mẫu thì bỏ trục từ cuối (gộp về ô cha).

    vol    thấp / vừa / cao     phân vị 250 phiên của std lợi suất 20 phiên   → độ rộng nón
    upvol  thấp / vừa / cao     tỷ trọng KL rơi vào phiên tăng trong 20 phiên → lệch hướng (7/11 năm)
    st     xanh / đỏ            Supertrend (10, 3)
    spike  có / không           có phiên KL ≥ 2× TB20 trong 3 phiên gần nhất (8/11 năm)
    climax có / không           trần + KL bùng nổ + phá đỉnh 20 phiên trong 3 phiên gần nhất
    gap    có / không           |gap mở cửa hôm nay| > 1 %

Pool của một ô = ma trận (n, 20) lợi suất log TỪNG PHIÊN đã chia cho vol20 tại t (chuẩn hoá theo biến động,
để HPG và VCB so được với nhau); cone.py nhân lại vol của mã hôm nay.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import HORIZON, PATH_COLS

AXES = ("vol", "upvol", "st", "spike", "climax", "gap")
MIN_N = 200
LABELS = {
    "vol": {"low": "biến động thấp", "mid": "biến động vừa", "high": "biến động cao"},
    "upvol": {"low": "KL dồn phiên giảm", "mid": "KL cân bằng", "high": "KL dồn phiên tăng"},
    "st": {"up": "ST xanh", "down": "ST đỏ"},
    "spike": {"yes": "KL bất thường ≥2×", "no": ""},
    "climax": {"yes": "trần + KL + phá đỉnh", "no": ""},
    "gap": {"yes": "gap mở cửa >1 %", "no": ""},
}


def _tri(x: float, lo: float, hi: float) -> str:
    return "low" if x < lo else ("mid" if x <= hi else "high")


def regime_key(row) -> tuple | None:
    """Ô của một hàng đặc trưng (Series hoặc dict). None nếu thiếu dữ liệu warm-up."""
    try:
        vr, uv, st = float(row["vol20_rank"]), float(row["upvol_share"]), row["st_up"]
    except (KeyError, TypeError, ValueError):
        return None
    if np.isnan(vr) or np.isnan(uv) or st is None or (isinstance(st, float) and np.isnan(st)):
        return None
    return (
        _tri(vr, 0.33, 0.67),
        _tri(uv, 0.40, 0.60),
        "up" if bool(st) else "down",
        "yes" if bool(row["spike3"]) else "no",
        "yes" if bool(row["climax3"]) else "no",
        "yes" if bool(row["gap_big"]) else "no",
    )


def keys_for(f: pd.DataFrame) -> pd.Series:
    """Ô cho cả DataFrame (vector hoá); None ở hàng thiếu dữ liệu."""
    ok = f["vol20_rank"].notna() & f["upvol_share"].notna() & f["st_up"].notna()
    vol = pd.cut(f["vol20_rank"], [-0.01, 0.33, 0.67, 1.01], labels=["low", "mid", "high"]).astype(object)
    uv = pd.cut(f["upvol_share"], [-0.01, 0.40, 0.60, 1.01], labels=["low", "mid", "high"]).astype(object)
    st = f["st_up"].map({True: "up", False: "down", 1.0: "up", 0.0: "down"})
    yn = lambda s: s.fillna(False).astype(bool).map({True: "yes", False: "no"})
    keys = list(zip(vol, uv, st, yn(f["spike3"]), yn(f["climax3"]), yn(f["gap_big"])))
    return pd.Series([k if o else None for k, o in zip(keys, ok)], index=f.index, dtype=object)


def chips(key: tuple) -> list[str]:
    """Nhãn tiếng Việt cho giao diện, bỏ nhãn rỗng ("không có gì")."""
    out = []
    for ax, val in zip(AXES, key):
        lab = LABELS[ax].get(val, "")
        if lab:
            out.append(lab)
    return out


def build_pools(f: pd.DataFrame, keys: pd.Series | None = None) -> dict[tuple, np.ndarray]:
    """Pool cho MỌI cấp gộp: khoá là tiền tố của ô (độ dài 0..6). Chỉ lấy hàng có đủ 20 phiên sau
    và vol20 > 0. Mỗi hàng pool: 20 lợi suất log từng phiên / vol20_t (float32)."""
    if keys is None:
        keys = keys_for(f)
    ok = keys.notna() & f[PATH_COLS].notna().all(axis=1) & (f["vol20"] > 0)
    sub = f.loc[ok]
    cum = sub[PATH_COLS].to_numpy(dtype=np.float64)
    steps = np.diff(np.concatenate([np.zeros((len(sub), 1)), cum], axis=1), axis=1)
    steps = (steps / sub["vol20"].to_numpy()[:, None]).astype(np.float32)
    pools: dict[tuple, list[int]] = {}
    for i, k in enumerate(keys.loc[ok]):
        for level in range(len(AXES) + 1):
            pools.setdefault(tuple(k[:level]), []).append(i)
    return {k: steps[np.asarray(ix)] for k, ix in pools.items()}


def pool_for(key: tuple, pools: dict[tuple, np.ndarray], min_n: int = MIN_N) -> tuple[np.ndarray, int, int]:
    """(pool, cấp gộp, n). Cấp 0 = đủ 6 trục; mỗi cấp bỏ một trục từ cuối; cấp 6 = toàn cục."""
    for level in range(len(AXES) + 1):
        k = tuple(key[: len(AXES) - level])
        p = pools.get(k)
        if p is not None and len(p) >= min_n:
            return p, level, len(p)
    p = pools.get((), np.zeros((0, HORIZON), dtype=np.float32))
    return p, len(AXES), len(p)


def freq_up(pool: np.ndarray, h: int) -> float:
    """Tần suất tăng lịch sử của pool sau h phiên (lợi suất cộng dồn > 0). 0,5 nếu pool rỗng."""
    if len(pool) == 0:
        return 0.5
    return float((pool[:, :h].sum(axis=1) > 0).mean())
