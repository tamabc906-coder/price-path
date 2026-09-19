"""Đánh giá nón + P(tăng) bằng walk-forward theo năm — script lưu trong repo để tái lập.

    venv\\Scripts\\python -m scripts.evaluate --from 2021 --md > reports/eval-<ngày>.md
    venv\\Scripts\\python -m scripts.evaluate --from 2021 --n 300 --gamma 0.05

Với mỗi năm thử Y: pool chỉ từ các phiên có đủ 20 phiên sau TRƯỚC 01/01/Y (không nhìn tương lai). Mỗi hàng
(mã, phiên) trong năm Y: mô phỏng --n đường từ pool của ô chế độ (model/regime.py) → phân vị thô → conformal
chạy TUẦN TỰ theo ngày như job thật (nón phát ngày t chỉ được chấm khi tới ngày t+h, rồi mới sửa s).
So sánh 3 biến thể:
  * regime+ACI  — ô chế độ mới + tự sửa cỡ (bản sẽ chạy trong app)
  * regime thô  — ô chế độ, không sửa cỡ (s = 1)
  * ngây thơ+ACI — pool toàn cục × vol_t (không chế độ) + tự sửa cỡ: mốc để chứng minh chế độ có ích
Chỉ số: coverage 50/80/90 tại h=5/10/20 (theo hàng và theo ngày), pinball loss trung bình 7 phân vị, độ rộng dải
80 %, coverage theo cấp gộp; P(tăng) = tần suất pool vs 3 mốc (luôn tăng, tần suất toàn cục, 0,5); backtest lệnh
MUA đơn giản có phí/thuế/T+2 so mua-đại. Cuối cùng in ĐẠT/KHÔNG ĐẠT theo ngưỡng kế hoạch.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from common import store
from common.config import HISTORY, INDEX_SYMBOL, TZ
from model import cone, conformal, regime
from model.features import build_all

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

HS, QS = cone.HS, cone.QS
TAU = np.array(QS) / 100.0
FEE, TAX = 0.0015, 0.001
HOLD = 10
P_MIN = 0.60
PASS_YEARS = 4          # ≥ 4/5 năm
BAND = {80: (0.76, 0.84), 90: (0.86, 0.94)}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def simulate_rows(f: pd.DataFrame, keys: pd.Series, pools: dict, n: int, rng, use_regime: bool):
    """Phân vị thô (m, 3, 7) + cấp gộp + n pool + tần suất tăng h5/h10 cho từng hàng."""
    m = len(f)
    q = np.zeros((m, len(HS), len(QS)), dtype=np.float32)
    level = np.full(m, len(regime.AXES), dtype=np.int8)
    npool = np.zeros(m, dtype=np.int32)
    p5 = np.full(m, 0.5, dtype=np.float32)
    p10 = np.full(m, 0.5, dtype=np.float32)
    vols = f["vol20"].to_numpy(dtype=np.float32)
    groups: dict[tuple, list[int]] = defaultdict(list)
    if use_regime:
        for i, k in enumerate(keys):
            groups[k].append(i)
    else:
        groups[()] = list(range(m))
    for k, ix in groups.items():
        pool, lv, cnt = regime.pool_for(k, pools) if use_regime else (pools[()], len(regime.AXES), len(pools[()]))
        ix = np.asarray(ix)
        level[ix], npool[ix] = lv, cnt
        p5[ix], p10[ix] = regime.freq_up(pool, 5), regime.freq_up(pool, 10)
        for s0 in range(0, len(ix), 400):
            sl = ix[s0:s0 + 400]
            cum = cone.simulate_batch(vols[sl], pool, n=n, rng=rng)
            q[sl] = cone.quantiles_batch(cum)
    return q, level, npool, p5, p10


def run_sequential(dates: list, date_idx: np.ndarray, q_raw: np.ndarray, real: np.ndarray, gamma: float, adapt: bool):
    """Conformal theo ngày. real: (m, 3) lợi suất thật tại h. Trả q_adj (m,3,7) và bảng tỷ lệ trúng theo ngày."""
    state = conformal.new_state(HS, gamma=gamma)
    q_adj = q_raw.astype(np.float64).copy()
    pending: dict[int, list] = defaultdict(list)          # ngày đến hạn → [(h, level, hit_rate)]
    daily: list[tuple] = []                                # (ngày phát, h, level, hit_rate)
    order = np.argsort(date_idx, kind="stable")
    by_day = defaultdict(list)
    for i in order:
        by_day[int(date_idx[i])].append(i)
    for di in range(len(dates)):
        for h, lv, hr in pending.pop(di, []):
            if adapt:
                conformal.update(state, h, lv, hr)
        rows = by_day.get(di)
        if not rows:
            continue
        rows = np.asarray(rows)
        for hi, h in enumerate(HS):
            med = q_raw[rows, hi, 3].astype(np.float64)
            for lv, (lo, hi_q) in conformal.LEVEL_QS.items():
                s = conformal.scale(state, h, lv)
                jlo, jhi = QS.index(lo), QS.index(hi_q)
                q_adj[rows, hi, jlo] = med + s * (q_raw[rows, hi, jlo] - med)
                q_adj[rows, hi, jhi] = med + s * (q_raw[rows, hi, jhi] - med)
                ok = ~np.isnan(real[rows, hi])
                if ok.any():
                    hit = ((q_adj[rows, hi, jlo] <= real[rows, hi]) & (real[rows, hi] <= q_adj[rows, hi, jhi]))[ok].mean()
                    pending[di + h].append((h, lv, float(hit)))
                    daily.append((di, h, lv, float(hit)))
    return q_adj, daily


def pinball(q_adj: np.ndarray, real: np.ndarray) -> np.ndarray:
    """(m, 3) pinball trung bình 7 phân vị, đơn vị lợi suất log."""
    d = real[:, :, None] - q_adj                                   # (m,3,7)
    loss = np.maximum(TAU * d, (TAU - 1) * d)
    return loss.mean(axis=2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_year", type=int, default=2021)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--gamma", type=float, default=conformal.GAMMA)
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pmin", type=float, default=P_MIN, help="ngưỡng P(tăng 10p) cho backtest lệnh")
    ap.add_argument("--no-q25", action="store_true", help="bỏ điều kiện q25(h10) > 0 trong backtest")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    st = store.load(HISTORY)
    syms = sorted(s for s in st["bars"] if s != INDEX_SYMBOL)
    log(f"đặc trưng {len(syms)} mã…")
    f = build_all(st, syms, INDEX_SYMBOL, store.bars)
    keys_all = regime.keys_for(f)
    f["year"] = f["d"].dt.year
    last_year = int(f["year"].max())
    years = list(range(a.from_year, last_year + 1))

    # --- mô phỏng từng năm với pool anchored ---
    tests = []
    for Y in years:
        cutoff = pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=35)
        train = f[f["d"] < cutoff]
        pools = regime.build_pools(train, keys_all.loc[train.index])
        te = f[(f["year"] == Y) & keys_all.notna() & f["fr20"].notna() & (f["vol20"] > 0)].copy()
        if te.empty:
            continue
        k = keys_all.loc[te.index]
        log(f"{Y}: pool {len(pools[()]):,} hàng, thử {len(te):,} hàng, {len([x for x in pools if len(x) == 6])} ô đủ trục")
        qr, lv, npool, p5, p10 = simulate_rows(te, k, pools, a.n, rng, True)
        qn, _, _, gp5, gp10 = simulate_rows(te, k, pools, a.n, rng, False)
        te["level"], te["npool"], te["p5"], te["p10"], te["gp5"], te["gp10"] = lv, npool, p5, p10, gp5, gp10
        te["_qr"] = list(qr)
        te["_qn"] = list(qn)
        tests.append(te)
    T = pd.concat(tests).sort_values(["d", "symbol"]).reset_index(drop=True)
    q_r = np.stack(T["_qr"].to_list())
    q_n = np.stack(T["_qn"].to_list())
    real = T[["fr5", "fr10", "fr20"]].to_numpy(dtype=np.float64)
    dates = sorted(T["d"].unique())
    dpos = {d: i for i, d in enumerate(dates)}
    date_idx = T["d"].map(dpos).to_numpy()

    log("conformal tuần tự…")
    variants = {
        "regime+ACI": run_sequential(dates, date_idx, q_r, real, a.gamma, True),
        "regime thô": run_sequential(dates, date_idx, q_r, real, a.gamma, False),
        "ngây thơ+ACI": run_sequential(dates, date_idx, q_n, real, a.gamma, True),
    }
    T["year"] = T["d"].dt.year
    yrs = sorted(T["year"].unique())
    md = a.md
    out: list[str] = []
    P = out.append
    stamp = datetime.now(TZ).strftime("%Y-%m-%d")
    P(f"# Đánh giá Price Path — walk-forward {years[0]}–{years[-1]} · {len(syms)} mã · {len(T):,} hàng · n={a.n} · γ={a.gamma} · {stamp}\n")
    P("Pool mỗi năm chỉ gồm phiên có đủ 20 phiên sau trước 01/01 năm đó. Conformal chạy tuần tự theo ngày. "
      "Coverage 'theo ngày' = trung bình tỷ lệ mã trúng mỗi phiên; 'ngày trong dải' = % phiên có tỷ lệ trúng trong ±4 điểm quanh mục tiêu.\n")

    # --- coverage ---
    def cov_tables(name, q_adj, daily):
        P(f"## {name}\n")
        P("| Năm | h | cov 50 | cov 80 | cov 90 | cửa sổ 20 phiên trong dải 80 | rộng 80 (%) | pinball ×100 |")
        P("|---|---:|---:|---:|---:|---:|---:|---:|")
        pb = pinball(q_adj, real) * 100
        dd = pd.DataFrame(daily, columns=["di", "h", "lv", "hit"]).sort_values("di")
        dd["year"] = [dates[i].year for i in dd["di"]]
        # coverage trượt 20 phiên (thước đo của tab Lịch sử): 39 mã cùng ngày tương quan nên từng ngày dao động mạnh
        dd["roll"] = dd.groupby(["h", "lv"])["hit"].transform(lambda s: s.rolling(20).mean())
        dd["roll60"] = dd.groupby(["h", "lv"])["hit"].transform(lambda s: s.rolling(60).mean())
        r60 = dd[(dd.h == 10) & (dd.lv == 80)]["roll60"].dropna()
        P(f"Cửa sổ 60 phiên (h=10, mức 80): trong [76; 84] {((r60>=0.76)&(r60<=0.84)).mean()*100:.0f} % số ngày; "
          f"trong [72; 88] {((r60>=0.72)&(r60<=0.88)).mean()*100:.0f} %; min {r60.min()*100:.0f}, max {r60.max()*100:.0f}.\n")
        res = {}
        for Y in yrs:
            m = (T["year"] == Y).to_numpy()
            for hi, h in enumerate(HS):
                covs = []
                for lv, (lo, hi_q) in conformal.LEVEL_QS.items():
                    jlo, jhi = QS.index(lo), QS.index(hi_q)
                    ok = m & ~np.isnan(real[:, hi])
                    c = ((q_adj[ok, hi, jlo] <= real[ok, hi]) & (real[ok, hi] <= q_adj[ok, hi, jhi])).mean()
                    covs.append(c)
                    res[(Y, h, lv)] = c
                d80 = dd[(dd.year == Y) & (dd.h == h) & (dd.lv == 80)]["roll"].dropna()
                inband = ((d80 >= 0.76) & (d80 <= 0.84)).mean() * 100 if len(d80) else float("nan")
                width = (q_adj[m, hi, QS.index(90)] - q_adj[m, hi, QS.index(10)]).mean() * 100
                P(f"| {Y} | {h} | {covs[0]*100:.1f} | {covs[1]*100:.1f} | {covs[2]*100:.1f} | {inband:.0f} % | {width:.1f} | {pb[m, hi].mean():.3f} |")
        P("")
        return res, pb

    res_r, pb_r = cov_tables("Nón chế độ + tự sửa cỡ (bản app)", variants["regime+ACI"][0], variants["regime+ACI"][1])
    res_raw, pb_raw = cov_tables("Nón chế độ thô (s = 1)", variants["regime thô"][0], variants["regime thô"][1])
    res_n, pb_n = cov_tables("Nón ngây thơ (pool toàn cục) + tự sửa cỡ", variants["ngây thơ+ACI"][0], variants["ngây thơ+ACI"][1])

    # --- so pinball & theo cấp gộp ---
    P("## Chế độ có ích không? pinball ×100 tại h=10 theo năm (thấp hơn = tốt)\n")
    P("| Năm | chế độ+ACI | chế độ thô | ngây thơ+ACI | chế độ thắng ngây thơ |")
    P("|---|---:|---:|---:|:---:|")
    wins = 0
    for Y in yrs:
        m = (T["year"] == Y).to_numpy()
        a_, b_, c_ = pb_r[m, 1].mean(), pb_raw[m, 1].mean(), pb_n[m, 1].mean()
        wins += a_ <= c_
        P(f"| {Y} | {a_:.3f} | {b_:.3f} | {c_:.3f} | {'✓' if a_ <= c_ else '✗'} |")
    P("")
    P("## Coverage 80 % tại h=10 theo cấp gộp (bản app) — cấp 0 = đủ 6 trục, 6 = toàn cục\n")
    P("| Cấp | hàng | cov 80 | rộng 80 (%) |")
    P("|---:|---:|---:|---:|")
    qa = variants["regime+ACI"][0]
    for lv in range(len(regime.AXES) + 1):
        m = (T["level"] == lv).to_numpy() & ~np.isnan(real[:, 1])
        if m.sum() < 100:
            continue
        c = ((qa[m, 1, QS.index(10)] <= real[m, 1]) & (real[m, 1] <= qa[m, 1, QS.index(90)])).mean()
        w = (qa[m, 1, QS.index(90)] - qa[m, 1, QS.index(10)]).mean() * 100
        P(f"| {lv} | {m.sum():,} | {c*100:.1f} | {w:.1f} |")
    P("")

    # --- P(tăng) ---
    P("## P(tăng) = tần suất pool chế độ, so 3 mốc (h = 10)\n")
    P("| Năm | tỷ lệ tăng thật | acc pool | acc luôn-tăng | Brier pool | Brier toàn cục | Brier 0,5 | pool thắng |")
    P("|---|---:|---:|---:|---:|---:|---:|:---:|")
    pwin = 0
    for Y in yrs:
        g = T[T["year"] == Y]
        y = g["y10"].astype(float).to_numpy()
        p, gp = g["p10"].to_numpy(dtype=float), g["gp10"].to_numpy(dtype=float)
        acc_p = ((p >= 0.5) == (y == 1)).mean()
        b_p, b_g, b_h = ((p - y) ** 2).mean(), ((gp - y) ** 2).mean(), ((0.5 - y) ** 2).mean()
        ok = b_p < b_g
        pwin += ok
        P(f"| {Y} | {y.mean()*100:.1f} % | {acc_p*100:.1f} % | {y.mean()*100:.1f} % | {b_p:.4f} | {b_g:.4f} | {b_h:.4f} | {'✓' if ok else '✗'} |")
    P("")

    # --- backtest lệnh ---
    pq = np.percentile(T["p10"], [5, 25, 50, 75, 95, 99])
    P("## Phân bố P(tăng 10p) từ pool chế độ (toàn kỳ)\n")
    P("| p5 | p25 | p50 | p75 | p95 | p99 | ≥ 0,55 | ≥ 0,60 |")
    P("|---:|---:|---:|---:|---:|---:|---:|---:|")
    P("| " + " | ".join(f"{x:.3f}" for x in pq) + f" | {(T['p10']>=0.55).mean()*100:.1f} % | {(T['p10']>=0.60).mean()*100:.1f} % |\n")
    cond = "" if a.no_q25 else " và q25(h10) > 0"
    P(f"## Backtest lệnh MUA: P(tăng 10p) ≥ {a.pmin:.2f}{cond} → vào mở cửa phiên sau, giữ {HOLD} phiên (T+2 thoả), phí {FEE*100:.2f} %/chiều + thuế {TAX*100:.1f} %\n")
    opens = {}
    for sym in syms:
        b = store.bars(st, sym)
        opens[sym] = pd.Series([x["o"] for x in b], index=pd.to_datetime([x["d"] for x in b]))
        opens[sym + "_c"] = pd.Series([x["c"] for x in b], index=opens[sym].index)
    def trade_ret(row):
        o, c = opens[row.symbol], opens[row.symbol + "_c"]
        i = o.index.get_loc(row.d)
        if i + 1 + HOLD >= len(o):
            return np.nan
        return c.iloc[i + 1 + HOLD] * (1 - FEE - TAX) / (o.iloc[i + 1] * (1 + FEE)) - 1
    q25 = qa[:, 1, QS.index(25)]
    T["sig"] = (T["p10"] >= a.pmin) & ((q25 > 0) | a.no_q25)
    T["net"] = [trade_ret(r) for r in T[["symbol", "d"]].itertuples(index=False)]
    P("| Năm | lệnh | lãi/lệnh | thắng | mua-đại lãi/lệnh | mua-đại thắng | thắng mua-đại |")
    P("|---|---:|---:|---:|---:|---:|:---:|")
    for Y in yrs:
        g = T[(T["year"] == Y) & T["net"].notna()]
        s_ = g[g["sig"]]
        if len(s_) == 0:
            P(f"| {Y} | 0 | — | — | {g['net'].mean()*100:+.2f} % | {(g['net']>0).mean()*100:.1f} % | — |")
            continue
        ok = s_["net"].mean() > g["net"].mean()
        P(f"| {Y} | {len(s_):,} | {s_['net'].mean()*100:+.2f} % | {(s_['net']>0).mean()*100:.1f} % | {g['net'].mean()*100:+.2f} % | {(g['net']>0).mean()*100:.1f} % | {'✓' if ok else '✗'} |")
    P("")

    # --- kết luận theo ngưỡng ---
    full_years = [Y for Y in yrs if Y < last_year] or yrs
    ok80 = sum(BAND[80][0] <= res_r[(Y, 10, 80)] <= BAND[80][1] for Y in full_years)
    ok90 = sum(BAND[90][0] <= res_r[(Y, 10, 90)] <= BAND[90][1] for Y in full_years)
    pin_ok = pb_r[:, 1].mean() <= pb_n[:, 1].mean()
    need = min(PASS_YEARS, len(full_years))
    passed = ok80 >= need and ok90 >= need and pin_ok
    P("## Kết luận theo ngưỡng kế hoạch\n")
    P(f"- Coverage 80 % (h=10) trong [76; 84]: **{ok80}/{len(full_years)} năm** (cần ≥ {need})")
    P(f"- Coverage 90 % (h=10) trong [86; 94]: **{ok90}/{len(full_years)} năm** (cần ≥ {need})")
    P(f"- Pinball chế độ ≤ ngây thơ (h=10, cả kỳ): **{'✓' if pin_ok else '✗'}** ({pb_r[:,1].mean():.3f} vs {pb_n[:,1].mean():.3f}); thắng theo năm {wins}/{len(yrs)}")
    P(f"- P(tăng) pool thắng Brier toàn cục: {pwin}/{len(yrs)} năm (không bắt buộc)")
    P(f"\n**{'ĐẠT' if passed else 'KHÔNG ĐẠT'}** — {'đủ điều kiện sang G3' if passed else 'app chỉ hiện nón ngây thơ có ghi rõ, hoặc sửa mô hình'}.")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
