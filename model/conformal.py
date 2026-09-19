"""Tự sửa cỡ nón — Adaptive Conformal Inference (Gibbs & Candès 2021) rút gọn.

Mỗi cặp (h, mức 50/80/90 %) giữ một hệ số giãn s ∈ [0,5; 3]: nón hiển thị = trung vị + s × (phân vị thô − trung vị).
Mỗi phiên, khi nón đã phát h phiên trước đến hạn, chấm tỷ lệ mã có giá thật nằm trong nón (một con số cho cả
danh mục — 39 mã cùng ngày không độc lập) rồi cập nhật: s ← s · exp(γ · (mục tiêu − tỷ lệ trúng)). Trúng ít hơn
mục tiêu → nới; nhiều hơn → co. Coverage rolling 250 phiên chỉ để hiển thị.
Trạng thái là dict JSON thuần (model/artifacts/conformal_state.json), không phụ thuộc numpy.
"""
from __future__ import annotations

import math

LEVELS = (50, 80, 90)
# (q thấp, q cao) của mỗi mức trong bộ phân vị cone.QS = (5, 10, 25, 50, 75, 90, 95)
LEVEL_QS = {50: (25, 75), 80: (10, 90), 90: (5, 95)}
GAMMA = 0.05
WINDOW = 250
S_MIN, S_MAX = 0.5, 3.0


def new_state(hs=(5, 10, 20), gamma: float = GAMMA, window: int = WINDOW) -> dict:
    return {"gamma": gamma, "window": window,
            "levels": {str(h): {str(lv): {"s": 1.0, "hits": []} for lv in LEVELS} for h in hs}}


def scale(state: dict, h: int, level: int) -> float:
    return float(state["levels"][str(h)][str(level)]["s"])


def adjust(q_log: dict[int, float], state: dict, h: int) -> dict[int, float]:
    """q_log: {q: lợi suất log} của một mốc h (phải có q 50). Trả bản đã giãn theo s của từng mức."""
    med = q_log[50]
    out = dict(q_log)
    for lv, (lo, hi) in LEVEL_QS.items():
        s = scale(state, h, lv)
        out[lo] = med + s * (q_log[lo] - med)
        out[hi] = med + s * (q_log[hi] - med)
    return out


def update(state: dict, h: int, level: int, hit_rate: float) -> float:
    """Ghi tỷ lệ trúng của một ngày cho (h, mức), cập nhật s. Trả s mới."""
    node = state["levels"][str(h)][str(level)]
    target = level / 100.0
    s = float(node["s"]) * math.exp(float(state.get("gamma", GAMMA)) * (target - hit_rate))
    node["s"] = round(min(S_MAX, max(S_MIN, s)), 4)
    hits = node["hits"]
    hits.append(round(float(hit_rate), 4))
    del hits[: max(0, len(hits) - int(state.get("window", WINDOW)))]
    return node["s"]


def coverage(state: dict, h: int, level: int, last: int | None = None) -> float | None:
    """Coverage rolling (toàn cửa sổ, hoặc `last` ngày gần nhất). None khi chưa có gì."""
    hits = state["levels"][str(h)][str(level)]["hits"]
    if last:
        hits = hits[-last:]
    return round(sum(hits) / len(hits), 4) if hits else None


def hit(q_log_adj: dict[int, float], realized_log: float, level: int) -> bool:
    lo, hi = LEVEL_QS[level]
    return q_log_adj[lo] <= realized_log <= q_log_adj[hi]
