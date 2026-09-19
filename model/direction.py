"""Xác suất hướng bằng LightGBM — có CỔNG: chỉ được bật nếu walk-forward thắng mốc ở ≥ 4/5 năm.

Nhãn: y_h = đóng cửa sau h phiên > đóng cửa hôm nay (h = 5, 10). Walk-forward theo năm: học ≤ năm t−1 (bỏ 35
ngày lịch cuối để nhãn không nhìn sang năm t — purge), thử năm t. Ba mốc mỗi năm:
  * luôn tăng      — accuracy = tỷ lệ tăng thật của năm (mốc khó vì 39 mã sống sót thường tăng)
  * tần suất ô     — P(tăng) của pool chế độ (model/regime.py) trên cùng pool anchored → Brier
  * 0,5            — Brier 0,25
Cổng: enabled = (Brier LGBM < Brier tần-suất-ô ở ≥ 4/5 năm trọn) AND (acc LGBM > acc luôn-tăng ở ≥ 4/5 năm trọn).
Mặc định TẮT. Actions chỉ nạp booster .txt (không huấn luyện); import lightgbm lỗi → job dùng tần suất ô.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import ARTIFACTS

FEATURES = [
    "r1", "r5", "r10", "r20", "z5", "z10", "z20", "vol20", "vol20_rank", "atr_pct",
    "st_up", "st_dist", "ema10_pos", "ema50_pos", "don20_pos", "dd_from_high60",
    "vol_ratio", "vol_z20", "spike3", "upvol_share", "hit_ceiling", "hit_floor", "n_ceiling5",
    "gap", "gap_big", "climax3", "idx_r5", "idx_r20", "idx_vol20", "idx_st_up", "idx_above_ema50", "dow",
]
PARAMS = {
    "objective": "binary", "num_leaves": 15, "min_data_in_leaf": 200, "learning_rate": 0.03,
    "feature_fraction": 0.7, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "verbose": -1, "seed": 7, "num_threads": 4,
}
N_ROUNDS = 300
PURGE_DAYS = 35
PASS_YEARS = 4
HS = (5, 10)
GATE = ARTIFACTS / "gate.json"


def booster_path(h: int) -> Path:
    return ARTIFACTS / f"lgbm_h{h}.txt"


def matrix(f: pd.DataFrame) -> np.ndarray:
    """Ma trận đặc trưng (float32); bool → 0/1; cột thiếu (không có VNINDEX) → NaN (LightGBM tự xử lý)."""
    m = pd.DataFrame(index=f.index)
    for c in FEATURES:
        m[c] = f[c].astype(float) if c in f.columns else np.nan
    return m.to_numpy(dtype=np.float32)


def train(f: pd.DataFrame, h: int, rounds: int = N_ROUNDS, params: dict | None = None):
    import lightgbm as lgb
    y = f[f"y{h}"].astype(int).to_numpy()
    ds = lgb.Dataset(matrix(f), label=y, feature_name=FEATURES, free_raw_data=False)
    return lgb.train(params or PARAMS, ds, num_boost_round=rounds)


def predict(booster, f: pd.DataFrame) -> np.ndarray:
    return booster.predict(matrix(f))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(((p - y) ** 2).mean())


def walk_forward(f: pd.DataFrame, pool_freq: pd.DataFrame, years: list[int], h: int) -> list[dict]:
    """pool_freq: cột `p{h}` = tần suất ô (đã anchored như scripts/evaluate.py) cùng index với f.
    Trả một dict chỉ số mỗi năm."""
    out = []
    lab = f"y{h}"
    for Y in years:
        cutoff = pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=PURGE_DAYS)
        tr = f[(f["d"] < cutoff) & f[lab].notna()]
        te = f[(f["d"].dt.year == Y) & f[lab].notna()]
        if len(tr) < 1000 or te.empty:
            continue
        bst = train(tr, h)
        p = predict(bst, te)
        y = te[lab].astype(float).to_numpy()
        base = float(tr[lab].astype(float).mean())
        pf = pool_freq.loc[te.index, f"p{h}"].to_numpy(dtype=float)
        imp = dict(zip(FEATURES, bst.feature_importance("gain")))
        top = sorted(imp.items(), key=lambda kv: -kv[1])[:5]
        out.append({
            "year": Y, "n_train": len(tr), "n_test": len(te),
            "up_rate": float(y.mean()),
            "acc_lgbm": float(((p >= 0.5) == (y == 1)).mean()),
            "acc_always_up": float(y.mean()),
            "brier_lgbm": brier(p, y), "brier_freq": brier(pf, y),
            "brier_global": brier(np.full_like(y, base), y), "brier_half": brier(np.full_like(y, 0.5), y),
            "p_mean": float(p.mean()), "p_q90": float(np.percentile(p, 90)),
            "top_features": [k for k, _ in top],
        })
    return out


def gate(metrics: dict[int, list[dict]], last_year: int) -> dict:
    """Quyết định bật/tắt từng h, chỉ tính năm trọn (< last_year)."""
    res = {"enabled": False, "per_h": {}}
    for h, rows in metrics.items():
        full = [r for r in rows if r["year"] < last_year]
        need = min(PASS_YEARS, len(full))
        w_b = sum(r["brier_lgbm"] < r["brier_freq"] for r in full)
        w_a = sum(r["acc_lgbm"] > r["acc_always_up"] for r in full)
        ok = bool(full) and w_b >= need and w_a >= need
        res["per_h"][str(h)] = {"enabled": ok, "wins_brier": f"{w_b}/{len(full)}", "wins_acc": f"{w_a}/{len(full)}",
                                "need": need, "rows": rows}
    res["enabled"] = all(v["enabled"] for v in res["per_h"].values()) if res["per_h"] else False
    return res


def save_gate(g: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    GATE.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")


def load_gate() -> dict:
    try:
        return json.loads(GATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"enabled": False, "per_h": {}}


def load_booster(h: int):
    """None nếu thiếu file hoặc lightgbm không import được — job rơi về tần suất ô."""
    p = booster_path(h)
    if not p.exists():
        return None
    try:
        import lightgbm as lgb
        return lgb.Booster(model_file=str(p))
    except Exception:  # noqa: BLE001
        return None
