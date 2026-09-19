"""Huấn luyện + kiểm định LightGBM xác suất hướng, quyết định cổng bật/tắt. Chạy TAY trên máy dev.

    venv\\Scripts\\python -m scripts.train_direction --from 2021 --md > reports/walkforward-<ngày>.md

Ghi: model/artifacts/lgbm_h5.txt, lgbm_h10.txt (booster cuối, học trên toàn bộ dữ liệu), gate.json (bảng theo năm
+ quyết định). Actions chỉ nạp các file này. Mốc "tần suất ô" tính anchored y như scripts/evaluate.py.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from common import store
from common.config import HISTORY, INDEX_SYMBOL, TZ
from model import direction, regime
from model.features import build_all

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def anchored_pool_freq(f: pd.DataFrame, keys: pd.Series, years: list[int]) -> pd.DataFrame:
    """Tần suất tăng của ô chế độ cho mỗi hàng năm Y, pool chỉ từ trước Y (purge 35 ngày)."""
    out = pd.DataFrame(index=f.index, columns=["p5", "p10"], dtype=float)
    for Y in years:
        cutoff = pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=35)
        train = f[f["d"] < cutoff]
        pools = regime.build_pools(train, keys.loc[train.index])
        te_ix = f.index[(f["d"].dt.year == Y) & keys.notna()]
        cache: dict[tuple, tuple[float, float]] = {}
        for i in te_ix:
            k = keys.loc[i]
            if k not in cache:
                pool, _, _ = regime.pool_for(k, pools)
                cache[k] = (regime.freq_up(pool, 5), regime.freq_up(pool, 10))
            out.loc[i, ["p5", "p10"]] = cache[k]
    return out.fillna(0.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_year", type=int, default=2021)
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--no-save", action="store_true", help="chỉ đo, không ghi booster/gate")
    ap.add_argument("--drop", default="", help="bỏ đặc trưng (phẩy) hoặc 'idx' = bỏ cả nhóm VN-Index")
    a = ap.parse_args()
    if a.drop:
        drop = {c for c in direction.FEATURES if c.startswith("idx_")} if a.drop == "idx" else set(a.drop.split(","))
        direction.FEATURES[:] = [c for c in direction.FEATURES if c not in drop]
        log(f"bỏ {len(drop)} đặc trưng, còn {len(direction.FEATURES)}")

    st = store.load(HISTORY)
    syms = sorted(s for s in st["bars"] if s != INDEX_SYMBOL)
    log(f"đặc trưng {len(syms)} mã…")
    f = build_all(st, syms, INDEX_SYMBOL, store.bars)
    keys = regime.keys_for(f)
    f = f[keys.notna()].copy()
    keys = keys.loc[f.index]
    last_year = int(f["d"].dt.year.max())
    years = list(range(a.from_year, last_year + 1))
    log("tần suất ô anchored…")
    pf = anchored_pool_freq(f, keys, years)

    metrics = {}
    for h in direction.HS:
        log(f"walk-forward h={h}…")
        metrics[h] = direction.walk_forward(f, pf, years, h)
    g = direction.gate(metrics, last_year)

    out = []
    P = out.append
    stamp = datetime.now(TZ).strftime("%Y-%m-%d")
    P(f"# LightGBM xác suất hướng — walk-forward {years[0]}–{last_year} · {len(syms)} mã · {stamp}\n")
    P(f"Tham số: {direction.PARAMS['num_leaves']} lá, min_data_in_leaf {direction.PARAMS['min_data_in_leaf']}, "
      f"lr {direction.PARAMS['learning_rate']}, {direction.N_ROUNDS} vòng, {len(direction.FEATURES)} đặc trưng, purge {direction.PURGE_DAYS} ngày. "
      f"Cổng: Brier < tần suất ô VÀ acc > luôn-tăng ở ≥ {direction.PASS_YEARS}/5 năm trọn.\n")
    for h in direction.HS:
        info = g["per_h"][str(h)]
        P(f"## h = {h} phiên — {'BẬT' if info['enabled'] else 'TẮT'} (Brier thắng {info['wins_brier']}, acc thắng {info['wins_acc']}, cần {info['need']})\n")
        P("| Năm | test | tăng thật | acc LGBM | acc luôn-tăng | Brier LGBM | Brier ô | Brier toàn cục | Brier 0,5 | p90 của P | đặc trưng mạnh |")
        P("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in metrics[h]:
            b = "✓" if r["brier_lgbm"] < r["brier_freq"] else "✗"
            c = "✓" if r["acc_lgbm"] > r["acc_always_up"] else "✗"
            P(f"| {r['year']}{'*' if r['year'] == last_year else ''} | {r['n_test']:,} | {r['up_rate']*100:.1f} % | {r['acc_lgbm']*100:.1f} % {c} | {r['acc_always_up']*100:.1f} % | "
              f"{r['brier_lgbm']:.4f} {b} | {r['brier_freq']:.4f} | {r['brier_global']:.4f} | {r['brier_half']:.4f} | {r['p_q90']:.3f} | {', '.join(r['top_features'][:4])} |")
        P("")
    P(f"(*) năm chưa trọn, không tính vào cổng.\n")
    P(f"## Quyết định: **{'BẬT' if g['enabled'] else 'TẮT'}** — app dùng {'LightGBM' if g['enabled'] else 'tần suất ô chế độ'} cho P(tăng).")
    print("\n".join(out))

    if not a.no_save:
        direction.save_gate({**g, "trained_at": stamp, "years": years, "features": direction.FEATURES})
        log(f"ghi {direction.GATE.name}: enabled={g['enabled']}")
        if not g["enabled"]:
            # cổng tắt → không ghi booster, tránh file mô hình vô dụng nằm trong repo; xoá bản cũ nếu có
            for h in direction.HS:
                direction.booster_path(h).unlink(missing_ok=True)
            return 0
        for h in direction.HS:
            tr = f[f[f"y{h}"].notna()]
            bst = direction.train(tr, h)
            direction.ARTIFACTS.mkdir(parents=True, exist_ok=True)
            bst.save_model(str(direction.booster_path(h)))
            log(f"ghi {direction.booster_path(h).name} ({len(tr):,} hàng)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
