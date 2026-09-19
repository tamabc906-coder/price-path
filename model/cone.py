"""Nón xác suất: block bootstrap trên pool của ô chế độ.

Mỗi đường mô phỏng 20 phiên = nối 4 khối 5 phiên liên tiếp, mỗi khối cắt từ một đường lịch sử ngẫu nhiên
trong pool tại vị trí ngẫu nhiên (giữ tự tương quan ngắn hạn, không "nhớ" quá 5 phiên). Pool đã chuẩn hoá
theo biến động nên nhân lại vol20 của mã hôm nay; kẹp mỗi phiên trong ±ln(1,07) (biên độ HOSE); cộng dồn.
Kết quả là lợi suất log cộng dồn; giá = price0 × exp(·). Không có công thức giá mục tiêu nào ở đây — nón
thuần là thống kê của những gì đã xảy ra.
"""
from __future__ import annotations

import hashlib

import numpy as np

from .features import HORIZON

N_SIM = 2000
BLOCK = 5
CLIP = float(np.log(1.07))
HS = (5, 10, 20)
QS = (5, 10, 25, 50, 75, 90, 95)


def seed_for(symbol: str, day: str) -> int:
    """Seed tái lập được theo (mã, ngày) — chạy lại job cùng ngày ra cùng nón."""
    return int(hashlib.sha1(f"{symbol}|{day}".encode()).hexdigest()[:8], 16)


def simulate_batch(vols: np.ndarray, pool: np.ndarray, n: int = N_SIM, block: int = BLOCK,
                   rng: np.random.Generator | None = None) -> np.ndarray:
    """vols: (m,) vol20 của m hàng dùng chung pool. Trả (m, n, 20) lợi suất log cộng dồn."""
    rng = rng or np.random.default_rng()
    m = len(vols)
    if len(pool) == 0:
        return np.zeros((m, n, HORIZON), dtype=np.float32)
    nblk = HORIZON // block
    rows = rng.integers(0, len(pool), size=(m, n, nblk))
    starts = rng.integers(0, HORIZON - block + 1, size=(m, n, nblk))
    offs = np.arange(block)
    idx = (starts[..., None] + offs).reshape(m, n, HORIZON)                 # vị trí trong đường gốc
    src = np.repeat(rows[..., None], block, axis=3).reshape(m, n, HORIZON)  # đường gốc của từng phiên
    steps = pool[src, idx] * vols.astype(np.float32)[:, None, None]
    np.clip(steps, -CLIP, CLIP, out=steps)
    return np.cumsum(steps, axis=2)


def simulate(vol_t: float, pool: np.ndarray, n: int = N_SIM, block: int = BLOCK, seed: int | None = None) -> np.ndarray:
    """(n, 20) cho một mã."""
    return simulate_batch(np.array([vol_t]), pool, n, block, np.random.default_rng(seed))[0]


def quantiles_batch(cum: np.ndarray, hs=HS, qs=QS) -> np.ndarray:
    """cum: (m, n, 20) → (m, len(hs), len(qs)) phân vị lợi suất log tại các mốc h."""
    sel = cum[:, :, [h - 1 for h in hs]]                    # (m, n, H)
    return np.percentile(sel, qs, axis=1).transpose(1, 2, 0)  # (m, H, Q)


def quantiles(paths: np.ndarray, price0: float, hs=HS, qs=QS) -> dict[int, dict[int, float]]:
    """{h: {q: giá}} cho một mã — giá nghìn đồng như DNSE, làm tròn 2 chữ số."""
    qb = quantiles_batch(paths[None, ...], hs, qs)[0]
    return {h: {q: round(float(price0 * np.exp(qb[i, j])), 2) for j, q in enumerate(qs)} for i, h in enumerate(hs)}


def scenarios(paths: np.ndarray, price0: float, k: int = 2, iters: int = 15, seed: int = 0) -> list[dict]:
    """Hai kịch bản xác suất cao nhất: k-means (k=2) trên hình dáng đường mô phỏng, trả tâm cụm + tỷ trọng,
    xếp tỷ trọng giảm dần. 'A 57 %' = 57 % đường giống A hơn B, KHÔNG phải 57 % chắc giá đi đúng A."""
    if len(paths) < k:
        return []
    rng = np.random.default_rng(seed)
    cent = paths[rng.choice(len(paths), k, replace=False)].astype(np.float64)
    lab = np.zeros(len(paths), dtype=int)
    for _ in range(iters):
        d = ((paths[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for j in range(k):
            if (lab == j).any():
                cent[j] = paths[lab == j].mean(axis=0)
    out = []
    for j in range(k):
        w = float((lab == j).mean())
        out.append({"weight": round(w, 3), "path": [round(float(price0 * np.exp(x)), 2) for x in cent[j]]})
    out.sort(key=lambda s: -s["weight"])
    for name, s in zip("AB", out):
        s["name"] = name
    return out
