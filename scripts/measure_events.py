"""Đo 4 sự kiện của model/events.py trong khung price-path — cổng quyết định sự kiện nào lên app.

    venv\\Scripts\\python -m scripts.measure_events --md          # → reports/events-<ngày>.md + model/artifacts/events_stats.json
    venv\\Scripts\\python -m scripts.measure_events --n 60         # thử nhanh, không ghi gì

Ba phần:
  1. Lệnh: tín hiệu đóng cửa t → mua mở cửa t+1 → bán đóng cửa t+H (H = 5/10/20), phí 0,15 %/chiều + thuế 0,1 %.
     So mua-đại = mọi phiên-mã cùng năm cùng cách vào/ra. Số năm đúng (năm có ≥ 5 lệnh), bỏ 2022, hai nửa thời gian.
  2. Nón sự kiện walk-forward 2021→: pool = đường 20 phiên sau các lần sự kiện có đủ 20 phiên sau TRƯỚC năm thử
     (cutoff 01/01 − 35 ngày như scripts/evaluate.py), chuẩn hoá vol20 như regime.build_pools, cone.simulate_batch.
     So nón app (ô chế độ) trên CÙNG các hàng: coverage 80 %, pinball h=10, trung vị (nón có nghiêng không).
  3. P(chạm +5 % trước −5 % trong 10 phiên) của nón sự kiện so tỷ lệ thật.

Cổng (ghi trước khi chạy): n ≥ 100 · ≥ 70 % số năm vượt mốc · bỏ 2022 vẫn dương · vượt ≥ 1 %/10p.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from common import store
from common.config import ARTIFACTS, HISTORY, INDEX_SYMBOL, ROOT, TZ
from model import cone, events, regime
from model.features import PATH_COLS, build_all

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

FEE, TAX = 0.0015, 0.001
HS = (5, 10, 20)
FROM_YEAR, WF_FROM, EXCL, SPLIT = 2016, 2021, 2022, 2021
GATE_N, GATE_YEAR_SHARE, GATE_EDGE = 100, 0.70, 0.01
UP, DN, BH = float(np.log(1.05)), float(np.log(0.95)), 10
TAU = np.array(cone.QS) / 100.0
STATS = ARTIFACTS / "events_stats.json"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def load_frame(st: dict) -> pd.DataFrame:
    """Đặc trưng app (build_all) + cột sự kiện + lãi lệnh net5/10/20, gộp mọi mã."""
    syms = sorted(s for s in st["bars"] if s != INDEX_SYMBOL)
    f = build_all(st, syms, INDEX_SYMBOL, store.bars)
    parts = []
    for sym in syms:
        b = store.bars(st, sym)
        if len(b) < 60:
            continue
        ev = events.detect(b)
        o = pd.Series([x["o"] for x in b])
        c = pd.Series([x["c"] for x in b])
        for H in HS:
            ev[f"net{H}"] = (c.shift(-H) * (1 - FEE - TAX) / (o.shift(-1) * (1 + FEE)) - 1).to_numpy()
        ev.insert(0, "symbol", sym)
        parts.append(ev)
    f = f.drop(columns=[k for k in events.CODES if k in f.columns])   # build_all có sẵn `climax` cùng công thức
    F = f.merge(pd.concat(parts, ignore_index=True), on=["symbol", "d"], how="left")
    F["year"] = F["d"].dt.year
    return F


def trade_stats(sel: pd.DataFrame, bm: dict) -> dict:
    out = {}
    for H in HS:
        col = f"net{H}"
        g = sel[sel[col].notna()]
        if g.empty:
            out[H] = {"n": 0}
            continue
        ex = g[col] - g["year"].map(bm[H])
        by = ex.groupby(g["year"]).agg(["mean", "size"])
        by = by[by["size"] >= 5]
        half = [ex[g["year"] < SPLIT], ex[g["year"] >= SPLIT]]
        out[H] = {"n": int(len(g)), "ret": float(g[col].mean()), "ex": float(ex.mean()), "win": float((g[col] > 0).mean()),
                  "years_win": int((by["mean"] > 0).sum()), "years": int(len(by)),
                  "ex_no22": float(ex[g["year"] != EXCL].mean()), "n22": int((g["year"] == EXCL).sum()),
                  "half": [float(x.mean()) if len(x) else None for x in half], "half_n": [int(len(x)) for x in half],
                  "by_year": {int(y): [float(r["mean"]), int(r["size"])] for y, r in by.iterrows()}}
    return out


def passes(s10: dict) -> bool:
    return (s10.get("n", 0) >= GATE_N and s10["years"] > 0 and s10["years_win"] / s10["years"] >= GATE_YEAR_SHARE
            and s10["ex_no22"] > 0 and s10["ex"] >= GATE_EDGE)


def steps_of(rows: pd.DataFrame) -> np.ndarray:
    cum = rows[PATH_COLS].to_numpy(np.float64)
    st = np.diff(np.concatenate([np.zeros((len(rows), 1)), cum], axis=1), axis=1)
    return (st / rows["vol20"].to_numpy()[:, None]).astype(np.float32)


def touch(cum: np.ndarray) -> np.ndarray:
    c = cum[..., :BH]
    hu, hd = c >= UP, c <= DN
    tu = np.where(hu.any(axis=-1), hu.argmax(axis=-1), BH + 1)
    td = np.where(hd.any(axis=-1), hd.argmax(axis=-1), BH + 1)
    return (tu < td).astype(np.float32)


def pinball(q: np.ndarray, real: np.ndarray) -> float:
    d = real[:, None] - q
    return float(np.maximum(TAU * d, (TAU - 1) * d).mean() * 100)


def walk_forward(F: pd.DataFrame, n_sim: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    keys = regime.keys_for(F)
    ok = F[PATH_COLS].notna().all(axis=1) & (F["vol20"] > 0) & keys.notna()
    last = int(F["year"].max())
    res: dict = {k: {} for k in events.CODES}
    for Y in range(WF_FROM, last + 1):
        cutoff = pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=35)
        train = F[F["d"] < cutoff]
        app_pools = regime.build_pools(train, keys.loc[train.index])
        for k in events.CODES:
            ev_mask = F[k].fillna(False).astype(bool)
            pool_rows = F[(F["d"] < cutoff) & ev_mask & ok]
            te = F[(F["year"] == Y) & ev_mask & F["fr10"].notna() & (F["vol20"] > 0) & keys.notna()]
            if len(pool_rows) < 30 or te.empty:
                res[k][Y] = {"n": int(len(te)), "pool": int(len(pool_rows))}
                continue
            pool = steps_of(pool_rows)
            vols = te["vol20"].to_numpy(np.float32)
            cum = cone.simulate_batch(vols, pool, n=n_sim, rng=rng)
            q_ev = cone.quantiles_batch(cum, hs=(10,))[:, 0, :]
            p_tc = touch(cum).mean(axis=1)
            q_app = np.zeros_like(q_ev)
            for i, (kk, v) in enumerate(zip(keys.loc[te.index], vols)):
                p, _, _ = regime.pool_for(kk, app_pools)
                q_app[i] = cone.quantiles_batch(cone.simulate_batch(np.array([v]), p, n=n_sim, rng=rng), hs=(10,))[0, 0, :]
            real = te["fr10"].to_numpy(np.float64)
            y_tc = touch(te[PATH_COLS[:BH]].to_numpy(np.float64))
            j10, j50, j90 = cone.QS.index(10), cone.QS.index(50), cone.QS.index(90)
            res[k][Y] = {
                "n": int(len(te)), "pool": int(len(pool_rows)),
                "cov80_ev": float(((q_ev[:, j10] <= real) & (real <= q_ev[:, j90])).mean()),
                "cov80_app": float(((q_app[:, j10] <= real) & (real <= q_app[:, j90])).mean()),
                "pin_ev": pinball(q_ev, real), "pin_app": pinball(q_app, real),
                "med_ev": float(np.mean(np.expm1(q_ev[:, j50]))), "med_app": float(np.mean(np.expm1(q_app[:, j50]))),
                "real_mean": float(np.mean(np.expm1(real))),
                "ptc_ev": float(p_tc.mean()), "ptc_real": float(y_tc.mean()),
                "brier_tc_ev": float(np.mean((p_tc - y_tc) ** 2)),
            }
        log(f"walk-forward {Y} xong")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--md", action="store_true", help="ghi reports/events-<ngày>.md + model/artifacts/events_stats.json")
    a = ap.parse_args()

    st = store.load(HISTORY)
    log("đặc trưng + sự kiện…")
    F = load_frame(st)
    E = F[(F["year"] >= FROM_YEAR) & F["net20"].notna()]
    bm = {H: E.groupby("year")[f"net{H}"].mean() for H in HS}
    stats = {}
    for k in events.CODES:
        sel = E[E[k].fillna(False).astype(bool)]
        stats[k] = trade_stats(sel, bm)
        s10 = stats[k][10]
        log(f"{k}: n={s10.get('n')} vượt {s10.get('ex', 0)*100:+.2f}% năm {s10.get('years_win')}/{s10.get('years')} → "
            f"{'ĐẠT' if passes(s10) else '—'}")
    log("walk-forward nón sự kiện…")
    wf = walk_forward(F, a.n, a.seed)

    stamp = datetime.now(TZ).strftime("%Y-%m-%d")
    last_day = str(F["d"].max().date())
    lines = render(stats, wf, bm, E, a.n, stamp, last_day)
    print("\n".join(lines))
    if a.md:
        (ROOT / "reports" / f"events-{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        art = {"generated": stamp, "last_day": last_day, "gate": {"n": GATE_N, "year_share": GATE_YEAR_SHARE, "edge": GATE_EDGE},
               "events": {}}
        for k in events.CODES:
            s10 = stats[k][10]
            ws = [w for w in wf[k].values() if "cov80_ev" in w]
            cov = sum(w["cov80_ev"] * w["n"] for w in ws) / max(1, sum(w["n"] for w in ws)) if ws else None
            art["events"][k] = {"name": events.NAMES[k], "pass": passes(s10), "n": s10.get("n", 0),
                                "ex10": s10.get("ex"), "ret10": s10.get("ret"), "win10": s10.get("win"),
                                "years_win": s10.get("years_win"), "years": s10.get("years"),
                                "ex5": stats[k][5].get("ex"), "ex20": stats[k][20].get("ex"),
                                "cov80": cov}
        STATS.parent.mkdir(parents=True, exist_ok=True)
        STATS.write_text(json.dumps(art, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"ghi reports/events-{stamp}.md + {STATS.name}")
    return 0


def render(stats, wf, bm, E, n_sim, stamp, last_day) -> list[str]:
    pc = lambda x: "—" if x is None else f"{x*100:+.2f} %"
    L = [f"# Sự kiện có điều kiện — {E['symbol'].nunique()} mã · {FROM_YEAR}–{last_day[:4]} (nến cuối {last_day}) · {stamp}\n",
         "Mua mở cửa phiên sau, bán đóng cửa t+H, phí 0,15 %/chiều + thuế 0,1 %. 'Vượt' = lãi − mua-đại cùng năm. "
         f"Chống đếm trùng {events.DEDUP} phiên. Cổng: n ≥ {GATE_N} · ≥ {GATE_YEAR_SHARE:.0%} số năm (≥ 5 lệnh) vượt · "
         f"bỏ 2022 vẫn dương · vượt ≥ {GATE_EDGE:.0%}/10p.\n",
         f"Mua-đại cả kỳ: +5p {pc(E['net5'].mean())} · +10p {pc(E['net10'].mean())} · +20p {pc(E['net20'].mean())}\n",
         "## 1. Lệnh sau sự kiện\n",
         "| Sự kiện | Lệnh | Lãi 10p | Thắng | Vượt 5p | Vượt 10p | Vượt 20p | Năm vượt (10p) | Bỏ 2022 | 2016–20 / 2021– | Cổng |",
         "|---|---:|---:|---:|---:|---:|---:|:---:|---:|---|:---:|"]
    for k in events.CODES:
        s = stats[k]
        t = s[10]
        if not t.get("n"):
            L.append(f"| {events.NAMES[k]} | 0 | | | | | | | | | — |")
            continue
        h = t["half"]
        L.append(f"| {events.NAMES[k]} | {t['n']:,} | {pc(t['ret'])} | {t['win']*100:.0f} % | {pc(s[5]['ex'])} | **{pc(t['ex'])}** | "
                 f"{pc(s[20]['ex'])} | {t['years_win']}/{t['years']} | {pc(t['ex_no22'])} | {pc(h[0])} ({t['half_n'][0]}) / {pc(h[1])} ({t['half_n'][1]}) | "
                 f"{'**ĐẠT**' if passes(t) else '—'} |")
    L.append("")
    L.append("### Vượt mốc 10p theo năm (số lệnh)\n")
    years = sorted({y for k in events.CODES for y in stats[k][10].get("by_year", {})})
    L.append("| Sự kiện | " + " | ".join(str(y) for y in years) + " |")
    L.append("|---|" + "---:|" * len(years))
    for k in events.CODES:
        by = stats[k][10].get("by_year", {})
        L.append(f"| {events.NAMES[k]} | " + " | ".join(f"{by[y][0]*100:+.1f} ({by[y][1]})" if y in by else "·" for y in years) + " |")
    L.append("")
    L.append(f"## 2. Nón sự kiện vs nón app trên cùng các hàng (h = 10, walk-forward, {n_sim} đường)\n")
    L.append("Nón sự kiện = pool đường đi sau các lần sự kiện trước năm thử. 'Trung vị' = trung bình của trung vị nón (%), "
             "so lãi thật trung bình. Coverage 80 % đúng cỡ ≈ 80.\n")
    L.append("| Sự kiện | Năm | Hàng | Pool | Trung vị sự kiện | Trung vị app | Lãi thật | cov80 sự kiện | cov80 app | Pinball sự kiện | Pinball app | P chạm +5 % dự / thật |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for k in events.CODES:
        for Y, w in sorted(wf[k].items()):
            if "cov80_ev" not in w:
                L.append(f"| {events.NAMES[k]} | {Y} | {w['n']} | {w['pool']} | | | | | | | | |")
                continue
            L.append(f"| {events.NAMES[k]} | {Y} | {w['n']} | {w['pool']} | {pc(w['med_ev'])} | {pc(w['med_app'])} | {pc(w['real_mean'])} | "
                     f"{w['cov80_ev']*100:.0f} | {w['cov80_app']*100:.0f} | {w['pin_ev']:.3f} | {w['pin_app']:.3f} | "
                     f"{w['ptc_ev']*100:.0f} / {w['ptc_real']*100:.0f} % |")
    L.append("")
    L.append("## Tổng hợp cả kỳ walk-forward (gộp theo số hàng)\n")
    L.append("| Sự kiện | Hàng | cov80 sự kiện | cov80 app | Pinball sự kiện | Pinball app | Trung vị sự kiện | Trung vị app | Lãi thật |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k in events.CODES:
        ws = [w for w in wf[k].values() if "cov80_ev" in w]
        n = sum(w["n"] for w in ws)
        if not n:
            continue
        avg = lambda key: sum(w[key] * w["n"] for w in ws) / n
        L.append(f"| {events.NAMES[k]} | {n} | {avg('cov80_ev')*100:.0f} | {avg('cov80_app')*100:.0f} | {avg('pin_ev'):.3f} | "
                 f"{avg('pin_app'):.3f} | {pc(avg('med_ev'))} | {pc(avg('med_app'))} | {pc(avg('real_mean'))} |")
    return L


if __name__ == "__main__":
    raise SystemExit(main())
